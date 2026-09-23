"""System type (Lagersystem) application, extracted from the page (v33.73).

These pin the exact pre-extraction behaviour: a mapped System type column lets
the customer's stated system win over the planner's routing — "KTC" forces a
vending machine, "Locker" forces a size-matched locker, "KTC or Kanban" leaves
the threshold to decide — and fixed rows are pinned via Routing_Pinned so bulk
routing and consolidation leave them alone. Mirrors force_special_to_ktc.
"""

import pandas as pd

from engine.cabinet_math import apply_system_type


PARAMS = dict(
    threshold=5.0,
    helix_threshold=50.0,
    min_carousel_compartments=3,
    carousel_reserve_factor=0.85,
    helix_overfill_factor=1.10,
)


def _row(system_typ, *, size="S", system="Kanban", cabinet="Kanban", reason=""):
    """A low-consumption row (0.2 packs/mo) that would route to Kanban on its own."""
    return {
        "SystemTyp": system_typ,
        "Monthly_packs": 0.2, "Monthly_pcs": 1.0, "Target_packs": 1.0,
        "SizeCategory": size, "ProductCategory": "drills", "Regrind": False,
        "SystemCategory": system, "CabinetType": cabinet,
        "Spiral_capacity": pd.NA, "Spirals_needed": 0, "Carousel_stockpiles": 0,
        "Routing_Pinned": False, "SystemCategory_Reason": reason,
    }


def test_ktc_value_forces_vending_and_pins():
    work = pd.DataFrame([_row("KTC")])
    counts = apply_system_type(work, **PARAMS)
    assert counts == {"ktc": 1, "locker": 0, "flex": 0}
    assert work.at[0, "SystemCategory"] == "KTC"
    assert work.at[0, "CabinetType"] != "Kanban"
    assert bool(work.at[0, "Routing_Pinned"]) is True
    assert work.at[0, "SystemCategory_Reason"] == "System type fixed: KTC (forced vending)"


def test_locker_value_forces_size_matched_locker():
    work = pd.DataFrame([_row("Locker", size="XL")])
    counts = apply_system_type(work, **PARAMS)
    assert counts == {"ktc": 0, "locker": 1, "flex": 0}
    assert work.at[0, "SystemCategory"] == "KTC"
    assert work.at[0, "CabinetType"] == "Locker A"            # XL -> Locker A
    assert work.at[0, "Spirals_needed"] == 0
    assert work.at[0, "Carousel_stockpiles"] == 0
    assert bool(work.at[0, "Routing_Pinned"]) is True
    assert work.at[0, "SystemCategory_Reason"] == "System type fixed: Locker (Locker A)"


def test_ktc_or_kanban_counts_flex_and_leaves_routing():
    work = pd.DataFrame([_row("KTC or Kanban")])
    counts = apply_system_type(work, **PARAMS)
    assert counts == {"ktc": 0, "locker": 0, "flex": 1}
    assert work.at[0, "CabinetType"] == "Kanban"             # routing untouched
    assert bool(work.at[0, "Routing_Pinned"]) is False


def test_blank_and_unrecognised_left_untouched():
    work = pd.DataFrame([_row(""), _row("Kanban"), _row("foo")])
    counts = apply_system_type(work, **PARAMS)
    assert counts == {"ktc": 0, "locker": 0, "flex": 0}
    assert list(work["CabinetType"]) == ["Kanban", "Kanban", "Kanban"]
    assert not work["Routing_Pinned"].any()


def test_no_systemtyp_column_is_a_noop():
    work = pd.DataFrame([{
        "Monthly_packs": 0.2, "Monthly_pcs": 1.0, "Target_packs": 1.0,
        "SizeCategory": "S", "ProductCategory": "drills", "Regrind": False,
        "SystemCategory": "Kanban", "CabinetType": "Kanban",
        "Spiral_capacity": pd.NA, "Spirals_needed": 0, "Carousel_stockpiles": 0,
        "Routing_Pinned": False, "SystemCategory_Reason": "",
    }])
    before = work.copy()
    counts = apply_system_type(work, **PARAMS)
    assert counts == {"ktc": 0, "locker": 0, "flex": 0}
    pd.testing.assert_frame_equal(work, before)


def test_mixed_frame_counts_each_kind():
    work = pd.DataFrame([
        _row("KTC"), _row("Locker", size="L"), _row("KTC or Kanban"), _row(""),
    ])
    counts = apply_system_type(work, **PARAMS)
    assert counts == {"ktc": 1, "locker": 1, "flex": 1}
    assert work.at[0, "SystemCategory"] == "KTC"
    assert work.at[1, "CabinetType"] == "Locker B"           # L -> Locker B
    assert work.at[2, "CabinetType"] == "Kanban"
    assert work.at[3, "CabinetType"] == "Kanban"
