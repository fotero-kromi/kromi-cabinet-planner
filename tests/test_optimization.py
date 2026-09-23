"""Tests for the PuLP/CBC KTC cabinet-allocation optimizer."""

from __future__ import annotations

from optimization import OptItem, solve_ktc_allocation


def test_empty_items():
    r = solve_ktc_allocation([])
    assert r.total_cabinets == 0 and r.optimal


def test_single_forced_helix_full_cabinet():
    r = solve_ktc_allocation([OptItem("a", helix_units=70, carousel_units=0, forced="Helix")])
    assert r.helix_cabinets == 1 and r.carousel_cabinets == 0
    assert r.routing["a"] == "Helix"


def test_helix_capacity_ceiling():
    # 71 spirals forced to Helix -> needs 2 cabinets (cap 70)
    r = solve_ktc_allocation([OptItem("a", 71, 0, forced="Helix")], helix_capacity=70)
    assert r.helix_cabinets == 2


def test_forced_carousel():
    r = solve_ktc_allocation([OptItem("a", 0, 720, forced="Carousel")], carousel_capacity=720)
    assert r.carousel_cabinets == 1 and r.helix_cabinets == 0


def test_routing_minimizes_total_cabinets():
    # Two flexible items. Each would need a whole Helix on its own (70 spirals),
    # but each fits comfortably in a shared Carousel (small slot use). The
    # optimizer should route both to one Carousel (1 cabinet) rather than two
    # Helix cabinets.
    items = [
        OptItem("a", helix_units=70, carousel_units=10),
        OptItem("b", helix_units=70, carousel_units=10),
    ]
    r = solve_ktc_allocation(items, helix_capacity=70, carousel_capacity=720)
    assert r.optimal
    assert r.total_cabinets == 1
    assert r.carousel_cabinets == 1 and r.helix_cabinets == 0
    assert r.routing["a"] == "Carousel" and r.routing["b"] == "Carousel"


def test_routing_prefers_helix_when_carousel_costly():
    # One item: 5 spirals on Helix, or 700 slots on Carousel. Cheapest is Helix.
    r = solve_ktc_allocation(
        [OptItem("a", helix_units=5, carousel_units=700)],
        helix_capacity=70,
        carousel_capacity=720,
    )
    assert r.helix_cabinets == 1 and r.carousel_cabinets == 0
    assert r.routing["a"] == "Helix"


def test_cost_weighting_changes_choice():
    # Equal raw counts would tie; make Carousel cheap so the solver consolidates
    # there even though Helix could also hold it.
    items = [OptItem("a", helix_units=70, carousel_units=70)]
    r = solve_ktc_allocation(items, helix_cost=10.0, carousel_cost=1.0)
    assert r.routing["a"] == "Carousel"


def test_mixed_forced_and_flexible():
    items = [
        OptItem("f1", 70, 0, forced="Helix"),
        OptItem("x", helix_units=10, carousel_units=10),
    ]
    r = solve_ktc_allocation(items)
    assert r.helix_cabinets >= 1
    assert r.routing["f1"] == "Helix"
    assert r.total_cabinets == r.helix_cabinets + r.carousel_cabinets


# ---------------------------------------------------------------------------
# v33 regression: phantom cabinet savings from zero helix_units
#
# The heuristic only stamps Spiral_capacity on rows it routed to Helix; Carousel
# rows carry None. The optimizer page used that stored value directly, so
# compute_helix_spirals_needed(tp, None) returned 0 for every carousel item and
# the solver packed unlimited carousel items into a single Helix for free,
# reporting impossible savings (e.g. 405 items collapsing 3 cabinets to 1).
# helix_units_for_routing derives the capacity from size+category instead.
# ---------------------------------------------------------------------------
from optimization import helix_units_for_routing


def test_helix_units_nonzero_when_capacity_missing():
    # A carousel-style row: positive demand, NO stored spiral capacity (None).
    # Must still report a positive helix cost (what it WOULD use in a Helix).
    u = helix_units_for_routing(
        target_packs=2.0, stored_spiral_capacity=None, size_cat="M", prod_cat="drills"
    )
    assert u > 0, "carousel item must not be weightless in a Helix"


def test_helix_units_zero_only_for_zero_demand():
    assert helix_units_for_routing(0.0, None, "M", "drills") == 0
    assert helix_units_for_routing(float("nan"), None, "M", "drills") == 0


def test_helix_units_uses_stored_capacity_when_valid():
    # When a valid stored capacity is present it should be honored.
    u_stored = helix_units_for_routing(50.0, 10, "M", "drills")
    assert u_stored >= 1


def test_no_phantom_savings_when_units_derived():
    # 60 carousel-type items, each ~3 carousel slots, each a real >=1 spiral in
    # Helix. They cannot all collapse into one cabinet. With derived helix units
    # (never zero), the solver must not report a single-cabinet solution.
    items = []
    for i in range(60):
        h = helix_units_for_routing(2.0, None, "M", "drills")  # derived, > 0
        items.append(OptItem(str(i), helix_units=float(h), carousel_units=3.0))
    r = solve_ktc_allocation(items, helix_capacity=70, carousel_capacity=720)
    # 60 items * >=1 spiral > 70 cannot fit one Helix; 60*3=180 slots fits one
    # Carousel, so the honest optimum is 1 Carousel — but never 1 Helix holding
    # all 60. Assert the result is actually feasible for whatever it routed.
    routed_helix = sum(items[int(k)].helix_units for k, v in r.routing.items() if v == "Helix")
    routed_car = sum(items[int(k)].carousel_units for k, v in r.routing.items() if v == "Carousel")
    assert r.helix_cabinets * 70 >= routed_helix
    assert r.carousel_cabinets * 720 >= routed_car


def test_zero_capacity_input_is_the_old_bug_signature():
    # Documents the failure mode: if helix_units is 0 (the old wiring), the
    # solver legitimately packs everything into a free Helix. This is correct
    # solver behavior on bad input — which is exactly why the caller must derive
    # real units via helix_units_for_routing.
    items = [OptItem(str(i), helix_units=0.0, carousel_units=3.0) for i in range(405)]
    r = solve_ktc_allocation(items, helix_capacity=70, carousel_capacity=720)
    assert r.total_cabinets <= 1  # phantom: all 405 "fit" a single empty Helix
