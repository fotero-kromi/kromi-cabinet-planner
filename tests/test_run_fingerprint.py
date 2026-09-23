"""Tests for the run fingerprint (v33.82).

The fingerprint gates ``has_results``: when it changes, the displayed plan is
invalidated and the user must re-run. The two risks are a dropped input (a control
changes but the plan is not invalidated, the v33.71 bug) and silent drift in the
tuple (which would force a spurious re-run). These tests pin both: a golden tuple
for fixed inputs, and a sensitivity check that every single input moves the
fingerprint.
"""

import pytest

from engine.run_fingerprint import FingerprintInputs, compute_run_fingerprint

# Exact fingerprint for the baseline below, captured from the value-faithful
# extraction. Regenerate deliberately if the fingerprint contract changes.
GOLDEN = ('cust.xlsx', 12345, 'e3b0' + '0' * 60, 'Tools', 'PPE', 'packs', 'A', 'B', 'C', 'D', 'E', 'F', 'G',
          'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 7.5, 55.0, 12.0, True,
          (('drills', 3.0), ('mills', 4.0)), 10, 3, 30, 45, 1.1, 0.85, 1.0, True, 20.0, 10.0,
          2, 'auto', True, False, True, False, 'latest', 'sum', True, 500, 20, False, 5,
          (('P1', 1), ('P2', 2)), 'Capped', (), 4, True, 'CUST', 'SITE', True)

# Baseline keeps the conditional inputs live (Capped mode, program mapping active)
# so every input is in a position that affects the tuple.
_BASE = dict(
    file_name="cust.xlsx", file_size=12345, content_sha="e3b0" + "0" * 60, sheet_tools="Tools", sheet_ppe="PPE",
    calc_mode="packs", columns=tuple("ABCDEFGHIJKLMNOP"),
    usage_threshold=7.5, helix_threshold=55.0, consumption_period_months=12.0,
    optional_thresholds_active=True, per_class_thresholds={"drills": 3.0, "mills": 4.0},
    insert_default_pack_units=10, minimum_carousel_allocation=3, coverage_days=30,
    coverage_days_special=45, helix_single_spiral_overfill_factor=1.1, carousel_reserve_factor=0.85,
    carousel_fill_ceiling=1.0,
    enable_rebalancer=True, underuse_threshold_pct=20.0, capacity_buffer_pct=10.0,
    n_supply_points=2, sp_mode="auto", enable_pack_hint_extraction=True, enable_bulk_routing=False,
    force_screws_accessories_kanban=True, use_description_2=False, year_mode="latest",
    dedup_mode="sum", use_ai=True, max_ai_items=500, batch_size=20, trim_ai_reason=False,
    ai_concurrency=5, program_to_sp_map={"P1": 1, "P2": 2}, program_mapping_active=True,
    op_mode="Capped", max_carousels_cap=4, special_ktc_enabled=True,
    effective_customer="CUST", effective_site="SITE", apply_overrides=True, restock_categories=(),
)


def _fp(**overrides):
    d = dict(_BASE)
    d.update(overrides)
    return compute_run_fingerprint(FingerprintInputs(**d))


def test_matches_golden():
    assert _fp() == GOLDEN


def test_length_is_stable():
    assert len(_fp()) == 58


# distinct alternates for every scalar field
_SCALAR_ALTS = dict(
    file_name="other.xlsx", file_size=999, content_sha="f" * 64, restock_categories=("inserts",), sheet_tools="T2", sheet_ppe="P2", calc_mode="pcs",
    usage_threshold=8.5, helix_threshold=60.0, consumption_period_months=6.0,
    optional_thresholds_active=False, insert_default_pack_units=5, minimum_carousel_allocation=4,
    coverage_days=60, coverage_days_special=90, helix_single_spiral_overfill_factor=1.2,
    carousel_reserve_factor=0.9, enable_rebalancer=False, underuse_threshold_pct=25.0,
    capacity_buffer_pct=15.0, n_supply_points=3, sp_mode="manual", enable_pack_hint_extraction=False,
    enable_bulk_routing=True, force_screws_accessories_kanban=False, use_description_2=True,
    year_mode="all", dedup_mode="max", use_ai=False, max_ai_items=999, batch_size=25,
    trim_ai_reason=True, ai_concurrency=10, op_mode="Unlimited", apply_overrides=False,
    effective_customer="C2", effective_site="S2",
    per_class_thresholds={"drills": 99.0, "mills": 4.0},
    program_to_sp_map={"P1": 9, "P2": 2},
    carousel_fill_ceiling=0.75,
)


@pytest.mark.parametrize("field,alt", list(_SCALAR_ALTS.items()))
def test_every_scalar_input_moves_the_fingerprint(field, alt):
    assert _fp(**{field: alt}) != GOLDEN, f"{field} did not affect the fingerprint"


@pytest.mark.parametrize("pos", range(15))
def test_every_column_moves_the_fingerprint(pos):
    cols = list(_BASE["columns"])
    cols[pos] = "ZZZ"
    assert _fp(columns=tuple(cols)) != GOLDEN, f"column {pos} did not affect the fingerprint"


def test_special_ktc_toggle_moves_the_fingerprint():
    assert _fp(special_ktc_enabled=False) != GOLDEN


def test_carousel_cap_only_folded_in_capped_mode():
    # in Capped mode the cap matters
    assert _fp(max_carousels_cap=9) != _fp(max_carousels_cap=4)
    # outside Capped mode the cap is folded out (None), so it must not matter
    assert _fp(op_mode="Unlimited", max_carousels_cap=9) == _fp(op_mode="Unlimited", max_carousels_cap=4)


def test_program_map_only_folded_when_active():
    # active: the map matters
    assert _fp(program_to_sp_map={"P1": 9}) != _fp(program_to_sp_map={"P1": 1, "P2": 2})
    # inactive: the map is folded out (None), so it must not matter
    assert _fp(program_mapping_active=False, program_to_sp_map={"P1": 9}) == \
        _fp(program_mapping_active=False, program_to_sp_map={"X": 1})


def test_per_class_thresholds_are_order_independent():
    assert _fp(per_class_thresholds={"drills": 3.0, "mills": 4.0}) == \
        _fp(per_class_thresholds={"mills": 4.0, "drills": 3.0})


def test_program_map_is_order_independent():
    assert _fp(program_to_sp_map={"P1": 1, "P2": 2}) == \
        _fp(program_to_sp_map={"P2": 2, "P1": 1})


def test_numeric_and_bool_fields_are_coerced():
    # a truthy non-bool coerces to True; an int-valued float coerces like the int
    assert _fp(enable_rebalancer=1) == GOLDEN
    assert _fp(insert_default_pack_units=10.0) == GOLDEN
