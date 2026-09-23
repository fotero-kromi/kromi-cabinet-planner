"""End-to-end pipeline verification through the page's reload path.

The AppTest render smoke stops at the upload gate and never executes the planning
pipeline. This drives the page's full deterministic pipeline headlessly on a real
customer file by using the reload path: stored input bytes plus stored
classifications are injected into session_state, so the page recomputes the run on
the current engine without ever calling OpenAI. The one-shot _force_run flag pushes
it past the run gate.

This is the verification vehicle for the decomposition campaign: run it before and
after a refactor on the same engine version and the metrics must be identical.

Both files are supplied from outside the shipped code (no customer name lives in
the test):
  KROMI_RAW_INPUT_XLSX   -- the raw consumption workbook fed to the planner
  KROMI_GROUNDTRUTH_XLSX -- the planner Result workbook for that run (classifications)
"""

import os
import tempfile

import pandas as pd
import pytest

from engine.run_restore import build_seed, NOT_AVAIL
from tests._paths import PLANNER_PAGE

_RAW = os.environ.get("KROMI_RAW_INPUT_XLSX", "")
_RESULT = os.environ.get("KROMI_GROUNDTRUTH_XLSX", "")

_HAVE_FILES = bool(_RAW and os.path.exists(_RAW) and _RESULT and os.path.exists(_RESULT))


def _metric_value(at, label):
    for m in at.metric:
        if m.label == label:
            v = m.value
            try:
                return int(str(v).replace(",", "").split()[0])
            except (ValueError, IndexError):
                return v
    return None


def _drive_pipeline(at, raw_path, result_path):
    """Inject a reload context built from real files and run the full pipeline."""
    raw_bytes = open(raw_path, "rb").read()
    raw_cols = list(pd.ExcelFile(raw_path).parse("Sheet1").columns)

    res = pd.ExcelFile(result_path).parse("Result")
    classifications = {
        str(r["Code"]): {"size_category": r["SizeCategory"],
                         "product_category": r["ProductCategory"]}
        for _, r in res.iterrows()
    }

    ui_state = {
        "cm_code": "WZIntNr",
        "cm_desc1": "WZBez",
        "cm_cons": "Consumption Last 16 Months",
        "cm_stdspecial": "WZArtID (1Standard/2Sonder)",
        "cm_sup": "WZLiefStamm.LWZBestellNr",
        "cm_site": "Werk",
        "ks_ktc_threshold": 1.0,
        "ks_helix_threshold": 4.0,
        "ks_consumption_months": 16,
        "ks_overfill": 1.1,
        "ks_min_carousel": 3,
        "cov_days_standard": 18,
        "cov_days_special": 18,
        "ks_reserve": 0.85,
        "ks_max_carousels": 1,
        "ks_op_mode": "Helix + Carousel (capped)",
        "ks_insert_pack": 10,
        "ks_sheet_tools": "Sheet1",
    }
    restore = build_seed(ui_state, raw_cols)
    restore["ks_hide_optional"] = False
    restore["ks_ai_colmap"] = False
    _ss = ui_state.get("cm_stdspecial")
    restore["_std_special_mapped"] = bool(
        isinstance(_ss, str) and _ss not in ("", NOT_AVAIL) and _ss in raw_cols
    )

    reload_ctx = {
        "run_id": 1, "bytes": raw_bytes, "filename": "input.xlsx",
        "customer": "TestCustomer", "site": "TestSite",
        "classifications": classifications,
        "override_mode": "none", "override_set_id": None,
    }

    at.session_state["_reload_ctx"] = reload_ctx
    at.session_state["_pending_restore"] = restore
    at.run()                                   # run 1: seed mapping + controls, render gate
    at.session_state["_force_run"] = True
    at.run()                                   # run 2: execute the pipeline
    return len(res)


@pytest.mark.skipif(not _HAVE_FILES,
                    reason="set KROMI_RAW_INPUT_XLSX and KROMI_GROUNDTRUTH_XLSX to run")
def test_full_pipeline_runs_end_to_end_on_real_data(monkeypatch, tmp_path):
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "e2e.db"))
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    n_rows = _drive_pipeline(at, _RAW, _RESULT)

    # the pipeline ran cleanly through to a rendered plan
    assert not at.exception, f"page raised: {at.exception}"
    assert len(at.metric) >= 7, "the plan metrics did not render"
    assert not list(at.error), f"page rendered an error: {[e.value for e in at.error]}"

    # every customer row survives preprocessing, split across the two systems
    ktc = _metric_value(at, "KTC articles")
    kanban = _metric_value(at, "Kanban articles")
    assert ktc is not None and kanban is not None
    assert ktc + kanban == n_rows == 1075

    # deterministic sizing base reproduces the ground truth exactly
    assert _metric_value(at, "Helix cabinets (+15%)") == 2
    assert _metric_value(at, "Carousel cabinets (+15%)") == 1

    # the pipeline reached the late stages (export section rendered)
    subheaders = [str(getattr(s, "value", s)) for s in at.subheader]
    assert any("Export" in s for s in subheaders), "pipeline did not reach Export"


@pytest.mark.skipif(not _HAVE_FILES,
                    reason="set KROMI_RAW_INPUT_XLSX and KROMI_GROUNDTRUTH_XLSX to run")
def test_pipeline_is_deterministic_across_two_drives(monkeypatch, tmp_path):
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "e2e_det.db"))
    from streamlit.testing.v1 import AppTest

    labels = ["KTC articles", "Kanban articles",
              "Helix cabinets (+15%)", "Carousel cabinets (+15%)"]

    at1 = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    _drive_pipeline(at1, _RAW, _RESULT)
    first = {lbl: _metric_value(at1, lbl) for lbl in labels}

    at2 = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    _drive_pipeline(at2, _RAW, _RESULT)
    second = {lbl: _metric_value(at2, lbl) for lbl in labels}

    assert first == second, f"non-deterministic pipeline: {first} != {second}"
