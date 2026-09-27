"""The settings of one planning run as the API receives them.

Every field maps one to one onto the engine's ``RunSettings`` (planning) and
``ColumnMapping`` (columns); defaults and limits come from
``engine.planning_defaults``, so the Streamlit app and this app cannot start
from different values. Unknown fields are refused, so a misspelt setting is an
error instead of being silently ignored.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from engine.planning_defaults import (
    CALC_MODE_LABELS,
    DEDUP_MODE_LABELS,
    DEFAULTS,
    LIMITS,
    OP_STANDARD,
    SP_MODE_LABELS,
    YEAR_MODE_LABELS,
)
from engine.run_settings import RunSettings
from engine.tool_list import ColumnMapping


def _limited(name: str, default: Any) -> Any:
    low, high = LIMITS[name]
    return Field(default=default, ge=low, le=high)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ColumnMappingIn(_Strict):
    """Source column per planning field; ``None`` = not mapped."""

    code: str = Field(min_length=1)
    description: str = Field(min_length=1)
    consumption: str = Field(min_length=1)
    description_2: str | None = None
    category: str | None = None
    supplier_code: str | None = None
    size: str | None = None
    pack_units: str | None = None
    year: str | None = None
    program: str | None = None
    restocking: str | None = None
    site: str | None = None
    std_special: str | None = None
    dimensions: str | None = None
    regrind: str | None = None
    system_type: str | None = None
    stock: str | None = None

    def to_engine(self) -> ColumnMapping:
        return ColumnMapping(**self.model_dump())


MachineRow = tuple[int, int, int, int, int, int]


class PlanningIn(_Strict):
    """The planning controls; field names and defaults are ``RunSettings``'."""

    use_description_2: bool = DEFAULTS.use_description_2
    year_mode: str = DEFAULTS.year_mode
    dedup_mode: str = DEFAULTS.dedup_mode
    ktc_threshold: float = _limited("ktc_threshold", DEFAULTS.ktc_threshold)
    optional_thresholds_active: bool = False
    per_class_thresholds: list[tuple[str, Annotated[float, Field(ge=0.0)]]] = []
    insert_pack_units: int = _limited("insert_pack_units", DEFAULTS.insert_pack_units)
    helix_threshold: float = _limited("helix_threshold", DEFAULTS.helix_threshold)
    consumption_months: float = _limited("consumption_months", DEFAULTS.consumption_months)
    helix_overfill_factor: float = _limited("helix_overfill_factor",
                                            DEFAULTS.helix_overfill_factor)
    min_carousel_allocation: int = _limited("min_carousel_allocation",
                                            DEFAULTS.min_carousel_allocation)
    coverage_days: int = _limited("coverage_days", DEFAULTS.coverage_days)
    coverage_days_special: int = _limited("coverage_days_special",
                                          DEFAULTS.coverage_days_special)
    special_ktc: bool = DEFAULTS.special_ktc
    carousel_reserve_factor: float = _limited("carousel_reserve_factor",
                                              DEFAULTS.carousel_reserve_factor)
    carousel_fill_ceiling: float = _limited("carousel_fill_ceiling",
                                            DEFAULTS.carousel_fill_ceiling)
    enable_rebalancer: bool = DEFAULTS.enable_rebalancer
    underuse_threshold_pct: float = _limited("underuse_threshold_pct",
                                             DEFAULTS.underuse_threshold_pct)
    capacity_buffer_pct: float = _limited("capacity_buffer_pct", DEFAULTS.capacity_buffer_pct)
    restock_categories: list[str] = []
    pack_hint_extraction: bool = DEFAULTS.pack_hint_extraction
    bulk_routing: bool = DEFAULTS.bulk_routing
    force_screws_kanban: bool = DEFAULTS.force_screws_kanban
    n_supply_points: int = _limited("n_supply_points", DEFAULTS.n_supply_points)
    sp_mode: str = DEFAULTS.sp_mode
    calc_mode: str = DEFAULTS.calc_mode
    op_mode: str = DEFAULTS.op_mode
    max_carousels: int = _limited("max_carousels", DEFAULTS.max_carousels)
    fixed_headroom_pct: float = _limited("fixed_headroom_pct", DEFAULTS.fixed_headroom_pct)
    fixed_allow_spill: bool = DEFAULTS.fixed_allow_spill
    fixed_stock_promotion: bool = DEFAULTS.fixed_stock_promotion
    fixed_stock_months: float = _limited("fixed_stock_months", DEFAULTS.fixed_stock_months)
    fixed_machines: list[MachineRow] = []

    @field_validator("year_mode")
    @classmethod
    def _year(cls, v: str) -> str:
        return _choice(v, YEAR_MODE_LABELS)

    @field_validator("dedup_mode")
    @classmethod
    def _dedup(cls, v: str) -> str:
        return _choice(v, DEDUP_MODE_LABELS)

    @field_validator("sp_mode")
    @classmethod
    def _sp(cls, v: str) -> str:
        return _choice(v, SP_MODE_LABELS)

    @field_validator("calc_mode")
    @classmethod
    def _calc(cls, v: str) -> str:
        return _choice(v, CALC_MODE_LABELS)

    @field_validator("op_mode")
    @classmethod
    def _op(cls, v: str) -> str:
        if v != OP_STANDARD:
            raise ValueError("only the standard operation mode is available in this version")
        return v

    def to_engine(self) -> RunSettings:
        data = self.model_dump()
        data["per_class_thresholds"] = tuple(
            sorted((str(k), float(v)) for k, v in self.per_class_thresholds))
        data["restock_categories"] = tuple(self.restock_categories)
        data["fixed_machines"] = tuple(tuple(row) for row in self.fixed_machines)
        return RunSettings(**data)


def _choice(value: str, labels: dict[str, str]) -> str:
    if value not in labels:
        raise ValueError(f"must be one of {sorted(labels)}")
    return value


class ScopeIn(_Strict):
    """Whose run this is (Run_Metadata, override scope) and the numbering KTC-ID."""

    customer: str = ""
    site: str = ""
    ktc_id: str = DEFAULTS.ktc_id
    apply_overrides: bool = DEFAULTS.apply_overrides


class ExportIn(_Strict):
    include_planogram: bool = DEFAULTS.include_planogram
    include_technical: bool = DEFAULTS.include_technical


class RunRequest(_Strict):
    """Everything one planning run needs besides the workbook itself."""

    sheet: str = Field(min_length=1)
    header_row: int = _limited("header_row", DEFAULTS.header_row)
    mapping: ColumnMappingIn
    planning: PlanningIn = PlanningIn()
    scope: ScopeIn = ScopeIn()
    export: ExportIn = ExportIn()
    program_to_sp: dict[str, Annotated[int, Field(ge=1)]] = {}

    @model_validator(mode="after")
    def _programs_fit_the_supply_points(self) -> RunRequest:
        too_high = {p: sp for p, sp in self.program_to_sp.items()
                    if sp > self.planning.n_supply_points}
        if too_high:
            raise ValueError(f"supply point above the number of supply points: {too_high}")
        return self
