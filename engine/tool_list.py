"""Building the tool list from the mapped sheets (v34.61).

Moved out of the planner page so every front end turns an uploaded workbook
into the same planning frame. The functions report what the page used to show
as messages (missing columns, dropped blank codes, several sites) as data; the
caller decides how to show them. Behaviour is unchanged from the page.

Order of use, as in the page:
``effective_mapping`` -> ``mapping_collisions`` (must be empty) ->
``build_tool_list`` -> ``resolve_override_scope`` -> ``assign_supply_points``
(with a Program mapping) -> ``preprocessing.prepare_planning_base`` ->
``add_classification_audit_columns`` -> heuristics -> ``plan.run_plan`` ->
``apply_export_display_columns``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from .cabinet_math import SPECIAL_KTC_REASON
from .routing_rules import classify_standard_special, is_regrind
from .sizing_factors import LISTING_PPE, LISTING_TOOLS
from .takeover import CATEGORY_TEXT_COL, STOCK_COL
from .text_utils import clean_code_cell, clean_text_cell, parse_number_series, parse_year_series


@dataclass(frozen=True)
class ColumnMapping:
    """Source column per planning field; ``None`` = not mapped."""

    code: str
    description: str
    consumption: Optional[str] = None
    description_2: Optional[str] = None
    category: Optional[str] = None
    supplier_code: Optional[str] = None
    size: Optional[str] = None
    pack_units: Optional[str] = None
    year: Optional[str] = None
    program: Optional[str] = None
    restocking: Optional[str] = None
    site: Optional[str] = None
    std_special: Optional[str] = None
    dimensions: Optional[str] = None
    regrind: Optional[str] = None
    system_type: Optional[str] = None
    stock: Optional[str] = None


#: (field, planning column) in the order the page builds its rename map.
_RENAME_ORDER: Tuple[Tuple[str, str], ...] = (
    ("code", "Code"), ("description", "Description"), ("consumption", "Consumption_pcs"),
    ("supplier_code", "SupplierCode"), ("description_2", "Description_2"),
    ("category", "ProductCategory"), ("size", "SizeCategory"), ("pack_units", "PackUnits"),
    ("year", "Year"), ("program", "Program"), ("restocking", "Restocking"), ("site", "Site"),
    ("std_special", "StdSpecial"), ("dimensions", "PackageDimensions"),
    ("regrind", "Regrind"), ("system_type", "SystemTyp"), ("stock", STOCK_COL),
)

#: (field, name shown in the conflict message) in the page's check order.
_COLLISION_ORDER: Tuple[Tuple[str, str], ...] = (
    ("code", "Code"), ("description", "Description"), ("description_2", "Description_2"),
    ("consumption", "Consumption pcs"), ("category", "ProductCategory"),
    ("supplier_code", "SupplierCode"), ("size", "SizeCategory"), ("pack_units", "PackUnits"),
    ("year", "Year"), ("program", "Program"), ("restocking", "Restocking"), ("site", "Site"),
    ("std_special", "StdSpecial"), ("dimensions", "PackageDimensions"),
    ("regrind", "Regrind"), ("system_type", "SystemTyp"), ("stock", "Stock"),
)

#: A sheet without these mapped columns would plan with no code or no demand.
CRITICAL_FIELDS = frozenset({"Code", "Consumption_pcs"})

_TEXT_COLUMNS = ("Code", "Description", "Description_2", "SupplierCode", "ProductCategory",
                 "SizeCategory", "Program", "Site", "StdSpecial", "PackageDimensions",
                 "Regrind", "SystemTyp")

#: Classification provenance columns every run starts with, in this order.
CLASSIFICATION_AUDIT_COLUMNS: Dict[str, object] = {
    "ProductCategory_Source": "",
    "ProductCategory_AI_Model": "",
    "ProductCategory_AI_TimestampUTC": "",
    "ProductCategory_AI_Consulted": False,
    "ProductCategory_Evidence": "",
    "ProductCategory_Confidence": "",
    "ProductCategory_Reason": "",
    "ToolClass": "",
    "ToolClass_Source": "",
    "SizeCategory_Source": "",
    "SizeCategory_AI_Model": "",
    "SizeCategory_AI_TimestampUTC": "",
    "SizeCategory_AI_Consulted": False,
    "PackUnits_Source": "",
    "PackUnits_AI_Model": "",
    "PackUnits_AI_TimestampUTC": "",
    "PackUnits_AI_Consulted": False,
    "SystemCategory_Reason": "",
}


def effective_mapping(mapping: ColumnMapping, *, use_description_2: bool) -> ColumnMapping:
    """The mapping as planned: Description 2 is ignored when switched off."""
    return mapping if use_description_2 else replace(mapping, description_2=None)


def mapping_collisions(mapping: ColumnMapping) -> Dict[str, List[str]]:
    """Source columns mapped to more than one field, with those fields."""
    by_column: Dict[str, List[str]] = {}
    for name, label in _COLLISION_ORDER:
        column = getattr(mapping, name)
        if column:
            by_column.setdefault(column, []).append(label)
    return {col: fields for col, fields in by_column.items() if len(fields) > 1}


def rename_map(mapping: ColumnMapping) -> Dict[str, str]:
    """Source column -> planning column for every mapped field."""
    out: Dict[str, str] = {}
    for name, target in _RENAME_ORDER:
        column = getattr(mapping, name)
        if column or name in ("code", "description"):
            out[column] = target
    return out


@dataclass(frozen=True)
class MissingColumns:
    """Mapped columns a sheet does not contain: (source, planning column) pairs."""

    listing: str
    missing: Tuple[Tuple[str, str], ...]

    @property
    def critical(self) -> Tuple[str, ...]:
        return tuple(dst for _src, dst in self.missing if dst in CRITICAL_FIELDS)


@dataclass
class ToolList:
    """The planning frame and what was noticed while building it."""

    work: pd.DataFrame
    missing: Tuple[MissingColumns, ...] = ()
    dropped_empty_codes: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def blocking(self) -> Tuple[MissingColumns, ...]:
        """Sheets that lack a code or consumption column: planning must stop."""
        return tuple(m for m in self.missing if m.critical)


def prepare_listing(raw_df: Optional[pd.DataFrame], listing: str,
                    renames: Mapping[str, str]) -> Optional[pd.DataFrame]:
    """Rename, tag and clean one sheet (the input frame is not changed)."""
    if raw_df is None:
        return None
    out = raw_df.copy()
    out.rename(columns={s: d for s, d in renames.items() if s in out.columns}, inplace=True)
    out["Listing"] = listing
    for c in _TEXT_COLUMNS:
        if c in out.columns:
            # Codes: integral floats keep their integer text (v34.50).
            out[c] = out[c].map(clean_code_cell if c == "Code" else clean_text_cell)
    return out


def _missing(raw_df: pd.DataFrame, renames: Mapping[str, str]) -> Tuple[Tuple[str, str], ...]:
    present = set(raw_df.columns)
    return tuple((src, dst) for src, dst in renames.items() if src not in present)


def build_tool_list(df_tools: Optional[pd.DataFrame], df_ppe: Optional[pd.DataFrame],
                    mapping: ColumnMapping, *, use_description_2: bool) -> ToolList:
    """The planning frame from the Tools and (optional) PPE sheets.

    ``mapping`` is the effective mapping (see :func:`effective_mapping`). Rows
    with a blank code are dropped and returned in ``dropped_empty_codes``;
    missing mapped columns are reported per sheet (see ``ToolList.blocking``).
    """
    renames = rename_map(mapping)
    missing: List[MissingColumns] = []
    frames: List[pd.DataFrame] = []
    for raw, tag in ((df_tools, LISTING_TOOLS), (df_ppe, LISTING_PPE)):
        if raw is None:
            continue
        gaps = _missing(raw, renames)
        if gaps:
            missing.append(MissingColumns(tag, gaps))
        prepped = prepare_listing(raw, tag, renames)
        if prepped is not None:
            frames.append(prepped)

    work = pd.concat(frames, ignore_index=True)

    dropped = work.iloc[0:0]
    if "Code" in work.columns:
        empty_code = work["Code"].map(clean_text_cell).eq("")
        if int(empty_code.sum()) > 0:
            dropped = work.loc[empty_code]
            work = work.loc[~empty_code].reset_index(drop=True)

    for c in ("Code", "Description", "Consumption_pcs"):
        if c not in work.columns:
            work[c] = ""
    for c in ("SupplierCode", "Description_2", "ProductCategory", "SizeCategory"):
        if c not in work.columns:
            work[c] = ""
    if not use_description_2:
        work["Description_2"] = ""
    # Regrind flag (YES/NO) floors reground Helix items to two spirals.
    if "Regrind" in work.columns:
        work["Regrind"] = work["Regrind"].map(is_regrind)
    else:
        work["Regrind"] = False
    # System type stays raw text here; it is applied after routing.
    if "SystemTyp" not in work.columns:
        work["SystemTyp"] = ""
    work["Routing_Pinned"] = False
    if "PackUnits" not in work.columns:
        work["PackUnits"] = ""
    if "Year" not in work.columns:
        work["Year"] = pd.NA
    if "Program" not in work.columns:
        work["Program"] = ""
    if "Site" not in work.columns:
        work["Site"] = ""

    work["Consumption_pcs"] = parse_number_series(work["Consumption_pcs"], default=0.0)
    work["PackUnits"] = parse_number_series(work["PackUnits"], default=float("nan"))
    # Takeover (v34.56): stock in pieces (missing or negative counts as none)
    # and, with a category column, its raw text. Only with a stock column.
    if mapping.stock and STOCK_COL in work.columns:
        work[STOCK_COL] = parse_number_series(work[STOCK_COL], default=0.0).clip(lower=0.0)
        if mapping.category:
            work[CATEGORY_TEXT_COL] = work["ProductCategory"].map(clean_text_cell)
    work["Year"] = parse_year_series(work["Year"])
    return ToolList(work=work, missing=tuple(missing), dropped_empty_codes=dropped)


def scope_value(value: Optional[str]) -> str:
    """A customer or site entry as used for the override scope."""
    return (value or "").strip() or "default"


def resolve_override_scope(customer: Optional[str], site: Optional[str], work: pd.DataFrame,
                           *, site_mapped: bool) -> Tuple[str, str, List[str]]:
    """(customer, site, site values found in the file).

    A mapped Site column with exactly one value sets the site; with several
    values the entered site is kept.
    """
    eff_customer, eff_site = scope_value(customer), scope_value(site)
    sites: List[str] = []
    if site_mapped and "Site" in work.columns:
        sites = [s for s in work["Site"].astype(str).str.strip().unique()
                 if s and s.lower() not in {"", "nan", "none"}]
        if len(sites) == 1:
            eff_site = sites[0]
    return eff_customer, eff_site, sites


def distinct_programs(work: pd.DataFrame) -> List[str]:
    """The programmes in the file, sorted, with a blank programme last."""
    programs = sorted(p for p in work["Program"].astype(str).unique() if p.strip() != "")
    if (work["Program"].astype(str).str.strip() == "").any():
        programs.append("")
    return programs


def unassigned_programs(programs: Sequence[str], program_to_sp: Mapping[str, int]) -> List[str]:
    return [p for p in programs if p not in program_to_sp]


def assign_supply_points(work: pd.DataFrame, program_to_sp: Mapping[str, int]) -> int:
    """Set ``SupplyPoint`` from the Program column, in place, before dedup.

    Returns how many rows matched no programme and went to supply point 1.
    """
    work["SupplyPoint"] = work["Program"].astype(str).map(program_to_sp).astype("Int64")
    missing = work["SupplyPoint"].isna()
    n_default = int(missing.sum())
    if n_default:
        work.loc[missing, "SupplyPoint"] = 1
    work["SupplyPoint"] = work["SupplyPoint"].astype(int)
    return n_default


def add_classification_audit_columns(work: pd.DataFrame) -> None:
    """Add the classification provenance columns, in place."""
    for column, default in CLASSIFICATION_AUDIT_COLUMNS.items():
        work[column] = default


def apply_export_display_columns(work: pd.DataFrame) -> None:
    """The display columns the exports carry, in place, after the plan.

    With a Standard/Special column: ``Std_Special`` and ``Forced_to_KTC``. A
    boolean ``Restockable`` becomes "Yes" / "" (guarded, so a second pass
    changes nothing).
    """
    if "StdSpecial" in work.columns:
        labels = {"standard": "Standard", "special": "Special"}
        work["Std_Special"] = work["StdSpecial"].map(
            lambda v: labels.get(classify_standard_special(v), ""))
        work["Forced_to_KTC"] = (
            work["SystemCategory_Reason"].astype(str) == SPECIAL_KTC_REASON
        ).map({True: "Yes", False: ""})
    if "Restockable" in work.columns and work["Restockable"].dtype == bool:
        work["Restockable"] = work["Restockable"].map({True: "Yes", False: ""})
