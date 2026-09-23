"""kromi_app.engine.preprocessing — planning base prep.

Single function: prepare_planning_base. Handles year filtering (latest-only
or all-years) plus optional deduplication on (Code) or (Code+SupplierCode),
with optional Listing and SupplyPoint as additional dedup keys.

Pure function with no UI/IO. Depends on engine.text_utils (first_nonempty,
first_positive_number, first_valid_size) and engine.classification
(first_valid_product_category_text).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .classification import first_valid_product_category_text
from .text_utils import (
    first_nonempty,
    first_positive_number,
    first_valid_size,
)


def _normalize_site(v: Any) -> str:
    """Normalize a Site label for dedup keying (C2): fold case and whitespace,
    and treat numeric-equivalent labels as one site so int ``1``, float ``1.0``
    and the strings ``"1"`` / ``"1.0"`` all key to ``"1"``. The original value
    is preserved separately for display; only the key uses this form."""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    if s == "":
        return ""
    # Integer-valued numbers (incl. "1.0") collapse to a canonical integer
    # string so int/float/string spellings of the same code match.
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except (ValueError, TypeError):
        pass
    return s.casefold()


def prepare_planning_base(
    df: pd.DataFrame,
    dedup_mode: str,
    year_mode: str,
    has_year: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    base = df.copy()

    # Negative consumption guard: ERP extracts can carry credit / return
    # artifacts as negative period quantities. A negative consumption is
    # meaningless for sizing and, worse, the dedup aggregation below would
    # silently SUM it into other rows of the same key, corrupting a total that
    # then looks plausible. Clamp to zero before anything else and surface the
    # count; when nothing is negative the frame is not written to at all, so
    # clean data passes through with identical values and dtypes.
    _neg_clamped = 0
    if "Consumption_pcs" in base.columns:
        _cons_num = pd.to_numeric(base["Consumption_pcs"], errors="coerce")
        _neg_mask = _cons_num < 0
        _neg_clamped = int(_neg_mask.sum())
        if _neg_clamped:
            base.loc[_neg_mask, "Consumption_pcs"] = 0.0

    def _cons_sum(frame: pd.DataFrame) -> float:
        if "Consumption_pcs" not in frame.columns:
            return 0.0
        return float(pd.to_numeric(frame["Consumption_pcs"], errors="coerce").fillna(0.0).sum())

    info: dict[str, Any] = {
        "negative_consumption_clamped": _neg_clamped,
        "rows_before": len(base),
        "rows_after_year_filter": len(base),
        "rows_after_dedup": len(base),
        "latest_year_used": None,
        "dedup_groups": None,
        "consumption_before": _cons_sum(base),
        "consumption_after_year": _cons_sum(base),
        "consumption_after_dedup": _cons_sum(base),
    }

    # Accept the internal value and the UI label, and fold case/spacing, so a
    # caller passing the wrong spelling can never silently skip the filter.
    _ym = str(year_mode or "").strip().lower().replace(" ", "_")
    _latest_aliases = {"latest_year_only", "keep_latest_year_only", "latest", "latest_only"}
    if has_year and _ym in _latest_aliases:
        valid_year = base["Year"].notna()
        if valid_year.any():
            latest_year = int(base.loc[valid_year, "Year"].max())
            base = base[(base["Year"].isna()) | (base["Year"] == latest_year)].copy()
            info["latest_year_used"] = latest_year
            info["rows_after_year_filter"] = len(base)
    info["consumption_after_year"] = _cons_sum(base)

    if dedup_mode == "none":
        info["rows_after_dedup"] = len(base)
        info["consumption_after_dedup"] = _cons_sum(base)
        return base, info

    key_cols = ["Code"] if dedup_mode == "code" else ["Code", "SupplierCode"]

    # If Listing column is present, include it in the dedup key so that a
    # shared code across Tools and PPE listings is NOT collapsed into one row.
    if "Listing" in base.columns:
        key_cols = ["Listing"] + key_cols

    # if a SupplyPoint column is already assigned (from the program→SP
    if "SupplyPoint" in base.columns:
        key_cols = key_cols + ["SupplyPoint"]

    # Site-aware dedup (HMA-3) + Site normalization (C2): when a Site column is
    # present, key on a NORMALIZED form so the same physical site is never split
    # by case, whitespace, or numeric-equivalent labels (int 1 vs float 1.0 vs
    # "1"/"1.0"). The original Site is preserved for display via aggregation
    # below. For a single-site dataset this is a no-op.
    site_key_col = None
    if "Site" in base.columns:
        site_key_col = "_site_key"
        base[site_key_col] = base["Site"].map(_normalize_site)
        key_cols = key_cols + [site_key_col]

    for c in key_cols:
        if c not in base.columns:
            base[c] = ""

    # Deterministic dedup (HMA-2): the aggregations below keep the first
    # matching row's value for conflicting attributes (e.g. a code whose
    # ProductCategory or PackUnits drifted across years). Sort to a fixed order
    # first so the result never depends on input row order. Latest year wins,
    # then highest consumption, then a stable content order.
    _sort_cols, _ascending = [], []
    if "Year" in base.columns:
        _sort_cols.append("Year"); _ascending.append(False)
    if "Consumption_pcs" in base.columns:
        _sort_cols.append("Consumption_pcs"); _ascending.append(False)
    for _c in ("ProductCategory", "PackUnits", "SizeCategory", "Description"):
        if _c in base.columns:
            _sort_cols.append(_c); _ascending.append(True)
    if _sort_cols:
        base = base.sort_values(
            by=_sort_cols, ascending=_ascending, kind="mergesort", na_position="last"
        ).reset_index(drop=True)

    # Preserve Program column in a compact "all programmes that contributed
    agg_spec: dict[str, Any] = {
        "Description": first_nonempty,
        "Description_2": first_nonempty,
        "Consumption_pcs": "sum",
        "PackUnits": lambda s: first_positive_number(s, default=float("nan")),
        # The provided text is kept (v34.56); the boundary normalizes it.
        "ProductCategory": lambda s: first_valid_product_category_text(s, default=""),
        "SizeCategory": lambda s: first_valid_size(s, default=""),
    }
    # Year is only aggregated when the column exists; including it
    # unconditionally would raise KeyError on a frame without a Year column.
    if "Year" in base.columns:
        agg_spec["Year"] = "max"
    if "Program" in base.columns:
        agg_spec["Program"] = lambda s: ", ".join(
            sorted({str(x) for x in s if str(x).strip() != ""})
        )[:200]

    # Preserve optional source-mapped columns the planner uses downstream but
    # that are not dedup keys. Without this, columns like PackageDimensions
    # (the optional dimensional fit-check signal) are silently dropped by the
    # groupby below — the fit-check then never engages because the column
    # the page looks for is gone. StdSpecial (the standard/special coverage
    # signal) and SupplierCode (shown in exports, used as a classification
    # hint) are preserved here for the same reason.
    for opt_col in ("PackageDimensions", "Site", "StdSpecial", "SupplierCode", "Regrind", "SystemTyp", "Restocking",
                    "ProductCategory_Text"):
        if opt_col in base.columns and opt_col not in key_cols:
            agg_spec[opt_col] = first_nonempty
    # Takeover stock (v34.56, only when a stock column is mapped): the pieces
    # of every merged row belong to the article, so they add up.
    if "Stock_pcs" in base.columns:
        agg_spec["Stock_pcs"] = "sum"

    # Legible precondition (audit M2): the aggregation below requires the
    # prepared planning columns; a caller handing over a raw or mis-mapped
    # frame gets a message naming what is missing instead of a pandas
    # KeyError from deep inside the groupby.
    _needed = list(dict.fromkeys(list(key_cols) + list(agg_spec)))
    _missing = [c for c in _needed if c not in base.columns]
    if _missing:
        raise ValueError(
            "prepare_planning_base requires the prepared planning columns; "
            f"missing: {_missing}"
        )

    grouped = base.groupby(key_cols, dropna=False, as_index=False).agg(agg_spec)

    # Drop the internal normalized-site key; the original Site is preserved via
    # aggregation above for display.
    if site_key_col is not None and site_key_col in grouped.columns:
        grouped = grouped.drop(columns=[site_key_col])

    # Conflict detection: when rows that collapse into one group disagree on an
    # attribute that drives classification/sizing (ProductCategory, PackUnits),
    # first_nonempty/first_valid keep the first row's value, so the result
    # depends on input row order. Count such groups so the page can warn — the
    # consumption SUM is still conserved, but the kept attributes are not
    # order-independent.
    def _n_conflicting(col: str, positive_only: bool = False) -> int:
        if col not in base.columns:
            return 0
        def _distinct(s: "pd.Series") -> int:
            vals = s.dropna()
            if positive_only:
                nums = pd.to_numeric(vals, errors="coerce")
                vals = nums[nums > 0]
            else:
                vals = vals[vals.astype(str).str.strip() != ""]
            return vals.nunique()
        return int((base.groupby(key_cols, dropna=False)[col].apply(_distinct) > 1).sum())

    info["dedup_conflict_groups"] = {
        "ProductCategory": _n_conflicting("ProductCategory"),
        "PackUnits": _n_conflicting("PackUnits", positive_only=True),
    }

    # Stale latest-year metadata diagnostic (B4): count groups where the latest
    # year's value is blank but an earlier year has one, so first_nonempty /
    # first_valid retains the EARLIER year's value. Detection only — the value
    # is still retained; this just makes the fallback visible.
    def _n_stale_latest(col: str) -> int:
        # An empty groupby's .apply(...).sum() returns a Series, not a scalar,
        # so int(...) below would raise. A 0-row base has no stale groups.
        if base.empty or "Year" not in base.columns or col not in base.columns:
            return 0
        def _stale(g: "pd.DataFrame") -> bool:
            years = pd.to_numeric(g["Year"], errors="coerce")
            if years.notna().sum() == 0:
                return False
            latest = years.max()
            vals = g[col].astype(str).str.strip()
            latest_blank = (vals[years == latest] == "").all()
            earlier_filled = (vals[years < latest] != "").any()
            return bool(latest_blank and earlier_filled)
        # Select only the columns _stale needs (Year + col). They are never
        # group keys (key_cols is Code/SupplierCode/Listing/SupplyPoint/Site),
        # so this is the "explicitly select columns after groupby" path that
        # silences the grouping-column FutureWarning without relying on
        # include_groups= (which only exists in pandas >= 2.2).
        return int(
            base.groupby(key_cols, dropna=False)[["Year", col]].apply(_stale).sum()
        )

    info["stale_latest_year_groups"] = {
        "ProductCategory": _n_stale_latest("ProductCategory"),
        "SizeCategory": _n_stale_latest("SizeCategory"),
    }
    info["dedup_groups"] = len(grouped)
    info["rows_after_dedup"] = len(grouped)
    info["consumption_after_dedup"] = _cons_sum(grouped)
    return grouped, info


_RESTOCK_TRUE = {"yes", "y", "ja", "j", "1", "x", "true", "wahr"}
_RESTOCK_FALSE = {"no", "n", "nein", "0", "false", "falsch", ""}


def normalize_restock_flag(raw) -> bool | None:
    """Normalize a mapped restocking yes/no cell (v34.24).

    Returns True or False for the recognized German and English spellings and
    None for anything else, so the caller can count unknown values as a data
    quality signal instead of guessing. None and empty cells are False: an
    unfilled cell means not restockable, an unrecognized word means the file
    needs a look.
    """
    if raw is None or (isinstance(raw, float) and raw != raw):
        return False  # None and NaN are empty cells: not restockable
    s = str(raw).strip().lower()
    if s in _RESTOCK_TRUE:
        return True
    if s in _RESTOCK_FALSE:
        return False
    return None
