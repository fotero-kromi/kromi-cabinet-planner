"""Export safety: customer text never becomes a live spreadsheet formula (v34.48).

Uploaded customer workbooks are semi-trusted input. openpyxl stores any string
that starts with "=" as a formula, so a description such as
``=HYPERLINK("http://...", "click")`` used to leave the app as a working
formula in the plan workbook and the Article setup workbook. The functions
below keep every exported value visibly identical and only change how it is
stored or quoted:

* :func:`neutralize_formula_cells` re-types formula cells of an openpyxl
  workbook as plain text. The app writes no intentional formulas, so every
  formula cell in an export came from data. If an intentional formula is ever
  needed, write it after this call.
* :func:`csv_safe_frame` applies the standard CSV protection (a leading
  apostrophe) to text starting with = + - @ tab or carriage return, because
  Excel evaluates such CSV cells. Plain numbers such as "-5" and lone
  placeholders such as "-" are left untouched.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

#: First characters that make Excel treat a CSV cell as a formula.
FORMULA_TRIGGERS: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")

_PLAIN_NUMBER = re.compile(r"^[+-]?(\d+([.,]\d*)?|[.,]\d+)([eE][+-]?\d+)?$")


def neutralize_formula_cells(workbook: Any) -> int:
    """Store every formula-typed cell of ``workbook`` as text; return how many.

    The cell value (the visible text) is unchanged; only its data type moves
    from formula ("f") to string ("s"), so Excel shows the text instead of
    evaluating it.
    """
    n = 0
    for ws in workbook.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    cell.data_type = "s"
                    n += 1
    return n


def is_formula_like(value: Any) -> bool:
    """True when ``value`` is text that a spreadsheet would evaluate."""
    if not isinstance(value, str) or len(value) < 2:
        return False
    if not value.startswith(FORMULA_TRIGGERS):
        return False
    return not _PLAIN_NUMBER.match(value.strip())


def csv_safe_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` whose formula-like text cells are apostrophe-quoted.

    Only object (text) columns are inspected; numeric columns and non-string
    cells pass through unchanged. Never mutates ``df``.
    """
    out = df.copy()
    for col in out.columns:
        if out[col].dtype != object:
            continue
        out[col] = out[col].map(lambda v: "'" + v if is_formula_like(v) else v)
    return out
