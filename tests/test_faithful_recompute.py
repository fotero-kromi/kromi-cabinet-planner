"""Faithful "Load & recompute" (v34.54, audit C9).

A recompute must reproduce the stored run with only the engine changed. It
did not: the PPE sheet, the per-class thresholds, the Program -> supply point
map, the restockable categories, the site, the KTC-ID and the customer label
were not restored; a banner-row file lost its whole column mapping because the
columns were read from row 1; the applied override set was never recorded; and
the save check ignored the build, so after an upgrade the same inputs were
"already archived" and the new result was never stored.
"""
import dataclasses
import json
import re
from io import BytesIO
from pathlib import Path

import pandas as pd

from engine import run_restore as rr
from tests._paths import PLANNER_PAGE


# ---- capture and seed ----------------------------------------------------------------

_STATE = {
    "ks_sheet_tools": "Tools", "ks_sheet_ppe": "PPE", "ks_site": "Werk 2",
    "ks_apply_overrides": False, "adv_thr_active": True,
    "adv_thr_vals": {"drills": 4.0, "mills": 2.5},
    "ks_restock_categories": ["drills", "reamers"],
    "prog_sp::Line A": 1, "prog_sp::Line B": 2,
    "ks_buffer": 10.0, "unrelated": "x",
}


def test_capture_covers_every_recompute_input():
    snap = rr.capture_ui_state(_STATE)
    expected = dict(_STATE)
    expected.pop("unrelated")
    assert snap == expected


def test_seed_round_trips_through_json():
    snap = json.loads(json.dumps(rr.capture_ui_state(_STATE)))
    seed = rr.build_seed(snap, ["Code"], sheet_names=["Tools", "PPE"])
    for key, value in snap.items():
        assert seed[key] == value, key


def test_seed_drops_sheets_the_workbook_does_not_have():
    seed = rr.build_seed({"ks_sheet_tools": "Tools", "ks_sheet_ppe": "Old PPE"}, ["Code"],
                         sheet_names=["Tools"])
    assert seed["ks_sheet_tools"] == "Tools" and "ks_sheet_ppe" not in seed
    seed = rr.build_seed({"ks_sheet_ppe": rr.SHEET_NOT_USED}, ["Code"], sheet_names=["Tools"])
    assert seed["ks_sheet_ppe"] == rr.SHEET_NOT_USED


def test_seed_drops_malformed_structured_values():
    seed = rr.build_seed({"adv_thr_vals": {"drills": "high"}, "prog_sp::X": "two",
                          "ks_restock_categories": "drills"}, ["Code"])
    assert "adv_thr_vals" not in seed and "prog_sp::X" not in seed
    assert "ks_restock_categories" not in seed


def test_restore_summary_names_what_was_not_restored():
    ui = {"cm_code": "Code", "cm_size": "Gone", "ks_buffer": 10.0, "ks_sheet_ppe": "Old"}
    seed = rr.build_seed(ui, ["Code"], sheet_names=["Tools"])
    s = rr.restore_summary(ui, seed)
    assert (s["restored"], s["total"]) == (2, 4)
    assert s["dropped"] == ["cm_size", "ks_sheet_ppe"]


# ---- the save check and the applied override set ------------------------------------------

_PAGE = Path(PLANNER_PAGE).read_text(encoding="utf-8")


def test_save_key_carries_the_build_and_the_classifications():
    m = re.search(r"^_save_key = \((.*?)^\)", _PAGE, re.DOTALL | re.MULTILINE)
    assert m
    expr = m.group(1)
    assert "BUILD" in expr and "_cls_sig" in expr


def test_deleting_an_override_set_keeps_the_runs_that_used_it(tmp_path):
    import db as kdb
    from db.store import get_run
    from engine.overrides import OVERRIDE_COLUMNS
    conn = kdb.init_db(str(tmp_path / "ov.db"))
    row = {c: "" for c in OVERRIDE_COLUMNS}
    row.update({"code": "A1", "listing": "Tools", "size_category_override": "M"})
    sid = kdb.save_override_set(conn, customer="C", site="S",
                                overrides_df=pd.DataFrame([row], columns=OVERRIDE_COLUMNS))
    fid = kdb.upsert_file(conn, sha256="f", content=b"x")
    rid = kdb.insert_run(conn, file_id=fid, applied_override_set_id=sid)
    assert kdb.delete_override_set(conn, sid) is True
    assert get_run(conn, rid)["applied_override_set_id"] is None
    conn.close()


# ---- the page: run, archive, load & recompute --------------------------------------------

def _workbook():
    tools = pd.DataFrame({
        "ItemCode": [f"T{i}" for i in range(6)],
        "ItemName": [f"Bohrer D{i + 3},5" for i in range(6)],
        "Cons16": [(i + 1) * 300.0 for i in range(6)],
        "Line": ["Line A", "Line B"] * 3,
    })
    ppe = pd.DataFrame({"ItemCode": ["P1", "P2"], "ItemName": ["Handschuh Gr 9", "Brille"],
                        "Cons16": [800.0, 400.0], "Line": ["Line A", "Line B"]})
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        tools.to_excel(w, index=False, sheet_name="Tools")
        ppe.to_excel(w, index=False, sheet_name="PPE")
    return bio.getvalue(), list(tools.columns)


def _spy(monkeypatch, captured):
    import engine.plan as ep
    orig = ep.run_plan

    def spy(work, ov, params):
        captured.append(params)
        return orig(work, ov, params)
    monkeypatch.setattr(ep, "run_plan", spy)


def test_load_and_recompute_reproduces_the_run(monkeypatch, tmp_path):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    import db as kdb

    db_path = tmp_path / "rc.db"
    monkeypatch.setenv("KROMI_DB_PATH", str(db_path))
    st.cache_data.clear()
    params = []
    _spy(monkeypatch, params)
    raw, cols = _workbook()

    # 1. The original run, with every hard-to-restore input set.
    seed = rr.build_seed({"cm_code": "ItemCode", "cm_desc1": "ItemName", "cm_cons": "Cons16",
                          "ks_sheet_tools": "Tools"}, cols)
    seed.update({"ks_hide_optional": False, "ks_ai_colmap": False, "_std_special_mapped": False,
                 "ks_n_sp": 2, "adv_thr_active": True,
                 "adv_thr_vals": {c: 1.0 for c in ("drills", "mills")} | {"drills": 3.0},
                 "ks_restock_categories": ["drills"]})
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 0, "bytes": raw, "filename": "input.xlsx", "customer": "RcCustomer",
        "site": "RcSite", "classifications": {}, "override_mode": "none",
        "override_set_id": None}
    at.session_state["_pending_restore"] = seed
    at.run()
    next(s for s in at.selectbox if str(s.label) == "PPE sheet (optional)").select("PPE").run()
    next(s for s in at.selectbox if s.key == "cm_program").select("Line").run()
    next(s for s in at.selectbox if s.key == "prog_sp::Line B").select(2).run()
    next(t for t in at.text_input if t.label == "KTC-ID").input("150").run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception
    original = params[-1]
    assert original.per_class_thresholds and original.restock_categories == ("drills",)

    conn = kdb.init_db(str(db_path))
    run_id = conn.execute("SELECT MAX(run_id) FROM analysis_runs").fetchone()[0]
    run_row = kdb.get_run(conn, run_id)
    assert run_row["ktc_id"] == "150"
    settings = json.loads(run_row["settings_json"])
    assert settings["overrides"] == {"source": "none", "set_id": None}
    conn.close()

    # 2. A fresh session loads the run and recomputes it. The values
    # remembered per file are cleared, so the KTC-ID must come from the run.
    import engine.run_prefs as run_prefs
    monkeypatch.setattr(run_prefs, "DEFAULT_PREFS_PATH", tmp_path / "fresh" / "prefs.json")
    st.cache_data.clear()
    rc = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    rc.run()
    rc.radio(key="_start_mode").set_value("Load a previous run").run()
    rc.selectbox(key="_load_sel").select(run_id).run()
    rc.button(key="_load_recompute_btn").click().run()
    assert not rc.exception, rc.exception
    rc.session_state["_force_run"] = True
    rc.run()
    assert not rc.exception, rc.exception
    banner = " ".join(str(i.value) for i in rc.info)
    assert re.search(r"Restored (\d+) of \1 stored settings", banner), banner
    recomputed = params[-1]
    same = dataclasses.replace(recomputed, stored_classifications=original.stored_classifications)
    assert same == original
    assert next(t for t in rc.text_input if t.label == "KTC-ID").value == "150"
    assert next(s for s in rc.selectbox if str(s.label) == "PPE sheet (optional)").value == "PPE"


def test_recompute_restores_a_banner_row_mapping(monkeypatch, tmp_path):
    """Columns are validated at the run's header row, not at row 1."""
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    import db as kdb

    db_path = tmp_path / "hr.db"
    monkeypatch.setenv("KROMI_DB_PATH", str(db_path))
    st.cache_data.clear()
    # Neutral headers auto-detection cannot guess, so only a restored
    # mapping can pick them.
    body = pd.DataFrame({"Zeile": list(range(1, 6)),
                         "Kennung": [f"H{i}" for i in range(5)],
                         "Text": [f"Fraeser D{i + 4}" for i in range(5)],
                         "Wert": [(i + 2) * 200.0 for i in range(5)]})
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        pd.DataFrame([["Import template"], [""], [""]]).to_excel(
            w, index=False, header=False, sheet_name="Import")
        body.to_excel(w, index=False, sheet_name="Import", startrow=3)
    raw = bio.getvalue()
    seed = rr.build_seed({"cm_code": "Kennung", "cm_desc1": "Text", "cm_cons": "Wert",
                          "ks_sheet_tools": "Import", "ks_header_row": 4}, list(body.columns))
    seed.update({"ks_hide_optional": False, "ks_ai_colmap": False, "_std_special_mapped": False})
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 0, "bytes": raw, "filename": "banner.xlsx", "customer": "HrC",
        "site": "HrS", "classifications": {}, "override_mode": "none", "override_set_id": None}
    at.session_state["_pending_restore"] = seed
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception
    conn = kdb.init_db(str(db_path))
    run_id = conn.execute("SELECT MAX(run_id) FROM analysis_runs").fetchone()[0]
    conn.close()

    st.cache_data.clear()
    rc = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    rc.run()
    rc.radio(key="_start_mode").set_value("Load a previous run").run()
    rc.selectbox(key="_load_sel").select(run_id).run()
    rc.button(key="_load_recompute_btn").click().run()
    assert not rc.exception, rc.exception
    assert rc.selectbox(key="cm_code").value == "Kennung"
    assert rc.selectbox(key="cm_desc1").value == "Text"
    assert rc.selectbox(key="cm_cons").value == "Wert"
