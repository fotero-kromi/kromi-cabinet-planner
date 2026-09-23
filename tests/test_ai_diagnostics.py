"""Tests for engine.ai_classifier.AIRunDiagnostics (v33.95).

The loose counters the AI classification driver accumulated, batches and items
run, failures, missing responses, token usage, per-batch durations, are now a
single dataclass. These tests pin the accumulation rules (including the two exact
error-message formats and the err-over-missing precedence), the derived figures
(total tokens, average duration, cost), and a real-data simulation that drives the
diagnostics from batches built off a planner Result workbook.
"""

import os

import pandas as pd
import pytest

from engine.ai_classifier import AIRunDiagnostics, build_classification_batches

PRICE_IN, PRICE_OUT = 0.15, 0.60


def _res(b, n, intok, outtok, dur, err=None, missing=0):
    return {"b": b, "n_items": n, "in_tok": intok, "out_tok": outtok,
            "duration": dur, "err": err, "missing": missing}


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_fresh_diagnostics_is_empty():
    d = AIRunDiagnostics()
    assert (d.batches_run, d.items_run, d.batches_failed, d.missing_responses) == (0, 0, 0, 0)
    assert (d.in_tokens, d.out_tokens) == (0, 0)
    assert d.errors == [] and d.durations == []
    assert d.total_tokens == 0 and d.avg_duration == 0.0


# ---------------------------------------------------------------------------
# record_batch
# ---------------------------------------------------------------------------

def test_record_batch_accumulates_tokens_and_counts():
    d = AIRunDiagnostics()
    d.record_batch(_res(0, 40, 1000, 500, 1.2), total_batches=3)
    assert d.in_tokens == 1000 and d.out_tokens == 500
    assert d.batches_run == 1 and d.items_run == 40
    assert d.durations == [1.2]
    assert d.batches_failed == 0 and d.missing_responses == 0


def test_record_batch_with_error_increments_failed_and_logs():
    d = AIRunDiagnostics()
    d.record_batch(_res(2, 40, 0, 0, 0.9, err="HTTP 500"), total_batches=6)
    assert d.batches_failed == 1
    assert d.errors == ["Batch 3/6 (40 items): HTTP 500"]
    assert d.batches_run == 1  # still counts as run


def test_record_batch_with_missing_increments_missing():
    d = AIRunDiagnostics()
    d.record_batch(_res(1, 40, 100, 50, 1.0, missing=3), total_batches=6)
    assert d.missing_responses == 3
    assert d.batches_failed == 0


def test_error_takes_precedence_over_missing():
    # the rule is `if err: ... elif missing`: an errored batch never also counts missing
    d = AIRunDiagnostics()
    d.record_batch(_res(0, 40, 0, 0, 1.0, err="boom", missing=5), total_batches=2)
    assert d.batches_failed == 1
    assert d.missing_responses == 0


def test_token_values_coerced_to_int():
    d = AIRunDiagnostics()
    d.record_batch(_res(0, 10, 100, 50, 0.5), total_batches=1)
    assert isinstance(d.in_tokens, int) and isinstance(d.out_tokens, int)


# ---------------------------------------------------------------------------
# record_crash
# ---------------------------------------------------------------------------

def test_record_crash_logs_and_increments_failed():
    d = AIRunDiagnostics()
    d.record_crash(4, 6, RuntimeError("boom"))
    assert d.batches_failed == 1
    assert d.errors == ["Batch 4/6 crashed: RuntimeError: boom"]
    assert d.batches_run == 0  # a crash is not a run


def test_crash_message_uses_exception_type_name():
    class WeirdError(ValueError):
        pass
    d = AIRunDiagnostics()
    d.record_crash(1, 1, WeirdError("x"))
    assert "WeirdError" in d.errors[0]


# ---------------------------------------------------------------------------
# Derived figures
# ---------------------------------------------------------------------------

def test_total_tokens():
    d = AIRunDiagnostics()
    d.record_batch(_res(0, 10, 100, 50, 0.5), 2)
    d.record_batch(_res(1, 10, 200, 80, 0.7), 2)
    assert d.total_tokens == 430


def test_avg_duration_is_mean():
    d = AIRunDiagnostics()
    for i, dur in enumerate([1.0, 2.0, 3.0]):
        d.record_batch(_res(i, 10, 0, 0, dur), 3)
    assert d.avg_duration == 2.0


def test_avg_duration_empty_is_zero():
    assert AIRunDiagnostics().avg_duration == 0.0


def test_cost_computation():
    d = AIRunDiagnostics()
    d.record_batch(_res(0, 10, 1_000_000, 2_000_000, 1.0), 1)
    # 1M in * 0.15 + 2M out * 0.60 = 0.15 + 1.20
    assert round(d.cost(PRICE_IN, PRICE_OUT), 6) == 1.35


def test_cost_zero_when_no_tokens():
    assert AIRunDiagnostics().cost(PRICE_IN, PRICE_OUT) == 0.0


# ---------------------------------------------------------------------------
# Sequences
# ---------------------------------------------------------------------------

def test_mixed_sequence_totals():
    d = AIRunDiagnostics()
    d.record_batch(_res(0, 40, 1000, 500, 1.2), 6)
    d.record_batch(_res(1, 40, 1100, 480, 1.4, missing=3), 6)
    d.record_batch(_res(2, 40, 0, 0, 0.9, err="HTTP 500"), 6)
    d.record_crash(4, 6, RuntimeError("boom"))
    d.record_batch(_res(4, 40, 950, 510, 1.1), 6)
    d.record_batch(_res(5, 17, 400, 220, 0.7), 6)
    assert d.batches_run == 5
    assert d.items_run == 177
    assert d.batches_failed == 2
    assert d.missing_responses == 3
    assert d.in_tokens == 3450 and d.out_tokens == 1710
    assert len(d.errors) == 2
    assert len(d.durations) == 5


def test_durations_order_preserved():
    d = AIRunDiagnostics()
    for i, dur in enumerate([0.3, 0.1, 0.2]):
        d.record_batch(_res(i, 1, 0, 0, dur), 3)
    assert d.durations == [0.3, 0.1, 0.2]


# ---------------------------------------------------------------------------
# Real-data simulation: diagnostics driven by batches off a real workbook
# ---------------------------------------------------------------------------

_GROUND_TRUTH = os.environ.get("KROMI_GROUNDTRUTH_XLSX", "")


@pytest.mark.skipif(not (_GROUND_TRUTH and os.path.exists(_GROUND_TRUTH)),
                    reason="set KROMI_GROUNDTRUTH_XLSX to a planner Result workbook to run")
def test_real_data_run_diagnostics_account_for_every_item():
    res = pd.ExcelFile(_GROUND_TRUTH).parse("Result")
    work = pd.DataFrame({
        "Code": res.Code, "Description": res.Description, "Description_2": "",
        "ProductCategory": res.ProductCategory, "SupplierCode": res.SupplierCode,
        "PackUnits": pd.to_numeric(res.PackUnits, errors="coerce").fillna(1.0),
        "SizeCategory": res.SizeCategory, "Listing": res.get("Listing", "Tools"),
    }, index=res.index)
    plans = build_classification_batches(work, list(work.index), batch_size=40,
                                         model="gpt-5-mini", trim_reason=False, max_desc_chars=220)
    total = len(plans)
    d = AIRunDiagnostics()
    for p in plans:
        d.record_batch(_res(p["b"], p["n_items"], 1000, 500, 1.0), total)
    assert d.batches_run == total
    assert d.items_run == len(work)  # every customer row accounted for
    assert d.batches_failed == 0 and d.missing_responses == 0
    assert d.total_tokens == total * 1500
