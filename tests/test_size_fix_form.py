"""The size-fix form must render once per unique code (found via export capture).

In replicate mode every item exists once per supply point, and any tool flagged
with a size issue is flagged on all its replicas. The form used to key one
checkbox per flagged ROW on the code alone, so two supply points meant two
checkboxes with the same key and Streamlit raised StreamlitDuplicateElementKey,
killing the page before the exports. Gated on the real raw workbook because the
flag requires a capped-mode carousel overflow that a tiny synthetic frame does
not reliably produce; the capture instrument that found the defect drives the
same configuration.
"""

import os

import pandas as pd
import pytest

from engine.run_restore import build_seed
from tests._paths import PLANNER_PAGE

_RAW = os.environ.get("KROMI_RAW_INPUT_XLSX", "")
_HAVE_RAW = bool(_RAW and os.path.exists(_RAW))


@pytest.mark.skipif(not _HAVE_RAW, reason="set KROMI_RAW_INPUT_XLSX to run")
def test_capped_replicate_with_flagged_rows_renders(monkeypatch, tmp_path):
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "sf.db"))
    from streamlit.testing.v1 import AppTest

    raw_bytes = open(_RAW, "rb").read()
    raw_cols = list(pd.ExcelFile(_RAW).parse("Sheet1").columns)
    ui = {"cm_code": "WZIntNr", "cm_desc1": "WZBez",
          "cm_cons": "Consumption Last 16 Months",
          "cm_stdspecial": "WZArtID (1Standard/2Sonder)",
          "cm_sup": "WZLiefStamm.LWZBestellNr", "cm_site": "Werk",
          "ks_sheet_tools": "Sheet1",
          "ks_op_mode": "Helix + Carousel (capped)", "ks_n_sp": 2}
    restore = build_seed(ui, raw_cols)
    restore["ks_hide_optional"] = False
    restore["ks_ai_colmap"] = False
    restore["_std_special_mapped"] = True

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

    # The configuration must have flagged rows on both supply points, or the
    # regression this test guards is not being exercised.
    flagged = [cb for cb in at.checkbox if str(cb.key or "").startswith("sizefit_cb_")]
    assert len(flagged) > 0, "no size-flagged rows; the scenario no longer exercises the form"
    keys = [cb.key for cb in flagged]
    assert len(keys) == len(set(keys)), "duplicate checkbox keys in the size-fix form"
