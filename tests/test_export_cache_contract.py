"""Contract for caching the workbook builder (v34.12, PDF retired in v34.25).

The page builds the result workbook eagerly on every script pass. This
contract counts the build across an initial run pass and a plain rerun,
using a marker only the builder reaches: the KROMI numbering augmentation
(called per exported view inside the workbook build). Before the cache the
counter grows on the rerun; after it the rerun adds zero calls. Counted
relative to the run pass, so the test is independent of where the run gate
sits.
"""

from io import BytesIO

import pandas as pd
import pytest

import engine.workbook as kn
from tests._paths import PLANNER_PAGE

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


def test_export_builds_run_once_across_reruns(monkeypatch, tmp_path):
    from engine.run_restore import build_seed

    counts = {"augment": 0}
    _orig_aug = kn.augment_for_export

    def counting_aug(*a, **k):
        counts["augment"] += 1
        return _orig_aug(*a, **k)

    monkeypatch.setattr(kn, "augment_for_export", counting_aug)
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "exp_cache.db"))

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
    at.run()
    _btn = next(b for b in at.button if getattr(b, "key", "") == "btn_prepare_exports")
    _btn.click()
    at.run()                                    # pass 2: execute the run
    assert not at.exception, f"page raised: {at.exception}"
    after_run = dict(counts)
    assert after_run["augment"] >= 1, "the run pass never built the workbook views"

    at.run()                                    # pass 3: plain rerun
    assert not at.exception, f"page raised on rerun: {at.exception}"
    assert counts["augment"] == after_run["augment"], (
        f"a plain rerun rebuilt the workbook views "
        f"({counts['augment'] - after_run['augment']} extra augment call(s))")
