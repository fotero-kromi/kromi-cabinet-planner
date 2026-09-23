"""Phase 1 dual-write tests.

Cover the write itself, not the page: a completed run persists every table with
the right counts, the stored rows reconstruct the computed result faithfully,
re-running the same file reuses its records, and a failure rolls the whole run
back rather than leaving a partial one.
"""

import os

import pandas as pd
import pytest

import db
from db import store
from db.persist_run import (
    persist_run, tools_from_dataframe, summary_rows_from_plans, rebalance_events_from_audit,
)


def _work_df():
    """A small work frame mirroring the real columns the extractor reads."""
    return pd.DataFrame([
        {
            "Code": "A100", "Description": "drill", "Description_2": "", "SupplierCode": "S1",
            "Listing": "Tools", "SystemTyp": "", "Consumption_pcs": 320.0, "PackUnits": 10.0,
            "SizeCategory": "S", "ProductCategory": "drills",
            "SizeCategory_Source": "ai", "ProductCategory_Source": "ai",
            "SizeCategory_AI_Model": "gpt-x", "ProductCategory_AI_Model": "gpt-x",
            "ProductCategory_Reason": "twist drill", "ProductCategory_Confidence": 0.9,
            "SystemCategory": "KTC", "CabinetType": "Helix", "Spirals_needed": 3,
            "Carousel_stockpiles": 0, "Spiral_capacity": 28, "Monthly_packs": 8.0,
            "Target_packs": 8.0, "SupplyPoint": 1, "SizeIssue": False,
            "SystemCategory_Reason": "", "Override_Applied": False,
        },
        {
            "Code": "B200", "Description": "grooving", "Description_2": "x", "SupplierCode": "S2",
            "Listing": "Tools", "SystemTyp": "", "Consumption_pcs": 16.0, "PackUnits": 1.0,
            "SizeCategory": "L", "ProductCategory": "holders",
            "SizeCategory_Source": "heuristic", "ProductCategory_Source": "heuristic",
            "SizeCategory_AI_Model": None, "ProductCategory_AI_Model": None,
            "ProductCategory_Reason": "", "ProductCategory_Confidence": None,
            "SystemCategory": "KTC", "CabinetType": "Carousel", "Spirals_needed": 0,
            "Carousel_stockpiles": 3, "Spiral_capacity": None, "Monthly_packs": 1.0,
            "Target_packs": 1.0, "SupplyPoint": 1, "SizeIssue": True,
            "SystemCategory_Reason": "L forces a near-empty Carousel", "Override_Applied": False,
        },
        {
            "Code": "C300", "Description": "big body", "Description_2": "", "SupplierCode": "S3",
            "Listing": "Tools", "SystemTyp": "LOCKER", "Consumption_pcs": 16.0, "PackUnits": 1.0,
            "SizeCategory": "XXL", "ProductCategory": "bodies",
            "SizeCategory_Source": "manual", "ProductCategory_Source": "manual",
            "SizeCategory_AI_Model": None, "ProductCategory_AI_Model": None,
            "ProductCategory_Reason": "", "ProductCategory_Confidence": None,
            "SystemCategory": "KTC", "CabinetType": "Locker A", "Spirals_needed": 0,
            "Carousel_stockpiles": 0, "Spiral_capacity": None, "Monthly_packs": 1.0,
            "Target_packs": 1.0, "SupplyPoint": 1, "SizeIssue": False,
            "SystemCategory_Reason": "", "Override_Applied": True,
        },
    ])


def _bucket_plans():
    return [(
        "Tools @ SP 1",
        {"helix_cabs": 1, "car_cabs": 1, "cabA": 1, "cabB": 0, "cabC": 0,
         "total_cabs": 3, "total_spirals": 3, "car_slots": 3,
         "ktc_count": 3, "kanban_count": 0},
    )]


def _grand():
    return {"helix_cabs": 1, "car_cabs": 1, "cabA": 1, "cabB": 0, "cabC": 0,
            "total_cabs": 3, "total_spirals": 3, "car_slots": 3,
            "ktc_count": 3, "kanban_count": 0}


def _audit():
    return [{
        "cabinets_before": 2, "cabinets_after": 1, "bucket": "Tools @ SP 1",
        "items_moved": [{"code": "A100", "from_cabinet": "Carousel", "to_cabinet": "Helix"}],
    }]


def _file(sha="sha-1"):
    return {"sha256": sha, "original_filename": "cat.xlsx", "content": b"workbook-bytes",
            "byte_size": 14, "sheet_tools": "Tools", "sheet_ppe": None, "row_count": 3,
            "first_seen_customer": "PlantA", "first_seen_ktc_id": "191"}


def _run(cfg_id):
    return {"machine_config_id": cfg_id, "build_version": "v33.46", "customer": "PlantA",
            "site": "P1", "ktc_id": "191", "calc_mode": "Combined", "operational_mode": "",
            "max_carousels": None, "supply_points": 1, "sp_mode": "single",
            "settings_json": '{"buffer": 15}', "applied_override_set_id": None,
            "status": "completed", "notes": None}


def _execution():
    return {"build_version": "v33.46", "duration_ms": 120, "rows_processed": 3,
            "rebalance_moves": 1, "cabinets_saved": 1, "size_issues_found": 1,
            "grand_total_cabs": 3, "inputs_hash": "h1"}


@pytest.fixture()
def conn(tmp_path):
    c = store.init_db(os.path.join(str(tmp_path), "p1.db"))
    yield c
    c.close()


def _persist(conn, sha="sha-1"):
    cfg = store.get_active_machine_config(conn)
    tools = tools_from_dataframe(_work_df())
    plan_rows = summary_rows_from_plans(_bucket_plans(), _grand())
    events = rebalance_events_from_audit(_audit())
    return persist_run(
        conn, file=_file(sha), run=_run(cfg["config_id"]),
        tools=tools, plan_rows=plan_rows, rebalance_events=events, execution=_execution(),
    )


# --- migration 002 ---

def test_migration_002_applied(conn):
    assert store.current_schema_version(conn) == 4
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(cabinet_calculations)")]
    assert "size_category" in cols
    assert "product_category" in cols


def test_migration_004_applied(conn):
    names = [r["name"] for r in conn.execute(
        "PRAGMA index_list(engine_executions)")]
    assert "idx_engine_executions_inputs_hash" in names


def test_migration_003_applied(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(cabinet_calculations)")]
    assert "restockable" in cols
    assert "restock_slots" in cols


# --- population ---

def test_persist_populates_all_tables(conn):
    run_id = _persist(conn)

    def count(table, where="", params=()):
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table} {where}", params).fetchone()["n"]

    assert count("uploaded_files") == 1
    assert count("tool_records") == 3
    assert count("tool_classifications") == 3
    assert count("analysis_runs") == 1
    assert count("cabinet_calculations", "WHERE run_id = ?", (run_id,)) == 3
    # one summary row per bucket plus grand total
    assert count("cabinet_plan_summary", "WHERE run_id = ?", (run_id,)) == 2
    assert count("rebalance_events", "WHERE run_id = ?", (run_id,)) == 1
    assert count("engine_executions", "WHERE run_id = ?", (run_id,)) == 1
    # one validation row for the single size-issue tool
    assert count("validation_results", "WHERE run_id = ?", (run_id,)) == 1


# --- fidelity: stored rows reconstruct the computed result ---

def test_stored_calculations_match_computed(conn):
    run_id = _persist(conn)
    rows = conn.execute(
        "SELECT tr.code AS code, cc.cabinet_type, cc.system_category, cc.spirals_needed, "
        "cc.carousel_stockpiles, cc.size_category, cc.size_issue "
        "FROM cabinet_calculations cc JOIN tool_records tr "
        "ON tr.tool_record_id = cc.tool_record_id "
        "WHERE cc.run_id = ? ORDER BY tr.code", (run_id,),
    ).fetchall()
    got = {r["code"]: r for r in rows}

    assert got["A100"]["cabinet_type"] == "Helix"
    assert got["A100"]["spirals_needed"] == 3
    assert got["A100"]["size_category"] == "S"
    assert got["A100"]["size_issue"] == 0

    assert got["B200"]["cabinet_type"] == "Carousel"
    assert got["B200"]["carousel_stockpiles"] == 3
    assert got["B200"]["size_category"] == "L"
    assert got["B200"]["size_issue"] == 1  # the flagged tool

    assert got["C300"]["cabinet_type"] == "Locker A"
    assert got["C300"]["size_category"] == "XXL"


def test_plan_summary_matches_grand_total(conn):
    run_id = _persist(conn)
    grand = conn.execute(
        "SELECT * FROM cabinet_plan_summary WHERE run_id = ? AND bucket_label = 'Grand total'",
        (run_id,),
    ).fetchone()
    assert grand["helix_cabs"] == 1
    assert grand["carousel_cabs"] == 1
    assert grand["locker_a"] == 1
    assert grand["total_cabs"] == 3
    assert grand["total_spirals"] == 3


def test_rebalance_event_flattened(conn):
    run_id = _persist(conn)
    ev = conn.execute(
        "SELECT * FROM rebalance_events WHERE run_id = ?", (run_id,)
    ).fetchone()
    assert ev["item_code"] == "A100"
    assert ev["from_cabinet"] == "Carousel"
    assert ev["to_cabinet"] == "Helix"
    assert ev["cabinets_before"] == 2
    assert ev["cabinets_after"] == 1


def test_classification_carries_source_and_reason(conn):
    _persist(conn)
    row = conn.execute(
        "SELECT c.* FROM tool_classifications c JOIN tool_records tr "
        "ON tr.tool_record_id = c.tool_record_id WHERE tr.code = 'A100'"
    ).fetchone()
    assert row["source"] == "ai"
    assert row["model"] == "gpt-x"
    assert row["reason"] == "twist drill"
    assert abs(row["confidence"] - 0.9) < 1e-9


# --- dedup: re-running the same file reuses its records ---

def test_same_file_reused_across_runs(conn):
    r1 = _persist(conn, sha="same")
    r2 = _persist(conn, sha="same")
    assert r1 != r2
    # one file, one set of tool_records and classifications, two runs and two calc sets
    assert conn.execute("SELECT COUNT(*) AS n FROM uploaded_files").fetchone()["n"] == 1
    assert conn.execute("SELECT COUNT(*) AS n FROM tool_records").fetchone()["n"] == 3
    assert conn.execute("SELECT COUNT(*) AS n FROM tool_classifications").fetchone()["n"] == 3
    assert conn.execute("SELECT COUNT(*) AS n FROM analysis_runs").fetchone()["n"] == 2
    assert conn.execute("SELECT COUNT(*) AS n FROM cabinet_calculations").fetchone()["n"] == 6


def test_different_files_kept_separate(conn):
    _persist(conn, sha="file-a")
    _persist(conn, sha="file-b")
    assert conn.execute("SELECT COUNT(*) AS n FROM uploaded_files").fetchone()["n"] == 2
    assert conn.execute("SELECT COUNT(*) AS n FROM tool_records").fetchone()["n"] == 6


# --- atomicity: a failure rolls the whole run back ---

def test_failed_persist_rolls_back(conn):
    cfg = store.get_active_machine_config(conn)
    tools = tools_from_dataframe(_work_df())
    # A plan row with a column that does not exist forces the summary insert to
    # fail after the run and calculations were already inserted in the same
    # transaction. The whole run must roll back.
    bad_plan = [{"bucket_label": "x", "nonexistent_column": 1}]
    with pytest.raises(Exception):
        persist_run(
            conn, file=_file("rollback"), run=_run(cfg["config_id"]),
            tools=tools, plan_rows=bad_plan, rebalance_events=[], execution=_execution(),
        )
    # Nothing from the failed run survives.
    assert conn.execute("SELECT COUNT(*) AS n FROM analysis_runs").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM cabinet_calculations").fetchone()["n"] == 0
    # The file insert is part of the same transaction, so it rolls back too.
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM uploaded_files WHERE sha256 = 'rollback'"
    ).fetchone()["n"] == 0
