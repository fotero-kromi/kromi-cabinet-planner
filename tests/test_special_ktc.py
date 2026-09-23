"""Special-tools-as-KTC forcing (v33.68).

When the 'Set special tools as KTC' toggle is on, every row marked Special in
the mapped Standard/Special column is forced onto a vending machine regardless
of its consumption, with the full sizing consequences, and is protected from
bulk routing and consolidation exactly like a System-type-fixed row. A row
already fixed by System type is left untouched (System type wins).
"""

import pandas as pd

from engine.cabinet_math import force_special_to_ktc, SPECIAL_KTC_REASON


PARAMS = dict(
    threshold=5.0,
    helix_threshold=50.0,
    min_carousel_compartments=3,
    carousel_reserve_factor=0.85,
    helix_overfill_factor=1.10,
)


def _row(std_special, *, forced=False, cabinet="Kanban", system="Kanban",
         reason="", size="S"):
    """A low-consumption row (0.2 packs/mo, below the threshold). Left alone it
    routes to Kanban; the force is what can move it to KTC."""
    return {
        "StdSpecial": std_special,
        "Monthly_packs": 0.2, "Monthly_pcs": 1.0, "Target_packs": 1.0,
        "SizeCategory": size, "ProductCategory": "drills", "Regrind": False,
        "SystemCategory": system, "CabinetType": cabinet,
        "Spiral_capacity": pd.NA, "Spirals_needed": 0, "Carousel_stockpiles": 0,
        "Routing_Pinned": forced, "SystemCategory_Reason": reason,
    }


def test_reason_constant_value_is_stable():
    # The export's Forced_to_KTC column and the Run_Metadata count both key on
    # this exact string, so its value is pinned here to catch a silent change.
    assert SPECIAL_KTC_REASON == "Special tool forced to KTC"


def test_special_low_mover_is_forced_to_ktc():
    work = pd.DataFrame([_row("2")])
    n = force_special_to_ktc(work, **PARAMS)
    assert n == 1
    assert work.at[0, "SystemCategory"] == "KTC"
    assert work.at[0, "CabinetType"] != "Kanban"          # landed in a machine
    assert bool(work.at[0, "Routing_Pinned"]) is True   # protected from moves
    assert work.at[0, "SystemCategory_Reason"] == SPECIAL_KTC_REASON


def test_standard_row_is_untouched():
    work = pd.DataFrame([_row("1")])
    n = force_special_to_ktc(work, **PARAMS)
    assert n == 0
    assert work.at[0, "SystemCategory"] == "Kanban"
    assert work.at[0, "CabinetType"] == "Kanban"
    assert bool(work.at[0, "Routing_Pinned"]) is False


def test_system_type_fixed_special_row_wins_and_is_left_alone():
    # Special, but System type already fixed it to a Locker. System type wins:
    # the toggle must not overwrite it or re-count it.
    work = pd.DataFrame([
        _row("2", forced=True, cabinet="Locker A", system="KTC",
             reason="System type fixed: Locker (Locker A)")
    ])
    n = force_special_to_ktc(work, **PARAMS)
    assert n == 0
    assert work.at[0, "CabinetType"] == "Locker A"
    assert work.at[0, "SystemCategory_Reason"] == "System type fixed: Locker (Locker A)"


def test_blank_zero_and_unknown_markers_are_not_forced():
    # "" is blank, "0" is no longer a recognised code, "blue" is unknown.
    work = pd.DataFrame([_row(""), _row("0"), _row("blue")])
    n = force_special_to_ktc(work, **PARAMS)
    assert n == 0
    assert list(work["CabinetType"]) == ["Kanban", "Kanban", "Kanban"]


def test_no_stdspecial_column_is_a_noop():
    work = pd.DataFrame([{
        "Monthly_packs": 0.2, "Monthly_pcs": 1.0, "Target_packs": 1.0,
        "SizeCategory": "S", "ProductCategory": "drills", "Regrind": False,
        "SystemCategory": "Kanban", "CabinetType": "Kanban",
        "Spiral_capacity": pd.NA, "Spirals_needed": 0, "Carousel_stockpiles": 0,
        "Routing_Pinned": False, "SystemCategory_Reason": "",
    }])
    before = work.copy()
    n = force_special_to_ktc(work, **PARAMS)
    assert n == 0
    pd.testing.assert_frame_equal(work, before)


def test_mixed_frame_forces_only_the_eligible_special_rows():
    work = pd.DataFrame([
        _row("2"),                                   # forced
        _row("1"),                                   # standard, skipped
        _row("2", forced=True, cabinet="Helix"),     # system-type-fixed, skipped
        _row("special"),                             # word form, forced
    ])
    n = force_special_to_ktc(work, **PARAMS)
    assert n == 2
    assert work.at[0, "SystemCategory"] == "KTC"
    assert work.at[3, "SystemCategory"] == "KTC"
    assert work.at[1, "CabinetType"] == "Kanban"
    assert work.at[2, "CabinetType"] == "Helix"
