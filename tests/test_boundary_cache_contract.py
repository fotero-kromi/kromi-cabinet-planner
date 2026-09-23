"""Contract for the boundary heuristics extraction and cache (v34.14).

apply_pre_ai_heuristics carries steps A through D of the page's boundary
(ProductCategory classification, ToolClass derivation, insert override,
SizeCategory and PackUnits resolution with the insert pack safety net) and
apply_post_ai_safety carries the final insert pass and default size fill. The
behavior pins below exercise the branches that matter on real files: blank
categories resolved by the description classifier, pack sizes parsed from
text hints, the insert override with the PPE exemption, provided-value
normalization, and the defaults. Purity, determinism, and picklability are
what the page's content-addressed cache relies on. The last test defines the
release: across an initial run pass and a plain rerun, each boundary pass
executes exactly once.
"""

import pickle
from io import BytesIO

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import engine.boundary as eb
from engine.boundary import apply_post_ai_safety, apply_pre_ai_heuristics
from tests._paths import PLANNER_PAGE


def _scaffold(rows: dict) -> pd.DataFrame:
    n = len(next(iter(rows.values())))
    base = {
        "Code": [f"C{i}" for i in range(n)],
        "SupplierCode": [""] * n,
        "Listing": ["Tools"] * n,
        "Description": [""] * n,
        "Description_2": [""] * n,
        "ProductCategory": [""] * n,
        "ProductCategory_Source": [""] * n,
        "ProductCategory_Evidence": [""] * n,
        "ProductCategory_Confidence": [""] * n,
        "ToolClass": [""] * n,
        "ToolClass_Source": [""] * n,
        "SizeCategory": [""] * n,
        "SizeCategory_Source": [""] * n,
        "PackUnits": [pd.NA] * n,
        "PackUnits_Source": [""] * n,
    }
    base.update(rows)
    return pd.DataFrame(base)


def test_blank_categories_resolved_by_classifier():
    df = _scaffold({"Description": ["End mill 10mm", "Insert CNMG 120408", "mystery item"]})
    out = apply_pre_ai_heuristics(df, enable_pack_hint_extraction=True,
                                  insert_default_pack_units=10.0)
    assert out.loc[0, "ProductCategory"] == "mills"
    assert out.loc[0, "ProductCategory_Source"] == "Heuristic"
    assert out.loc[1, "ProductCategory"] == "inserts"
    # the unresolvable row is tagged for the AI stage, not invented
    assert out.loc[2, "ProductCategory"] in ("other", "")
    assert out.loc[2, "ProductCategory_Confidence"] in ("unknown", "low")


def test_pack_hint_extraction_toggle():
    df = _scaffold({"Description": ["Schrauben carton de 60"]})
    on = apply_pre_ai_heuristics(df, enable_pack_hint_extraction=True,
                                 insert_default_pack_units=10.0)
    assert float(on.loc[0, "PackUnits"]) == 60.0
    assert str(on.loc[0, "PackUnits_Evidence"]).startswith("text:")
    off = apply_pre_ai_heuristics(df, enable_pack_hint_extraction=False,
                                  insert_default_pack_units=10.0)
    assert not str(off.loc[0, "PackUnits_Evidence"]).startswith("text:")


def test_insert_override_forces_category_and_pack_with_ppe_exempt():
    df = _scaffold({
        "Description": ["Wendeplatte WNMG 080408", "Wendeplatte WNMG 080408"],
        "ProductCategory": ["drills", "drills"],
        "ProductCategory_Source": ["Provided", "Provided"],
        "Listing": ["Tools", "PPE"],
        "PackUnits": [1.0, 1.0],
    })
    out = apply_pre_ai_heuristics(df, enable_pack_hint_extraction=True,
                                  insert_default_pack_units=10.0)
    assert out.loc[0, "ProductCategory"] == "inserts"
    assert float(out.loc[0, "PackUnits"]) == 10.0
    assert out.loc[1, "ProductCategory"] == "drills", "PPE rows are exempt"


def test_provided_values_normalized_and_trusted():
    df = _scaffold({
        "Description": ["End mill"],
        "ProductCategory": ["Mills"],
        "SizeCategory": ["m"],
        "PackUnits": [5.0],
    })
    out = apply_pre_ai_heuristics(df, enable_pack_hint_extraction=True,
                                  insert_default_pack_units=10.0)
    # Canonical category names are identity under normalization (v34.18), so a
    # mapped column carrying them keeps Provided status; size and pack
    # provided values are trusted and normalized as before.
    assert out.loc[0, "ProductCategory"] == "mills"
    assert out.loc[0, "ProductCategory_Source"] == "Provided"
    assert out.loc[0, "SizeCategory"] == "M"
    assert out.loc[0, "SizeCategory_Source"] == "Provided"
    assert out.loc[0, "PackUnits_Source"] == "Provided"


def test_post_ai_safety_fills_and_forces():
    df = _scaffold({
        "Description": ["Insert CNMG 120408", "Holder plain"],
        "ProductCategory": ["other", "holders"],
        "PackUnits": [1.0, 1.0],
        "SizeCategory": ["", ""],
    })
    out = apply_post_ai_safety(df, insert_default_pack_units=10.0)
    assert out.loc[0, "ProductCategory"] == "inserts"
    assert float(out.loc[0, "PackUnits"]) == 10.0
    assert out.loc[0, "SizeCategory"] == "S"
    assert out.loc[1, "SizeCategory"] == "L"
    assert out.loc[1, "SizeCategory_Source"] == "Default"


@pytest.mark.parametrize("fn,kw", [
    (apply_pre_ai_heuristics, {"enable_pack_hint_extraction": True,
                               "insert_default_pack_units": 10.0}),
    (apply_post_ai_safety, {"insert_default_pack_units": 10.0}),
])
def test_boundary_passes_are_pure_deterministic_picklable(fn, kw):
    df = _scaffold({"Description": ["End mill 10mm", "Insert CNMG", "carton de 60 Schrauben"]})
    if fn is apply_post_ai_safety:
        # the final pass runs after pre-AI in the page, so PackUnits is
        # always resolved by the time it executes; honor that precondition
        df = apply_pre_ai_heuristics(df, enable_pack_hint_extraction=True,
                                     insert_default_pack_units=10.0)
    before = df.copy(deep=True)
    a = fn(df, **kw)
    assert_frame_equal(df, before, check_dtype=True)
    b = fn(df, **kw)
    assert_frame_equal(a, b, check_dtype=True)
    c = pickle.loads(pickle.dumps(a))
    assert_frame_equal(c, a, check_dtype=True)


def _synthetic_workbook_bytes():
    rows = 12
    df = pd.DataFrame({
        "ItemCode": [f"K{i:03d}" for i in range(rows)],
        "ItemName": [f"Synthetic tool {i}" for i in range(rows)],
        "Cons16": [(i + 1) * 40.0 for i in range(rows)],
    })
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    return bio.getvalue(), list(df.columns)


def test_page_boundary_passes_run_once_across_reruns(monkeypatch, tmp_path):
    """The release contract: the page routes both boundary passes through the
    engine functions, and a plain rerun adds zero calls to either."""
    from engine.run_restore import build_seed

    counts = {"pre": 0, "post": 0}
    _pre, _post = eb.apply_pre_ai_heuristics, eb.apply_post_ai_safety

    def cpre(*a, **k):
        counts["pre"] += 1
        return _pre(*a, **k)

    def cpost(*a, **k):
        counts["post"] += 1
        return _post(*a, **k)

    monkeypatch.setattr(eb, "apply_pre_ai_heuristics", cpre)
    monkeypatch.setattr(eb, "apply_post_ai_safety", cpost)
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "bnd_cache.db"))

    raw_bytes, cols = _synthetic_workbook_bytes()
    ui = {"cm_code": "ItemCode", "cm_desc1": "ItemName", "cm_cons": "Cons16",
          "ks_sheet_tools": "Sheet1"}
    restore = build_seed(ui, cols)
    restore["ks_hide_optional"] = False
    restore["ks_ai_colmap"] = False
    restore["_std_special_mapped"] = False

    import streamlit as st
    st.cache_data.clear()   # order-independence: another test may share keys
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": raw_bytes, "filename": "input.xlsx",
        "customer": "TestCustomer", "site": "TestSite",
        "classifications": {}, "override_mode": "none", "override_set_id": None,
    }
    at.session_state["_pending_restore"] = restore
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    after_run = dict(counts)
    assert after_run["pre"] >= 1, "the run pass never reached the pre-AI boundary pass"
    assert after_run["post"] >= 1, "the run pass never reached the post-AI safety pass"

    at.run()
    assert not at.exception, f"page raised on rerun: {at.exception}"
    assert counts == after_run, (
        f"a plain rerun re-executed the boundary passes: {counts} vs {after_run}")
