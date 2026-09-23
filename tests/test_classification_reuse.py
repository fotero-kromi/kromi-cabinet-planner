"""R2 tests for classification reuse.

The reuse must key on tool code, never row position, so applying stored
classifications to a different row set (reordered, with rows added or dropped)
lands each value on the right code. The critical test uses distinct sizes per
code so any positional misalignment would be caught.
"""

import os

import pandas as pd
import pytest

from db import store
from db.persist_run import persist_run, tools_from_dataframe, summary_rows_from_plans
from db.classification_reuse import (
    classifications_by_code, apply_stored_classifications,
)


def _work_three_distinct_sizes():
    base = {
        "Description_2": "", "SupplierCode": "S", "Listing": "Tools", "SystemTyp": "",
        "PackUnits": 1.0, "ProductCategory_Source": "ai", "SizeCategory_Source": "ai",
        "SizeCategory_AI_Model": "m", "ProductCategory_AI_Model": "m",
        "ProductCategory_Reason": "", "ProductCategory_Confidence": None,
        "SystemCategory": "KTC", "CabinetType": "Helix", "Carousel_stockpiles": 0,
        "Spiral_capacity": 28, "Monthly_packs": 1.0, "Target_packs": 1.0,
        "Consumption_pcs": 10.0, "SupplyPoint": 1, "SizeIssue": False,
        "SystemCategory_Reason": "", "Override_Applied": False, "Spirals_needed": 1,
    }
    # Distinct size and product per code so a positional mix-up cannot pass.
    return pd.DataFrame([
        {**base, "Code": "A", "Description": "alpha", "SizeCategory": "S",   "ProductCategory": "drills"},
        {**base, "Code": "B", "Description": "bravo", "SizeCategory": "L",   "ProductCategory": "holders"},
        {**base, "Code": "C", "Description": "charl", "SizeCategory": "XXL", "ProductCategory": "bodies"},
    ])


@pytest.fixture()
def conn(tmp_path):
    c = store.init_db(os.path.join(str(tmp_path), "reuse.db"))
    yield c
    c.close()


def _persist(conn, work):
    cfg = store.get_active_machine_config(conn)
    return persist_run(
        conn,
        file={"sha256": "sha-reuse", "original_filename": "c.xlsx", "content": b"b",
              "byte_size": 1, "sheet_tools": "Tools", "sheet_ppe": None, "row_count": len(work),
              "first_seen_customer": "PlantA", "first_seen_ktc_id": "191"},
        run={"machine_config_id": cfg["config_id"], "build_version": "v33.50", "customer": "PlantA",
             "site": "P1", "ktc_id": "191", "calc_mode": "Combined", "operational_mode": "",
             "max_carousels": None, "supply_points": 1, "sp_mode": "single",
             "settings_json": "{}", "applied_override_set_id": None, "status": "completed"},
        tools=tools_from_dataframe(work),
        plan_rows=summary_rows_from_plans([], {}),
        rebalance_events=[], execution={"build_version": "v33.50", "rows_processed": len(work),
            "rebalance_moves": 0, "cabinets_saved": 0, "size_issues_found": 0,
            "grand_total_cabs": 0, "inputs_hash": "h"},
    )


# --- lookup ---

def test_lookup_by_run_id(conn):
    run_id = _persist(conn, _work_three_distinct_sizes())
    lookup = classifications_by_code(conn, run_id=run_id)
    assert lookup["A"]["size_category"] == "S"
    assert lookup["B"]["size_category"] == "L"
    assert lookup["C"]["size_category"] == "XXL"
    assert lookup["A"]["product_category"] == "drills"
    assert lookup["A"]["source"] == "ai"
    assert lookup["A"]["model"] == "m"


def test_lookup_by_file_id_matches_run_id(conn):
    run_id = _persist(conn, _work_three_distinct_sizes())
    file_id = store.get_run(conn, run_id)["file_id"]
    by_run = classifications_by_code(conn, run_id=run_id)
    by_file = classifications_by_code(conn, file_id=file_id)
    assert by_run == by_file


def test_lookup_missing_run_is_empty(conn):
    assert classifications_by_code(conn, run_id=999999) == {}


def test_lookup_requires_an_id(conn):
    with pytest.raises(ValueError):
        classifications_by_code(conn)


def test_newest_classification_wins(conn):
    run_id = _persist(conn, _work_three_distinct_sizes())
    file_id = store.get_run(conn, run_id)["file_id"]
    tr = conn.execute(
        "SELECT tool_record_id FROM tool_records WHERE file_id = ? AND code = 'A'", (file_id,)
    ).fetchone()
    # A newer classification for code A revises its size from S to M.
    store.insert_row(conn, "tool_classifications", {
        "file_id": file_id, "tool_record_id": tr["tool_record_id"],
        "size_category": "M", "product_category": "drills", "source": "manual",
        "model": None, "prompt_version": None, "reason": "corrected",
        "confidence": None, "classified_at": "2026-02-01T00:00:00+00:00",
    })
    lookup = classifications_by_code(conn, file_id=file_id)
    assert lookup["A"]["size_category"] == "M"      # newest wins for the file
    assert lookup["A"]["source"] == "manual"
    # The run keeps the answer it used (v34.53, audit C8): a recompute
    # reproduces that run, not whatever the file saw later.
    assert classifications_by_code(conn, run_id=run_id)["A"]["size_category"] == "S"


# --- the critical R2 test: alignment by code, not position ---

def test_apply_aligns_by_code_under_reorder_add_drop(conn):
    run_id = _persist(conn, _work_three_distinct_sizes())
    lookup = classifications_by_code(conn, run_id=run_id)

    # A recompute frame with the rows reordered, an extra code D (no stored
    # classification), and starting size values that are deliberately wrong.
    df = pd.DataFrame([
        {"Code": "C", "SizeCategory": "?", "ProductCategory": "?"},
        {"Code": "A", "SizeCategory": "?", "ProductCategory": "?"},
        {"Code": "D", "SizeCategory": "keep", "ProductCategory": "keep"},
        {"Code": "B", "SizeCategory": "?", "ProductCategory": "?"},
    ])
    out, hits, misses = apply_stored_classifications(df, lookup)

    by_code = {r["Code"]: r for r in out.to_dict("records")}
    # Each code gets ITS OWN stored value despite the reordering.
    assert by_code["C"]["SizeCategory"] == "XXL"
    assert by_code["A"]["SizeCategory"] == "S"
    assert by_code["B"]["SizeCategory"] == "L"
    assert by_code["C"]["ProductCategory"] == "bodies"
    assert by_code["A"]["ProductCategory"] == "drills"
    # The unknown code is left untouched and reported as a miss.
    assert by_code["D"]["SizeCategory"] == "keep"
    assert set(hits) == {"A", "B", "C"}
    assert misses == ["D"]


def test_apply_with_dropped_rows(conn):
    run_id = _persist(conn, _work_three_distinct_sizes())
    lookup = classifications_by_code(conn, run_id=run_id)
    # Only two of the three codes present; both should resolve correctly.
    df = pd.DataFrame([
        {"Code": "A", "SizeCategory": "?", "ProductCategory": "?"},
        {"Code": "C", "SizeCategory": "?", "ProductCategory": "?"},
    ])
    out, hits, misses = apply_stored_classifications(df, lookup)
    by_code = {r["Code"]: r for r in out.to_dict("records")}
    assert by_code["A"]["SizeCategory"] == "S"
    assert by_code["C"]["SizeCategory"] == "XXL"
    assert set(hits) == {"A", "C"}
    assert misses == []


def test_apply_without_code_column_reports_all_miss(conn):
    df = pd.DataFrame([{"NotCode": "x", "SizeCategory": "?"}])
    out, hits, misses = apply_stored_classifications(df, {"A": {"size_category": "S"}})
    assert hits == []
    assert len(misses) == 1
