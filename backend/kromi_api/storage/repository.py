"""Saving and loading workbooks, runs and results.

Values are stored exactly: every planner row goes into JSON with its column
types recorded, so ``load_plan_result`` rebuilds the planner's result with the
same fingerprint (the parity oracle holds after the database round trip).
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.build_info import BUILD

from ..services.export import ResultWorkbook
from ..services.planning import PlanOutcome
from ..settings import RunRequest
from .models import Run, RunBucket, RunFile, RunSummary, RunTool, Workbook

#: Bumped when the stored settings layout changes (a migration then converts old rows).
SETTINGS_VERSION = 1
RESULT_WORKBOOK = "result_workbook"


def _now() -> datetime:
    return datetime.now(UTC)


# ---- exact JSON values ----------------------------------------------------------------

def to_json(value: Any) -> Any:
    """A value as plain JSON; missing values become None. Unknown types and
    infinite numbers are refused rather than stored as something else."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if type(value).__module__ == "numpy" and hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            raise ValueError("an infinite number cannot be stored")
        return value
    if isinstance(value, list | tuple):
        return [to_json(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_json(v) for k, v in value.items()}
    raise TypeError(f"cannot store a {type(value).__name__}")


def frame_to_rows(frame: pd.DataFrame) -> tuple[list[list[str]], list[dict[str, Any]]]:
    """(columns with their types, rows as JSON) for a planner frame."""
    columns = [[str(c), str(t)] for c, t in frame.dtypes.items()]
    names = [c for c, _ in columns]
    rows = [{name: to_json(value) for name, value in zip(names, record, strict=True)}
            for record in frame.itertuples(index=False, name=None)]
    return columns, rows


def rows_to_frame(columns: list[list[str]], rows: list[dict[str, Any]]) -> pd.DataFrame:
    """The planner frame back from ``frame_to_rows``: same columns, order and types.

    Built as plain objects first, so pandas never guesses a type (a text column
    holding 2025 and a gap must not come back as 2025.0)."""
    names = [c for c, _ in columns]
    frame = pd.DataFrame([[row.get(n) for n in names] for row in rows], columns=names,
                         dtype=object)
    for name, dtype in columns:
        if dtype != "object":
            frame[name] = frame[name].astype(dtype)
    return frame


# ---- workbooks ------------------------------------------------------------------------

def save_workbook(db: Session, filename: str, raw: bytes) -> Workbook:
    """The stored workbook for ``raw``; the same content is stored only once."""
    sha = hashlib.sha256(raw).hexdigest()
    existing = db.scalar(select(Workbook).where(Workbook.sha256 == sha))
    if existing is not None:
        return existing
    wb = Workbook(sha256=sha, filename=(filename or "upload.xlsx")[:255], size_bytes=len(raw),
                  content=raw)
    db.add(wb)
    db.flush()
    return wb


def workbook_bytes(db: Session, workbook_id: int) -> bytes | None:
    return db.scalar(select(Workbook.content).where(Workbook.id == workbook_id))


# ---- runs -----------------------------------------------------------------------------

def inputs_hash(workbook_sha: str, request: RunRequest) -> str:
    """Identifies a run: the workbook, every setting, the engine build."""
    payload = json.dumps({"workbook": workbook_sha, "settings": request.model_dump(mode="json"),
                          "settings_version": SETTINGS_VERSION, "build": BUILD},
                         sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_run(db: Session, wb: Workbook, request: RunRequest) -> Run:
    run = Run(workbook_id=wb.id, status="queued", settings=request.model_dump(mode="json"),
              settings_version=SETTINGS_VERSION, inputs_hash=inputs_hash(wb.sha256, request),
              engine_build=BUILD, notes=[])
    db.add(run)
    db.flush()
    return run


def find_finished_run(db: Session, workbook_id: int, request: RunRequest) -> Run | None:
    """An earlier successful run with exactly these inputs, if any."""
    wb = db.get(Workbook, workbook_id)
    if wb is None:
        return None
    return db.scalar(select(Run).where(
        Run.workbook_id == workbook_id, Run.status == "succeeded",
        Run.inputs_hash == inputs_hash(wb.sha256, request)).order_by(Run.id.desc()).limit(1))


def mark_running(db: Session, run: Run) -> None:
    run.status = "running"
    run.started_at = _now()


def mark_failed(db: Session, run: Run, code: str, message: str, details: Any = None) -> None:
    run.status = "failed"
    run.error_code = code
    run.error_message = message
    run.error_details = to_json(details)
    run.finished_at = _now()


def _text(value: Any) -> str | None:
    value = to_json(value)
    return None if value is None or value == "" else str(value)


def _number(value: Any) -> float | None:
    value = to_json(value)
    return None if value is None else float(value)


def _count(value: Any) -> int | None:
    value = to_json(value)
    return None if value is None else int(value)


def save_result(db: Session, run: Run, outcome: PlanOutcome, book: ResultWorkbook, *,
                filename: str) -> None:
    """Store a finished run: summary, buckets, every article row and the workbook."""
    r = outcome.result
    columns, rows = frame_to_rows(r.work)
    db.add(RunSummary(
        run_id=run.id, customer=outcome.customer, site=outcome.site,
        grand=to_json(r.grand), base_info=to_json(outcome.base_info),
        restock_info=to_json(r.restock_info), vend_stats=to_json(r.vend_stats),
        override_stats=to_json(r.override_stats),
        validation_issues=to_json(r.validation_issues), split_coverage=bool(r.split_coverage),
        listings=to_json(r.listings), rebalance_audit=to_json(r.rebalance_audit),
        sp_conservation=to_json(r.sp_conservation), tool_columns=columns,
        export_problems=list(book.problems), export_notes=book.notes))
    for position, (label, plan) in enumerate(r.bucket_plans):
        db.add(RunBucket(
            run_id=run.id, position=position, label=str(label),
            ktc_count=int(plan["ktc_count"]), kanban_count=int(plan["kanban_count"]),
            helix_cabinets=int(plan["helix_cabs"]), carousel_cabinets=int(plan["car_cabs"]),
            locker_a_cabinets=int(plan["cabA"]), locker_b_cabinets=int(plan["cabB"]),
            locker_c_cabinets=int(plan["cabC"]), total_cabinets=int(plan["total_cabs"]),
            plan=to_json(plan)))
    db.add_all(RunTool(
        run_id=run.id, line_no=i, listing=_text(row.get("Listing")), code=_text(row.get("Code")),
        description=_text(row.get("Description")), category=_text(row.get("ProductCategory")),
        size=_text(row.get("SizeCategory")), pack_units=_number(row.get("PackUnits")),
        system_category=_text(row.get("SystemCategory")),
        cabinet_type=_text(row.get("CabinetType")), supply_point=_count(row.get("SupplyPoint")),
        monthly_pcs=_number(row.get("Monthly_pcs")),
        monthly_packs=_number(row.get("Monthly_packs")),
        spirals=_count(row.get("Spirals_needed")),
        compartments=_count(row.get("Carousel_stockpiles")), row=row)
        for i, row in enumerate(rows, start=1))
    db.add(RunFile(run_id=run.id, kind=RESULT_WORKBOOK, filename=filename[:255],
                   sha256=hashlib.sha256(book.data).hexdigest(), content=book.data))
    run.notes = list(outcome.notes)
    run.status = "succeeded"
    run.finished_at = _now()
    db.flush()


# ---- reading results ------------------------------------------------------------------

def load_plan_result(db: Session, run_id: int) -> SimpleNamespace:
    """The planner's result of a stored run, rebuilt from the database."""
    summary = db.get(RunSummary, run_id)
    if summary is None:
        raise LookupError(f"run {run_id} has no stored result")
    rows = [t.row for t in tool_rows(db, run_id)]
    return SimpleNamespace(
        work=rows_to_frame(summary.tool_columns, rows),
        bucket_plans=[(b.label, b.plan) for b in bucket_rows(db, run_id)],
        grand=summary.grand, restock_info=summary.restock_info,
        vend_stats=summary.vend_stats, override_stats=summary.override_stats,
        validation_issues=summary.validation_issues, split_coverage=summary.split_coverage,
        listings=summary.listings, rebalance_audit=summary.rebalance_audit,
        sp_conservation=summary.sp_conservation)


def tool_rows(db: Session, run_id: int) -> list[RunTool]:
    return list(db.scalars(select(RunTool).where(RunTool.run_id == run_id)
                           .order_by(RunTool.line_no)))


def bucket_rows(db: Session, run_id: int) -> list[RunBucket]:
    return list(db.scalars(select(RunBucket).where(RunBucket.run_id == run_id)
                           .order_by(RunBucket.position)))


def result_file(db: Session, run_id: int) -> RunFile | None:
    return db.scalar(select(RunFile).where(RunFile.run_id == run_id,
                                           RunFile.kind == RESULT_WORKBOOK))


def recent_runs(db: Session, limit: int = 50) -> list[Run]:
    return list(db.scalars(select(Run).order_by(Run.id.desc()).limit(limit)))
