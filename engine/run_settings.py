"""The typed settings of one planning run and the rules that turn them into the
planner's parameters (v34.62).

Moved out of the planner page so every front end plans with the same rules.
``RunSettings`` holds what the user chooses (every default from
``planning_defaults.DEFAULTS``); ``effective_settings`` applies the mode rules
the page's controls used to apply; ``build_plan_params`` produces the frozen
``PlanParams`` that ``plan.run_plan`` takes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Optional, Sequence, Tuple

import pandas as pd

from .fixed_config import FIXED_MODE
from .plan import BaseCounts, PlanParams
from .plan_config import PlanConfig
from .planning_defaults import CALC_COMBINED, CALC_SEPARATED, DEFAULTS, OP_NUMBERING_ONLY
from .sizing_factors import SP_MODE_PARTITION, SP_MODE_REPLICATE
from .tool_list import ColumnMapping

#: One fixed-configuration row: (supply point, Helix, Carousel, Locker A, B, C).
MachineRow = Tuple[int, int, int, int, int, int]


@dataclass(frozen=True)
class RunSettings:
    """What the user chooses for one planning run (choices as tokens)."""

    # Planning base
    use_description_2: bool = DEFAULTS.use_description_2
    year_mode: str = DEFAULTS.year_mode
    dedup_mode: str = DEFAULTS.dedup_mode
    # Routing and sizing
    ktc_threshold: float = DEFAULTS.ktc_threshold
    optional_thresholds_active: bool = False
    per_class_thresholds: Tuple[Tuple[str, float], ...] = ()
    insert_pack_units: int = DEFAULTS.insert_pack_units
    helix_threshold: float = DEFAULTS.helix_threshold
    consumption_months: float = DEFAULTS.consumption_months
    helix_overfill_factor: float = DEFAULTS.helix_overfill_factor
    min_carousel_allocation: int = DEFAULTS.min_carousel_allocation
    coverage_days: int = DEFAULTS.coverage_days
    coverage_days_special: int = DEFAULTS.coverage_days_special
    special_ktc: bool = DEFAULTS.special_ktc
    carousel_reserve_factor: float = DEFAULTS.carousel_reserve_factor
    carousel_fill_ceiling: float = DEFAULTS.carousel_fill_ceiling
    enable_rebalancer: bool = DEFAULTS.enable_rebalancer
    underuse_threshold_pct: float = DEFAULTS.underuse_threshold_pct
    capacity_buffer_pct: float = DEFAULTS.capacity_buffer_pct
    restock_categories: Tuple[str, ...] = ()
    # Vend-mode controls
    pack_hint_extraction: bool = DEFAULTS.pack_hint_extraction
    bulk_routing: bool = DEFAULTS.bulk_routing
    force_screws_kanban: bool = DEFAULTS.force_screws_kanban
    # Supply points and listings
    n_supply_points: int = DEFAULTS.n_supply_points
    sp_mode: str = DEFAULTS.sp_mode
    calc_mode: str = DEFAULTS.calc_mode
    # Operation mode
    op_mode: str = DEFAULTS.op_mode
    max_carousels: int = DEFAULTS.max_carousels
    fixed_headroom_pct: float = DEFAULTS.fixed_headroom_pct
    fixed_allow_spill: bool = DEFAULTS.fixed_allow_spill
    fixed_stock_promotion: bool = DEFAULTS.fixed_stock_promotion
    fixed_stock_months: float = DEFAULTS.fixed_stock_months
    fixed_machines: Tuple[MachineRow, ...] = ()


def sp_mode_from_label(label: str) -> str:
    """The supply-point mode of a page label (anything but "Replicate..." partitions)."""
    return SP_MODE_REPLICATE if str(label).startswith("Replicate") else SP_MODE_PARTITION


def calc_mode_from_label(label: str) -> str:
    """The Tools + PPE handling of a page label (only "Separated..." separates)."""
    return CALC_SEPARATED if str(label).startswith("Separated") else CALC_COMBINED


def effective_settings(s: RunSettings, *, stdspecial_mapped: bool,
                       both_listings: bool) -> RunSettings:
    """The settings as planned, after the mode rules.

    * Without a Standard/Special column, special tools use the standard coverage.
    * One listing, or the fixed configuration, always plans Tools + PPE combined.
    * The fixed configuration keeps no buffer, fills carousels to 1.0 and does
      not consolidate cabinets (the headroom takes that role); outside it, the
      machines, the headroom and the stock promotion do not apply.
    * Per-class thresholds apply only while they are switched on.
    """
    changes: dict = {}
    if not stdspecial_mapped:
        changes["coverage_days_special"] = s.coverage_days
    if s.op_mode == FIXED_MODE:
        changes.update(carousel_fill_ceiling=1.0, enable_rebalancer=False,
                       capacity_buffer_pct=0.0, calc_mode=CALC_COMBINED)
    else:
        changes.update(fixed_headroom_pct=0.0, fixed_machines=(), fixed_allow_spill=True,
                       fixed_stock_promotion=False)
        if not both_listings:
            changes["calc_mode"] = CALC_COMBINED
    if not s.optional_thresholds_active:
        changes["per_class_thresholds"] = ()
    return replace(s, **changes)


def plan_config(s: RunSettings) -> PlanConfig:
    """The sizing factors of the run."""
    return PlanConfig(
        helix_overfill_factor=float(s.helix_overfill_factor),
        carousel_reserve_factor=float(s.carousel_reserve_factor),
        carousel_fill_ceiling=float(s.carousel_fill_ceiling),
    )


def build_plan_params(s: RunSettings, *, mapping: ColumnMapping, base_info: Mapping,
                      manual_size_fixes: Optional[Mapping[str, str]] = None,
                      stored_classifications: Sequence[Tuple[str, Optional[str], Optional[str]]] = (),
                      ) -> PlanParams:
    """The planner's parameters for effective settings ``s`` (see ``effective_settings``).

    ``manual_size_fixes`` are the technician's size fixes (code -> size);
    ``stored_classifications`` are (code, size, category) answers reused from
    earlier runs of the same workbook.
    """
    fixes = manual_size_fixes or {}
    fixed = s.op_mode == FIXED_MODE
    return PlanParams(
        n_supply_points=int(s.n_supply_points),
        sp_mode=s.sp_mode,
        consumption_period_months=float(s.consumption_months),
        coverage_days=s.coverage_days,
        coverage_days_special=s.coverage_days_special,
        usage_threshold=s.ktc_threshold,
        per_class_thresholds=tuple(sorted(s.per_class_thresholds)),
        optional_thresholds_active=bool(s.optional_thresholds_active),
        force_screws_accessories_kanban=bool(s.force_screws_kanban),
        manual_size_fixes=tuple(sorted((str(k), str(v)) for k, v in fixes.items())),
        stored_classifications=tuple(stored_classifications),
        helix_threshold=s.helix_threshold,
        dims_mapped=bool(mapping.dimensions),
        minimum_carousel_allocation=int(s.min_carousel_allocation),
        plan_cfg=plan_config(s),
        system_type_mapped=bool(mapping.system_type),
        special_ktc=bool(s.special_ktc),
        stdspecial_mapped=bool(mapping.std_special),
        enable_bulk_routing=bool(s.bulk_routing),
        op_mode=s.op_mode,
        restock_categories=tuple(s.restock_categories),
        calc_mode_separated=s.calc_mode == CALC_SEPARATED,
        capacity_buffer_pct=float(s.capacity_buffer_pct),
        enable_rebalancer=bool(s.enable_rebalancer),
        underuse_threshold_pct=float(s.underuse_threshold_pct),
        max_carousels_cap=s.max_carousels,
        fixed_machines=tuple(s.fixed_machines) if fixed else (),
        fixed_headroom_pct=float(s.fixed_headroom_pct) if fixed else 0.0,
        fixed_allow_spill=bool(s.fixed_allow_spill) if fixed else True,
        fixed_stock_promotion_months=(
            float(s.fixed_stock_months) if fixed and s.fixed_stock_promotion else 0.0),
        base_counts=BaseCounts(
            rows_before=int(base_info["rows_before"]),
            rows_after_year_filter=int(base_info["rows_after_year_filter"]),
            rows_after_dedup=int(base_info["rows_after_dedup"]),
            consumption_before=base_info.get("consumption_before"),
            consumption_after_year=base_info.get("consumption_after_year"),
            consumption_after_dedup=base_info.get("consumption_after_dedup"),
        ),
    )


def program_mapping_active(work: pd.DataFrame, mapping: ColumnMapping, *,
                           n_supply_points: int, op_mode: str) -> bool:
    """Programmes decide the supply point: a Program column and several supply points."""
    return bool(mapping.program is not None and "Program" in work.columns
                and int(n_supply_points) > 1 and op_mode != OP_NUMBERING_ONLY)


def restock_slots_total(restock_info: Mapping) -> int:
    """Compartments reserved as restock buffer, over the Carousel and the lockers."""
    return (int(restock_info.get("slots_carousel", 0)) + int(restock_info.get("slots_lockerA", 0))
            + int(restock_info.get("slots_lockerB", 0)) + int(restock_info.get("slots_lockerC", 0)))
