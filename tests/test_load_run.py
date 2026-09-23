"""Phase 3 read-back: the golden round-trip fidelity gate.

The plain-reload promise is that a stored run reconstructs as the exact result it
delivered. These tests persist a run, read it back, and assert every stored
field of every row matches, the plans and grand total match, and the split case
(one tool across two supply points) keeps its per-row values. This gate must
pass before any UI is built on the read-back layer.
"""

import math
import os

import pandas as pd
import pytest

from db import store
from db.persist_run import (
    persist_run, tools_from_dataframe, summary_rows_from_plans,
)
from db.load_run import (
    load_run_snapshot, list_runs_for_picker, _SNAPSHOT_FIELDS, _coerce,
)


def _golden_work():
    """Diverse rows with distinct codes: Helix, Carousel (size issue, null
    capacity), Locker (override applied). Size/Product classification variants
    are set consistently so the stored value is unambiguous."""
    base = {
        "SizeCategory_Source": "ai", "ProductCategory_Source": "ai",
        "SizeCategory_AI_Model": "gpt-x", "ProductCategory_AI_Model": "gpt-x",
    }
    return pd.DataFrame([
        {**base,
         "Code": "A100", "Description": "drill", "Description_2": "5mm", "SupplierCode": "S1",
         "Listing": "Tools", "SystemTyp": "", "PackUnits": 10.0,
         "SizeCategory": "S", "ProductCategory": "drills",
         "ProductCategory_Reason": "twist drill", "ProductCategory_Confidence": 0.92,
         "SystemCategory": "KTC", "CabinetType": "Helix", "Spirals_needed": 3,
         "Carousel_stockpiles": 0, "Spiral_capacity": 28, "Monthly_packs": 8.0,
         "Restockable": 1, "Restock_slots": 1,
         "Target_packs": 8.0, "Consumption_pcs": 320.0, "SupplyPoint": 1,
         "SizeIssue": False, "SystemCategory_Reason": "", "Override_Applied": False},
        {**base,
         "Code": "B200", "Description": "grooving insert", "Description_2": "", "SupplierCode": "S2",
         "Listing": "Tools", "SystemTyp": "", "PackUnits": 1.0,
         "SizeCategory": "L", "ProductCategory": "holders",
         "ProductCategory_Reason": "boring bar", "ProductCategory_Confidence": 0.4,
         "SystemCategory": "KTC", "CabinetType": "Carousel", "Spirals_needed": 0,
         "Carousel_stockpiles": 3, "Spiral_capacity": None, "Monthly_packs": 1.0,
         "Restockable": 0, "Restock_slots": 0,
         "Target_packs": 1.0, "Consumption_pcs": 16.0, "SupplyPoint": 1,
         "SizeIssue": True, "SystemCategory_Reason": "L forces a near-empty Carousel",
         "Override_Applied": False},
        {**base,
         "Code": "C300", "Description": "tool body", "Description_2": "", "SupplierCode": "S3",
         "Listing": "Tools", "SystemTyp": "LOCKER", "PackUnits": 1.0,
         "SizeCategory": "XXL", "ProductCategory": "bodies",
         "ProductCategory_Reason": "", "ProductCategory_Confidence": None,
         "SystemCategory": "KTC", "CabinetType": "Locker A", "Spirals_needed": 0,
         "Carousel_stockpiles": 0, "Spiral_capacity": None, "Monthly_packs": 2.0,
         "Restockable": 0, "Restock_slots": 0,
         "Target_packs": 2.0, "Consumption_pcs": 24.0, "SupplyPoint": 1,
         "SizeIssue": False, "SystemCategory_Reason": "", "Override_Applied": True},
    ])


def _plans():
    bp = [(
        "Tools @ SP 1",
        {"helix_cabs": 1, "car_cabs": 1, "cabA": 1, "cabB": 0, "cabC": 0,
         "total_cabs": 3, "total_spirals": 3, "car_slots": 3, "ktc_count": 3, "kanban_count": 0},
    )]
    grand = {"helix_cabs": 1, "car_cabs": 1, "cabA": 1, "cabB": 0, "cabC": 0,
             "total_cabs": 3, "total_spirals": 3, "car_slots": 3, "ktc_count": 3, "kanban_count": 0}
    return bp, grand


@pytest.fixture()
def conn(tmp_path):
    c = store.init_db(os.path.join(str(tmp_path), "load.db"))
    yield c
    c.close()


def _persist(conn, work, bp, grand, build="v33.47", customer="PlantA", site="P1"):
    cfg = store.get_active_machine_config(conn)
    return persist_run(
        conn,
        file={"sha256": f"sha-{customer}-{site}", "original_filename": "cat.xlsx",
              "content": b"bytes", "byte_size": 5, "sheet_tools": "Tools", "sheet_ppe": None,
              "row_count": len(work), "first_seen_customer": customer, "first_seen_ktc_id": "191"},
        run={"machine_config_id": cfg["config_id"], "build_version": build, "customer": customer,
             "site": site, "ktc_id": "191", "calc_mode": "Combined", "operational_mode": "",
             "max_carousels": None, "supply_points": 1, "sp_mode": "single",
             "settings_json": "{}", "applied_override_set_id": None, "status": "completed"},
        tools=tools_from_dataframe(work),
        plan_rows=summary_rows_from_plans(bp, grand),
        rebalance_events=[], execution={"build_version": build, "rows_processed": len(work),
            "rebalance_moves": 0, "cabinets_saved": 0, "size_issues_found": 0,
            "grand_total_cabs": grand["total_cabs"], "inputs_hash": "h"},
    )


def _norm(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def _assert_rows_match(orig: pd.DataFrame, recon: pd.DataFrame):
    assert len(recon) == len(orig)
    orig_recs = orig.to_dict("records")
    recon_recs = recon.to_dict("records")
    for o, r in zip(orig_recs, recon_recs):
        for alias, col, kind in _SNAPSHOT_FIELDS:
            exp = _coerce(_norm(o.get(col)), kind)
            got = _coerce(_norm(r.get(col)), kind)
            if kind == "float":
                if exp is None:
                    assert got is None, f"{col}: expected None, got {got!r}"
                else:
                    assert got is not None and abs(got - exp) < 1e-9, f"{col}: {got!r} != {exp!r}"
            else:
                assert got == exp, f"{col}: {got!r} != {exp!r}"


# --- the gate ---

def test_golden_round_trip_work(conn):
    work = _golden_work()
    bp, grand = _plans()
    run_id = _persist(conn, work, bp, grand)
    snap = load_run_snapshot(conn, run_id)
    assert snap is not None
    _assert_rows_match(work, snap["work"])


def test_golden_round_trip_plans(conn):
    work = _golden_work()
    bp, grand = _plans()
    run_id = _persist(conn, work, bp, grand)
    snap = load_run_snapshot(conn, run_id)
    assert snap["bucket_plans"] == bp
    assert snap["grand"] == grand


def test_snapshot_metadata(conn):
    work = _golden_work()
    bp, grand = _plans()
    run_id = _persist(conn, work, bp, grand, build="v33.47", customer="PlantA", site="P1")
    snap = load_run_snapshot(conn, run_id)
    assert snap["build_version"] == "v33.47"
    assert snap["customer"] == "PlantA"
    assert snap["site"] == "P1"
    assert snap["filename"] == "cat.xlsx"
    assert snap["status"] == "completed"


# --- split case: one tool across two supply points keeps per-row values ---

def test_split_rows_keep_per_row_values(conn):
    base = {
        "SizeCategory_Source": "ai", "ProductCategory_Source": "ai",
        "SizeCategory_AI_Model": "m", "ProductCategory_AI_Model": "m",
        "ProductCategory_Reason": "", "ProductCategory_Confidence": None,
        "Code": "DUP", "Description": "shared tool", "Description_2": "", "SupplierCode": "S",
        "Listing": "Tools", "SystemTyp": "", "PackUnits": 5.0,
        "SizeCategory": "S", "ProductCategory": "drills", "SystemCategory": "KTC",
        "CabinetType": "Helix", "Carousel_stockpiles": 0, "Spiral_capacity": 28,
        "SizeIssue": False, "SystemCategory_Reason": "", "Override_Applied": False,
    }
    # Same code, two supply points, different per-row consumption and spiral counts.
    work = pd.DataFrame([
        {**base, "SupplyPoint": 1, "Consumption_pcs": 200.0, "Monthly_packs": 5.0,
         "Target_packs": 5.0, "Spirals_needed": 2},
        {**base, "SupplyPoint": 2, "Consumption_pcs": 80.0, "Monthly_packs": 2.0,
         "Target_packs": 2.0, "Spirals_needed": 1},
    ])
    bp, grand = _plans()
    run_id = _persist(conn, work, bp, grand)
    snap = load_run_snapshot(conn, run_id)
    recon = snap["work"]
    assert len(recon) == 2
    # one shared tool record, two calculations
    assert conn.execute("SELECT COUNT(*) AS n FROM tool_records").fetchone()["n"] == 1
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM cabinet_calculations WHERE run_id = ?", (run_id,)
    ).fetchone()["n"] == 2
    # per-row values preserved despite the shared record
    rows = recon.sort_values("SupplyPoint").to_dict("records")
    assert rows[0]["SupplyPoint"] == 1 and rows[0]["Consumption_pcs"] == 200.0
    assert rows[0]["Spirals_needed"] == 2
    assert rows[1]["SupplyPoint"] == 2 and rows[1]["Consumption_pcs"] == 80.0
    assert rows[1]["Spirals_needed"] == 1


# --- picker ---

def test_load_run_snapshot_missing_returns_none(conn):
    assert load_run_snapshot(conn, 99999) is None


def test_list_runs_for_picker(conn):
    work = _golden_work()
    bp, grand = _plans()
    r1 = _persist(conn, work, bp, grand, customer="PlantA", site="P1")
    r2 = _persist(conn, work, bp, grand, customer="PlantB", site="P2")
    rows = list_runs_for_picker(conn)
    assert len(rows) == 2
    # newest first
    assert rows[0]["run_id"] == max(r1, r2)
    assert rows[0]["total_cabs"] == 3
    assert rows[0]["filename"] == "cat.xlsx"
    # filter by customer
    only_a = list_runs_for_picker(conn, customer="planta")
    assert len(only_a) == 1
    assert only_a[0]["customer"] == "PlantA"
