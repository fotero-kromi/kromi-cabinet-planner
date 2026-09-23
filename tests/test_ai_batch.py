"""Contracts for the AI classification batch call (v34.48, audit C7).

The batch call used to live in the page and *return* its failure tuple from
inside ``st.cache_data``, so one timeout or rate-limit error was replayed from
the cache for the life of the process and those rows never got AI
classification again. The call now lives in ``engine/ai_batch.py`` with an
injected transport: success returns the result map, a final failure raises
``AIBatchFailed``, and the Streamlit wrapper in ``ui/ai_calls.py`` converts
the exception into the same 5-tuple the page always consumed. Streamlit never
caches an exception, so a failed batch is retried on the next run. A batch
that comes back with no rows at all counts as a failure too.
"""

import json

import pytest

from engine.ai_batch import AIBatchFailed, classify_batch

ITEMS = (
    # row_id, code, prod_cat, desc1, desc2, supplier, pack, size, listing
    ("0", "A1", "", "Bohrer D8,5", "", "", 1, "", "Tools"),
    ("1", "A2", "", "Fraeser D12", "", "", 1, "", "Tools"),
)


def _content(rows):
    return json.dumps({"results": rows})


def _row(rid, **kw):
    base = {"row_id": rid, "product_category": "drills",
            "tool_class": "solid_carbide_drill", "size_category": "M",
            "pack_units": 1, "confidence": "high", "reason": "ok"}
    base.update(kw)
    return base


def _no_sleep(_s):
    return None


def test_success_returns_validated_results():
    def call(prompt, schema):
        assert "Bohrer" in prompt
        return _content([_row("0"), _row("1", product_category="mills",
                                          tool_class="solid_end_mill")]), 10, 5

    out, in_tok, out_tok, missing = classify_batch(
        ITEMS, trim_reason=False, call=call, attempts=3, max_backoff=0,
        sleep=_no_sleep)
    assert set(out) == {"0", "1"} and missing == 0
    assert (in_tok, out_tok) == (10, 5)
    assert out["1"]["product_category"] == "mills"


def test_invalid_values_are_normalised_not_trusted():
    long_reason = "x" * 500

    def call(prompt, schema):
        return _content([_row("0", product_category="rockets",
                              tool_class="laser", pack_units=7,
                              confidence="certain", reason=long_reason),
                         _row("1")]), 1, 1

    out, *_ = classify_batch(ITEMS, trim_reason=False, call=call, attempts=1,
                             max_backoff=0, sleep=_no_sleep)
    r = out["0"]
    assert r["product_category"] == "other"
    assert r["tool_class"] == "other"
    assert r["pack_units"] is None
    assert r["confidence"] == "medium"
    assert len(r["reason"]) == 200


def test_transient_error_is_retried_then_succeeds():
    calls = {"n": 0}

    def call(prompt, schema):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("slow")
        return _content([_row("0"), _row("1")]), 1, 1

    out, *_ = classify_batch(ITEMS, trim_reason=False, call=call, attempts=3,
                             max_backoff=0, sleep=_no_sleep)
    assert calls["n"] == 2 and set(out) == {"0", "1"}


def test_final_failure_raises_with_missing_count():
    def call(prompt, schema):
        raise ConnectionError("down")

    with pytest.raises(AIBatchFailed) as exc:
        classify_batch(ITEMS, trim_reason=False, call=call, attempts=3,
                       max_backoff=0, sleep=_no_sleep)
    assert exc.value.n_missing == 2
    assert "failed after 3 attempts" in str(exc.value)
    assert "ConnectionError" in str(exc.value)


def test_malformed_json_is_a_retryable_failure():
    def call(prompt, schema):
        return "not json", 1, 1

    with pytest.raises(AIBatchFailed):
        classify_batch(ITEMS, trim_reason=False, call=call, attempts=2,
                       max_backoff=0, sleep=_no_sleep)


def test_empty_results_for_a_nonempty_batch_is_a_failure():
    def call(prompt, schema):
        return _content([]), 1, 1

    with pytest.raises(AIBatchFailed):
        classify_batch(ITEMS, trim_reason=False, call=call, attempts=2,
                       max_backoff=0, sleep=_no_sleep)


def test_partial_results_report_missing_rows():
    def call(prompt, schema):
        return _content([_row("0")]), 1, 1

    out, _i, _o, missing = classify_batch(
        ITEMS, trim_reason=False, call=call, attempts=1, max_backoff=0,
        sleep=_no_sleep)
    assert set(out) == {"0"} and missing == 1


# ---- the Streamlit wrapper never caches a failure --------------------------

class _FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step

        class _Msg:
            content = step
            refusal = None

        class _Choice:
            message = _Msg()

        class _Usage:
            prompt_tokens = 3
            completion_tokens = 2

        class _Resp:
            choices = [_Choice()]
            usage = _Usage()

        return _Resp()


class _FakeClient:
    def __init__(self, completions):
        class _Chat:
            pass
        self.chat = _Chat()
        self.chat.completions = completions


def test_wrapper_returns_failure_tuple_but_does_not_cache_it(monkeypatch):
    import streamlit as st
    import ui.ai_calls as ai_calls

    st.cache_data.clear()
    good = _content([_row("0"), _row("1")])
    completions = _FakeCompletions(
        [ConnectionError("down")] * ai_calls.AI_RETRY_ATTEMPTS + [good])
    monkeypatch.setattr(ai_calls, "get_openai_client",
                        lambda: _FakeClient(completions))
    monkeypatch.setattr(ai_calls, "_sleep", _no_sleep)

    key = ("test-model", False, ITEMS)
    result_map, _i, _o, err, missing = ai_calls.ai_classify_batch_cached(key)
    assert result_map == {} and err and missing == 2

    # The outage is over: the same batch must be asked again, not replayed.
    result_map, _i, _o, err, missing = ai_calls.ai_classify_batch_cached(key)
    assert err is None and set(result_map) == {"0", "1"} and missing == 0

    # A success IS cached: a third call makes no request.
    before = completions.calls
    ai_calls.ai_classify_batch_cached(key)
    assert completions.calls == before
    st.cache_data.clear()
