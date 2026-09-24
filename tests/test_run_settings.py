"""engine/run_settings.py (v34.62): the typed settings of one planning run and
the rules that turn them into the planner's parameters, moved out of the
planner page so every front end plans with the same rules.
"""
import dataclasses

import pandas as pd
import pytest

from engine import run_settings as rs
from engine.fixed_config import FIXED_MODE
from engine.plan import BaseCounts, PlanParams
from engine.plan_config import PlanConfig
from engine.planning_defaults import CALC_COMBINED, CALC_SEPARATED, DEFAULTS as D
from engine.sizing_factors import SP_MODE_PARTITION, SP_MODE_REPLICATE
from engine.tool_list import ColumnMapping

_BASE = {"rows_before": 10, "rows_after_year_filter": 9, "rows_after_dedup": 8,
         "consumption_before": 100.0, "consumption_after_year": 90.0,
         "consumption_after_dedup": 80.0}
_MAP = ColumnMapping(code="Art", description="Text", consumption="Use")


def test_the_settings_start_from_the_shared_defaults():
    s = rs.RunSettings()
    for f in dataclasses.fields(rs.RunSettings):
        if hasattr(D, f.name):
            assert getattr(s, f.name) == getattr(D, f.name), f.name
    assert s.per_class_thresholds == () and s.optional_thresholds_active is False
    assert s.fixed_machines == () and s.restock_categories == ()


def test_the_settings_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        rs.RunSettings().ktc_threshold = 2.0  # type: ignore[misc]


# ---- labels ---------------------------------------------------------------------------

def test_label_parsing_matches_the_page():
    assert rs.sp_mode_from_label("Replicate - anything") == SP_MODE_REPLICATE
    assert rs.sp_mode_from_label("Partition \u2014 x") == SP_MODE_PARTITION
    assert rs.sp_mode_from_label("") == SP_MODE_PARTITION
    assert rs.calc_mode_from_label("Separated (Tools and PPE ...)") == CALC_SEPARATED
    assert rs.calc_mode_from_label("Combined (one ...)") == CALC_COMBINED
    assert rs.calc_mode_from_label("anything else") == CALC_COMBINED


# ---- mode rules -----------------------------------------------------------------------

def test_special_coverage_follows_standard_without_a_special_column():
    s = rs.RunSettings(coverage_days=25, coverage_days_special=40)
    assert rs.effective_settings(s, stdspecial_mapped=False, both_listings=False) \
        .coverage_days_special == 25
    assert rs.effective_settings(s, stdspecial_mapped=True, both_listings=False) \
        .coverage_days_special == 40


def test_one_listing_always_plans_combined():
    s = rs.RunSettings(calc_mode=CALC_SEPARATED)
    assert rs.effective_settings(s, stdspecial_mapped=False, both_listings=False).calc_mode \
        == CALC_COMBINED
    assert rs.effective_settings(s, stdspecial_mapped=False, both_listings=True).calc_mode \
        == CALC_SEPARATED


def test_the_fixed_configuration_forces_its_values():
    s = rs.RunSettings(op_mode=FIXED_MODE, carousel_fill_ceiling=0.8, enable_rebalancer=True,
                       capacity_buffer_pct=20.0, calc_mode=CALC_SEPARATED,
                       underuse_threshold_pct=45.0, fixed_headroom_pct=12.0,
                       fixed_machines=((1, 2, 1, 0, 0, 0),))
    e = rs.effective_settings(s, stdspecial_mapped=False, both_listings=True)
    assert (e.carousel_fill_ceiling, e.enable_rebalancer, e.capacity_buffer_pct,
            e.calc_mode) == (1.0, False, 0.0, CALC_COMBINED)
    assert e.underuse_threshold_pct == 45.0  # kept for the other modes
    assert e.fixed_headroom_pct == 12.0 and e.fixed_machines == ((1, 2, 1, 0, 0, 0),)


def test_outside_the_fixed_configuration_its_values_are_neutral():
    s = rs.RunSettings(fixed_headroom_pct=12.0, fixed_machines=((1, 2, 1, 0, 0, 0),),
                       fixed_allow_spill=False, fixed_stock_promotion=True)
    e = rs.effective_settings(s, stdspecial_mapped=False, both_listings=False)
    assert (e.fixed_headroom_pct, e.fixed_machines, e.fixed_allow_spill,
            e.fixed_stock_promotion) == (0.0, (), True, False)


def test_inactive_class_thresholds_are_dropped():
    s = rs.RunSettings(per_class_thresholds=(("drill", 2.0),))
    assert rs.effective_settings(s, stdspecial_mapped=False, both_listings=False) \
        .per_class_thresholds == ()
    on = dataclasses.replace(s, optional_thresholds_active=True)
    assert rs.effective_settings(on, stdspecial_mapped=False, both_listings=False) \
        .per_class_thresholds == (("drill", 2.0),)


# ---- planner parameters ----------------------------------------------------------------

def test_plan_config_carries_the_three_factors():
    s = rs.RunSettings(helix_overfill_factor=1.2, carousel_reserve_factor=0.9,
                       carousel_fill_ceiling=0.95)
    assert rs.plan_config(s) == PlanConfig(helix_overfill_factor=1.2,
                                           carousel_reserve_factor=0.9,
                                           carousel_fill_ceiling=0.95)


def test_build_plan_params_for_a_standard_run():
    s = rs.RunSettings()
    p = rs.build_plan_params(s, mapping=_MAP, base_info=_BASE)
    assert isinstance(p, PlanParams)
    assert p == PlanParams(
        n_supply_points=1, sp_mode=SP_MODE_REPLICATE, consumption_period_months=12.0,
        coverage_days=20, coverage_days_special=20, usage_threshold=1.0,
        per_class_thresholds=(), optional_thresholds_active=False,
        force_screws_accessories_kanban=False, manual_size_fixes=(),
        stored_classifications=(), restock_categories=(), helix_threshold=6.0,
        dims_mapped=False, minimum_carousel_allocation=3, plan_cfg=PlanConfig(),
        system_type_mapped=False, special_ktc=False, stdspecial_mapped=False,
        enable_bulk_routing=False, op_mode="", calc_mode_separated=False,
        capacity_buffer_pct=15.0, enable_rebalancer=True, underuse_threshold_pct=30.0,
        max_carousels_cap=2,
        base_counts=BaseCounts(rows_before=10, rows_after_year_filter=9, rows_after_dedup=8,
                               consumption_before=100.0, consumption_after_year=90.0,
                               consumption_after_dedup=80.0),
        fixed_machines=(), fixed_headroom_pct=0.0, fixed_allow_spill=True,
        fixed_stock_promotion_months=0.0,
    )


def test_build_plan_params_reads_the_mapping_and_the_extras():
    m = ColumnMapping(code="Art", description="Text", consumption="Use", dimensions="D",
                      system_type="S", std_special="X")
    s = rs.RunSettings(calc_mode=CALC_SEPARATED, special_ktc=True,
                       restock_categories=("tap",), optional_thresholds_active=True,
                       per_class_thresholds=(("drill", 2.0),))
    p = rs.build_plan_params(s, mapping=m, base_info=_BASE,
                             manual_size_fixes={"B": "M", "A": "M"},
                             stored_classifications=(("A", "S", "drill"),))
    assert (p.dims_mapped, p.system_type_mapped, p.stdspecial_mapped) == (True, True, True)
    assert p.calc_mode_separated is True and p.special_ktc is True
    assert p.restock_categories == ("tap",)
    assert p.per_class_thresholds == (("drill", 2.0),) and p.optional_thresholds_active
    assert p.manual_size_fixes == (("A", "M"), ("B", "M"))
    assert p.stored_classifications == (("A", "S", "drill"),)


def test_stock_promotion_months_only_in_the_fixed_configuration_with_promotion():
    fixed = rs.RunSettings(op_mode=FIXED_MODE, fixed_stock_promotion=True,
                           fixed_stock_months=4.0)
    assert rs.build_plan_params(fixed, mapping=_MAP, base_info=_BASE) \
        .fixed_stock_promotion_months == 4.0
    off = dataclasses.replace(fixed, fixed_stock_promotion=False)
    assert rs.build_plan_params(off, mapping=_MAP, base_info=_BASE) \
        .fixed_stock_promotion_months == 0.0
    std = rs.RunSettings(fixed_stock_promotion=True, fixed_stock_months=4.0)
    assert rs.build_plan_params(std, mapping=_MAP, base_info=_BASE) \
        .fixed_stock_promotion_months == 0.0


def test_the_parameter_types_match_the_page():
    p = rs.build_plan_params(rs.RunSettings(n_supply_points=2), mapping=_MAP, base_info=_BASE)
    assert type(p.n_supply_points) is int and type(p.consumption_period_months) is float
    assert type(p.capacity_buffer_pct) is float and type(p.underuse_threshold_pct) is float
    assert type(p.fixed_headroom_pct) is float and type(p.minimum_carousel_allocation) is int


# ---- derived values -------------------------------------------------------------------

def test_program_mapping_is_active_with_a_program_column_and_several_supply_points():
    w = pd.DataFrame({"Program": ["A"]})
    prog = ColumnMapping(code="C", description="D", program="P")
    assert rs.program_mapping_active(w, prog, n_supply_points=2, op_mode="")
    assert not rs.program_mapping_active(w, prog, n_supply_points=1, op_mode="")
    assert not rs.program_mapping_active(w, prog, n_supply_points=2, op_mode="NumberingOnly")
    assert not rs.program_mapping_active(w, _MAP, n_supply_points=2, op_mode="")
    assert not rs.program_mapping_active(pd.DataFrame({"X": [1]}), prog, n_supply_points=2,
                                         op_mode="")


def test_restock_slots_total_sums_the_buffer_compartments():
    assert rs.restock_slots_total({}) == 0
    assert rs.restock_slots_total({"slots_carousel": 3, "slots_lockerA": 1,
                                   "slots_lockerB": 2.0, "slots_lockerC": 4,
                                   "provided_true": 9}) == 10
