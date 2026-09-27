"""Reading an uploaded workbook: its sheets, a sheet's columns and first rows,
the header-row check and the suggested column mapping (all from the engine)."""

from __future__ import annotations

import math
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

import pandas as pd

from engine.colmap import headers_look_misplaced, suggest_header_row
from engine.column_suggest import suggest_columns

from .errors import PlanningError

PREVIEW_ROWS = 20
#: Rows read without a header to find the real header row, as the page does.
HEADER_SCAN_ROWS = 30


def _excel(raw: bytes) -> pd.ExcelFile:
    try:
        return pd.ExcelFile(BytesIO(raw), engine="openpyxl")
    except (zipfile.BadZipFile, ValueError, KeyError, OSError) as exc:
        raise PlanningError("unreadable_workbook",
                            "The file is not an Excel workbook (.xlsx) that can be read.") from exc


def sheet_names(raw: bytes) -> list[str]:
    """The sheets of the workbook, in workbook order."""
    return [str(n) for n in _excel(raw).sheet_names]


def read_sheet(raw: bytes, sheet: str, header_row: int) -> pd.DataFrame:
    """A sheet as a frame; ``header_row`` is 1-based, as in the page."""
    book = _excel(raw)
    if sheet not in book.sheet_names:
        raise PlanningError("unknown_sheet", f"The workbook has no sheet named '{sheet}'.",
                            {"sheets": [str(n) for n in book.sheet_names]})
    return pd.read_excel(BytesIO(raw), sheet_name=sheet, header=max(0, int(header_row) - 1))


def _plain(value: Any) -> Any:
    """A cell as plain JSON: missing values become None, numpy scalars Python ones."""
    if value is None:
        return None
    item = getattr(value, "item", None)
    if callable(item) and type(value).__module__ == "numpy":
        value = item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if value is pd.NaT:
        return None
    return value


@dataclass
class SheetInfo:
    columns: list[str]
    row_count: int
    preview: list[dict[str, Any]]
    headers_look_misplaced: bool
    suggested_header_row: int
    suggested_mapping: dict[str, str | None] = field(default_factory=dict)


def inspect_sheet(raw: bytes, sheet: str, header_row: int) -> SheetInfo:
    """Columns, first rows, header-row check and suggested mapping of one sheet."""
    frame = read_sheet(raw, sheet, header_row)
    head = pd.read_excel(BytesIO(raw), sheet_name=sheet, header=None, nrows=HEADER_SCAN_ROWS)
    columns = [str(c) for c in frame.columns]
    preview = [{str(k): _plain(v) for k, v in row.items()}
               for row in frame.head(PREVIEW_ROWS).to_dict(orient="records")]
    return SheetInfo(
        columns=columns,
        row_count=int(len(frame)),
        preview=preview,
        headers_look_misplaced=bool(headers_look_misplaced(frame)),
        suggested_header_row=int(suggest_header_row(head)),
        suggested_mapping=suggest_columns(frame),
    )
