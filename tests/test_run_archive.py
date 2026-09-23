"""Run archive contracts (v34.53, audit C8).

The archive wrote a file's tool records and classifications once, on the first
run of that file, and mapped every later run onto them:

* a later run of the same file with a code the first run did not have (PPE
  sheet added, a different year filter) failed with "Database copy skipped
  (KeyError)" and was never archived;
* a later run's classifications (an AI run after a heuristic one) were never
  stored, so the stored run and the recompute showed run 1's values and the
  snapshot labelled AI results "Heuristic".

Now tool records are added on demand, every run links to the classification
it actually used (a new row when it differs, the existing row when it is the
same, so repeated runs do not grow the table), a recompute reads the run's own
classifications, the file-level reuse picks the newest authoritative answer,
and a technician override is never stored as the classifier's answer.
"""

import os

import pandas as pd
import pytest

from db import store
from db.classification_reuse import classifications_by_code
from db.load_run import reconstruct_work
from db.persist_run import persist_run, summary_rows_from_plans, tools_from_dataframe


def _row(code, size="M", pc="drills", source="Heuristic", model=None, **extra):
    r = {
        "Code": code, "Description": f"tool {code}", "Description_2": "", "SupplierCode": "S",
        "Listing": "Tools", "SystemTyp": "", "Consumption_pcs": 120.0, "PackUnits": 1.0,
        "SizeCategory": size, "ProductCategory": pc,
        "SizeCategory_Source": source, "ProductCategory_Source": source,
        "SizeCategory_AI_Model": model, "ProductCategory_AI_Model": model,
        "ProductCategory_Reason": "", "ProductCategory_Confidence": None,
        "SystemCategory": "KTC", "CabinetType": "Helix", "Spirals_needed": 1,
        "Carousel_stockpiles": 0, "Spiral_capacity": 22, "Monthly_packs": 10.0,
        "Target_packs": 6.6, "SupplyPoint": 1, "SizeIssue": False,
        "SystemCategory_Reason": "", "Override_Applied": False,
    }
    r.update(extra)
    return r


@pytest.fixture()
def conn(tmp_path):
    c = store.init_db(os.path.join(str(tmp_path), "arch.db"))
    yield c
    c.close()


def _persist(conn, rows, sha="same-file", inputs_hash="h"):
    cfg = store.get_active_machine_config(conn)
    work = pd.DataFrame(rows)
    return persist_run(
        conn,
        file={"sha256": sha, "original_filename": "c.xlsx", "content": b"b",
              "byte_size": 1, "sheet_tools": "Tools", "sheet_ppe": None,
              "row_count": len(work), "first_seen_customer": "C", "first_seen_ktc_id": "191"},
        run={"machine_config_id": cfg["config_id"], "build_version": "t", "customer": "C",
             "site": "S", "ktc_id": "191", "calc_mode": "Combined", "operational_mode": "",
             "max_carousels": None, "supply_points": 1, "sp_mode": "replicate",
             "settings_json": "{}", "applied_override_set_id": None, "status": "completed"},
        tools=tools_from_dataframe(work),
        plan_rows=summary_rows_from_plans([], {}),
        rebalance_events=[],
        execution={"build_version": "t", "rows_processed": len(work), "rebalance_moves": 0,
                   "cabinets_saved": 0, "size_issues_found": 0, "grand_total_cabs": 0,
                   "inputs_hash": inputs_hash},
    )


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---- a later run with new codes is archived ------------------------------------------

def test_later_run_with_a_new_code_is_archived(conn):
    _persist(conn, [_row("A"), _row("B")])
    r2 = _persist(conn, [_row("A"), _row("B"), _row("PPE1", pc="ppe", Listing="PPE")])
    assert _count(conn, "tool_records") == 3
    snap = reconstruct_work(conn, r2)
    assert list(snap["Code"]) == ["A", "B", "PPE1"]
    assert snap.set_index("Code").loc["PPE1", "Listing"] == "PPE"
    assert classifications_by_code(conn, run_id=r2)["PPE1"]["product_category"] == "ppe"


def test_new_tool_records_continue_the_line_numbers(conn):
    _persist(conn, [_row("A"), _row("B")])
    _persist(conn, [_row("C"), _row("A")])
    lines = dict(conn.execute("SELECT code, line_no FROM tool_records").fetchall())
    assert lines == {"A": 1, "B": 2, "C": 3}


# ---- every run keeps its own classifications -----------------------------------------------

def test_each_run_reads_its_own_classifications(conn):
    r1 = _persist(conn, [_row("A", size="L", source="Heuristic")])
    r2 = _persist(conn, [_row("A", size="M", pc="reamers", source="AI", model="gpt-x")])
    one = classifications_by_code(conn, run_id=r1)["A"]
    two = classifications_by_code(conn, run_id=r2)["A"]
    assert (one["size_category"], one["product_category"], one["source"]) == ("L", "drills", "Heuristic")
    assert (two["size_category"], two["product_category"], two["source"]) == ("M", "reamers", "AI")
    assert two["model"] == "gpt-x"
    file_id = store.get_run(conn, r2)["file_id"]
    assert classifications_by_code(conn, file_id=file_id)["A"]["source"] == "AI"   # newest


def test_snapshot_labels_each_run_with_its_own_source(conn):
    r1 = _persist(conn, [_row("A", source="Heuristic")])
    r2 = _persist(conn, [_row("A", size="S", source="AI", model="gpt-x")])
    assert reconstruct_work(conn, r1).loc[0, "SizeCategory_Source"] == "Heuristic"
    assert reconstruct_work(conn, r2).loc[0, "SizeCategory_Source"] == "AI"


def test_identical_runs_share_classification_rows(conn):
    _persist(conn, [_row("A"), _row("B")])
    _persist(conn, [_row("A"), _row("B")])
    _persist(conn, [_row("B"), _row("A")])
    assert _count(conn, "tool_classifications") == 2


def test_a_newer_answer_supersedes_the_previous_one(conn):
    _persist(conn, [_row("A", size="L")])
    _persist(conn, [_row("A", size="M", source="AI", model="gpt-x")])
    rows = conn.execute(
        "SELECT classification_id, size_category, superseded_by FROM tool_classifications "
        "ORDER BY classification_id").fetchall()
    assert [r["size_category"] for r in rows] == ["L", "M"]
    assert rows[0]["superseded_by"] == rows[1]["classification_id"]
    assert rows[1]["superseded_by"] is None


def test_recompute_of_an_old_run_links_to_its_rows(conn):
    r1 = _persist(conn, [_row("A", size="L")])
    _persist(conn, [_row("A", size="M", source="AI", model="gpt-x")])
    # A recompute of run 1 reapplies run 1's stored values (marked as reused).
    r3 = _persist(conn, [_row("A", size="L", source="Reused from stored run")])
    assert _count(conn, "tool_classifications") == 2
    assert classifications_by_code(conn, run_id=r3) == classifications_by_code(conn, run_id=r1)
    file_id = store.get_run(conn, r3)["file_id"]
    assert classifications_by_code(conn, file_id=file_id)["A"]["source"] == "AI"


def test_file_reuse_can_ask_for_the_newest_authoritative_answer(conn):
    r1 = _persist(conn, [_row("A", size="M", source="AI", model="gpt-x"), _row("B")])
    _persist(conn, [_row("A", size="L", source="Heuristic"), _row("B")])
    file_id = store.get_run(conn, r1)["file_id"]
    got = classifications_by_code(conn, file_id=file_id, sources=("ai", "manual"))
    assert set(got) == {"A"}
    assert got["A"]["size_category"] == "M"


def test_legacy_run_without_links_falls_back_to_the_file(conn):
    r1 = _persist(conn, [_row("A")])
    conn.execute("UPDATE cabinet_calculations SET classification_id = NULL WHERE run_id = ?", (r1,))
    conn.commit()
    assert classifications_by_code(conn, run_id=r1)["A"]["size_category"] == "M"


# ---- overrides are not the classifier's answer ----------------------------------------------

def test_overridden_fields_are_not_stored_as_classifications(conn):
    ov = _row("A", size="XL", pc="holders", Override_Applied=True,
              SizeCategory_Source="Override", ProductCategory_Source="Override",
              ProductCategory_PreOverride="drills")
    part = _row("B", size="S", pc="taps", source="Heuristic", Override_Applied=True,
                ProductCategory_Source="Override", ProductCategory_PreOverride="mills")
    r1 = _persist(conn, [ov, part])
    cls = classifications_by_code(conn, run_id=r1)
    assert cls["A"]["size_category"] is None            # re-derived on a recompute
    assert cls["A"]["product_category"] == "drills"     # the classifier's answer
    assert cls["B"]["size_category"] == "S" and cls["B"]["product_category"] == "mills"
    assert cls["B"]["source"] == "Heuristic"
    snap = reconstruct_work(conn, r1).set_index("Code")
    # The delivered result still shows what the run used.
    assert (snap.loc["A", "SizeCategory"], snap.loc["A", "ProductCategory"]) == ("XL", "holders")
    assert snap.loc["B", "ProductCategory"] == "taps"


# ---- the page: a second run of the same file with the PPE sheet added is saved ------------

def _two_sheet_workbook():
    from io import BytesIO
    tools = pd.DataFrame({"ItemCode": [f"T{i}" for i in range(5)],
                          "ItemName": [f"Bohrer D{i + 3},5" for i in range(5)],
                          "Cons16": [(i + 1) * 400.0 for i in range(5)]})
    ppe = pd.DataFrame({"ItemCode": ["P1", "P2"], "ItemName": ["Handschuh Gr 9", "Brille klar"],
                        "Cons16": [900.0, 500.0]})
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        tools.to_excel(w, index=False, sheet_name="Tools")
        ppe.to_excel(w, index=False, sheet_name="PPE")
    return bio.getvalue(), list(tools.columns)


def test_second_run_with_the_ppe_sheet_added_is_saved(monkeypatch, tmp_path):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    from engine.run_restore import build_seed
    from tests._paths import PLANNER_PAGE

    db_path = tmp_path / "page.db"
    monkeypatch.setenv("KROMI_DB_PATH", str(db_path))
    st.cache_data.clear()
    raw, cols = _two_sheet_workbook()
    seed = build_seed({"cm_code": "ItemCode", "cm_desc1": "ItemName", "cm_cons": "Cons16",
                       "ks_sheet_tools": "Tools"}, cols)
    seed.update({"ks_hide_optional": False, "ks_ai_colmap": False, "_std_special_mapped": False})
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": raw, "filename": "input.xlsx", "customer": "ArcCustomer",
        "site": "ArcSite", "classifications": {}, "override_set_id": None}
    at.session_state["_pending_restore"] = seed
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception
    next(s for s in at.selectbox if str(s.label) == "PPE sheet (optional)").select("PPE").run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception
    captions = " ".join(str(c.value) for c in at.caption)
    assert "Database copy skipped" not in captions, captions
    import db as kdb
    conn = kdb.init_db(str(db_path))
    try:
        assert _count(conn, "analysis_runs") == 2
        codes = {r[0] for r in conn.execute("SELECT code FROM tool_records").fetchall()}
        assert {"P1", "P2"} <= codes
    finally:
        conn.close()
