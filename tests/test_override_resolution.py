"""Contract for override-source consolidation (I5, v34.20).

Corrections saved from the editor land in database override sets, but a fresh
upload used to read only the legacy per-customer file directory, so saved
corrections never applied to the next fresh run and the editor merged its
diffs against a base that diverged from what actually applied. The page now
resolves the default override source in one place: the newest active database
set for the exact customer and site applies, and since v34.23 the database is
the only runtime source. Explicit choices keep precedence: live pending edits outrank
everything, a picker reload with a chosen set applies exactly that set, and a
reload with overrides disabled applies none.
"""

import hashlib
from io import BytesIO

import pandas as pd

import engine.plan as ep
from engine.overrides import OVERRIDE_COLUMNS
from engine.run_restore import build_seed
from tests._paths import PLANNER_PAGE


def _synthetic_workbook_bytes():
    rows = 6
    df = pd.DataFrame({
        "ItemCode": [f"V{i:03d}" for i in range(rows)],
        "ItemName": [f"Override target {i}" for i in range(rows)],
        "Cons16": [(i + 1) * 60.0 for i in range(rows)],
    })
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    return bio.getvalue(), list(df.columns)


def _drive(raw_bytes, cols, override_mode=None):
    import streamlit as st
    st.cache_data.clear()
    from streamlit.testing.v1 import AppTest
    ui = {"cm_code": "ItemCode", "cm_desc1": "ItemName", "cm_cons": "Cons16",
          "ks_sheet_tools": "Sheet1"}
    restore = build_seed(ui, cols)
    restore["ks_hide_optional"] = False
    restore["ks_ai_colmap"] = False
    restore["_std_special_mapped"] = False
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    ctx = {"run_id": 1, "bytes": raw_bytes, "filename": "input.xlsx",
           "customer": "TestCustomer", "site": "TestSite",
           "classifications": {}, "override_set_id": None}
    if override_mode is not None:
        ctx["override_mode"] = override_mode
    at.session_state["_reload_ctx"] = ctx
    at.session_state["_pending_restore"] = restore
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    return at


def _seed_db_set(db_path):
    import db as kromi_db
    conn = kromi_db.init_db(db_path)
    row = {c: "" for c in OVERRIDE_COLUMNS}
    row.update({"code": "V001", "listing": "TOOLS",
                "product_category_override": "reamers",
                "reviewed_by": "tester", "reviewed_at": "2026-07-05T12:00:00Z"})
    set_id = kromi_db.save_override_set(
        conn, customer="TestCustomer", site="TestSite",
        reviewer_name="tester", notes="seeded",
        overrides_df=pd.DataFrame([row], columns=OVERRIDE_COLUMNS))
    conn.close()
    return set_id


def test_fresh_run_prefers_latest_db_set_with_file_fallback(monkeypatch, tmp_path):
    db_path = str(tmp_path / "ov.db")
    monkeypatch.setenv("KROMI_DB_PATH", db_path)
    raw_bytes, cols = _synthetic_workbook_bytes()

    captured = {}
    _orig = ep.run_plan

    def spying(df, overrides, params):
        captured["codes"] = sorted(
            str(c) for c in getattr(overrides, "get", lambda *_: pd.Series([], dtype=str))("code", pd.Series([], dtype=str))
        ) if hasattr(overrides, "get") else []
        captured["n"] = len(overrides)
        return _orig(df, overrides, params)

    monkeypatch.setattr(ep, "run_plan", spying)

    _drive(raw_bytes, cols)                       # nothing stored anywhere
    assert captured["n"] == 0, "with no db set and no file library, no overrides apply"

    _seed_db_set(db_path)
    _drive(raw_bytes, cols)                       # same scope, fresh drive
    assert captured["n"] == 1 and "V001" in captured["codes"], (
        "the newest active database set for the scope must apply on a fresh run"
    )


def test_reload_with_overrides_disabled_still_applies_none(monkeypatch, tmp_path):
    db_path = str(tmp_path / "ovnone.db")
    monkeypatch.setenv("KROMI_DB_PATH", db_path)
    raw_bytes, cols = _synthetic_workbook_bytes()
    _drive(raw_bytes, cols)
    _seed_db_set(db_path)

    captured = {}
    _orig = ep.run_plan

    def spying(df, overrides, params):
        captured["n"] = len(overrides)
        return _orig(df, overrides, params)

    monkeypatch.setattr(ep, "run_plan", spying)
    _drive(raw_bytes, cols, override_mode="none")
    assert captured["n"] == 0, "an explicit no-overrides recompute must stay empty"


def test_resolution_helper_serves_both_call_sites():
    src = open(PLANNER_PAGE, encoding="utf-8").read()
    assert src.count("def _resolve_active_overrides(") == 1
    assert src.count("_resolve_active_overrides(") >= 3, (
        "the apply path and the editor merge base must share the resolver"
    )

def test_runtime_reads_only_the_database(monkeypatch, tmp_path):
    """The file library is retired from the runtime (v34.23): the page holds
    no directory binding and no file readers; the resolver answers from the
    database or not at all. The engine file functions remain solely as the
    foundation of the migration instrument."""
    src = open(PLANNER_PAGE, encoding="utf-8").read()
    assert "OVERRIDES_DIR" not in src
    assert "load_overrides(" not in src
    assert "overrides_folder(" not in src
    assert "save_overrides(" not in src

    db_path = str(tmp_path / "dbonly.db")
    monkeypatch.setenv("KROMI_DB_PATH", db_path)
    raw_bytes, cols = _synthetic_workbook_bytes()

    captured = {}
    _orig = ep.run_plan

    def spying(df, overrides, params):
        captured["n"] = len(overrides)
        return _orig(df, overrides, params)

    monkeypatch.setattr(ep, "run_plan", spying)
    _drive(raw_bytes, cols)
    assert captured["n"] == 0, "an empty database yields an empty override frame"
