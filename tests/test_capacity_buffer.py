"""Tests for the per-type capacity buffer (v33.88).

``compute_plan_for_subset`` gained ``buf_helix`` / ``buf_carousel`` /
``buf_locker`` keyword arguments. A per-family value of ``None`` falls back to
the global ``buf_pct``, so the original single-buffer behaviour is preserved
exactly. These tests pin both halves: the fallback is byte-identical, and a
per-family value inflates only that family's cabinet count.

The frame is sized so a 15% buffer crosses a cabinet boundary for each family:
70 spirals (Helix cap 70), 720 carousel slots (cap 720), 48 Locker A items
(cap 48) all sit at exactly one cabinet, and +15% tips each to two.
"""

import pandas as pd

from engine.cabinet_math import compute_plan_for_subset


def _frame():
    rows = [
        dict(SystemCategory="KTC", CabinetType="Helix",    Spirals_needed=70,  Carousel_stockpiles=0,   Consumption_pcs=100),
        dict(SystemCategory="KTC", CabinetType="Carousel", Spirals_needed=0,   Carousel_stockpiles=720, Consumption_pcs=100),
    ]
    rows += [dict(SystemCategory="KTC", CabinetType="Locker A", Spirals_needed=0, Carousel_stockpiles=0, Consumption_pcs=10)
             for _ in range(48)]
    return pd.DataFrame(rows)


def test_global_buffer_unchanged_when_per_type_none():
    df = _frame()
    a = compute_plan_for_subset(df, 15.0)
    b = compute_plan_for_subset(df, 15.0, buf_helix=None, buf_carousel=None, buf_locker=None)
    assert a == b


def test_global_equals_per_type_all_equal():
    df = _frame()
    glob = compute_plan_for_subset(df, 15.0)
    per = compute_plan_for_subset(df, 0.0, buf_helix=15.0, buf_carousel=15.0, buf_locker=15.0)
    assert glob == per


def test_helix_buffer_inflates_only_helix():
    df = _frame()
    base = compute_plan_for_subset(df, 0.0)
    out = compute_plan_for_subset(df, 0.0, buf_helix=15.0)
    assert out["helix_cabs"] == base["helix_cabs"] + 1   # 70 -> 81 spirals -> 2 cabs
    assert out["car_cabs"] == base["car_cabs"]            # carousel untouched
    assert out["cabA"] == base["cabA"]                    # lockers untouched


def test_carousel_buffer_inflates_only_carousel():
    df = _frame()
    base = compute_plan_for_subset(df, 0.0)
    out = compute_plan_for_subset(df, 0.0, buf_carousel=15.0)
    assert out["car_cabs"] == base["car_cabs"] + 1        # 720 -> 828 slots -> 2 cabs
    assert out["helix_cabs"] == base["helix_cabs"]
    assert out["cabA"] == base["cabA"]


def test_locker_buffer_inflates_only_lockers():
    df = _frame()
    base = compute_plan_for_subset(df, 0.0)
    out = compute_plan_for_subset(df, 0.0, buf_locker=15.0)
    assert out["cabA"] == base["cabA"] + 1                # 48 -> 56 items -> 2 cabs
    assert out["helix_cabs"] == base["helix_cabs"]
    assert out["car_cabs"] == base["car_cabs"]


def test_per_type_overrides_global():
    df = _frame()
    # global 0, but carousel set to 15: only carousel moves
    out = compute_plan_for_subset(df, 0.0, buf_carousel=15.0)
    base = compute_plan_for_subset(df, 0.0)
    assert out["car_cabs"] == base["car_cabs"] + 1
    assert out["helix_cabs"] == base["helix_cabs"]


def test_zero_buffer_is_a_noop():
    df = _frame()
    out = compute_plan_for_subset(df, 0.0, buf_helix=0.0, buf_carousel=0.0, buf_locker=0.0)
    assert out["total_spirals_buf"] == out["total_spirals"]
    assert out["car_slots_buf"] == out["car_slots"]
    assert out["countA_buf"] == out["countA"]


# ---------------------------------------------------------------------------
# Capped mode: the carousel cap is a hard limit (v34.02).
# The page passes buf_carousel=0.0 in capped mode so the capacity buffer never
# adds carousels beyond the cap, while it still applies to Helix and Locker.
# Frame reproduces the field report: 1404 carousel slots = 2 cabinets at base,
# 3 once a 10% buffer is applied; Helix sized to cross its own boundary too.
# ---------------------------------------------------------------------------

def _capped_frame():
    rows = [
        dict(SystemCategory="KTC", CabinetType="Carousel", Spirals_needed=0,  Carousel_stockpiles=702, Consumption_pcs=100),
        dict(SystemCategory="KTC", CabinetType="Carousel", Spirals_needed=0,  Carousel_stockpiles=702, Consumption_pcs=100),
        dict(SystemCategory="KTC", CabinetType="Helix",    Spirals_needed=70, Carousel_stockpiles=0,   Consumption_pcs=100),
    ]
    return pd.DataFrame(rows)


def test_capped_carousel_buffer_suppressed_keeps_base_count():
    df = _capped_frame()
    full = compute_plan_for_subset(df, 10.0)                      # global buffer on every dimension
    capped = compute_plan_for_subset(df, 10.0, buf_carousel=0.0)  # cap means capped
    assert full["car_cabs"] == 3                        # 1404 -> 1545 slots -> 3 cabs
    assert capped["car_cabs"] == 2                      # buffer suppressed -> base 2
    assert capped["car_cabs"] == capped["car_cabs_base"]


def test_capped_carousel_suppression_leaves_helix_buffered():
    df = _capped_frame()
    full = compute_plan_for_subset(df, 10.0)
    capped = compute_plan_for_subset(df, 10.0, buf_carousel=0.0)
    assert capped["helix_cabs"] == full["helix_cabs"]   # helix buffer unaffected
    assert capped["helix_cabs"] == 2                    # 70 -> 77 spirals -> 2 cabs


def test_capped_carousel_slots_buf_equals_base():
    df = _capped_frame()
    capped = compute_plan_for_subset(df, 10.0, buf_carousel=0.0)
    assert capped["car_slots_buf"] == capped["car_slots"]   # no buffer added to carousel slots


def test_uncapped_carousel_still_buffered():
    """Regression guard: the normal (non-capped) path must keep buffering carousels."""
    df = _capped_frame()
    out = compute_plan_for_subset(df, 10.0)             # buf_carousel defaults to global
    assert out["car_cabs"] == 3
