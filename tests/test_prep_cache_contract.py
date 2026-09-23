"""Contract for caching prepare_planning_base (the v34.11 release).

The page wraps engine.preprocessing.prepare_planning_base in st.cache_data keyed
on the content of its four arguments (the mapped frame plus three scalars). The
first three tests pin the properties that wrapping relies on: the function never
mutates its input frame, is deterministic in its inputs (frame and info dict
alike), and returns a value that survives a pickle round-trip, which is how a
cache hit hands back a fresh copy.

The last test defines the release: a small synthetic workbook is driven through
the page's reload path and the engine function's invocations are counted across
an initial run pass and a plain rerun. Before the cache the rerun re-executes
the preparation; after it the rerun adds zero calls. The count is asserted
relative to the run pass, so the test is independent of where the run gate sits.
"""

import pickle

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import engine.preprocessing as pp
from engine.preprocessing import prepare_planning_base
from tests._paths import PLANNER_PAGE


def _raw_frame() -> pd.DataFrame:
    """A frame shaped like the page's mapped input: duplicate codes across
    years with conflicting attributes, so the year filter, the dedup collapse,
    and the conflict scan all engage."""
    return pd.DataFrame({
        "Code": ["A1", "A1", "B2", "B2", "C3", "D4", "D4", "E5"],
        "Description": ["Mill 10", "Mill 10 old", "Insert", "Insert", "Drill",
                        "Tap", "Tap", "Holder"],
        "Description_2": [""] * 8,
        "SupplierCode": ["S1", "S1", "S2", "S2", "S3", "S4", "S4", "S5"],
        "Consumption_pcs": [120.0, 60.0, 900.0, 300.0, 45.0, 210.0, 70.0, 12.0],
        "PackUnits": [1.0, 2.0, 10.0, 10.0, 1.0, 1.0, 5.0, 1.0],
        "ProductCategory": ["mills", "drills", "inserts", "inserts", "drills",
                            "taps", "taps", "holders"],
        "SizeCategory": ["M", "M", "S", "S", "S", "M", "L", "L"],
        "Year": [2026, 2024, 2026, 2025, 2026, 2026, 2025, 2026],
    })


@pytest.mark.parametrize("dedup_mode", ["none", "code", "code_supplier"])
def test_prepare_planning_base_does_not_mutate_input(dedup_mode):
    df = _raw_frame()
    before = df.copy(deep=True)
    prepare_planning_base(df, dedup_mode=dedup_mode, year_mode="latest_year_only",
                          has_year=True)
    assert_frame_equal(df, before, check_dtype=True)


def test_prepare_planning_base_is_deterministic():
    df = _raw_frame()
    base1, info1 = prepare_planning_base(df, dedup_mode="code",
                                         year_mode="latest_year_only", has_year=True)
    base2, info2 = prepare_planning_base(df, dedup_mode="code",
                                         year_mode="latest_year_only", has_year=True)
    assert_frame_equal(base1, base2, check_dtype=True)
    assert info1 == info2


def test_prepare_planning_base_return_is_picklable():
    df = _raw_frame()
    base, info = prepare_planning_base(df, dedup_mode="code_supplier",
                                       year_mode="all_rows", has_year=True)
    clone_base, clone_info = pickle.loads(pickle.dumps((base, info)))
    assert_frame_equal(clone_base, base, check_dtype=True)
    assert clone_info == info


def _synthetic_workbook_bytes():
    from io import BytesIO
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


def test_page_prep_runs_once_across_reruns(monkeypatch, tmp_path):
    """The release contract: a plain rerun after a run adds zero preparation
    calls. Counted by patching the engine attribute the page re-imports on
    every script pass; a cache hit never enters the wrapper body, so the count
    freezes once the plan exists."""
    from engine.run_restore import build_seed

    calls = {"n": 0}
    _orig = pp.prepare_planning_base

    def counting(*args, **kwargs):
        calls["n"] += 1
        return _orig(*args, **kwargs)

    monkeypatch.setattr(pp, "prepare_planning_base", counting)
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "prep_cache.db"))

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
    at.run()                                    # pass 1: seed mapping, render
    at.session_state["_force_run"] = True
    at.run()                                    # pass 2: execute the run
    assert not at.exception, f"page raised: {at.exception}"
    n_after_run = calls["n"]
    assert n_after_run >= 1, "the run pass never reached the preparation"

    at.run()                                    # pass 3: plain rerun
    assert not at.exception, f"page raised on rerun: {at.exception}"
    assert calls["n"] == n_after_run, (
        f"a plain rerun re-executed prepare_planning_base "
        f"({calls['n'] - n_after_run} extra call(s)); expected a cache hit")
