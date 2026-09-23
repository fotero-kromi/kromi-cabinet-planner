"""kromi_app.engine.text_utils — small text/numeric utility helpers.

These have no domain knowledge of cabinet planning beyond a thin dependency
on SIZE_VALID (used by `_normalize_size_code` and `first_valid_size`).
"""

from __future__ import annotations

import re

import pandas as pd

from .constants import SIZE_VALID


def norm(s) -> str:
    if not isinstance(s, str):
        return ""
    return s.strip().lower()


def collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def clean_code_cell(value) -> str:
    """Sanitize an article code; integral floats keep their exact integer text.

    A numeric code column containing an empty cell is read by pandas as
    floats, which turned 12345 into "12345.0" in every export (v34.50). All
    other values are cleaned exactly like :func:`clean_text_cell`.
    """
    if isinstance(value, float) and value == value and value not in (float("inf"), float("-inf")):
        if value.is_integer():
            return str(int(value))
    return clean_text_cell(value)


def clean_text_cell(value) -> str:
    """Sanitize a single spreadsheet cell for safe downstream use."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        # pd.isna chokes on some object types — fall through
        pass
    s = str(value)
    # Strip known invisible contaminants
    for bad in ("\u00a0", "\t", "\r", "\n", "\u200b", "\ufeff"):
        s = s.replace(bad, " ")
    # Collapse runs of whitespace and trim
    s = re.sub(r"\s+", " ", s).strip()
    return s


def shorten(s: str, max_chars: int) -> str:
    s = collapse_ws(str(s or ""))
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1] + "…"


def _fmt_seconds(sec: float) -> str:
    sec = max(0.0, float(sec))
    if sec < 60:
        return f"{sec:.0f}s"
    return f"{sec / 60:.1f} min"


def _strip_json_code_fence(text: str) -> str:
    """Defensive cleanup — strict structured output shouldn't return fences,
    but older models or fallback paths sometimes do. Harmless no-op otherwise."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s)
    return s.strip()


def guess_column(df: pd.DataFrame, candidates) -> str | None:
    cols = list(df.columns)
    norm_map = {c: re.sub(r"[^a-z0-9]+", "", str(c).lower()) for c in cols}

    for cand in candidates:
        cand_n = re.sub(r"[^a-z0-9]+", "", cand.lower())
        for col, col_n in norm_map.items():
            if col_n == cand_n:
                return col

    for cand in candidates:
        cand_n = re.sub(r"[^a-z0-9]+", "", cand.lower())
        for col, col_n in norm_map.items():
            if cand_n and cand_n in col_n:
                return col

    return None


def parse_number_series(s: pd.Series, default: float = 0.0) -> pd.Series:
    if s is None:
        return pd.Series(dtype="float64")

    raw = s.astype(str).str.strip()
    raw = raw.str.replace("\u00a0", " ", regex=False)
    raw = raw.str.replace(" ", "", regex=False)

    def _parse_one(x) -> float | None:
        """Accept any input type defensively. Pandas 2.x can return
        mixed object series from astype(str) where some cells remain
        native NaN floats — we guard by always coercing to str first."""
        if x is None:
            return None
        # Handle native NaN floats that slip through astype(str)
        try:
            if isinstance(x, float) and pd.isna(x):
                return None
        except Exception:
            pass
        x = str(x).strip()
        if x == "" or x.lower() in {"nan", "none"}:
            return None

        x = re.sub(r"[^0-9,\.\-]", "", x)

        if x.count(",") > 0 and x.count(".") > 0:
            if x.rfind(",") > x.rfind("."):
                x = x.replace(".", "")
                x = x.replace(",", ".")
            else:
                x = x.replace(",", "")
        elif x.count(",") > 0 and x.count(".") == 0:
            x = x.replace(",", ".")
        else:
            pass

        try:
            return float(x)
        except Exception:
            return None

    parsed = raw.apply(_parse_one)
    # pandas 2.x+: fillna on an object-dtype series followed by astype raises
    return pd.Series(
        [
            float(default) if (v is None or (isinstance(v, float) and pd.isna(v))) else float(v)
            for v in parsed
        ],
        index=parsed.index,
        dtype="float64",
    )


def _normalize_size_code(raw: object) -> str:
    if raw is None:
        return "L"
    text = str(raw).strip().upper()
    text = "".join(ch for ch in text if ch.isalnum())
    if text in SIZE_VALID:
        return text
    for token in sorted(SIZE_VALID, key=len, reverse=True):
        if token in text:
            return token
    return "L"


def contains_any_keyword(text: str, keywords: list[str]) -> bool:
    """Return True if any keyword appears in text."""
    x = norm(text)
    if not x:
        return False
    for k in keywords:
        if len(k) <= 4:
            # Word-boundary match: safer for short French/Italian/Spanish stems
            if re.search(rf"\b{re.escape(k)}\b", x):
                return True
        else:
            if k in x:
                return True
    return False


def first_nonempty(series: pd.Series, default: str = ""):
    for v in series:
        if pd.isna(v):
            continue
        s = str(v).strip()
        if s != "":
            return v
    return default


def first_positive_number(series: pd.Series, default=None):
    for v in series:
        try:
            if pd.notna(v) and float(v) > 0:
                return float(v)
        except Exception:
            pass
    return default


def first_valid_size(series: pd.Series, default=""):
    for v in series:
        s = str(v).strip().upper()
        if s in SIZE_VALID:
            return s
    return default


def parse_year_series(s: pd.Series) -> pd.Series:
    if s is None:
        return pd.Series(dtype="float64")

    def _parse_year(x: object) -> int | None:
        # Missing values arrive as None / NaN / pd.NA. Guard explicitly: since
        # pandas 3.0, Series.astype(str) no longer renders a missing value as
        # the string "nan", so a bare float would otherwise reach .lower()
        # below and raise. Coerce everything else to a stripped string here so
        # int, float and string year columns are all handled uniformly.
        if pd.isna(x):
            return None
        x = str(x).strip()
        if x == "" or x.lower() in {"nan", "none"}:
            return None
        m = re.search(r"(19|20)\d{2}", x)
        if m:
            try:
                return int(m.group(0))
            except Exception:
                return None
        try:
            xf = float(x.replace(",", "."))
            xi = int(xf)
            if 1900 <= xi <= 2100:
                return xi
        except Exception:
            pass
        return None

    return s.apply(_parse_year)
