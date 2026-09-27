"""The ``/api/v1`` endpoints."""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Iterator
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from engine.build_info import BUILD
from engine.classification_tables import PC_VALID
from engine.planning_defaults import (
    CALC_MODE_LABELS,
    DEDUP_MODE_LABELS,
    DEFAULTS,
    LIMITS,
    OP_MODE_LABELS,
    OP_STANDARD,
    SP_MODE_LABELS,
    YEAR_MODE_LABELS,
)
from engine.tool_list import ColumnMapping, mapping_collisions, rename_map

from .. import config
from ..runner import execute_run
from ..services import workbook as wb_service
from ..services.errors import PlanningError
from ..settings import ExportIn, PlanningIn, ScopeIn
from ..storage import repository as repo
from ..storage.models import Run, RunSummary, Workbook
from .schemas import (
    BucketOut,
    DefaultsOut,
    MappingCheckIn,
    MappingCheckOut,
    RunCreate,
    RunError,
    RunOut,
    RunSummaryOut,
    SheetOut,
    ToolOut,
    WorkbookOut,
)

router = APIRouter(prefix="/api/v1")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Planning column (as the engine names fields) -> ColumnMappingIn field.
_SENTINEL = ColumnMapping(**{f.name: f.name for f in dataclasses.fields(ColumnMapping)})
FIELD_OF_COLUMN = {target: field for field, target in rename_map(_SENTINEL).items()}


def _factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def get_db(request: Request) -> Iterator[Session]:
    session = _factory(request)()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


Db = Annotated[Session, Depends(get_db)]


def _unprocessable(exc: PlanningError) -> HTTPException:
    return HTTPException(422,
                         detail={"code": exc.code, "message": exc.message,
                                 "details": exc.details})


def _workbook(db: Session, workbook_id: int) -> Workbook:
    wb = db.get(Workbook, workbook_id)
    if wb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such workbook.")
    return wb


def _workbook_bytes(db: Session, workbook_id: int) -> bytes:
    _workbook(db, workbook_id)
    raw = repo.workbook_bytes(db, workbook_id)
    if raw is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such workbook.")
    return raw


def _run(db: Session, run_id: int) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such run.")
    return run


# ---- health, defaults ------------------------------------------------------------------

@router.get("/health")
def health(db: Db) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001 - reported, not raised
        database = "unreachable"
    return {"status": "ok", "build": BUILD, "database": database}


@router.get("/settings/defaults", response_model=DefaultsOut)
def defaults() -> DefaultsOut:
    return DefaultsOut(
        header_row=DEFAULTS.header_row, planning=PlanningIn(), scope=ScopeIn(), export=ExportIn(),
        limits=dict(LIMITS),
        labels={"op_mode": {OP_STANDARD: OP_MODE_LABELS[OP_STANDARD]},
                "sp_mode": SP_MODE_LABELS, "calc_mode": CALC_MODE_LABELS,
                "year_mode": YEAR_MODE_LABELS, "dedup_mode": DEDUP_MODE_LABELS},
        choices={"restock_categories": sorted(PC_VALID)})


# ---- workbooks -------------------------------------------------------------------------

@router.post("/workbooks", response_model=WorkbookOut, status_code=status.HTTP_201_CREATED,
             responses={200: {"model": WorkbookOut, "description": "Already stored"}})
async def upload_workbook(db: Db, response: Response,
                          file: Annotated[UploadFile, File()]) -> WorkbookOut:
    raw = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413,
                            detail=f"The file is larger than {config.MAX_UPLOAD_BYTES} bytes.")
    try:
        sheets = wb_service.sheet_names(raw)
    except PlanningError as exc:
        raise _unprocessable(exc) from exc
    before = db.query(Workbook.id).filter_by(sha256=hashlib.sha256(raw).hexdigest()).first()
    wb = repo.save_workbook(db, file.filename or "upload.xlsx", raw)
    if before is not None:
        response.status_code = status.HTTP_200_OK
    return WorkbookOut(id=wb.id, sha256=wb.sha256, filename=wb.filename,
                       size_bytes=wb.size_bytes, uploaded_at=wb.uploaded_at, sheets=sheets)


@router.get("/workbooks/{workbook_id}/sheets/{sheet}", response_model=SheetOut)
def inspect_sheet(db: Db, workbook_id: int, sheet: str,
                  header_row: Annotated[int, Query(ge=1, le=50)] = DEFAULTS.header_row
                  ) -> SheetOut:
    raw = _workbook_bytes(db, workbook_id)
    try:
        info = wb_service.inspect_sheet(raw, sheet, header_row)
    except PlanningError as exc:
        raise _unprocessable(exc) from exc
    return SheetOut(sheet=sheet, header_row=header_row, columns=info.columns,
                    row_count=info.row_count, preview=info.preview,
                    headers_look_misplaced=info.headers_look_misplaced,
                    suggested_header_row=info.suggested_header_row,
                    suggested_mapping={FIELD_OF_COLUMN[k]: v
                                       for k, v in info.suggested_mapping.items()})


@router.post("/workbooks/{workbook_id}/mapping/check", response_model=MappingCheckOut)
def check_mapping(db: Db, workbook_id: int, body: MappingCheckIn) -> MappingCheckOut:
    raw = _workbook_bytes(db, workbook_id)
    try:
        columns = set(wb_service.inspect_sheet(raw, body.sheet, body.header_row).columns)
    except PlanningError as exc:
        raise _unprocessable(exc) from exc
    mapping = body.mapping.to_engine()
    conflicts = mapping_collisions(mapping)
    missing = [c for c in rename_map(mapping) if c and c not in columns]
    return MappingCheckOut(ok=not conflicts and not missing, conflicts=conflicts,
                           missing_columns=missing)


# ---- runs ------------------------------------------------------------------------------

def _run_out(db: Session, run: Run, *, reused: bool = False) -> RunOut:
    summary = db.get(RunSummary, run.id)
    summary_out = None
    if summary is not None:
        summary_out = RunSummaryOut(
            customer=summary.customer, site=summary.site, grand=summary.grand,
            buckets=[BucketOut.model_validate(b, from_attributes=True)
                     for b in repo.bucket_rows(db, run.id)],
            validation_issues=summary.validation_issues,
            export_problems=summary.export_problems, export_notes=summary.export_notes)
    error = (RunError(code=run.error_code, message=run.error_message or "",
                      details=run.error_details) if run.error_code else None)
    return RunOut(id=run.id, workbook_id=run.workbook_id, status=run.status,
                  engine_build=run.engine_build, created_at=run.created_at,
                  started_at=run.started_at, finished_at=run.finished_at, settings=run.settings,
                  error=error, notes=run.notes, summary=summary_out, reused=reused)


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED,
             responses={200: {"model": RunOut, "description": "Identical finished run reused"}})
def create_run(db: Db, request: Request, body: RunCreate, background: BackgroundTasks,
               response: Response) -> RunOut:
    wb = _workbook(db, body.workbook_id)
    existing = repo.find_finished_run(db, wb.id, body.settings)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _run_out(db, existing, reused=True)
    run = repo.create_run(db, wb, body.settings)
    db.commit()
    background.add_task(execute_run, run.id, _factory(request))
    return _run_out(db, run)


@router.get("/runs", response_model=list[RunOut])
def list_runs(db: Db, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[RunOut]:
    return [_run_out(db, r) for r in repo.recent_runs(db, limit)]


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(db: Db, run_id: int) -> RunOut:
    return _run_out(db, _run(db, run_id))


@router.get("/runs/{run_id}/tools", response_model=list[ToolOut])
def run_tools(db: Db, run_id: int) -> list[ToolOut]:
    _run(db, run_id)
    return [ToolOut.model_validate(t, from_attributes=True) for t in repo.tool_rows(db, run_id)]


@router.get("/runs/{run_id}/workbook", response_class=Response,
            responses={200: {"content": {XLSX: {}}}, 409: {"description": "Run not finished"}})
def run_workbook(db: Db, run_id: int) -> Response:
    run = _run(db, run_id)
    f = repo.result_file(db, run_id)
    if run.status != "succeeded" or f is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"The run has no workbook (status: {run.status}).")
    return Response(content=f.content, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{f.filename}"'})
