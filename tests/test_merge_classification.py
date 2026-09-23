"""Tests for engine.classification.merge_classification_results (v33.94).

The per-batch merge of AI classification results into the planning frame was
lifted out of the page. It applies the model's product-category, size, and
pack-unit answers, but only where the existing value is weak or empty, and it
corrects answers against the row's listing. These tests pin each gate and each
corrective rule with canonical category names, prove it mutates in place and
leaves untouched rows alone, and run a real-data merge simulation.
"""

import os

import pandas as pd
import pytest

from engine.classification import merge_classification_results

MODEL = "gpt-5-mini"
TS = "2026-06-25T12:00:00+00:00"


def _frame(rows):
    return pd.DataFrame(rows).set_index("idx")


def _one(idx="r", product="", listing="Tools", conf="unknown", toolclass="",
         pack_source="Default", pack=1.0, size=""):
    return dict(idx=idx, ProductCategory=product, Listing=listing,
                ProductCategory_Confidence=conf, ToolClass=toolclass,
                PackUnits_Source=pack_source, PackUnits=pack, SizeCategory=size)


def _merge(df, result_map):
    return merge_classification_results(df, list(df.index), result_map, model=MODEL, timestamp_utc=TS)


# ---------------------------------------------------------------------------
# Product-category gate
# ---------------------------------------------------------------------------

def test_weak_category_accepts_valid_ai_category():
    df = _frame([_one(product="other", conf="low")])
    _merge(df, {"r": {"product_category": "drills"}})
    assert df.at["r", "ProductCategory"] == "drills"
    assert df.at["r", "ProductCategory_Source"] == "AI"
    assert df.at["r", "ProductCategory_AI_Model"] == MODEL
    assert df.at["r", "ProductCategory_AI_TimestampUTC"] == TS
    assert df.at["r", "ProductCategory_Evidence"] == "ai:drills"


def test_strong_high_confidence_category_not_overwritten():
    df = _frame([_one(product="drills", conf="high")])
    _merge(df, {"r": {"product_category": "mills"}})
    assert df.at["r", "ProductCategory"] == "drills"  # kept


def test_low_confidence_category_is_replaced():
    df = _frame([_one(product="drills", conf="low")])
    _merge(df, {"r": {"product_category": "mills"}})
    assert df.at["r", "ProductCategory"] == "mills"


def test_invalid_ai_category_is_rejected():
    df = _frame([_one(product="other", conf="low")])
    _merge(df, {"r": {"product_category": "not_a_category"}})
    assert df.at["r", "ProductCategory"] == "other"  # unchanged
    assert "ProductCategory_Source" not in df.columns or pd.isna(df.at["r", "ProductCategory_Source"])


# ---------------------------------------------------------------------------
# Listing correction
# ---------------------------------------------------------------------------

def test_ppe_listing_forces_non_ppe_answer_to_ppe():
    df = _frame([_one(listing="PPE", conf="unknown")])
    _merge(df, {"r": {"product_category": "drills"}})
    assert df.at["r", "ProductCategory"] == "ppe"


def test_ppe_listing_keeps_accessories_and_screws():
    df = _frame([_one(idx="a", listing="PPE", conf="unknown"),
                 _one(idx="s", listing="PPE", conf="unknown")])
    _merge(df, {"a": {"product_category": "accessories"},
                "s": {"product_category": "screws"}})
    assert df.at["a", "ProductCategory"] == "accessories"
    assert df.at["s", "ProductCategory"] == "screws"


def test_tools_listing_forces_ppe_answer_to_other_low():
    df = _frame([_one(listing="Tools", conf="unknown")])
    _merge(df, {"r": {"product_category": "ppe", "confidence": "high"}})
    assert df.at["r", "ProductCategory"] == "other"
    assert df.at["r", "ProductCategory_Confidence"] == "low"  # other forced low


# ---------------------------------------------------------------------------
# Confidence, reason
# ---------------------------------------------------------------------------

def test_other_category_is_forced_low_confidence():
    df = _frame([_one(conf="unknown")])
    _merge(df, {"r": {"product_category": "other", "confidence": "high"}})
    assert df.at["r", "ProductCategory_Confidence"] == "low"


def test_invalid_confidence_defaults_medium():
    df = _frame([_one(conf="unknown")])
    _merge(df, {"r": {"product_category": "drills", "confidence": "banana"}})
    assert df.at["r", "ProductCategory_Confidence"] == "medium"


def test_reason_captured_when_present():
    df = _frame([_one(conf="unknown")])
    _merge(df, {"r": {"product_category": "drills", "reason": "twist drill body"}})
    assert df.at["r", "ProductCategory_Reason"] == "twist drill body"


# ---------------------------------------------------------------------------
# ToolClass
# ---------------------------------------------------------------------------

def test_toolclass_filled_only_when_blank():
    df = _frame([_one(conf="unknown", toolclass="")])
    _merge(df, {"r": {"product_category": "mills", "tool_class": "solid_end_mill"}})
    assert df.at["r", "ToolClass"] == "solid_end_mill"
    assert df.at["r", "ToolClass_Source"] == "AI"


def test_toolclass_not_overwritten_when_present():
    df = _frame([_one(conf="unknown", toolclass="face_mill")])
    _merge(df, {"r": {"product_category": "mills", "tool_class": "solid_end_mill"}})
    assert df.at["r", "ToolClass"] == "face_mill"  # kept


def test_invalid_toolclass_ignored():
    df = _frame([_one(conf="unknown", toolclass="")])
    _merge(df, {"r": {"product_category": "mills", "tool_class": "not_a_class"}})
    assert "ToolClass_Source" not in df.columns or pd.isna(df.at["r", "ToolClass_Source"])


# ---------------------------------------------------------------------------
# Pack units
# ---------------------------------------------------------------------------

def test_heuristic_pack_applied_when_source_default():
    df = _frame([_one(conf="unknown", pack_source="Default", pack=5.0)])
    _merge(df, {"r": {"product_category": "drills"}})  # drills -> heuristic 1
    assert df.at["r", "PackUnits"] == 1.0
    assert df.at["r", "PackUnits_Source"] == "Heuristic"


def test_heuristic_pack_not_applied_when_source_user():
    df = _frame([_one(conf="unknown", pack_source="User", pack=5.0)])
    _merge(df, {"r": {"product_category": "drills"}})
    assert df.at["r", "PackUnits"] == 5.0  # untouched
    assert df.at["r", "PackUnits_Source"] == "User"


def test_ai_pack_units_override_one_or_ten():
    df = _frame([_one(product="drills", conf="high", pack=1.0)])
    _merge(df, {"r": {"pack_units": 10}})
    assert df.at["r", "PackUnits"] == 10.0
    assert df.at["r", "PackUnits_Source"] == "AI"


def test_ai_pack_units_other_values_ignored():
    df = _frame([_one(product="drills", conf="high", pack=1.0)])
    _merge(df, {"r": {"pack_units": 7}})
    assert df.at["r", "PackUnits"] == 1.0  # unchanged


# ---------------------------------------------------------------------------
# Size
# ---------------------------------------------------------------------------

def test_size_filled_only_when_empty():
    df = _frame([_one(size="")])
    _merge(df, {"r": {"product_category": "drills", "size_category": "m"}})
    assert df.at["r", "SizeCategory"] == "M"
    assert df.at["r", "SizeCategory_Source"] == "AI"


def test_size_not_overwritten_when_present():
    df = _frame([_one(size="L")])
    _merge(df, {"r": {"product_category": "drills", "size_category": "s"}})
    assert df.at["r", "SizeCategory"] == "L"  # kept


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_row_with_no_result_is_untouched():
    df = _frame([_one(idx="r", product="drills", conf="medium", size="L", pack=10.0)])
    before = df.copy()
    _merge(df, {})  # no record for r
    pd.testing.assert_frame_equal(df, before)


def test_mutates_in_place_and_returns_same_object():
    df = _frame([_one(conf="unknown")])
    out = _merge(df, {"r": {"product_category": "drills"}})
    assert out is df


def test_multiple_rows_independent():
    df = _frame([_one(idx="a", conf="unknown"),
                 _one(idx="b", product="drills", conf="high")])
    _merge(df, {"a": {"product_category": "mills"}, "b": {"product_category": "taps"}})
    assert df.at["a", "ProductCategory"] == "mills"   # weak -> replaced
    assert df.at["b", "ProductCategory"] == "drills"  # strong -> kept


# ---------------------------------------------------------------------------
# Real-data simulation
# ---------------------------------------------------------------------------

_GROUND_TRUTH = os.environ.get("KROMI_GROUNDTRUTH_XLSX", "")


@pytest.mark.skipif(not (_GROUND_TRUTH and os.path.exists(_GROUND_TRUTH)),
                    reason="set KROMI_GROUNDTRUTH_XLSX to a planner Result workbook to run")
def test_real_data_merge_conserves_rows_and_only_fills_blanks():
    res = pd.ExcelFile(_GROUND_TRUTH).parse("Result")
    work = pd.DataFrame({
        "ProductCategory": res.ProductCategory.astype(str),
        "Listing": res.get("Listing", "Tools"),
        "ProductCategory_Confidence": "unknown",  # force the gate open
        "ToolClass": res.get("ToolClass", ""),
        "PackUnits_Source": "Default",
        "PackUnits": pd.to_numeric(res.PackUnits, errors="coerce").fillna(1.0),
        "SizeCategory": "",  # all blank -> AI size should fill
    }, index=res.index)
    n = len(work)
    rmap = {str(i): {"product_category": "drills", "size_category": "m", "confidence": "high"}
            for i in work.index}
    out = merge_classification_results(work, list(work.index), rmap, model=MODEL, timestamp_utc=TS)
    assert len(out) == n  # row count conserved
    assert (out["SizeCategory"] == "M").all()  # every blank size filled
    assert (out["SizeCategory_Source"] == "AI").all()
