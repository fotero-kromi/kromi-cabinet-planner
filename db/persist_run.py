"""Dual-write of a completed run into the database (Phase 1).

The application stays authoritative: a run still computes and exports exactly as
before. When the user opts to save a run, this module also writes a normalized
copy into the database so later phases can read it back. A failure here must
never break the run, so the caller wraps the call and the write is atomic (all
tables for a run commit together or not at all).

Granularity:
  * uploaded_files is written once per file content (deduplicated by hash).
  * tool_records hold one row per article code of a file; a later run that
    brings a code the file has not seen yet (a PPE sheet added, another year
    filter) adds it (v34.53, audit C8: it used to fail with a KeyError).
  * tool_classifications hold the classifier's answers. Every run links each
    of its rows to the answer it used: an identical earlier answer is reused,
    a different one is added and supersedes the previous newest (v34.53).
    Re-running the same catalog therefore adds nothing, an AI run after a
    heuristic one keeps both, and a recompute reads its run's own answers.
    A technician override is never stored as the classifier's answer.
  * analysis_runs, cabinet_calculations, cabinet_plan_summary, rebalance_events,
    engine_executions, and validation_results are written per run.

The extraction helpers turn the page's in-memory state (the work DataFrame, the
bucket plans, the rebalance audit) into plain lists of dicts, so persist_run
itself depends only on the database and is fully testable without Streamlit.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Source labels with a special meaning for the archive (v34.53).
_OVERRIDE_SOURCE = "Override"
# A recompute re-applies a stored run's answers and marks them with this
# source; the archive links such a row to the stored answer it came from.
REUSED_SOURCE = "Reused from stored run"


def _clean(value: Any) -> Any:
    """Normalize a cell to a SQLite-storable scalar: NaN and pandas NA become None."""
    if value is None:
        return None
    try:
        import pandas as pd  # local import keeps the module import-light
        if pd.isna(value):
            return None
    except (TypeError, ValueError, ImportError):
        pass
    return value


def _as_int(value: Any) -> Optional[int]:
    value = _clean(value)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    value = _clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Extraction helpers (page state -> plain lists of dicts)
# ---------------------------------------------------------------------------

def tools_from_dataframe(df) -> List[Dict[str, Any]]:
    """Build one dict per work row carrying the fields for all three per-tool
    tables (tool_records identity, tool_classifications, cabinet_calculations)."""
    tools: List[Dict[str, Any]] = []
    for rec in df.to_dict("records"):
        size_src = _clean(rec.get("SizeCategory_Source"))
        prod_src = _clean(rec.get("ProductCategory_Source"))
        size_ov = str(size_src or "").strip() == _OVERRIDE_SOURCE
        prod_ov = str(prod_src or "").strip() == _OVERRIDE_SOURCE
        # The classifier's answer, not a technician's correction (v34.53): an
        # overridden product falls back to the pre-override prediction, an
        # overridden size is left open (a recompute re-derives it), and the
        # source is the first field the classifier decided.
        cls_size = None if size_ov else _clean(rec.get("SizeCategory"))
        cls_prod = (_clean(rec.get("ProductCategory_PreOverride")) if prod_ov
                    else _clean(rec.get("ProductCategory")))
        cls_conf = (_as_float(rec.get("ProductCategory_ConfidencePreOverride")) if prod_ov
                    else _as_float(rec.get("ProductCategory_Confidence")))
        cls_source = next(
            (src for src, ov in ((size_src, size_ov), (prod_src, prod_ov)) if src and not ov),
            None)
        model = _clean(rec.get("SizeCategory_AI_Model")) or _clean(rec.get("ProductCategory_AI_Model"))
        tools.append({
            # identity (tool_records)
            "code": str(_clean(rec.get("Code")) or ""),
            "description": _clean(rec.get("Description")),
            "description_2": _clean(rec.get("Description_2")),
            "supplier_code": _clean(rec.get("SupplierCode")),
            "listing": _clean(rec.get("Listing")),
            "system_typ": _clean(rec.get("SystemTyp")),
            "raw_consumption": _as_float(rec.get("Consumption_pcs")),
            "pack_units": _as_float(rec.get("PackUnits")),
            # the run-effective values (cabinet_calculations)
            "size_category": _clean(rec.get("SizeCategory")),
            "product_category": _clean(rec.get("ProductCategory")),
            # the classifier's answer (tool_classifications)
            "classification_size": cls_size,
            "classification_product": cls_prod,
            "classification_source": cls_source,
            "classification_model": model,
            "classification_reason": _clean(rec.get("ProductCategory_Reason")),
            "classification_confidence": cls_conf,
            # calculation (cabinet_calculations)
            "system_category": _clean(rec.get("SystemCategory")),
            "cabinet_type": _clean(rec.get("CabinetType")),
            "spirals_needed": _as_int(rec.get("Spirals_needed")),
            "carousel_stockpiles": _as_int(rec.get("Carousel_stockpiles")),
            "spiral_capacity": _as_int(rec.get("Spiral_capacity")),
            "monthly_packs": _as_float(rec.get("Monthly_packs")),
            "target_packs": _as_float(rec.get("Target_packs")),
            "consumption_pcs": _as_float(rec.get("Consumption_pcs")),
            "supply_point": _as_int(rec.get("SupplyPoint")),
            "size_issue": 1 if bool(_clean(rec.get("SizeIssue"))) else 0,
            "size_issue_reason": _clean(rec.get("SystemCategory_Reason")),
            "override_applied": 1 if bool(_clean(rec.get("Override_Applied"))) else 0,
            "override_fields_json": None,
            # restocking (v34.27); robust to the bool frame value and to the
            # Yes/empty display normalization applied for the exports
            "restockable": 1 if str(_clean(rec.get("Restockable")) or "").strip().lower() in ("true", "yes", "1") else 0,
            "restock_slots": _as_int(rec.get("Restock_slots")) or 0,
        })
    return tools


def _summary_row(label: str, p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "bucket_label": label,
        "helix_cabs": _as_int(p.get("helix_cabs")) or 0,
        "carousel_cabs": _as_int(p.get("car_cabs")) or 0,
        "locker_a": _as_int(p.get("cabA")) or 0,
        "locker_b": _as_int(p.get("cabB")) or 0,
        "locker_c": _as_int(p.get("cabC")) or 0,
        "total_cabs": _as_int(p.get("total_cabs")) or 0,
        "total_spirals": _as_int(p.get("total_spirals")) or 0,
        "carousel_slots": _as_int(p.get("car_slots")) or 0,
        "ktc_count": _as_int(p.get("ktc_count")) or 0,
        "kanban_count": _as_int(p.get("kanban_count")) or 0,
    }


def summary_rows_from_plans(
    bucket_plans: Sequence, grand: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """One summary row per bucket plus a 'Grand total' row."""
    rows = [_summary_row(label, p) for label, p in bucket_plans]
    if grand:
        rows.append(_summary_row("Grand total", grand))
    return rows


def rebalance_events_from_audit(audit_all: Optional[Sequence]) -> List[Dict[str, Any]]:
    """Flatten the rebalance audit into one row per moved item."""
    out: List[Dict[str, Any]] = []
    for ev in audit_all or []:
        before = _as_int(ev.get("cabinets_before")) or 0
        after = _as_int(ev.get("cabinets_after")) or 0
        bucket = ev.get("bucket")
        for m in ev.get("items_moved", []) or []:
            out.append({
                "bucket_label": bucket,
                "cabinets_before": before,
                "cabinets_after": after,
                "item_code": str(m.get("code", "")),
                "from_cabinet": m.get("from_cabinet"),
                "to_cabinet": m.get("to_cabinet"),
            })
    return out


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def _insert(conn: sqlite3.Connection, table: str, row: Dict[str, Any]) -> int:
    """Insert without committing (the caller's transaction owns the commit)."""
    cols = list(row.keys())
    placeholders = ", ".join("?" for _ in cols)
    cur = conn.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
        [row[c] for c in cols],
    )
    rid = cur.lastrowid
    assert rid is not None  # the INSERT above always sets it
    return int(rid)


def persist_run(
    conn: sqlite3.Connection,
    *,
    file: Dict[str, Any],
    run: Dict[str, Any],
    tools: Sequence[Dict[str, Any]],
    plan_rows: Sequence[Dict[str, Any]],
    rebalance_events: Sequence[Dict[str, Any]],
    execution: Dict[str, Any],
) -> int:
    """Write a complete run to the database in one transaction and return run_id.

    ``file`` carries sha256 and the workbook metadata; ``run`` carries the
    settings and provenance for analysis_runs; ``tools`` is the per-tool payload
    from tools_from_dataframe; ``plan_rows`` and ``rebalance_events`` come from
    their helpers; ``execution`` carries the audit counters for this compute.
    """
    now = _utc_now()
    with conn:  # atomic: commit on success, roll back on any error
        # 1. File, deduplicated by content hash. Insert-or-ignore, then read
        #    the id back: two sessions saving the same new workbook at once
        #    used to collide on the unique hash (v34.55).
        conn.execute(
            "INSERT OR IGNORE INTO uploaded_files (sha256, original_filename, "
            "byte_size, content, sheet_tools, sheet_ppe, row_count, "
            "first_seen_customer, first_seen_ktc_id, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (file["sha256"], file.get("original_filename"), file.get("byte_size"),
             file.get("content"), file.get("sheet_tools"), file.get("sheet_ppe"),
             file.get("row_count"), file.get("first_seen_customer"),
             file.get("first_seen_ktc_id"), now),
        )
        file_row = conn.execute(
            "SELECT file_id FROM uploaded_files WHERE sha256 = ?", (file["sha256"],)
        ).fetchone()
        file_id = int(file_row[0])

        # 2. tool_records: one per code of the file, added on demand; each code
        #    links to the classification this run used (v34.53, audit C8).
        code_map = _link_tools_and_classifications(conn, file_id, tools, now)

        # 3. The run (hub).
        run_id = _insert(conn, "analysis_runs", {
            "file_id": file_id,
            "machine_config_id": run.get("machine_config_id"),
            "build_version": run.get("build_version"),
            "customer": run.get("customer"),
            "site": run.get("site"),
            "ktc_id": run.get("ktc_id"),
            "calc_mode": run.get("calc_mode"),
            "operational_mode": run.get("operational_mode"),
            "max_carousels": run.get("max_carousels"),
            "supply_points": run.get("supply_points"),
            "sp_mode": run.get("sp_mode"),
            "settings_json": run.get("settings_json"),
            "applied_override_set_id": run.get("applied_override_set_id"),
            "status": run.get("status", "completed"),
            "notes": run.get("notes"),
            "created_at": now,
        })

        # 4. cabinet_calculations: one per work row.
        for t in tools:
            tid, cid = code_map[t["code"]]
            _insert(conn, "cabinet_calculations", {
                "run_id": run_id,
                "tool_record_id": tid,
                "classification_id": cid,
                "system_category": t.get("system_category"),
                "cabinet_type": t.get("cabinet_type"),
                "spirals_needed": t.get("spirals_needed"),
                "carousel_stockpiles": t.get("carousel_stockpiles"),
                "spiral_capacity": t.get("spiral_capacity"),
                "size_category": t.get("size_category"),
                "product_category": t.get("product_category"),
                "monthly_packs": t.get("monthly_packs"),
                "target_packs": t.get("target_packs"),
                "consumption_pcs": t.get("consumption_pcs"),
                "supply_point": t.get("supply_point"),
                "bucket_label": t.get("bucket_label"),
                "size_issue": t.get("size_issue", 0),
                "size_issue_reason": t.get("size_issue_reason"),
                "override_applied": t.get("override_applied", 0),
                "override_fields_json": t.get("override_fields_json"),
                "restockable": t.get("restockable", 0),
                "restock_slots": t.get("restock_slots", 0),
            })

        # 5. Plan summary (per bucket plus grand total).
        for p in plan_rows:
            _insert(conn, "cabinet_plan_summary", {"run_id": run_id, **p})

        # 6. Rebalance events.
        for ev in rebalance_events:
            _insert(conn, "rebalance_events", {"run_id": run_id, **ev})

        # 7. Engine execution audit.
        _insert(conn, "engine_executions", {
            "run_id": run_id,
            "build_version": execution.get("build_version"),
            "executed_at": now,
            "duration_ms": execution.get("duration_ms"),
            "rows_processed": execution.get("rows_processed"),
            "rebalance_moves": execution.get("rebalance_moves"),
            "cabinets_saved": execution.get("cabinets_saved"),
            "size_issues_found": execution.get("size_issues_found"),
            "grand_total_cabs": execution.get("grand_total_cabs"),
            "inputs_hash": execution.get("inputs_hash"),
        })

        # 8. Validation: one row per tool flagged with a size issue.
        for t in tools:
            if t.get("size_issue"):
                tid, _cid = code_map[t["code"]]
                _insert(conn, "validation_results", {
                    "run_id": run_id,
                    "tool_record_id": tid,
                    "issue_type": "size_issue",
                    "severity": "warning",
                    "detail": t.get("size_issue_reason"),
                    "resolved": 0,
                    "resolved_by": None,
                    "resolved_at": None,
                })

    return run_id


def _same(a: Any, b: Any) -> bool:
    """NULL-safe equality for stored scalars."""
    if a is None or b is None:
        return a is None and b is None
    return a == b


def _link_tools_and_classifications(
    conn: sqlite3.Connection, file_id: int, tools: Sequence[Dict[str, Any]], now: str,
) -> Dict[str, tuple]:
    """Map every code of this run to (tool_record_id, classification_id).

    Tool records are per file and code; a code the file has not seen yet is
    added with the next line number. For the classification the run used (the
    first row of each code), an identical stored answer is reused, the newest
    one first; a recompute's re-applied answer matches on the values alone. A
    different answer is added and the previous newest is marked superseded.
    """
    records = {
        r["code"]: int(r["tool_record_id"])
        for r in conn.execute(
            "SELECT tool_record_id, code FROM tool_records WHERE file_id = ? "
            "ORDER BY tool_record_id", (file_id,)).fetchall()
    }
    line_row = conn.execute(
        "SELECT COALESCE(MAX(line_no), 0) FROM tool_records WHERE file_id = ?", (file_id,)
    ).fetchone()
    line_no = int(line_row[0])
    by_record: Dict[int, List[Any]] = {}
    for r in conn.execute(
            "SELECT classification_id, tool_record_id, size_category, product_category, "
            "source, model FROM tool_classifications WHERE file_id = ? "
            "ORDER BY classification_id", (file_id,)).fetchall():
        by_record.setdefault(int(r["tool_record_id"]), []).append(r)

    code_map: Dict[str, tuple] = {}
    for t in tools:
        code = t["code"]
        if code in code_map:
            continue
        tid = records.get(code)
        if tid is None:
            line_no += 1
            tid = _insert(conn, "tool_records", {
                "file_id": file_id,
                "line_no": line_no,
                "code": code,
                "description": t.get("description"),
                "description_2": t.get("description_2"),
                "supplier_code": t.get("supplier_code"),
                "listing": t.get("listing"),
                "raw_consumption": t.get("raw_consumption"),
                "pack_units": t.get("pack_units"),
                "period_months": t.get("period_months"),
                "source_size": t.get("source_size"),
                "system_typ": t.get("system_typ"),
                "extra_json": t.get("extra_json"),
            })
            records[code] = tid
        size = t.get("classification_size", t.get("size_category"))
        prod = t.get("classification_product", t.get("product_category"))
        source = t.get("classification_source")
        model = t.get("classification_model")
        reused = str(source or "").strip() == REUSED_SOURCE
        existing = by_record.get(tid, [])
        match = next((
            r for r in reversed(existing)
            if _same(r["size_category"], size) and _same(r["product_category"], prod)
            and (reused or (_same(r["source"], source) and _same(r["model"], model)))
        ), None)
        if match is not None:
            code_map[code] = (tid, int(match["classification_id"]))
            continue
        cid = _insert(conn, "tool_classifications", {
            "file_id": file_id,
            "tool_record_id": tid,
            "size_category": size,
            "product_category": prod,
            "source": source,
            "model": model,
            "prompt_version": t.get("classification_prompt_version"),
            "reason": t.get("classification_reason"),
            "confidence": t.get("classification_confidence"),
            "classified_at": now,
        })
        if existing:
            conn.execute(
                "UPDATE tool_classifications SET superseded_by = ? WHERE classification_id = ?",
                (cid, int(existing[-1]["classification_id"])))
        code_map[code] = (tid, cid)
    return code_map


def run_id_by_inputs_hash(conn, inputs_hash: str):
    """The run already archived for these exact inputs, if any (audit M3).

    engine_executions carries the inputs hash per archived run; the newest
    match wins so callers can point the user at the existing archive."""
    row = conn.execute(
        "SELECT run_id FROM engine_executions WHERE inputs_hash = ? "
        "ORDER BY execution_id DESC LIMIT 1",
        (inputs_hash,),
    ).fetchone()
    return int(row[0]) if row else None
