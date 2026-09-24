"""The planner page starts every sidebar control from engine/planning_defaults.py
(v34.61), so the Streamlit app and the new app share one set of defaults.
"""
from streamlit.testing.v1 import AppTest

from engine.planning_defaults import (
    CALC_MODE_LABELS,
    DEDUP_MODE_LABELS,
    DEFAULTS as D,
    SP_MODE_LABELS,
    YEAR_MODE_LABELS,
)
from tests._paths import PLANNER_PAGE


def test_a_fresh_page_starts_from_the_shared_defaults():
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=120)
    at.run()
    assert not at.exception
    want = {
        "ks_ktc_threshold": D.ktc_threshold,
        "ks_insert_pack": D.insert_pack_units,
        "ks_helix_threshold": D.helix_threshold,
        "ks_consumption_months": D.consumption_months,
        "ks_overfill": D.helix_overfill_factor,
        "ks_min_carousel": D.min_carousel_allocation,
        "cov_days_standard": D.coverage_days,
        "ks_reserve": D.carousel_reserve_factor,
        "ks_fill_ceiling": D.carousel_fill_ceiling,
        "ks_rebalancer": D.enable_rebalancer,
        "ks_empty_cab": D.underuse_threshold_pct,
        "ks_buffer": D.capacity_buffer_pct,
        "ks_pack_hint": D.pack_hint_extraction,
        "ks_bulk_routing": D.bulk_routing,
        "ks_force_screws": D.force_screws_kanban,
        "ks_n_sp": D.n_supply_points,
        "ks_sp_mode": SP_MODE_LABELS[D.sp_mode],
        "ks_calc_mode": CALC_MODE_LABELS[D.calc_mode],
        "ks_use_desc2": D.use_description_2,
        "ks_year_mode": YEAR_MODE_LABELS[D.year_mode],
        "ks_dedup_mode": DEDUP_MODE_LABELS[D.dedup_mode],
        "ks_apply_overrides": D.apply_overrides,
    }
    got = {key: at.session_state[key] for key in want}
    assert got == want
    for key, value in want.items():
        assert type(got[key]) is type(value), key
