"""Tests for the carousel fill ceiling + empty-threshold absorption (v33.89).

``carousel_cabinets_needed`` sizes carousel cabinets from a soft fill ceiling
(fraction of physical capacity) with an absorption rule governed by the
empty-cabinet threshold. The defaults (ceiling 1.0, threshold 0.0) reproduce the
original ``ceil(slots / capacity)`` count, which the counting functions
(``compute_carousel_needs``, ``compute_plan_for_subset``, ``apply_carousel_cap``)
now route through.

Physical capacity is 720 slots per cabinet.
"""

import math

import pandas as pd

from engine.cabinet_math import (
    carousel_cabinets_needed,
    compute_carousel_needs,
    compute_plan_for_subset,
    apply_carousel_cap,
    CAROUSEL_SLOTS_PER_CAB,
)

CAP = CAROUSEL_SLOTS_PER_CAB  # 720


# ---- the helper ----

def test_default_ceiling_matches_physical_ceil():
    for slots in [0, 1, 100, 612, 613, 719, 720, 721, 1224, 1440, 2001]:
        assert carousel_cabinets_needed(slots) == (math.ceil(slots / CAP) if slots > 0 else 0)


def test_zero_slots_is_zero():
    assert carousel_cabinets_needed(0) == 0
    assert carousel_cabinets_needed(0, fill_ceiling=0.85, empty_threshold_pct=30) == 0


def test_ceiling_honours_headroom_without_absorption():
    # at 85% fill, 612 fits one cabinet but 613 opens a second (threshold 0 = no absorb)
    assert carousel_cabinets_needed(612, fill_ceiling=0.85, empty_threshold_pct=0) == 1
    assert carousel_cabinets_needed(613, fill_ceiling=0.85, empty_threshold_pct=0) == 2


def test_absorption_drops_a_wasteful_marginal_cabinet():
    # the 1-slot overflow would make a near-empty second cabinet -> absorb it
    assert carousel_cabinets_needed(613, fill_ceiling=0.85, empty_threshold_pct=30) == 1


def test_marginal_cabinet_above_threshold_is_kept():
    # 970 slots: 612 + 358; the second cabinet at 358/720 = 49.7% clears 30% -> keep two
    assert carousel_cabinets_needed(970, fill_ceiling=0.85, empty_threshold_pct=30) == 2


def test_never_drops_below_physical_capacity():
    # 800 slots cannot fit one 720-slot cabinet, so two regardless of absorption
    assert carousel_cabinets_needed(800, fill_ceiling=0.85, empty_threshold_pct=99) == 2


def test_non_positive_ceiling_treated_as_one():
    for slots in [500, 720, 1500]:
        assert carousel_cabinets_needed(slots, fill_ceiling=0.0) == math.ceil(slots / CAP)
        assert carousel_cabinets_needed(slots, fill_ceiling=-1.0) == math.ceil(slots / CAP)


# ---- integration: counting functions route through the helper ----

def test_compute_carousel_needs_default_unchanged():
    df = pd.DataFrame([dict(Carousel_stockpiles=700)])
    assert compute_carousel_needs(df) == (700, 1)


def test_compute_carousel_needs_with_ceiling():
    df = pd.DataFrame([dict(Carousel_stockpiles=700)])
    # 700 > 612 -> two cabinets at 85% with no absorption
    assert compute_carousel_needs(df, fill_ceiling=0.85, empty_threshold_pct=0) == (700, 2)
    # but absorbed back to one when the threshold forbids the near-empty cabinet
    # (700 - 612 = 88 slots; 88/720 = 12.2% < 30%)
    assert compute_carousel_needs(df, fill_ceiling=0.85, empty_threshold_pct=30) == (700, 1)


def test_compute_plan_for_subset_ceiling_default_is_noop():
    df = pd.DataFrame([dict(SystemCategory="KTC", CabinetType="Carousel",
                            Spirals_needed=0, Carousel_stockpiles=700, Consumption_pcs=10)])
    base = compute_plan_for_subset(df, 0.0)
    explicit = compute_plan_for_subset(df, 0.0, carousel_fill_ceiling=1.0, empty_cabinet_threshold_pct=0.0)
    assert base == explicit


def test_compute_plan_for_subset_ceiling_increases_carousel_cabs():
    df = pd.DataFrame([dict(SystemCategory="KTC", CabinetType="Carousel",
                            Spirals_needed=0, Carousel_stockpiles=700, Consumption_pcs=10)])
    base = compute_plan_for_subset(df, 0.0)
    out = compute_plan_for_subset(df, 0.0, carousel_fill_ceiling=0.85, empty_cabinet_threshold_pct=0.0)
    assert out["car_cabs"] == base["car_cabs"] + 1


def test_apply_carousel_cap_counts_with_ceiling():
    # 700 carousel slots = 1 physical cabinet, but 2 at 85% fill.
    df = pd.DataFrame([
        dict(CabinetType="Carousel", Carousel_stockpiles=350, SizeCategory="S", Monthly_packs=1.0),
        dict(CabinetType="Carousel", Carousel_stockpiles=350, SizeCategory="M", Monthly_packs=2.0),
    ], index=[1, 2])
    # cap = 1: at physical fill the count is 1 (no spill); at 85% it is 2 (spill happens)
    out_phys, ov_phys = apply_carousel_cap(df, 1, helix_overfill_factor=1.10)
    assert list(out_phys["CabinetType"]) == ["Carousel", "Carousel"]  # within cap, untouched
    out_ceil, ov_ceil = apply_carousel_cap(
        df, 1, helix_overfill_factor=1.10, carousel_fill_ceiling=0.85, empty_cabinet_threshold_pct=0.0
    )
    assert (out_ceil["CabinetType"] == "Helix").any()  # ceiling pushed count over cap -> spill


# ---- UI wiring (v34.34) --------------------------------------------------------

def test_plan_config_carries_the_ceiling():
    from engine.plan_config import PlanConfig
    cfg = PlanConfig()
    assert cfg.carousel_fill_ceiling == 1.0
    assert PlanConfig(carousel_fill_ceiling=0.8).carousel_fill_ceiling == 0.8


def test_segment_math_responds_to_the_ceiling():
    """The bucket segment plans more Carousels for the same stockpiles when
    the fill ceiling drops: the knob reaches the rollup math."""
    import pandas as pd

    from engine.cabinet_math import CAROUSEL_SLOTS_PER_CAB
    from engine.plan import run_bucket_planning_segment

    n = CAROUSEL_SLOTS_PER_CAB
    work = pd.DataFrame({
        "Listing": ["Tools"] * n,
        "SupplyPoint": [1] * n,
        "SystemCategory": ["KTC"] * n,
        "CabinetType": ["Carousel"] * n,
        "SizeCategory": ["L"] * n,
        "Carousel_stockpiles": [1] * n,
        "Spirals_needed": [0] * n,
        "Spiral_capacity": [0] * n,
        "Monthly_packs": [1.0] * n,
        "Consumption_pcs": [10.0] * n,
    })
    def plan_with(ceiling):
        w = work.copy()
        buckets = [("Tools — SP 1", w)]
        _w, plans, _a = run_bucket_planning_segment(
            w, buckets,
            op_mode="Helix + Carousel", enable_rebalancer=False, buf_pct=0.0,
            minimum_carousel_allocation=1, underuse_threshold_pct=0.0,
            max_carousels_cap=0, helix_overfill_factor=1.1,
            carousel_reserve_factor=0.85, carousel_fill_ceiling=ceiling,
        )
        return sum(p.get("car_cabs", 0) for _l, p in plans)

    assert plan_with(0.5) > plan_with(1.0)


def test_run_plan_forwards_the_config_ceiling(monkeypatch):
    """run_plan passes the PlanConfig ceiling into the bucket segment: the
    widget value cannot silently fall back to a hidden default."""
    import dataclasses

    import engine.plan as ep
    from tests.test_run_plan_equivalence import _boundary_frame, _params

    seen = {}
    _orig = ep.run_bucket_planning_segment

    def spy(*a, **k):
        seen["ceiling"] = k.get("carousel_fill_ceiling")
        return _orig(*a, **k)

    monkeypatch.setattr(ep, "run_bucket_planning_segment", spy)
    df = _boundary_frame()
    base = _params(df)
    tight_cfg = dataclasses.replace(base.plan_cfg, carousel_fill_ceiling=0.62)
    ep.run_plan(df, (), dataclasses.replace(base, plan_cfg=tight_cfg))
    assert seen["ceiling"] == 0.62


def test_fingerprint_covers_the_ceiling():
    """Two runs differing only in the fill ceiling must never share a
    fingerprint, or cached and archived results would collide."""
    from tests.test_run_fingerprint import _fp

    assert _fp() != _fp(carousel_fill_ceiling=0.75)


def test_restore_carries_the_ceiling_key():
    from engine.run_restore import CONTROL_KEYS
    assert "ks_fill_ceiling" in CONTROL_KEYS


def test_run_metadata_names_the_ceiling():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "pages" / "1_Kromi_Planner.py").read_text(encoding="utf-8")
    assert '"Carousel fill ceiling"' in src
    assert "ks_fill_ceiling" in src
