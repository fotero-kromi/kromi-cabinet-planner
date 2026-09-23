"""UX safety contracts (v34.51, audit UX findings F10/F11/F12/F14).

* AI is off by default when no OpenAI key is configured (it used to be on and
  every batch failed after Run); with a key it stays on. "Max AI items" has an
  upper bound.
* The experimental optimizer no longer re-solves on every click: it runs on
  demand, its result is kept for the current plan, and it uses the run's own
  Helix overfill factor.
* Destructive technician actions ask first: clearing all pending
  corrections and deleting a row of a saved override set.
* Stale or wrong texts are gone (negative checks only).
"""
from io import BytesIO

import pandas as pd

from engine.overrides import OVERRIDE_COLUMNS
from engine.run_restore import build_seed
from tests._paths import PLANNER_PAGE, REPO


def _xlsx():
    df = pd.DataFrame({
        "ItemCode": [f"V{i:03d}" for i in range(6)],
        "ItemName": [f"Bohrer D{i + 3},5" for i in range(6)],
        "Cons16": [(i + 1) * 600.0 for i in range(6)],
    })
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Sheet1")
    return bio.getvalue(), list(df.columns)


def _drive(monkeypatch, tmp_path, *, run=True, extra_state=None):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "ux.db"))
    st.cache_data.clear()
    raw, cols = _xlsx()
    seed = build_seed({"cm_code": "ItemCode", "cm_desc1": "ItemName",
                       "cm_cons": "Cons16", "ks_sheet_tools": "Sheet1"}, cols)
    seed.update({"ks_hide_optional": False, "ks_ai_colmap": False,
                 "_std_special_mapped": False})
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": raw, "filename": "input.xlsx",
        "customer": "UxCustomer", "site": "UxSite", "classifications": {},
        "override_set_id": None}
    at.session_state["_pending_restore"] = seed
    for k, v in (extra_state or {}).items():
        at.session_state[k] = v
    at.run()
    if run:
        at.session_state["_force_run"] = True
        at.run()
    assert not at.exception, at.exception
    return at


def _checkbox(at, label_start):
    return next(c for c in at.checkbox if str(c.label).startswith(label_start))


# ---- AI defaults ------------------------------------------------------------

def _fresh_page(monkeypatch, tmp_path):
    # A fresh upload flow (no stored run): the AI controls render in the
    # sidebar before any file is chosen.
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "ux.db"))
    st.cache_data.clear()
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def test_ai_is_off_by_default_without_a_key(monkeypatch, tmp_path):
    at = _fresh_page(monkeypatch, tmp_path)
    assert _checkbox(at, "Use AI").value is False


def test_ai_stays_on_by_default_with_a_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    at = _fresh_page(monkeypatch, tmp_path)
    assert _checkbox(at, "Use AI").value is True


def test_max_ai_items_has_an_upper_bound(monkeypatch, tmp_path):
    at = _fresh_page(monkeypatch, tmp_path)
    ni = next(n for n in at.number_input if str(n.label).startswith("Max AI items"))
    assert ni.max <= 10**6 and ni.max >= ni.value


# ---- optimizer on demand ----------------------------------------------------

def test_optimizer_runs_only_on_request_and_is_kept(monkeypatch, tmp_path):
    import optimization
    calls = {"n": 0, "overfill": []}
    orig_solve = optimization.solve_ktc_allocation
    orig_units = optimization.helix_units_for_routing

    def solve_spy(*a, **k):
        calls["n"] += 1
        return orig_solve(*a, **k)

    def units_spy(*a, **k):
        calls["overfill"].append(k.get("overfill_factor"))
        return orig_units(*a, **k)

    monkeypatch.setattr(optimization, "solve_ktc_allocation", solve_spy)
    monkeypatch.setattr(optimization, "helix_units_for_routing", units_spy)
    at = _drive(monkeypatch, tmp_path)
    at.run()
    assert calls["n"] == 0, "the optimizer must not solve on a run or a plain rerun"
    btn = next(b for b in at.button if getattr(b, "key", "") == "btn_run_optimizer")
    btn.click()
    at.run()
    assert not at.exception, at.exception
    assert calls["n"] == 1
    at.run()
    at.run()
    assert calls["n"] == 1, "a plain rerun must show the kept result, not re-solve"
    assert calls["overfill"] and all(f is not None for f in calls["overfill"])


# ---- destructive technician actions ask first ----------------------------------

def test_clear_all_corrections_asks_first(monkeypatch, tmp_path):
    pending = {"V001": {"listing": "Tools", "size_category_override": "L"}}
    at = _drive(monkeypatch, tmp_path)
    # Seeded after the first pass: a new file's first pass clears pending
    # corrections of any previous file (v34.42/v34.50).
    at.session_state["_pending_overrides"] = pending
    at.run()
    clear = next(b for b in at.button if str(b.label) == "Clear all corrections")
    clear.click()
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["_pending_overrides"], "cleared without confirmation"
    yes = next(b for b in at.button if getattr(b, "key", "") == "_clear_all_yes")
    yes.click()
    at.run()
    assert not at.exception, at.exception
    assert not at.session_state["_pending_overrides"] if "_pending_overrides" in at.session_state else True


def test_deleting_a_row_of_a_saved_set_asks_first(monkeypatch, tmp_path):
    import db as kdb
    db_path = tmp_path / "ux.db"
    conn = kdb.init_db(str(db_path))
    row = {c: "" for c in OVERRIDE_COLUMNS}
    row.update({"code": "V001", "listing": "Tools", "size_category_override": "L"})
    sid = kdb.save_override_set(conn, customer="UxCustomer", site="UxSite",
                                overrides_df=pd.DataFrame([row], columns=OVERRIDE_COLUMNS))
    conn.close()
    at = _drive(monkeypatch, tmp_path, extra_state={"_manage_ovset_open": True})
    delete = next(b for b in at.button if getattr(b, "key", "") == f"_del_row_{sid}_V001")
    delete.click()
    at.run()
    assert not at.exception, at.exception
    conn = kdb.init_db(str(db_path))
    assert len(kdb.override_set_as_dataframe(conn, sid)) == 1, "deleted without confirmation"
    conn.close()
    yes = next(b for b in at.button if getattr(b, "key", "") == f"_del_row_yes_{sid}_V001")
    yes.click()
    at.run()
    assert not at.exception, at.exception
    conn = kdb.init_db(str(db_path))
    assert len(kdb.override_set_as_dataframe(conn, sid)) == 0
    conn.close()


# ---- stale texts are gone ---------------------------------------------------

def test_stale_texts_are_gone():
    page = (REPO / "pages" / "1_Kromi_Planner.py").read_text(encoding="utf-8")
    for stale in ("Save this run when", "./overrides/<Customer>__<Site>/overrides.csv",
                  "same data as PDF", "1/0, or yes/no",
                  "override library for the run's customer and site applies",
                  "File library (default)"):
        assert stale not in page, stale
