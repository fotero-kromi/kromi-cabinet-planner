"""Read a stored run back as the snapshot that was delivered (Phase 3).

The persistence strategy is snapshot plus build version: a plain reload shows the
exact result the run produced, not a recomputation. So this module reconstructs
the per-tool result table and the plan summary straight from the stored rows --
the cabinet-sizing numbers come from the database, never from re-running the
engine, which is what prevents a reload from drifting away from what was
delivered.

What a snapshot carries is the set of fields the dual-write stored: each tool's
identity, its size and product category, and its engine outputs, plus the plan
summary per bucket and the grand total. Columns the engine used internally but
did not store (intermediate routing columns, evidence, and such) are not part of
the snapshot; the reload renders the delivered result from the stored columns.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from db.store import get_run, get_file, search_runs


# Mapping from the stored row to the original work-frame column, with the type
# each value is coerced back to. This is the contract a reload renders against
# and the contract the golden round-trip test checks.
#   (select_alias, work_column, kind)
_SNAPSHOT_FIELDS = [
    ("code", "Code", "str"),
    ("description", "Description", "str"),
    ("description_2", "Description_2", "str"),
    ("supplier_code", "SupplierCode", "str"),
    ("listing", "Listing", "str"),
    ("system_typ", "SystemTyp", "str"),
    ("pack_units", "PackUnits", "float"),
    ("size_category", "SizeCategory", "str"),
    ("product_category", "ProductCategory", "str"),
    ("cls_source", "SizeCategory_Source", "str"),
    ("cls_model", "ProductCategory_AI_Model", "str"),
    ("cls_reason", "ProductCategory_Reason", "str"),
    ("cls_confidence", "ProductCategory_Confidence", "float"),
    ("system_category", "SystemCategory", "str"),
    ("cabinet_type", "CabinetType", "str"),
    ("spirals_needed", "Spirals_needed", "int"),
    ("carousel_stockpiles", "Carousel_stockpiles", "int"),
    ("restockable", "Restockable", "int"),
    ("restock_slots", "Restock_slots", "int"),
    ("spiral_capacity", "Spiral_capacity", "int"),
    ("monthly_packs", "Monthly_packs", "float"),
    ("target_packs", "Target_packs", "float"),
    ("consumption_pcs", "Consumption_pcs", "float"),
    ("supply_point", "SupplyPoint", "int"),
    ("size_issue", "SizeIssue", "bool"),
    ("size_issue_reason", "SystemCategory_Reason", "str"),
    ("override_applied", "Override_Applied", "bool"),
]

# Plan summary column (database) -> plan dict key (page).
_PLAN_FIELDS = [
    ("helix_cabs", "helix_cabs"),
    ("carousel_cabs", "car_cabs"),
    ("locker_a", "cabA"),
    ("locker_b", "cabB"),
    ("locker_c", "cabC"),
    ("total_cabs", "total_cabs"),
    ("total_spirals", "total_spirals"),
    ("carousel_slots", "car_slots"),
    ("ktc_count", "ktc_count"),
    ("kanban_count", "kanban_count"),
]

_GRAND_LABEL = "Grand total"


def _coerce(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if kind == "str":
        return str(value)
    if kind == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if kind == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if kind == "bool":
        return bool(value)
    return value


def reconstruct_work(conn, run_id: int):
    """Rebuild the per-tool result table for a run as a DataFrame, with the
    original work-frame column names and types. Rows come back in the order they
    were stored."""
    import pandas as pd

    select_cols = (
        "tr.code, tr.description, tr.description_2, tr.supplier_code, tr.listing, "
        "tr.system_typ, tr.pack_units, "
        "cc.size_category, cc.product_category, cc.system_category, cc.cabinet_type, "
        "cc.spirals_needed, cc.carousel_stockpiles, cc.spiral_capacity, "
        "cc.restockable, cc.restock_slots, "
        "cc.monthly_packs, cc.target_packs, cc.consumption_pcs, cc.supply_point, "
        "cc.size_issue, cc.size_issue_reason, cc.override_applied, "
        "cl.source AS cls_source, cl.model AS cls_model, cl.reason AS cls_reason, "
        "cl.confidence AS cls_confidence"
    )
    rows = conn.execute(
        f"SELECT {select_cols} "
        "FROM cabinet_calculations cc "
        "JOIN tool_records tr ON tr.tool_record_id = cc.tool_record_id "
        "LEFT JOIN tool_classifications cl ON cl.classification_id = cc.classification_id "
        "WHERE cc.run_id = ? ORDER BY cc.calc_id",
        (run_id,),
    ).fetchall()

    records: List[Dict[str, Any]] = []
    for r in rows:
        records.append({
            work_col: _coerce(r[alias], kind)
            for alias, work_col, kind in _SNAPSHOT_FIELDS
        })
    columns = [work_col for _, work_col, _ in _SNAPSHOT_FIELDS]
    return pd.DataFrame(records, columns=columns)


def reconstruct_plans(conn, run_id: int):
    """Rebuild (bucket_plans, grand) for a run from the stored plan summary."""
    rows = conn.execute(
        "SELECT * FROM cabinet_plan_summary WHERE run_id = ? ORDER BY summary_id",
        (run_id,),
    ).fetchall()
    bucket_plans: List[tuple] = []
    grand: Dict[str, Any] = {}
    for s in rows:
        plan = {dict_key: int(s[col]) if s[col] is not None else 0
                for col, dict_key in _PLAN_FIELDS}
        if s["bucket_label"] == _GRAND_LABEL:
            grand = plan
        else:
            bucket_plans.append((s["bucket_label"], plan))
    return bucket_plans, grand


def load_run_snapshot(conn, run_id: int) -> Optional[Dict[str, Any]]:
    """Load a run as the snapshot to display. Returns None if the run is absent.

    The returned dict carries the run row, the reconstructed work table, the
    plans and grand total, the file metadata, and the build version the run ran
    under (None for runs that predate build tracking, e.g. older imports)."""
    run = get_run(conn, run_id)
    if run is None:
        return None
    work = reconstruct_work(conn, run_id)
    bucket_plans, grand = reconstruct_plans(conn, run_id)
    file_row = get_file(conn, run["file_id"]) if run["file_id"] is not None else None
    return {
        "run": dict(run),
        "work": work,
        "bucket_plans": bucket_plans,
        "grand": grand,
        "filename": file_row["original_filename"] if file_row else None,
        "build_version": run["build_version"],
        "customer": run["customer"],
        "site": run["site"],
        "operational_mode": run["operational_mode"],
        "status": run["status"],
        "created_at": run["created_at"],
    }


def list_runs_for_picker(
    conn,
    *,
    customer: Optional[str] = None,
    site: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Compact run rows for the load picker: newest first, optionally filtered by
    customer and/or site, each with its file name and grand-total cabinet count."""
    out: List[Dict[str, Any]] = []
    for r in search_runs(conn, customer=customer, site=site, limit=limit):
        file_row = get_file(conn, r["file_id"]) if r["file_id"] is not None else None
        grand = conn.execute(
            "SELECT total_cabs FROM cabinet_plan_summary "
            "WHERE run_id = ? AND bucket_label = ? LIMIT 1",
            (r["run_id"], _GRAND_LABEL),
        ).fetchone()
        out.append({
            "run_id": r["run_id"],
            "customer": r["customer"],
            "site": r["site"],
            "ktc_id": r["ktc_id"],
            "build_version": r["build_version"],
            "operational_mode": r["operational_mode"],
            "calc_mode": r["calc_mode"],
            "status": r["status"],
            "created_at": r["created_at"],
            "filename": file_row["original_filename"] if file_row else None,
            "total_cabs": grand["total_cabs"] if grand else None,
        })
    return out
