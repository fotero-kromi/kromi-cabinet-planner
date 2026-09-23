"""Contract for the I1 per-click cost capstone (v34.29).

After a completed run, a plain widget rerun must not re-execute the engine,
must not rebuild the presentation deck, and must not walk the technician
editor diff loop when the form was not submitted. The run cache is keyed by
cheap content tokens (a vectorized frame digest plus the params hash)
instead of streamlit's generic serialization of the full frames, so the
per-click key cost stays flat as customer files grow. Counted relative to
the run pass, so the pins are independent of where the run gate sits.
"""

import os
import tempfile
from io import BytesIO
from pathlib import Path

import pandas as pd
from tests._paths import PLANNER_PAGE

REPO = Path(__file__).resolve().parents[1]


def _drive(monkeypatch, tmp_path, counters):
    import engine.plan as ep
    import presentation as pres
    import streamlit as st

    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "cc.db"))

    _orig_run = ep.run_plan
    _orig_deck = pres.build_summary_deck

    def run_spy(*a, **k):
        counters["run_plan"] += 1
        return _orig_run(*a, **k)

    def deck_spy(*a, **k):
        counters["deck"] += 1
        return _orig_deck(*a, **k)

    monkeypatch.setattr(ep, "run_plan", run_spy)
    monkeypatch.setattr(pres, "build_summary_deck", deck_spy)

    rows = 5
    df = pd.DataFrame({
        "ItemCode": [f"C{i:03d}" for i in range(rows)],
        "ItemName": [f"Cutting tool {i}" for i in range(rows)],
        "Cons16": [(i + 1) * 6000.0 for i in range(rows)],
    })
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Sheet1")

    from engine.run_restore import build_seed
    ui = {"cm_code": "ItemCode", "cm_desc1": "ItemName", "cm_cons": "Cons16",
          "ks_sheet_tools": "Sheet1"}
    seed = build_seed(ui, list(df.columns))
    seed["ks_hide_optional"] = False
    seed["ks_ai_colmap"] = False
    seed["_std_special_mapped"] = False

    st.cache_data.clear()
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": bio.getvalue(), "filename": "input.xlsx",
        "customer": "CacheContract", "site": "S",
        "classifications": {}, "override_mode": "none", "override_set_id": None,
    }
    at.session_state["_pending_restore"] = seed
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception
    return at


def test_plain_rerun_runs_nothing_heavy(monkeypatch, tmp_path):
    counters = {"run_plan": 0, "deck": 0}
    at = _drive(monkeypatch, tmp_path, counters)
    assert counters["run_plan"] >= 1, "the run pass never reached the engine"
    assert counters["deck"] == 0, (
        "the run pass must not build the deck any more (on-demand, v34.31)"
    )
    btn = next(b for b in at.button if getattr(b, "key", "") == "btn_prepare_exports")
    btn.click()
    at.run()
    assert not at.exception, at.exception
    after_run = dict(counters)
    assert after_run["deck"] >= 1, "the Prepare click never built the deck"

    at.run()
    at.run()
    assert not at.exception, at.exception
    assert counters["run_plan"] == after_run["run_plan"], (
        f"a plain rerun re-executed the engine "
        f"({counters['run_plan'] - after_run['run_plan']} extra call(s))"
    )
    assert counters["deck"] == after_run["deck"], (
        f"a plain rerun rebuilt the deck "
        f"({counters['deck'] - after_run['deck']} extra build(s))"
    )


def test_run_cache_is_token_keyed():
    src = (REPO / "pages" / "1_Kromi_Planner.py").read_text(encoding="utf-8")
    assert "def _frame_token(" in src, "the cheap frame digest helper is missing"
    assert "_cached_run_plan(" in src
    # the wrapper must not let streamlit hash the frames: they arrive
    # underscore-prefixed, and the token carries the content identity
    assert "def _cached_run_plan(plan_key: str, _work_df" in src


def test_editor_diffs_are_submit_gated():
    src = (REPO / "ui" / "technician_panel.py").read_text(encoding="utf-8")
    i_init = src.index("diffs: List[Dict[str, Any]] = []")
    i_gate = src.index("if _editor_applied:")
    i_loop = src.index("for ridx, orig_row in editor_df.set_index")
    assert i_init < i_gate < i_loop, (
        "diffs must exist on every path, and the diff walk must sit behind "
        "the form-submit gate so a plain rerun never performs it"
    )


def test_frame_token_tracks_content():
    import sys
    sys.path.insert(0, str(REPO))
    import importlib
    mod = importlib.import_module("engine.export_shaping")
    tok = getattr(mod, "frame_token")
    a = pd.DataFrame({"x": [1, 2], "y": ["a", "b"]})
    b = a.copy()
    assert tok(a) == tok(b)
    c = a.copy()
    c.loc[0, "x"] = 99
    assert tok(a) != tok(c)
    d = a.rename(columns={"y": "z"})
    assert tok(a) != tok(d)
    e = a.astype({"x": "float64"})
    assert tok(a) != tok(e)
    assert tok(pd.DataFrame()) == tok(pd.DataFrame())


# ---- fragments (v34.30) ------------------------------------------------------

def test_result_sections_are_fragments():
    """Repeat-click sections rerun locally: the distribution basis toggle and
    the technician review panel are st.fragment-wrapped, so their widget
    interactions cost the fragment, not a full script pass. Explicit
    st.rerun() calls keep app scope by default, so save and load flows still
    trigger full recomputes."""
    src = (REPO / "pages" / "1_Kromi_Planner.py").read_text(encoding="utf-8")
    for name in ("_distribution_basis_fragment", "_technician_review_fragment"):
        assert f"@st.fragment\ndef {name}():" in src, f"{name} missing"
        assert f"\n{name}()" in src, f"{name} never invoked"
    assert 'st.rerun(scope="fragment")' not in src, (
        "no fragment-scoped explicit rerun may sneak in; saves and loads "
        "must stay app-wide"
    )


# ---- on-demand exports (v34.31) ----------------------------------------------

def test_exports_build_on_demand(monkeypatch, tmp_path):
    """The workbook and deck leave the run pass: a completed run builds no
    export views, the Prepare click builds them once, and a plain rerun adds
    zero builds. The prepared downloads are keyed to the plan, so a new plan
    shows the Prepare step again instead of stale files."""
    import engine.workbook as kn
    counters = {"augment": 0}
    _orig = kn.augment_for_export

    def spy(*a, **k):
        counters["augment"] += 1
        return _orig(*a, **k)

    monkeypatch.setattr(kn, "augment_for_export", spy)

    at = _drive(monkeypatch, tmp_path, {"run_plan": 0, "deck": 0})
    assert counters["augment"] == 0, (
        "the run pass must not build export views any more"
    )
    btn = next(b for b in at.button if getattr(b, "key", "") == "btn_prepare_exports")
    btn.click()
    at.run()
    assert not at.exception, at.exception
    after_prepare = counters["augment"]
    assert after_prepare >= 1, "the Prepare click never built the workbook views"
    at.run()
    assert counters["augment"] == after_prepare, (
        "a plain rerun rebuilt the export views"
    )


def test_exports_fragment_structure():
    page = (REPO / "pages" / "1_Kromi_Planner.py").read_text(encoding="utf-8")
    panel = (REPO / "ui" / "exports_panel.py").read_text(encoding="utf-8")
    assert "@st.fragment\ndef _exports_fragment():" in page
    assert "exports_panel.render(" in page, "the fragment must stay a thin shell"
    assert '"btn_prepare_exports"' in panel
    assert '_exports_key' in panel


# ---- upload digest memo (v34.32) ----------------------------------------------

def test_upload_is_digested_once_per_file(monkeypatch, tmp_path):
    """The full upload bytes are hashed exactly once per distinct file: the
    run pass and every plain rerun afterwards reuse the memoized digest and
    bytes instead of re-copying and re-scanning the whole upload, which on
    very large customer files costs real time on every click."""
    import hashlib as _hl
    upload_len = {"raw": None}
    counts = {"full_sha": 0}
    _orig = _hl.sha256

    def spy(data=b"", *a, **k):
        if upload_len["raw"] is not None and isinstance(data, (bytes, bytearray)) \
                and bytes(data) == upload_len["raw"]:
            counts["full_sha"] += 1
        return _orig(data, *a, **k)

    monkeypatch.setattr(_hl, "sha256", spy)

    import engine.plan as ep  # noqa: F401  (drive helper expects the module importable)
    at = None
    # reuse the shared drive, but capture the upload size before it runs
    import pandas as pd
    from io import BytesIO
    rows = 5
    df = pd.DataFrame({
        "ItemCode": [f"D{i:03d}" for i in range(rows)],
        "ItemName": [f"Drill {i}" for i in range(rows)],
        "Cons16": [(i + 1) * 6000.0 for i in range(rows)],
    })
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Sheet1")
    raw = bio.getvalue()
    upload_len["raw"] = raw

    import streamlit as st
    from engine.run_restore import build_seed
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "dig.db"))
    ui = {"cm_code": "ItemCode", "cm_desc1": "ItemName", "cm_cons": "Cons16",
          "ks_sheet_tools": "Sheet1"}
    seed = build_seed(ui, list(df.columns))
    seed["ks_hide_optional"] = False
    seed["ks_ai_colmap"] = False
    seed["_std_special_mapped"] = False
    st.cache_data.clear()
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": raw, "filename": "input.xlsx",
        "customer": "DigestMemo", "site": "S",
        "classifications": {}, "override_mode": "none", "override_set_id": None,
    }
    at.session_state["_pending_restore"] = seed
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception
    at.run()
    at.run()
    assert not at.exception, at.exception
    assert counts["full_sha"] == 1, (
        f"the full upload was hashed {counts['full_sha']} times across the "
        f"parse pass, the run pass, and two plain reruns; the memo must hold it at one"
    )


def test_sheet_reader_is_token_keyed():
    src = (REPO / "pages" / "1_Kromi_Planner.py").read_text(encoding="utf-8")
    assert "def _read_sheet(input_sha: str, sheet_name, header_row: int," in src, (
        "the sheet reader must key on the digest, not on streamlit hashing "
        "the full bytes every pass"
    )
    assert "_file_bytes: bytes" in src, (
        "the upload bytes must stay underscore-prefixed so they never enter "
        "the cache key"
    )
    assert "_upload_bytes_memo" in src


# ---- execution duration (v34.33) ----------------------------------------------

def test_persisted_run_records_duration(monkeypatch, tmp_path):
    """The archived run carries how long the plan computation took: the page
    times the plan-retrieval call on the run pass and persists it, closing
    the parked forensics gap where duration_ms was always None."""
    import sqlite3
    counters = {"run_plan": 0, "deck": 0}
    _drive(monkeypatch, tmp_path, counters)
    conn = sqlite3.connect(str(tmp_path / "cc.db"))
    try:
        row = conn.execute(
            "SELECT duration_ms FROM engine_executions "
            "ORDER BY execution_id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "no execution row was persisted"
    assert row[0] is not None and int(row[0]) > 0, (
        f"duration_ms must carry the measured plan time, got {row[0]!r}"
    )



# ---- cached distributions (v34.37, audit P1) -----------------------------------

def test_distributions_are_plan_keyed():
    src = (REPO / "pages" / "1_Kromi_Planner.py").read_text(encoding="utf-8")
    assert "def _cached_distribution(plan_key: str" in src
    assert src.count("_cached_distribution(_plan_key,") == 4, (
        "all four distribution tables must go through the plan-keyed cache"
    )
