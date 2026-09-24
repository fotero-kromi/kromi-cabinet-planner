"""What the API sends back (request bodies are in ``kromi_api.settings``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..settings import ColumnMappingIn, ExportIn, PlanningIn, RunRequest, ScopeIn


class WorkbookOut(BaseModel):
    id: int
    sha256: str
    filename: str
    size_bytes: int
    uploaded_at: datetime
    sheets: list[str]


class SheetOut(BaseModel):
    sheet: str
    header_row: int
    columns: list[str]
    row_count: int
    preview: list[dict[str, Any]]
    headers_look_misplaced: bool
    suggested_header_row: int
    #: ColumnMappingIn field -> suggested source column (None = leave unmapped)
    suggested_mapping: dict[str, str | None]


class MappingCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet: str
    header_row: int = 1
    mapping: ColumnMappingIn


class MappingCheckOut(BaseModel):
    ok: bool
    #: source column -> the fields it is mapped to (more than one is a conflict)
    conflicts: dict[str, list[str]]
    #: mapped columns the sheet does not have
    missing_columns: list[str]


class DefaultsOut(BaseModel):
    header_row: int
    planning: PlanningIn
    scope: ScopeIn
    export: ExportIn
    limits: dict[str, tuple[float | None, float | None]]
    labels: dict[str, dict[str, str]]
    #: allowed values of list settings (``restock_categories``)
    choices: dict[str, list[str]]


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workbook_id: int
    settings: RunRequest


class RunError(BaseModel):
    code: str
    message: str
    details: Any = None


class BucketOut(BaseModel):
    position: int
    label: str
    ktc_count: int
    kanban_count: int
    helix_cabinets: int
    carousel_cabinets: int
    locker_a_cabinets: int
    locker_b_cabinets: int
    locker_c_cabinets: int
    total_cabinets: int


class RunSummaryOut(BaseModel):
    customer: str
    site: str
    grand: dict[str, Any]
    buckets: list[BucketOut]
    validation_issues: list[str]
    export_problems: list[str]
    export_notes: str


class RunOut(BaseModel):
    id: int
    workbook_id: int
    status: str
    engine_build: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    settings: dict[str, Any]
    error: RunError | None
    notes: list[str]
    summary: RunSummaryOut | None
    reused: bool = False


class ToolOut(BaseModel):
    line_no: int
    listing: str | None
    code: str | None
    description: str | None
    category: str | None
    size: str | None
    pack_units: float | None
    system_category: str | None
    cabinet_type: str | None
    supply_point: int | None
    monthly_pcs: float | None
    monthly_packs: float | None
    spirals: int | None
    compartments: int | None
