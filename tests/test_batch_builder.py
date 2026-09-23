"""Tests for engine.ai_classifier.build_classification_batches (v33.93).

The batch-preparation step of the AI classification driver was lifted out of the
page. It splits the rows that need AI into batch-sized chunks and builds each
batch's per-item payload plus the deterministic cache key the cached classifier
consumes. The cache key is load-bearing: a wrong key means a needless model call
(cost, latency) or a wrong cached answer. These tests pin the batching maths, the
payload shaping, and the cache-key behaviour, plus a real-data simulation.
"""

import os

import pandas as pd
import pytest

from engine.ai_classifier import build_classification_batches, make_batch_cache_key
from engine.constants import LISTING_TOOLS

MODEL = "gpt-5-mini"


def _frame(n, **over):
    rows = []
    for i in range(n):
        r = dict(Code=f"C{i}", Description=f"desc {i}", Description_2="",
                 ProductCategory="milling", SupplierCode=f"sup{i}", PackUnits=1.0,
                 SizeCategory="M", Listing="Tools")
        r.update(over)
        rows.append(r)
    return pd.DataFrame(rows)


def _build(df, capped=None, batch_size=40, trim=False, max_desc=220):
    capped = list(df.index) if capped is None else capped
    return build_classification_batches(df, capped, batch_size=batch_size, model=MODEL,
                                        trim_reason=trim, max_desc_chars=max_desc)


# ---------------------------------------------------------------------------
# Batching maths
# ---------------------------------------------------------------------------

def test_batch_count_is_ceil_division():
    plans = _build(_frame(137), batch_size=40)
    assert len(plans) == 4  # ceil(137/40)


def test_last_batch_holds_the_remainder():
    plans = _build(_frame(137), batch_size=40)
    assert [p["n_items"] for p in plans] == [40, 40, 40, 17]


def test_row_coverage_is_conserved_and_ordered():
    df = _frame(137)
    plans = _build(df, batch_size=40)
    covered = [i for p in plans for i in p["batch_idx"]]
    assert covered == list(df.index)  # every row once, original order


def test_single_batch_when_batch_size_exceeds_rows():
    plans = _build(_frame(10), batch_size=40)
    assert len(plans) == 1 and plans[0]["n_items"] == 10


def test_batch_size_one_makes_one_batch_per_row():
    plans = _build(_frame(5), batch_size=1)
    assert len(plans) == 5 and all(p["n_items"] == 1 for p in plans)


def test_empty_capped_rows_returns_no_plans():
    assert _build(_frame(10), capped=[]) == []


def test_batch_ordinals_are_sequential():
    plans = _build(_frame(100), batch_size=30)
    assert [p["b"] for p in plans] == [0, 1, 2, 3]


def test_only_capped_rows_are_batched():
    df = _frame(10)
    plans = _build(df, capped=list(df.index[:3]), batch_size=40)
    assert sum(p["n_items"] for p in plans) == 3


def test_preserves_non_default_index():
    df = _frame(3)
    df.index = [11, 22, 33]
    plans = _build(df, batch_size=40)
    assert list(plans[0]["batch_idx"]) == [11, 22, 33]


# ---------------------------------------------------------------------------
# Payload shaping
# ---------------------------------------------------------------------------

def test_payload_fields_present_and_cleaned():
    df = _frame(1, Code="  ab  cd ", SupplierCode="xy12", SizeCategory="m", PackUnits=10.0)
    # the payload feeds the cache key; rebuild the expected items the same way
    plans = _build(df, batch_size=40)
    # build a one-row reference via the key: identical key => identical payload
    key = plans[0]["cache_key"]
    assert isinstance(key, tuple)
    # supplier code and size category are upper-cased, whitespace collapsed
    ref = make_batch_cache_key([{
        "row_id": str(df.index[0]),
        "code": "ab cd", "prod_cat": "milling", "desc1": "desc 0", "desc2": "",
        "supplier_code": "XY12", "current_pack_units": "10",
        "current_size_category": "M", "listing": "Tools",
    }], MODEL, False)
    assert key == ref


def test_long_descriptions_are_shortened():
    long_desc = "x" * 500
    df = _frame(1, Description=long_desc)
    short = _build(df, max_desc=50)
    full = _build(df, max_desc=500)
    # different desc bounds change the payload, hence the key
    assert short[0]["cache_key"] != full[0]["cache_key"]


def test_missing_listing_defaults_to_tools():
    df = _frame(1)
    df = df.drop(columns=["Listing"])
    with_default = _build(df, batch_size=40)
    explicit = _build(_frame(1, Listing=LISTING_TOOLS), batch_size=40)
    assert with_default[0]["cache_key"] == explicit[0]["cache_key"]


# ---------------------------------------------------------------------------
# Cache-key behaviour
# ---------------------------------------------------------------------------

def test_cache_key_is_hashable_tuple():
    plans = _build(_frame(5), batch_size=40)
    assert isinstance(plans[0]["cache_key"], tuple)
    hash(plans[0]["cache_key"])  # usable as a dict key


def test_cache_key_is_deterministic():
    a = _build(_frame(40), batch_size=40)
    b = _build(_frame(40), batch_size=40)
    assert a[0]["cache_key"] == b[0]["cache_key"]


def test_trim_reason_changes_the_cache_key():
    no_trim = _build(_frame(40), batch_size=40, trim=False)
    trim = _build(_frame(40), batch_size=40, trim=True)
    assert no_trim[0]["cache_key"] != trim[0]["cache_key"]


def test_model_change_changes_the_cache_key():
    df = _frame(40)
    a = build_classification_batches(df, list(df.index), batch_size=40, model="gpt-5-mini",
                                     trim_reason=False, max_desc_chars=220)
    b = build_classification_batches(df, list(df.index), batch_size=40, model="gpt-4o",
                                     trim_reason=False, max_desc_chars=220)
    assert a[0]["cache_key"] != b[0]["cache_key"]


def test_different_rows_get_different_keys():
    p1 = _build(_frame(1, Code="AAA"), batch_size=40)
    p2 = _build(_frame(1, Code="BBB"), batch_size=40)
    assert p1[0]["cache_key"] != p2[0]["cache_key"]


# ---------------------------------------------------------------------------
# Real-data simulation
# ---------------------------------------------------------------------------

_GROUND_TRUTH = os.environ.get("KROMI_GROUNDTRUTH_XLSX", "")


@pytest.mark.skipif(not (_GROUND_TRUTH and os.path.exists(_GROUND_TRUTH)),
                    reason="set KROMI_GROUNDTRUTH_XLSX to a planner Result workbook to run")
def test_real_data_batches_conserve_every_row():
    res = pd.ExcelFile(_GROUND_TRUTH).parse("Result")
    work = pd.DataFrame({
        "Code": res.Code, "Description": res.Description, "Description_2": "",
        "ProductCategory": res.ProductCategory, "SupplierCode": res.SupplierCode,
        "PackUnits": pd.to_numeric(res.PackUnits, errors="coerce").fillna(1.0),
        "SizeCategory": res.SizeCategory, "Listing": res.get("Listing", "Tools"),
    }, index=res.index)
    capped = list(work.index)
    plans = build_classification_batches(work, capped, batch_size=40, model=MODEL,
                                         trim_reason=False, max_desc_chars=220)
    covered = [i for p in plans for i in p["batch_idx"]]
    assert covered == capped  # every customer row batched exactly once, in order
    assert sum(p["n_items"] for p in plans) == len(work)
    # keys are unique per distinct batch content and stable across a rebuild
    plans2 = build_classification_batches(work, capped, batch_size=40, model=MODEL,
                                          trim_reason=False, max_desc_chars=220)
    assert [p["cache_key"] for p in plans] == [p["cache_key"] for p in plans2]
