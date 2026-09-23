"""Scenario tests for the run fingerprint (v33.83).

The golden and per-field tests live in test_run_fingerprint.py. These check the
fingerprint behaves correctly across realistic settings combinations: the
stability the gate depends on (identical settings always yield the same value),
and the conditional folding of the carousel cap and program map under modes that
match real runs. Settings values are generic.
"""

from engine.run_fingerprint import FingerprintInputs, compute_run_fingerprint


def _inputs(**o):
    base = dict(
        file_name="list.xlsx", file_size=200000, content_sha="e3b0" + "0" * 60, sheet_tools="Sheet1", sheet_ppe=None,
        calc_mode="combined", columns=tuple(f"c{i}" for i in range(16)),
        usage_threshold=1.0, helix_threshold=4.0, consumption_period_months=16.0,
        optional_thresholds_active=False, per_class_thresholds={},
        insert_default_pack_units=10, minimum_carousel_allocation=3, coverage_days=18,
        coverage_days_special=18, helix_single_spiral_overfill_factor=1.1, carousel_reserve_factor=0.85, carousel_fill_ceiling=1.0,
        enable_rebalancer=True, underuse_threshold_pct=20.0, capacity_buffer_pct=0.0,
        n_supply_points=1, sp_mode="replicate", enable_pack_hint_extraction=True,
        enable_bulk_routing=True, force_screws_accessories_kanban=False, use_description_2=False,
        year_mode="all_years", dedup_mode="none", use_ai=True, max_ai_items=2000, batch_size=20,
        trim_ai_reason=False, ai_concurrency=4, program_to_sp_map={}, program_mapping_active=False,
        op_mode="Capped", max_carousels_cap=1, special_ktc_enabled=False,
        effective_customer="cust", effective_site="default", apply_overrides=True, restock_categories=(),
    )
    base.update(o)
    return FingerprintInputs(**base)


def test_identical_settings_yield_identical_fingerprint():
    # the invariant the has_results gate relies on
    assert compute_run_fingerprint(_inputs()) == compute_run_fingerprint(_inputs())


def test_capped_scenario_folds_cap_in():
    a = compute_run_fingerprint(_inputs(op_mode="Capped", max_carousels_cap=1))
    b = compute_run_fingerprint(_inputs(op_mode="Capped", max_carousels_cap=2))
    assert a != b


def test_standard_scenario_folds_cap_out():
    a = compute_run_fingerprint(_inputs(op_mode="", max_carousels_cap=1))
    b = compute_run_fingerprint(_inputs(op_mode="", max_carousels_cap=2))
    assert a == b


def test_helix_only_scenario_folds_cap_out():
    a = compute_run_fingerprint(_inputs(op_mode="Helix", max_carousels_cap=1))
    b = compute_run_fingerprint(_inputs(op_mode="Helix", max_carousels_cap=5))
    assert a == b


def test_program_mapping_scenario_folds_map_in():
    a = compute_run_fingerprint(_inputs(program_mapping_active=True, program_to_sp_map={"P": 1}))
    b = compute_run_fingerprint(_inputs(program_mapping_active=True, program_to_sp_map={"P": 2}))
    assert a != b


def test_program_mapping_off_folds_map_out():
    a = compute_run_fingerprint(_inputs(program_mapping_active=False, program_to_sp_map={"P": 1}))
    b = compute_run_fingerprint(_inputs(program_mapping_active=False, program_to_sp_map={"Q": 9}))
    assert a == b


def test_special_ktc_toggle_changes_the_fingerprint():
    a = compute_run_fingerprint(_inputs(special_ktc_enabled=False))
    b = compute_run_fingerprint(_inputs(special_ktc_enabled=True))
    assert a != b


def test_changing_consumption_window_changes_the_fingerprint():
    a = compute_run_fingerprint(_inputs(consumption_period_months=16.0))
    b = compute_run_fingerprint(_inputs(consumption_period_months=12.0))
    assert a != b


def test_changing_coverage_window_changes_the_fingerprint():
    a = compute_run_fingerprint(_inputs(coverage_days=18))
    b = compute_run_fingerprint(_inputs(coverage_days=30))
    assert a != b


def test_two_distinct_scenarios_have_distinct_fingerprints():
    capped = compute_run_fingerprint(_inputs(op_mode="Capped", max_carousels_cap=1, n_supply_points=1))
    multi = compute_run_fingerprint(_inputs(op_mode="", n_supply_points=3, sp_mode="auto"))
    assert capped != multi


def test_toggling_ai_changes_the_fingerprint():
    assert compute_run_fingerprint(_inputs(use_ai=True)) != compute_run_fingerprint(_inputs(use_ai=False))


def test_enabling_optional_thresholds_changes_the_fingerprint():
    a = compute_run_fingerprint(_inputs(optional_thresholds_active=False, per_class_thresholds={"inserts": 3.0}))
    b = compute_run_fingerprint(_inputs(optional_thresholds_active=True, per_class_thresholds={"inserts": 3.0}))
    # optional_thresholds_active is itself a fingerprint field, so the flag flip alone moves it
    assert a != b
