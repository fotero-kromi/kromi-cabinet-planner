"""kromi_app.optimization — solver-based KTC cabinet allocation (PuLP + CBC).

The heuristic planner routes each KTC item to Helix or Carousel by a fixed
demand threshold, then counts cabinets per type. That count is already optimal
*given a fixed routing* (it's ceil(units / capacity)); the slack the heuristic
can leave is in the routing itself — a borderline item sent to Carousel might
have topped up a half-empty Helix instead, or vice versa.

This module reformulates the routing + counting as one mixed-integer program and
lets CBC choose the routing that minimizes the total cabinet count (or a
cost/footprint-weighted count). It is deliberately honest about its value: on
many datasets the heuristic is already at or near the optimum, so the page shows
the heuristic result next to this one and reports the difference rather than
asserting a win.

Kept out of engine/ (like presentation.py) because PuLP shells out to the CBC
binary and ships no type stubs; the logic here is still unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pulp


@dataclass(frozen=True)
class OptItem:
    """One KTC item and what it would consume in each cabinet type."""

    item_id: str
    helix_units: float  # spirals consumed if routed to Helix
    carousel_units: float  # carousel slots consumed if routed to Carousel
    forced: str | None = None  # "Helix" | "Carousel" | None (flexible)


@dataclass(frozen=True)
class AllocationResult:
    helix_cabinets: int
    carousel_cabinets: int
    total_cabinets: int
    objective: float
    status: str
    optimal: bool
    routing: dict[str, str] = field(default_factory=dict)  # item_id -> cabinet type


def helix_units_for_routing(
    target_packs: float,
    stored_spiral_capacity: object,
    size_cat: str,
    prod_cat: str,
    overfill_factor: float = 1.10,
) -> int:
    """Spirals an item WOULD consume if routed to Helix.

    The heuristic only stamps ``Spiral_capacity`` on rows it actually routed to
    Helix; Carousel/Locker rows carry ``None``. The optimizer must still know
    what those rows would cost in a Helix, so when the stored capacity is
    missing or non-positive we derive it from size + category. Returning 0 for
    such rows (the original bug) made the solver treat carousel items as
    weightless and pack them into a Helix for free, reporting phantom savings.
    """
    import math

    import pandas as pd

    from engine.cabinet_math import compute_helix_spirals_needed, decide_spiral_capacity

    if target_packs is None or (isinstance(target_packs, float) and math.isnan(target_packs)):
        return 0
    if float(target_packs) <= 0:
        return 0

    cap = pd.to_numeric(stored_spiral_capacity, errors="coerce")
    if pd.isna(cap) or float(cap) <= 0:
        cap = decide_spiral_capacity(str(size_cat), str(prod_cat))
    return int(compute_helix_spirals_needed(float(target_packs), float(cap), overfill_factor))


def solve_ktc_allocation(
    items: list[OptItem],
    helix_capacity: int = 70,
    carousel_capacity: int = 720,
    helix_cost: float = 1.0,
    carousel_cost: float = 1.0,
    time_limit_s: int = 20,
) -> AllocationResult:
    """Minimize weighted Helix+Carousel cabinet count over the routing of items.

    Forced items are pinned to their cabinet type; flexible items are routed by
    the solver. Costs let you weight by footprint/price instead of raw count
    (equal costs => minimize total cabinets).
    """
    if not items:
        return AllocationResult(0, 0, 0, 0.0, "Empty", True, {})

    prob = pulp.LpProblem("ktc_allocation", pulp.LpMinimize)

    helix_terms = []
    carousel_terms = []
    route_vars: dict[str, pulp.LpVariable] = {}
    routing: dict[str, str] = {}

    for it in items:
        if it.forced == "Helix":
            helix_terms.append(it.helix_units)
            routing[it.item_id] = "Helix"
        elif it.forced == "Carousel":
            carousel_terms.append(it.carousel_units)
            routing[it.item_id] = "Carousel"
        else:
            v = pulp.LpVariable(f"route_{it.item_id}", cat="Binary")  # 1 => Helix
            route_vars[it.item_id] = v
            helix_terms.append(v * it.helix_units)
            carousel_terms.append((1 - v) * it.carousel_units)

    n_helix = pulp.LpVariable("n_helix", lowBound=0, cat="Integer")
    n_carousel = pulp.LpVariable("n_carousel", lowBound=0, cat="Integer")

    prob += n_helix * helix_capacity >= pulp.lpSum(helix_terms)
    prob += n_carousel * carousel_capacity >= pulp.lpSum(carousel_terms)
    prob += helix_cost * n_helix + carousel_cost * n_carousel

    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit_s))

    status = pulp.LpStatus[prob.status]
    optimal = status == "Optimal"

    for item_id, v in route_vars.items():
        routing[item_id] = "Helix" if round(v.value() or 0) == 1 else "Carousel"

    nh = int(round(n_helix.value() or 0))
    nc = int(round(n_carousel.value() or 0))
    return AllocationResult(
        helix_cabinets=nh,
        carousel_cabinets=nc,
        total_cabinets=nh + nc,
        objective=float(pulp.value(prob.objective) or 0.0),
        status=status,
        optimal=optimal,
        routing=routing,
    )
