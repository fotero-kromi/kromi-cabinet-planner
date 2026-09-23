"""Sizing orchestration: assigning each row to a cabinet type.

The planner page glued together the cabinet-math primitives with inline loops.
This module starts moving that orchestration into the engine so the sizing flow
becomes testable on its own. It holds the orchestration; the per-row decisions
stay in ``engine.cabinet_math``.

Pure: no Streamlit, no I/O. Functions return a new frame and do not mutate input.
"""

from __future__ import annotations

import math

import pandas as pd

from engine.cabinet_math import (
    compute_helix_spirals_needed,
    decide_cabinet_type,
    decide_spiral_capacity,
    regrind_spiral_floor,
)


def assign_cabinet_types(df: pd.DataFrame, *, helix_threshold: float) -> pd.DataFrame:
    """Add ``CabinetType`` and ``Spiral_capacity`` for every row.

    Kanban rows are not on a cabinet, so they get ``CabinetType`` "Kanban" and no
    spiral capacity. Every other row is routed to a cabinet by
    :func:`engine.cabinet_math.decide_cabinet_type`; a Helix row also gets a spiral
    capacity from :func:`engine.cabinet_math.decide_spiral_capacity`. Requires
    ``SystemCategory``, ``SizeCategory``, ``Monthly_packs``, ``ProductCategory``.

    Row count and index are preserved exactly: one cabinet type is produced per
    input row, in row order.
    """
    out = df.copy()
    cabinet_types: list[str] = []
    spiral_caps: list[int | None] = []

    for _, row in out.iterrows():
        if row["SystemCategory"] == "Kanban":
            cabinet_types.append("Kanban")
            spiral_caps.append(None)
            continue

        cab_type = decide_cabinet_type(
            size_cat=str(row.get("SizeCategory", "")),
            monthly_packs=float(row["Monthly_packs"]),
            helix_threshold_packs=float(helix_threshold),
        )
        cabinet_types.append(cab_type)

        if cab_type == "Helix":
            spiral_caps.append(
                decide_spiral_capacity(str(row.get("SizeCategory", "")), str(row.get("ProductCategory", "")))
            )
        else:
            spiral_caps.append(None)

    out["CabinetType"] = cabinet_types
    out["Spiral_capacity"] = spiral_caps
    return out


def assign_physical_sizing(
    df: pd.DataFrame,
    *,
    minimum_carousel_allocation: int,
    carousel_reserve_factor: float,
    helix_overfill_factor: float,
) -> pd.DataFrame:
    """Add ``Spirals_needed`` (Helix) and ``Carousel_stockpiles`` (KTC carousel).

    Helix rows are sized from ``Target_packs`` (the coverage-window-scaled demand)
    and their spiral capacity by :func:`engine.cabinet_math.compute_helix_spirals_needed`.
    A reground tool kept in a Helix needs new and reground pieces in separate
    spirals, so a regrind Helix row sized to one spiral is floored to two via
    :func:`engine.cabinet_math.regrind_spiral_floor`; carousel and locker reserve
    already covers the combined consumption, so only Helix is bumped.

    KTC carousel rows are sized from ``Target_packs`` scaled by the reserve factor,
    then floored to ``minimum_carousel_allocation`` for every carousel row -- a row
    that cleared the KTC threshold belongs in the machine, and a single compartment
    is a stockout risk. A final pass re-applies that floor defensively.

    ``carousel_reserve_factor`` and ``helix_overfill_factor`` are passed in rather
    than read from constants because the page lets the user adjust both at run time;
    the values here are the user's chosen settings. Requires ``CabinetType``,
    ``Target_packs``, ``Spiral_capacity``, ``SystemCategory``, ``Regrind``.

    Row count and index are preserved exactly; both columns are integer-typed.
    """
    out = df.copy()

    out["Spirals_needed"] = 0
    mask_helix = out["CabinetType"] == "Helix"
    if mask_helix.any():
        helix_df = out.loc[mask_helix, ["Target_packs", "Spiral_capacity"]].copy()
        helix_df["Spirals_needed"] = helix_df.apply(
            lambda r: compute_helix_spirals_needed(
                monthly_packs=r["Target_packs"],
                spiral_capacity=r["Spiral_capacity"],
                overfill_factor=helix_overfill_factor,
            ),
            axis=1,
        )
        out.loc[mask_helix, "Spirals_needed"] = helix_df["Spirals_needed"].astype(int)

    _mask_regrind_helix = mask_helix & out["Regrind"].astype(bool)
    if _mask_regrind_helix.any():
        out.loc[_mask_regrind_helix, "Spirals_needed"] = [
            regrind_spiral_floor(s, True)
            for s in out.loc[_mask_regrind_helix, "Spirals_needed"]
        ]

    out["Carousel_stockpiles"] = 0
    mask_car = (out["SystemCategory"] == "KTC") & (out["CabinetType"] == "Carousel")
    if mask_car.any():
        car_raw = (
            out.loc[mask_car, "Target_packs"] * carousel_reserve_factor
        ).apply(lambda x: max(1, int(math.ceil(x))))
        car_raw = car_raw.clip(lower=int(minimum_carousel_allocation))
        out.loc[mask_car, "Carousel_stockpiles"] = car_raw.astype(int)

    # Defensive floor: no KTC carousel row may stay below the user-set minimum,
    # regardless of how it was sized upstream.
    mask_car_min = (out["SystemCategory"] == "KTC") & (out["CabinetType"] == "Carousel")
    if mask_car_min.any():
        out.loc[mask_car_min, "Carousel_stockpiles"] = (
            pd.to_numeric(out.loc[mask_car_min, "Carousel_stockpiles"], errors="coerce")
            .fillna(0)
            .clip(lower=int(minimum_carousel_allocation))
            .astype(int)
        )

    return out
