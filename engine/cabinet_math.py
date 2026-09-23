"""kromi_app.engine.cabinet_math — cabinet sizing math + the rebalancer.

This is the most behavior-sensitive engine module. It owns:

* `apply_capacity_buffer` — inflate counts by buffer_pct rounded up
* `decide_cabinet_type` / `decide_spiral_capacity` — per-item routing
* `compute_helix_spirals_needed` — spirals needed for one item (parametrized
   by the overfill factor)
* `compute_helix_needs` / `compute_carousel_needs` / `compute_locker_needs`
   — roll-up cabinet counts for a DataFrame
* `assign_supply_points` + `_partition_supply_points_lpt` +
  `_replicate_across_supply_points` — SP assignment strategies
* `apply_bulk_routing` — route bulk-consumable families to Kanban
* `compute_plan_for_subset` — full rollup for one subset (returns a plan dict)
* `rebalance_cabinets` — bidirectional rebalancer (consolidates underused
   cabinets by moving items to other cabinet types with headroom)

DESIGN NOTE on factor handling:
Two domain constants — HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR (default 1.10) and
CAROUSEL_RESERVE_FACTOR (default 0.85) — are mutated at runtime by the page's
sidebar. To keep this module free of mutable global state and still honor the
user's chosen values, we accept both as optional parameters with defaults
imported from engine.constants. The page passes its CURRENT runtime values
through thin shims, so the user's sidebar choices are always respected.
"""

from __future__ import annotations

import math
from typing import Any, Dict

import pandas as pd

from .classification import detect_item_family
from .constants import (
    BULK_ALWAYS_FAMILIES,
    CAROUSEL_SLOTS_PER_CAB,
    DISPOSABLE_PPE_FAMILIES,
    HELIX_SPIRALS_PER_CAB,
    LISTING_TOOLS,
    LOCKER_A_CAP,
    LOCKER_B_CAP,
    LOCKER_C_CAP,
    SP_MODE_PARTITION,
    SP_MODE_REPLICATE,
    SP_MODE_VALID,
)
from .constants import (
    CAROUSEL_RESERVE_FACTOR as _DEFAULT_CAROUSEL_RESERVE_FACTOR,
)
from .constants import (
    HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR as _DEFAULT_HELIX_OVERFILL_FACTOR,
)
from .text_utils import norm

# Reason string stamped on a row that the "Set special tools as KTC" toggle
# forced onto vending. Defined once here because the Excel export's
# Forced_to_KTC column and the Run_Metadata "Special forced to KTC" count both
# key on this exact value; keeping it a shared constant stops the engine and the
# export from drifting apart.
SPECIAL_KTC_REASON = "Special tool forced to KTC"

# ---- Per-row sizing ----


def apply_capacity_buffer(value: int, buffer_pct: float) -> int:
    """Inflate a demand count by buffer_pct %, rounded up."""
    if buffer_pct <= 0 or value <= 0:
        return int(value)
    return int(math.ceil(float(value) * (1.0 + buffer_pct / 100.0)))


def decide_cabinet_type(size_cat: str, monthly_packs: float, helix_threshold_packs: float) -> str:
    sc = norm(size_cat)
    if sc == "xxl":
        return "Locker A"
    if sc == "xxls":
        return "Locker B"
    if sc == "xls":
        return "Locker C"
    if monthly_packs > float(helix_threshold_packs):
        return "Helix"
    return "Carousel"


def decide_spiral_capacity(size_cat: str, prod_cat: str) -> int:
    sc = norm(size_cat)
    pc = norm(prod_cat)

    if sc == "s":
        return 28
    if sc == "m":
        return 22
    if sc == "l":
        return 18
    if sc == "xl":
        return 12

    if pc == "inserts":
        return 28
    if pc == "drills":
        return 22
    return 18


def compute_helix_spirals_needed(
    monthly_packs: float,
    spiral_capacity: float,
    overfill_factor: float = _DEFAULT_HELIX_OVERFILL_FACTOR,
) -> int:
    """Spirals required to hold `monthly_packs` packs given a single-spiral
    capacity of `spiral_capacity` packs. A single spiral suffices if demand
    is within `spiral_capacity * overfill_factor`. The page passes its
    runtime overfill_factor; tests/CLI can rely on the default 1.10."""
    if pd.isna(monthly_packs) or pd.isna(spiral_capacity) or spiral_capacity <= 0:
        return 0

    monthly_packs = float(monthly_packs)
    spiral_capacity = float(spiral_capacity)

    if monthly_packs <= 0:
        return 0

    if monthly_packs <= spiral_capacity * overfill_factor:
        return 1

    return int(math.ceil(monthly_packs / spiral_capacity))


def locker_for_size(size_cat: str) -> str:
    """Locker tier (Locker A / B / C) for a forced-locker item, chosen by size.

    Consistent with :func:`decide_cabinet_type` for the oversize taxonomy
    (xxl -> Locker A 48, xxls -> Locker B 72, xls -> Locker C 96) and extended
    to the regular S/M/L/XL sizes a customer may flag as Locker: bigger tools
    get the lower-count locker (larger compartments). Used only when a row's
    System type is fixed to Locker; never changes normal routing.
    """
    sc = norm(size_cat)
    if sc in ("xxl", "xl"):
        return "Locker A"
    if sc in ("xxls", "l"):
        return "Locker B"
    return "Locker C"


def regrind_spiral_floor(spirals: Any, regrind: bool) -> int:
    """Helix spiral floor for reground tools.

    A reground tool kept in a Helix needs new and reground pieces in separate
    spirals (they cannot share a coil). So a regrind Helix item sized to a
    single spiral is floored to two; an item that already needs two or more
    spirals is left as-is (the existing spirals already separate the two
    streams and cover the combined consumption). A 0-spiral item (not on a
    Helix) is never bumped.
    """
    n = int(spirals)
    if regrind and n >= 1:
        return max(2, n)
    return n


def route_and_size_row(
    *,
    monthly_packs: float,
    target_packs: float,
    size_cat: str,
    product_category: str,
    threshold: float,
    helix_threshold: float,
    min_carousel_compartments: int,
    carousel_reserve_factor: float,
    helix_overfill_factor: float,
    force_kanban: bool = False,
    monthly_pcs: float | None = None,
    regrind: bool = False,
    force_ktc: bool = False,
) -> dict:
    """Decide SystemCategory, CabinetType, and vending counts for one row.

    ``force_kanban`` pins the row to Kanban (e.g. screws/accessories). ``force_ktc``
    does the opposite: it skips the Kanban gate so the row always stays KTC and
    receives a cabinet, even when consumption is below the threshold (used by the
    customer System type = KTC override). If both are set, ``force_kanban`` wins.

    Pure composition of the routing/sizing primitives. Used to re-route a row
    after a library override changes its inputs (ProductCategory / PackUnits)
    so its routing reflects its final attributes rather than the decision made
    before the override (HMA-1). `threshold` is the already-resolved per-row
    KTC/Kanban threshold (the caller applies the per-class rule); set
    `force_kanban` when a category rule (e.g. force screws/accessories) pins the
    row to the warehouse.

    The KTC/Kanban gate is compared against `monthly_pcs` (monthly pieces) when
    supplied; if it is None the gate falls back to `monthly_packs` for backward
    compatibility. Physical sizing (Helix-vs-Carousel split, spirals, carousel
    stockpiles) always uses packs. `regrind` floors a Helix item to two spirals.
    Returns SystemCategory, CabinetType, Spiral_capacity, Spirals_needed,
    Carousel_stockpiles.
    """
    mp = float(monthly_packs) if not pd.isna(monthly_packs) else 0.0
    gate_val = mp if monthly_pcs is None else (
        float(monthly_pcs) if not pd.isna(monthly_pcs) else 0.0
    )
    if force_kanban or (not force_ktc and gate_val <= float(threshold)):
        return {
            "SystemCategory": "Kanban", "CabinetType": "Kanban",
            "Spiral_capacity": None, "Spirals_needed": 0, "Carousel_stockpiles": 0,
        }
    cab = decide_cabinet_type(
        size_cat=str(size_cat), monthly_packs=mp,
        helix_threshold_packs=float(helix_threshold),
    )
    if cab == "Helix":
        cap = decide_spiral_capacity(str(size_cat), str(product_category))
        spirals = int(max(1, compute_helix_spirals_needed(mp, cap, float(helix_overfill_factor))))
        spirals = regrind_spiral_floor(spirals, bool(regrind))
        return {
            "SystemCategory": "KTC", "CabinetType": "Helix",
            "Spiral_capacity": cap, "Spirals_needed": spirals, "Carousel_stockpiles": 0,
        }
    if cab == "Carousel":
        tp = float(target_packs) if not pd.isna(target_packs) else 0.0
        stockpiles = max(int(min_carousel_compartments),
                         max(1, math.ceil(tp * float(carousel_reserve_factor))))
        return {
            "SystemCategory": "KTC", "CabinetType": "Carousel",
            "Spiral_capacity": None, "Spirals_needed": 0, "Carousel_stockpiles": int(stockpiles),
        }
    # Locker A/B/C (oversize): KTC but no spirals/stockpiles.
    return {
        "SystemCategory": "KTC", "CabinetType": cab,
        "Spiral_capacity": None, "Spirals_needed": 0, "Carousel_stockpiles": 0,
    }


def apply_system_type(
    work: pd.DataFrame,
    *,
    threshold: float,
    helix_threshold: float,
    min_carousel_compartments: int,
    carousel_reserve_factor: float,
    helix_overfill_factor: float,
) -> Dict[str, int]:
    """Apply a customer-specified System type (Lagersystem) column to the plan.

    When a ``SystemTyp`` column is present, the customer's stated system wins over
    the planner's own KTC/Kanban/cabinet decision: ``"KTC"`` forces a vending
    machine (never Kanban, even at low consumption), ``"Locker"`` forces a
    size-matched locker, and ``"KTC or Kanban"`` keeps the normal monthly-pieces
    threshold. Forced rows (KTC and Locker) are pinned via ``Routing_Pinned`` so
    bulk routing and cabinet consolidation leave them in place, exactly like a
    technician cabinet override. Blank or unrecognised values are left untouched.

    Returns counts ``{"ktc": n, "locker": n, "flex": n}`` for the caller to
    report. Without a ``SystemTyp`` column nothing is applied and the counts are
    zero. Mutates ``work`` in place. Mirrors ``force_special_to_ktc``.
    """
    from .routing_rules import parse_system_type

    if "SystemTyp" not in work.columns:
        return {"ktc": 0, "locker": 0, "flex": 0}

    stype = work["SystemTyp"].map(parse_system_type)
    n_ktc = n_locker = n_flex = 0
    for idx in work.index:
        sval = stype.at[idx]
        if sval == "KTC":
            res = route_and_size_row(
                monthly_packs=pd.to_numeric(work.at[idx, "Monthly_packs"], errors="coerce"),
                monthly_pcs=pd.to_numeric(work.at[idx, "Monthly_pcs"], errors="coerce"),
                target_packs=pd.to_numeric(work.at[idx, "Target_packs"], errors="coerce"),
                size_cat=work.at[idx, "SizeCategory"],
                product_category=work.at[idx, "ProductCategory"],
                threshold=float(threshold),
                helix_threshold=float(helix_threshold),
                min_carousel_compartments=int(min_carousel_compartments),
                carousel_reserve_factor=float(carousel_reserve_factor),
                helix_overfill_factor=float(helix_overfill_factor),
                regrind=bool(work.at[idx, "Regrind"]),
                force_ktc=True,
            )
            work.at[idx, "SystemCategory"] = res["SystemCategory"]
            work.at[idx, "CabinetType"] = res["CabinetType"]
            work.at[idx, "Spiral_capacity"] = (
                res["Spiral_capacity"] if res["Spiral_capacity"] is not None else pd.NA
            )
            work.at[idx, "Spirals_needed"] = int(res["Spirals_needed"])
            work.at[idx, "Carousel_stockpiles"] = int(res["Carousel_stockpiles"])
            work.at[idx, "Routing_Pinned"] = True
            work.at[idx, "SystemCategory_Reason"] = "System type fixed: KTC (forced vending)"
            n_ktc += 1
        elif sval == "LOCKER":
            lk = locker_for_size(work.at[idx, "SizeCategory"])
            work.at[idx, "SystemCategory"] = "KTC"
            work.at[idx, "CabinetType"] = lk
            work.at[idx, "Spiral_capacity"] = pd.NA
            work.at[idx, "Spirals_needed"] = 0
            work.at[idx, "Carousel_stockpiles"] = 0
            work.at[idx, "Routing_Pinned"] = True
            work.at[idx, "SystemCategory_Reason"] = f"System type fixed: Locker ({lk})"
            n_locker += 1
        elif sval == "KTC_OR_KANBAN":
            n_flex += 1
        # blank / unrecognised -> no change (normal routing stands)
    return {"ktc": n_ktc, "locker": n_locker, "flex": n_flex}


def force_special_to_ktc(
    work: pd.DataFrame,
    *,
    threshold: float,
    helix_threshold: float,
    min_carousel_compartments: int,
    carousel_reserve_factor: float,
    helix_overfill_factor: float,
) -> int:
    """Force every row marked Special onto KTC vending, returning the count forced.

    A row is Special when its ``StdSpecial`` marker classifies as special
    (``routing_rules.classify_standard_special``: 1 = standard, 2 = special, plus
    the words and yes/no). Each such row is re-routed and re-sized exactly like
    the customer System type = KTC override (``route_and_size_row`` with
    ``force_ktc=True``), so it lands in a vending machine even below the
    KTC/Kanban threshold, with the spiral/stockpile sizing that implies. The row
    is then pinned with ``Routing_Pinned`` so bulk routing and cabinet
    consolidation leave it in place, matching how a System-type-fixed or
    technician-fixed row is protected.

    System type wins where it already fixed a row: any row already carrying
    ``Routing_Pinned`` is skipped, so a System type = KTC/Locker decision is
    never overwritten by this toggle. Rows that are not Special, or whose marker
    is blank, standard, or unrecognised, keep the routing the planner gave them.

    Requires a ``StdSpecial`` column; without it nothing is Special and the
    function returns 0 and changes nothing. Mutates ``work`` in place.
    """
    from .routing_rules import classify_standard_special, SPECIAL

    if "StdSpecial" not in work.columns:
        return 0
    has_forced_col = "Routing_Pinned" in work.columns
    n_forced = 0
    for idx in work.index:
        if classify_standard_special(work.at[idx, "StdSpecial"]) != SPECIAL:
            continue
        if has_forced_col and bool(work.at[idx, "Routing_Pinned"]):
            continue  # System type already fixed this row; it wins.
        res = route_and_size_row(
            monthly_packs=pd.to_numeric(work.at[idx, "Monthly_packs"], errors="coerce"),
            monthly_pcs=pd.to_numeric(work.at[idx, "Monthly_pcs"], errors="coerce"),
            target_packs=pd.to_numeric(work.at[idx, "Target_packs"], errors="coerce"),
            size_cat=work.at[idx, "SizeCategory"],
            product_category=work.at[idx, "ProductCategory"],
            threshold=float(threshold),
            helix_threshold=float(helix_threshold),
            min_carousel_compartments=int(min_carousel_compartments),
            carousel_reserve_factor=float(carousel_reserve_factor),
            helix_overfill_factor=float(helix_overfill_factor),
            regrind=bool(work.at[idx, "Regrind"]) if "Regrind" in work.columns else False,
            force_ktc=True,
        )
        work.at[idx, "SystemCategory"] = res["SystemCategory"]
        work.at[idx, "CabinetType"] = res["CabinetType"]
        work.at[idx, "Spiral_capacity"] = (
            res["Spiral_capacity"] if res["Spiral_capacity"] is not None else pd.NA
        )
        work.at[idx, "Spirals_needed"] = int(res["Spirals_needed"])
        work.at[idx, "Carousel_stockpiles"] = int(res["Carousel_stockpiles"])
        if has_forced_col:
            work.at[idx, "Routing_Pinned"] = True
        work.at[idx, "SystemCategory_Reason"] = SPECIAL_KTC_REASON
        n_forced += 1
    return n_forced


# ---- Roll-ups ----


def compute_helix_needs(
    df: pd.DataFrame,
    overfill_factor: float = _DEFAULT_HELIX_OVERFILL_FACTOR,
) -> tuple[int, int]:
    if df.empty:
        return 0, 0

    if "Spirals_needed" in df.columns:
        total_spirals = int(pd.to_numeric(df["Spirals_needed"], errors="coerce").fillna(0).sum())
    else:
        total_spirals = 0
        for _, row in df.iterrows():
            # Defense-in-depth: this only runs on Helix subsets (which always
            # carry a Spiral_capacity), but derive from size+category if it's
            # ever missing so a refactor can't reopen the "None -> 0 spirals"
            # hole that bit the optimizer and rebalancer.
            cap = pd.to_numeric(row.get("Spiral_capacity"), errors="coerce")
            if pd.isna(cap) or float(cap) <= 0:
                cap = decide_spiral_capacity(
                    str(row.get("SizeCategory", "")), str(row.get("ProductCategory", ""))
                )
            total_spirals += (
                regrind_spiral_floor(
                    max(1, int(compute_helix_spirals_needed(
                        monthly_packs=row.get("Monthly_packs", 0),
                        spiral_capacity=cap,
                        overfill_factor=overfill_factor,
                    ))),
                    True,
                )
                if bool(row.get("Regrind", False))
                else compute_helix_spirals_needed(
                    monthly_packs=row.get("Monthly_packs", 0),
                    spiral_capacity=cap,
                    overfill_factor=overfill_factor,
                )
            )

    cabinets = math.ceil(total_spirals / HELIX_SPIRALS_PER_CAB) if total_spirals > 0 else 0
    return total_spirals, cabinets


def carousel_cabinets_needed(
    slots: int,
    *,
    fill_ceiling: float = 1.0,
    empty_threshold_pct: float = 0.0,
) -> int:
    """Number of carousel cabinets to hold ``slots`` compartments.

    ``fill_ceiling`` is the soft fill target as a fraction of physical capacity.
    At 1.0 (the default) cabinets fill to physical capacity and this returns
    ``ceil(slots / capacity)`` -- the original behaviour. Below 1.0 it leaves
    headroom (0.85 fills to 85%), which can require an extra cabinet.

    ``empty_threshold_pct`` governs that extra cabinet. A headroom-driven cabinet
    is only opened if its occupation against physical capacity would reach this
    percentage; otherwise its contents are absorbed into the headroom of the
    others (filling them above the soft target, up to physical capacity). At 0.0
    (the default) no absorption happens, so the headroom is always honoured. The
    result is never below ``ceil(slots / capacity)``, so physical capacity is
    always respected.
    """
    cap = CAROUSEL_SLOTS_PER_CAB
    slots = int(slots)
    if slots <= 0:
        return 0
    ceiling = float(fill_ceiling)
    if ceiling <= 0:
        ceiling = 1.0
    target = cap * ceiling
    n_hard = math.ceil(slots / cap)
    n_soft = math.ceil(slots / target)
    if n_soft <= n_hard:
        return n_hard
    n = n_soft
    while n > n_hard:
        last_fill = slots - (n - 1) * target
        if last_fill > 0 and (last_fill / cap) * 100.0 >= float(empty_threshold_pct):
            break  # the marginal cabinet is full enough to justify keeping it
        if (n - 1) * cap < slots:
            break  # cannot drop a cabinet without exceeding physical capacity
        n -= 1  # marginal cabinet too empty -> absorb into headroom, drop it
    return n


def compute_carousel_needs(
    df: pd.DataFrame,
    *,
    fill_ceiling: float = 1.0,
    empty_threshold_pct: float = 0.0,
    extra_slots: int = 0,
) -> tuple[int, int]:
    """``extra_slots`` (v34.24) are restock buffer compartments: exact
    reservations added on top of the row stockpiles. One buffer slot alone
    opens the first cabinet, which is how a supply point with a restockable
    Helix item ends up with its Carousel."""
    stock = 0
    if not df.empty:
        stock = int(df["Carousel_stockpiles"].fillna(0).clip(lower=0).sum())
    slots = stock + max(0, int(extra_slots))
    if slots <= 0:
        return 0, 0
    cabinets = carousel_cabinets_needed(
        slots, fill_ceiling=fill_ceiling, empty_threshold_pct=empty_threshold_pct
    )
    return slots, cabinets


def compute_locker_needs(df: pd.DataFrame, extras: tuple[int, int, int] = (0, 0, 0)):
    """``extras`` (v34.24) are restock buffer compartments per locker class
    (A, B, C), added to the compartment counts before the cabinet ceiling."""
    dfA = df[df["CabinetType"] == "Locker A"]
    dfB = df[df["CabinetType"] == "Locker B"]
    dfC = df[df["CabinetType"] == "Locker C"]

    countA = len(dfA) + max(0, int(extras[0]))
    countB = len(dfB) + max(0, int(extras[1]))
    countC = len(dfC) + max(0, int(extras[2]))

    cabA = math.ceil(countA / LOCKER_A_CAP) if countA else 0
    cabB = math.ceil(countB / LOCKER_B_CAP) if countB else 0
    cabC = math.ceil(countC / LOCKER_C_CAP) if countC else 0

    return (countA, cabA), (countB, cabB), (countC, cabC)


# ---- Supply-point assignment ----


def assign_supply_points(
    df: pd.DataFrame, n_sp: int, mode: str = SP_MODE_PARTITION
) -> pd.DataFrame:
    """Assign each row to one or more supply points."""
    mode = (mode or SP_MODE_PARTITION).strip().lower()
    if mode not in SP_MODE_VALID:
        mode = SP_MODE_PARTITION

    out = df.copy()

    # if SupplyPoint is already populated with real values (from the
    if "SupplyPoint" in out.columns:
        existing = pd.to_numeric(out["SupplyPoint"], errors="coerce")
        if existing.notna().all() and (existing >= 1).all():
            # Programme mapping path. Coerce to int in case it's Int64/float.
            out["SupplyPoint"] = existing.astype(int)
            return out

    if n_sp <= 1:
        out["SupplyPoint"] = 1
        return out

    if mode == SP_MODE_REPLICATE:
        return _replicate_across_supply_points(out, n_sp)
    return _partition_supply_points_lpt(out, n_sp)


def _partition_supply_points_lpt(df: pd.DataFrame, n_sp: int) -> pd.DataFrame:
    """LPT greedy: sort by Consumption_pcs desc, assign each next item to
    whichever SP currently has the lightest total. Done within each
    Listing so Tools and PPE are balanced independently."""
    out = df.copy()
    out["SupplyPoint"] = 1
    listings_present = out["Listing"].unique() if "Listing" in out.columns else [LISTING_TOOLS]

    for listing_val in listings_present:
        mask = (
            out["Listing"] == listing_val
            if "Listing" in out.columns
            else pd.Series([True] * len(out), index=out.index)
        )
        sub_idx = out.index[mask].tolist()
        if not sub_idx:
            continue

        sub_items = [
            (
                idx,
                float(out.at[idx, "Consumption_pcs"])
                if pd.notna(out.at[idx, "Consumption_pcs"])
                else 0.0,
            )
            for idx in sub_idx
        ]
        sub_items.sort(key=lambda x: -x[1])

        sp_loads = [0.0] * n_sp
        for idx, cons in sub_items:
            target_sp = min(range(n_sp), key=lambda s: sp_loads[s])
            out.at[idx, "SupplyPoint"] = target_sp + 1
            sp_loads[target_sp] += cons

    return out


def _replicate_across_supply_points(df: pd.DataFrame, n_sp: int) -> pd.DataFrame:
    """Duplicate each row n_sp times, dividing Consumption_pcs equally."""
    if n_sp <= 1:
        out = df.copy()
        out["SupplyPoint"] = 1
        return out

    # Repeat each row n_sp times (fast, pandas-native)
    out = df.loc[df.index.repeat(n_sp)].reset_index(drop=True).copy()

    # Tag each copy with its SupplyPoint (1..n_sp, cycling)
    out["SupplyPoint"] = (out.index % n_sp) + 1

    # Divide consumption equally across the N copies
    out["Consumption_pcs"] = pd.to_numeric(out["Consumption_pcs"], errors="coerce").fillna(
        0.0
    ) / float(n_sp)

    return out


# ---- Bulk routing ----


def apply_bulk_routing(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """(opt-in): route rows in bulk-consumable families out of vending."""
    out = df.copy()

    # Compute ItemFamily for every row (cheap)
    out["ItemFamily"] = out.apply(
        lambda r: detect_item_family(
            r.get("Description", ""),
            r.get("Description_2", ""),
            r.get("Code", ""),
            r.get("SupplierCode", ""),
        ),
        axis=1,
    )

    # Preserve pre-route values
    out["CabinetType_pre_route"] = out["CabinetType"] if "CabinetType" in out.columns else ""
    if "Spirals_needed" in out.columns:
        out["Spirals_needed_pre_route"] = (
            pd.to_numeric(out["Spirals_needed"], errors="coerce").fillna(0).astype(int)
        )
    else:
        out["Spirals_needed_pre_route"] = 0
    if "Carousel_stockpiles" in out.columns:
        out["Carousel_stockpiles_pre_route"] = (
            pd.to_numeric(out["Carousel_stockpiles"], errors="coerce").fillna(0).astype(int)
        )
    else:
        out["Carousel_stockpiles_pre_route"] = 0

    # if a row was already overridden by the technician (apply_overrides
    if "Override_Applied" in out.columns:
        has_override = out["Override_Applied"] == True  # noqa: E712
    else:
        has_override = pd.Series(False, index=out.index)
    # Rows whose System type is fixed (KTC or Locker) are protected exactly like
    # technician overrides: bulk routing must not move them out of vending.
    if "Routing_Pinned" in out.columns:
        has_override = has_override | (out["Routing_Pinned"] == True)  # noqa: E712

    # Only reset VendMode/VendBlockReason on rows NOT overridden
    if (~has_override).any():
        out.loc[~has_override, "VendMode"] = "Vending"
        out.loc[~has_override, "VendBlockReason"] = ""
    # Initialize columns for any overridden rows that happen to lack them
    # (shouldn't happen in practice, but extra)
    if "VendMode" not in out.columns:
        out["VendMode"] = "Vending"
    if "VendBlockReason" not in out.columns:
        out["VendBlockReason"] = ""

    # route a row to Bulk/Kanban ONLY if it's a bulk-family AND was
    route_mask = out["ItemFamily"].isin(BULK_ALWAYS_FAMILIES | DISPOSABLE_PPE_FAMILIES) & (
        ~has_override
    )
    if route_mask.any():
        out.loc[route_mask, "VendMode"] = "Bulk/Kanban"
        out.loc[route_mask, "VendBlockReason"] = "bulk-family:" + out.loc[
            route_mask, "ItemFamily"
        ].astype(str)
        out.loc[route_mask, "SystemCategory"] = "Kanban"
        out.loc[route_mask, "CabinetType"] = "Kanban"
        out.loc[route_mask, "Spirals_needed"] = 0
        out.loc[route_mask, "Carousel_stockpiles"] = 0
        out.loc[route_mask, "Spiral_capacity"] = pd.NA

    # Count overrides that prevented bulk routing, for audit purposes
    overridden_bulk_candidates = int(
        (
            out["ItemFamily"].isin(BULK_ALWAYS_FAMILIES | DISPOSABLE_PPE_FAMILIES) & has_override
        ).sum()
    )

    stats = {
        "routed_rows": int(route_mask.sum()),
        "removed_spirals": int(out.loc[route_mask, "Spirals_needed_pre_route"].sum()),
        "removed_carousel_slots": int(out.loc[route_mask, "Carousel_stockpiles_pre_route"].sum()),
        "by_family": dict(out.loc[route_mask, "ItemFamily"].value_counts()),
        "overridden_bulk_candidates": overridden_bulk_candidates,
    }
    return out, stats


# ---- Plan rollup ----


def compute_plan_for_subset(
    df_subset: pd.DataFrame,
    buf_pct: float,
    overfill_factor: float = _DEFAULT_HELIX_OVERFILL_FACTOR,
    *,
    buf_helix: float | None = None,
    buf_carousel: float | None = None,
    buf_locker: float | None = None,
    carousel_fill_ceiling: float = 1.0,
    empty_cabinet_threshold_pct: float = 0.0,
) -> dict[str, Any]:
    """Run the entire rollup calculation for a subset of rows.

    Accepts overfill_factor for compute_helix_needs; the page passes the
    runtime-mutated value through a shim. Default preserves the original 1.10.

    The capacity buffer can be set globally via ``buf_pct`` or per cabinet
    family via ``buf_helix`` / ``buf_carousel`` / ``buf_locker``. A per-family
    value of ``None`` falls back to ``buf_pct``, so passing only ``buf_pct``
    reproduces the original single-buffer behaviour exactly.

    ``carousel_fill_ceiling`` and ``empty_cabinet_threshold_pct`` size the
    carousel cabinet count via :func:`carousel_cabinets_needed`; the defaults
    (1.0 and 0.0) reproduce the original ``ceil(slots / capacity)`` behaviour.
    """
    _bh = buf_pct if buf_helix is None else buf_helix
    _bc = buf_pct if buf_carousel is None else buf_carousel
    _bl = buf_pct if buf_locker is None else buf_locker

    df_ktc_sub = df_subset[df_subset["SystemCategory"] == "KTC"].copy()
    df_kanban_sub = df_subset[df_subset["SystemCategory"] == "Kanban"].copy()
    df_helix_sub = df_ktc_sub[df_ktc_sub["CabinetType"] == "Helix"].copy()
    df_car_sub = df_ktc_sub[df_ktc_sub["CabinetType"] == "Carousel"].copy()

    # Restock buffers (v34.24): exact compartment reservations riding the
    # frame. They are added on top of the percentage capacity buffer, never
    # inflated by it, and the spill and rebalance logic operates on the row
    # stockpiles only, so a buffer can never be moved or reduced.
    def _extra(target: str) -> int:
        if "Restock_slots" not in df_ktc_sub.columns:
            return 0
        m = df_ktc_sub.get("Restock_target")
        if m is None:
            return 0
        sel = df_ktc_sub["Restock_slots"].where(m.astype(str) == target, 0)
        return int(pd.to_numeric(sel, errors="coerce").fillna(0).clip(lower=0).sum())

    extra_car = _extra("Carousel")
    extra_lockers = (_extra("Locker A"), _extra("Locker B"), _extra("Locker C"))

    total_spirals, helix_cabs_base = compute_helix_needs(
        df_helix_sub, overfill_factor=overfill_factor
    )
    car_slots, car_cabs_base = compute_carousel_needs(
        df_car_sub,
        fill_ceiling=carousel_fill_ceiling,
        empty_threshold_pct=empty_cabinet_threshold_pct,
        extra_slots=extra_car,
    )
    (countA, cabA_base), (countB, cabB_base), (countC, cabC_base) = compute_locker_needs(
        df_ktc_sub, extras=extra_lockers
    )

    total_spirals_buf = apply_capacity_buffer(total_spirals, _bh)
    car_slots_buf = apply_capacity_buffer(car_slots - extra_car, _bc) + extra_car
    countA_buf = apply_capacity_buffer(countA - extra_lockers[0], _bl) + extra_lockers[0]
    countB_buf = apply_capacity_buffer(countB - extra_lockers[1], _bl) + extra_lockers[1]
    countC_buf = apply_capacity_buffer(countC - extra_lockers[2], _bl) + extra_lockers[2]

    helix_cabs = (
        math.ceil(total_spirals_buf / HELIX_SPIRALS_PER_CAB) if total_spirals_buf > 0 else 0
    )
    car_cabs = carousel_cabinets_needed(
        car_slots_buf,
        fill_ceiling=carousel_fill_ceiling,
        empty_threshold_pct=empty_cabinet_threshold_pct,
    )
    cabA = math.ceil(countA_buf / LOCKER_A_CAP) if countA_buf > 0 else 0
    cabB = math.ceil(countB_buf / LOCKER_B_CAP) if countB_buf > 0 else 0
    cabC = math.ceil(countC_buf / LOCKER_C_CAP) if countC_buf > 0 else 0

    return {
        "rows_total": len(df_subset),
        "ktc_count": len(df_ktc_sub),
        "kanban_count": len(df_kanban_sub),
        "helix_refs": len(df_helix_sub),
        "carousel_refs": len(df_car_sub),
        "locker_a_refs": int((df_ktc_sub["CabinetType"] == "Locker A").sum()),
        "locker_b_refs": int((df_ktc_sub["CabinetType"] == "Locker B").sum()),
        "locker_c_refs": int((df_ktc_sub["CabinetType"] == "Locker C").sum()),
        "total_spirals": total_spirals,
        "total_spirals_buf": total_spirals_buf,
        "car_slots": car_slots,
        "car_slots_buf": car_slots_buf,
        "countA": countA,
        "countA_buf": countA_buf,
        "countB": countB,
        "countB_buf": countB_buf,
        "countC": countC,
        "countC_buf": countC_buf,
        "helix_cabs_base": helix_cabs_base,
        "helix_cabs": helix_cabs,
        "car_cabs_base": car_cabs_base,
        "car_cabs": car_cabs,
        "cabA_base": cabA_base,
        "cabA": cabA,
        "cabB_base": cabB_base,
        "cabB": cabB,
        "cabC_base": cabC_base,
        "cabC": cabC,
        "total_cabs_base": helix_cabs_base + car_cabs_base + cabA_base + cabB_base + cabC_base,
        "total_cabs": helix_cabs + car_cabs + cabA + cabB + cabC,
        "total_consumption": float(df_subset["Consumption_pcs"].fillna(0).sum()),
        "restock_car_slots": extra_car,
        "restock_lockerA": extra_lockers[0],
        "restock_lockerB": extra_lockers[1],
        "restock_lockerC": extra_lockers[2],
    }


# ---- Bidirectional rebalancer ----


def rebalance_cabinets(
    work: pd.DataFrame,
    buf_pct: float,
    minimum_carousel_allocation: int,
    underuse_threshold_pct: float,
    carousel_reserve_factor: float = _DEFAULT_CAROUSEL_RESERVE_FACTOR,
    overfill_factor: float = _DEFAULT_HELIX_OVERFILL_FACTOR,
    *,
    buf_helix: float | None = None,
    buf_carousel: float | None = None,
    buf_locker: float | None = None,
    carousel_fill_ceiling: float = 1.0,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Bidirectional rebalancer: consolidates underused cabinets by moving
    items to other cabinet types that have headroom.

    The rebalancer runs AFTER all initial routing (size, velocity, overrides,
    bulk routing). It computes the current plan, identifies any cabinet type
    where the last cabinet would be below the underuse threshold, and tries
    to relocate those items into cabinets of other types that have room.

    Rules:
      - Only the LAST cabinet of each type is consolidation-eligible.
      - Items with size XL/XXL/L stay in their Locker — they only fit there.
      - Items marked Override_Applied with cabinet_type in Override_Fields
        are PROTECTED (the technician explicitly placed them; never move).
      - Items are tried in velocity order: when promoting Carousel→Helix,
        fastest items first; when demoting Helix→Carousel, slowest first.
      - The move is atomic: either ALL items in the underused cabinet
        relocate, or NONE do (no partial moves).
      - Total post-rebalance cabinet count must be STRICTLY LOWER than
        pre-rebalance, else the move is reverted.

    Args:
        work: The work DataFrame post-routing.
        buf_pct: Capacity buffer percentage (e.g. 15 for 15%).
        minimum_carousel_allocation: Min stockpiles per KTC item routed to
            Carousel.
        underuse_threshold_pct: Below this occupation % the last cabinet of
            a type is consolidation-eligible (e.g. 30 means <30% triggers).
        carousel_reserve_factor: The carousel-reserve scalar. Default 0.85.
            The page passes its runtime-mutated value through a shim.
        overfill_factor: The helix single-spiral overfill factor. Default 1.10.
            The page passes its runtime-mutated value through a shim.

    Returns:
        (rebalanced_work, audit_events) where audit_events is a list of
        dicts describing what moved.
    """
    audit: list[dict[str, Any]] = []
    out = work.copy()

    # Helpers for what an item costs in each cabinet type.
    def _spirals_for(row) -> int:
        # Carousel/Locker rows carry no Spiral_capacity (only Helix rows get
        # one). To know what an item WOULD cost if promoted to a Helix, derive
        # the capacity from size + category when it's missing — otherwise
        # compute_helix_spirals_needed returns 0 and the move looks free, so the
        # rebalancer "consolidates" a fast mover into a Helix at zero spirals
        # and reports cost_at_destination = 0 (a phantom saving that overfills
        # the Helix in reality).
        cap = pd.to_numeric(row.get("Spiral_capacity"), errors="coerce")
        if pd.isna(cap) or float(cap) <= 0:
            cap = decide_spiral_capacity(
                str(row.get("SizeCategory", "")),
                str(row.get("ProductCategory", "")),
            )
        n = compute_helix_spirals_needed(
            monthly_packs=row.get("Target_packs", 0),
            spiral_capacity=cap,
            overfill_factor=overfill_factor,
        )
        if bool(row.get("Regrind", False)):
            n = regrind_spiral_floor(max(1, int(n)), True)
        return n

    def _stockpiles_for(row) -> int:
        """Cost of an item if placed in the Carousel. Applies the same
        minimum-allocation floor as the main pipeline so projected moves use
        consistent numbers."""
        tp = float(row.get("Target_packs", 0) or 0)
        if tp <= 0:
            return 0
        raw = max(1, int(math.ceil(tp * carousel_reserve_factor)))
        return max(raw, int(minimum_carousel_allocation))

    def _is_protected(row) -> bool:
        # A row fixed to Locker must stay in its locker: the rebalancer only
        # relocates items into Helix/Carousel, which would dissolve a forced
        # locker. Rows fixed to KTC are NOT pinned here -- they are ordinary KTC
        # vending items and may be consolidated between vending cabinets like any
        # other KTC item (the rebalancer never routes anything to Kanban, so the
        # "never Kanban" guarantee is unaffected). Technician cabinet_type
        # overrides stay pinned exactly as before.
        if bool(row.get("Routing_Pinned", False)) and str(
            row.get("CabinetType", "")
        ).startswith("Locker"):
            return True
        if not bool(row.get("Override_Applied", False)):
            return False
        fields = str(row.get("Override_Fields", ""))
        return "cabinet_type" in fields

    def _is_size_eligible(size_cat: str, target_cabinet: str) -> bool:
        s = (size_cat or "").upper()
        if target_cabinet == "Helix":
            return s in ("S", "M", "")
        if target_cabinet == "Carousel":
            # The Carousel is the larger vending compartment and is the catch-all
            # for any vending-sized tool. decide_cabinet_type sends every
            # non-locker size (S/M/L/XL) into vending, so the rebalancer must be
            # able to relocate an XL vending item here too -- otherwise a single
            # XL tool pins its cabinet and blocks consolidation. Only the true
            # locker sizes (XXL/XLS/XXLS) are excluded.
            return s in ("S", "M", "L", "XL", "")
        if target_cabinet == "Locker A":
            return s in ("S", "M")
        if target_cabinet == "Locker B":
            return s in ("L",)
        if target_cabinet == "Locker C":
            return s in ("XL", "XXL", "XLS", "XXLS")
        return False

    # Iterate up to N passes — each pass may eliminate one cabinet and create
    # new opportunities (e.g. eliminating a Carousel may free room for promoting
    # other items; but typically one pass is enough).
    MAX_PASSES = 4
    for pass_num in range(MAX_PASSES):
        moves_this_pass = 0

        # For each cabinet TYPE with >1 cabinets, check if the LAST one is
        # underused. We process types in priority order: try to eliminate
        # Carousel first (lowest "per-cabinet value" since they hold many items),
        # then Helix, then Lockers.
        candidates = [
            # (cabinet_type, items_per_cab, key_count_field, key_cabs_field)
            ("Carousel", CAROUSEL_SLOTS_PER_CAB, "car_slots_buf", "car_cabs"),
            ("Helix", HELIX_SPIRALS_PER_CAB, "total_spirals_buf", "helix_cabs"),
            ("Locker A", LOCKER_A_CAP, "countA_buf", "cabA"),
            ("Locker B", LOCKER_B_CAP, "countB_buf", "cabB"),
            ("Locker C", LOCKER_C_CAP, "countC_buf", "cabC"),
        ]

        plan = compute_plan_for_subset(
            out, buf_pct, overfill_factor=overfill_factor,
            buf_helix=buf_helix, buf_carousel=buf_carousel, buf_locker=buf_locker,
            carousel_fill_ceiling=carousel_fill_ceiling,
            empty_cabinet_threshold_pct=underuse_threshold_pct,
        )
        consolidated_a_cabinet = False

        for cab_type, cab_cap, count_key, cabs_key in candidates:
            n_cabs = plan[cabs_key]
            if n_cabs < 1:
                continue  # cabinet type isn't in use

            # If this is the ONLY cabinet of its type, we can still try to
            # eliminate it — but only if ALL its items can fit into another
            # cabinet type. This is the small-customer "5 lonely items"
            # case: one nearly-empty Carousel that could collapse into an
            # under-half-full Helix.
            #
            # When n_cabs >= 2, we target only the LAST cabinet's spillover
            # items. When n_cabs == 1, we target ALL items in that cabinet
            # (because eliminating the cabinet means moving everything).

            buf_count = plan[count_key]
            if n_cabs >= 2:
                full_cabs = n_cabs - 1
                usage_in_last = buf_count - (full_cabs * cab_cap)
                occupation_pct = (usage_in_last / cab_cap) * 100 if cab_cap > 0 else 0
            else:
                # Single cabinet — its occupation is the whole bucket
                usage_in_last = buf_count
                occupation_pct = (buf_count / cab_cap) * 100 if cab_cap > 0 else 0

            if occupation_pct >= underuse_threshold_pct:
                continue  # cabinet is healthily occupied

            # The items in this cabinet type, sorted for relocation
            cab_items = out[
                (out["SystemCategory"] == "KTC") & (out["CabinetType"] == cab_type)
            ].copy()

            # Which items belong to the LAST (underused) cabinet?
            # Greedy approximation: take the slowest items totaling
            # `usage_in_last` of resource.
            if cab_type == "Helix":
                cost_col = "Spirals_needed"
                cab_items = cab_items.sort_values("Monthly_packs", ascending=True)
            elif cab_type == "Carousel":
                cost_col = "Carousel_stockpiles"
                cab_items = cab_items.sort_values("Monthly_packs", ascending=False)
            else:  # Lockers
                cost_col = None  # 1 item per locker compartment
                cab_items = cab_items.sort_values("Monthly_packs", ascending=True)

            # Build the "items to relocate" set.
            # When n_cabs >= 2: only the slowest items totaling ~usage_in_last
            # (the spillover into the last underused cabinet).
            # When n_cabs == 1: ALL items in the cabinet (eliminate it entirely).
            last_cab_items = []
            if n_cabs >= 2:
                target_usage = usage_in_last
                accumulated = 0
                for idx, row in cab_items.iterrows():
                    if cost_col:
                        cost = int(pd.to_numeric(row[cost_col], errors="coerce") or 0)
                    else:
                        cost = 1
                    if accumulated >= target_usage:
                        break
                    last_cab_items.append((idx, row, cost))
                    accumulated += cost
            else:
                # Single cabinet — try to move everything
                for idx, row in cab_items.iterrows():
                    if cost_col:
                        cost = int(pd.to_numeric(row[cost_col], errors="coerce") or 0)
                    else:
                        cost = 1
                    last_cab_items.append((idx, row, cost))

            if not last_cab_items:
                continue

            # Try to relocate each to another cabinet type with room.
            # Working snapshot of moves; commit only if ALL fit.
            # Set to None as a sentinel when a move must be aborted.
            proposed_moves: list[dict[str, Any]] | None = []
            simulated = out.copy()

            for idx, row, cost in last_cab_items:
                if _is_protected(row):
                    proposed_moves = None
                    break  # can't move a protected item; abort this consolidation

                size = str(row.get("SizeCategory", "")).upper()
                moved = False

                # Try each alternative cabinet in priority order
                alt_options = []
                if cab_type != "Helix":
                    alt_options.append(("Helix", HELIX_SPIRALS_PER_CAB))
                if cab_type != "Carousel":
                    alt_options.append(("Carousel", CAROUSEL_SLOTS_PER_CAB))

                for alt_type, _alt_cap in alt_options:
                    if not _is_size_eligible(size, alt_type):
                        continue
                    # What would this item cost in alt cabinet?
                    if alt_type == "Helix":
                        alt_cost = _spirals_for(row)
                    elif alt_type == "Carousel":
                        alt_cost = _stockpiles_for(row)
                    else:
                        alt_cost = 1

                    # Project the simulated plan if we moved this item
                    test_df = simulated.copy()
                    test_df.at[idx, "CabinetType"] = alt_type
                    if alt_type == "Helix":
                        test_df.at[idx, "Spirals_needed"] = alt_cost
                        test_df.at[idx, "Carousel_stockpiles"] = 0
                    elif alt_type == "Carousel":
                        test_df.at[idx, "Spirals_needed"] = 0
                        test_df.at[idx, "Carousel_stockpiles"] = alt_cost

                    test_plan = compute_plan_for_subset(
                        test_df, buf_pct, overfill_factor=overfill_factor,
                        buf_helix=buf_helix, buf_carousel=buf_carousel, buf_locker=buf_locker,
                        carousel_fill_ceiling=carousel_fill_ceiling,
                        empty_cabinet_threshold_pct=underuse_threshold_pct,
                    )
                    # Did we BLOW UP a different cabinet count?
                    if test_plan[cabs_key] >= n_cabs and cab_type != alt_type:
                        # Source cabinet count didn't go down yet — OK, we're
                        # still in the middle of moving items out
                        pass
                    # Check that the destination didn't increase its own cab count
                    dest_cabs_field = {
                        "Helix": "helix_cabs",
                        "Carousel": "car_cabs",
                    }.get(alt_type)
                    if dest_cabs_field:
                        old_dest = plan[dest_cabs_field]
                        new_dest = test_plan[dest_cabs_field]
                        if new_dest > old_dest:
                            continue  # this destination would need an extra cabinet — bad
                    # Accept the move
                    simulated = test_df
                    # proposed_moves is only None after a `break`, which exits
                    # this loop — so it is always a list here.
                    assert proposed_moves is not None
                    proposed_moves.append(
                        {
                            "code": str(row.get("Code", "")),
                            "description": str(row.get("Description", ""))[:50],
                            "from_cabinet": cab_type,
                            "to_cabinet": alt_type,
                            "monthly_packs": float(row.get("Monthly_packs", 0) or 0),
                            "cost_at_origin": cost,
                            "cost_at_destination": alt_cost,
                        }
                    )
                    moved = True
                    break

                if not moved:
                    # Couldn't find a home for this item — abort consolidation
                    proposed_moves = None
                    break

            if not proposed_moves:
                continue

            # Verify the simulated plan reduces total cabinets
            sim_plan = compute_plan_for_subset(
                simulated, buf_pct, overfill_factor=overfill_factor,
                buf_helix=buf_helix, buf_carousel=buf_carousel, buf_locker=buf_locker,
                carousel_fill_ceiling=carousel_fill_ceiling,
                empty_cabinet_threshold_pct=underuse_threshold_pct,
            )
            if sim_plan["total_cabs"] >= plan["total_cabs"]:
                continue  # consolidation did not reduce the cabinet count

            # Commit
            out = simulated
            audit.append(
                {
                    "pass": pass_num + 1,
                    "eliminated_cabinet": cab_type,
                    "items_moved": proposed_moves,
                    "cabinets_before": plan["total_cabs"],
                    "cabinets_after": sim_plan["total_cabs"],
                }
            )
            moves_this_pass += 1
            consolidated_a_cabinet = True
            break  # restart the pass; new opportunities may have opened up

        if not consolidated_a_cabinet:
            break  # no more consolidations available, exit

    return out, audit


def detect_size_locked_items(
    df: pd.DataFrame,
    buf_pct: float,
    minimum_carousel_allocation: int,
    underuse_threshold_pct: float,
    carousel_reserve_factor: float = _DEFAULT_CAROUSEL_RESERVE_FACTOR,
    overfill_factor: float = _DEFAULT_HELIX_OVERFILL_FACTOR,
    *,
    buf_helix: float | None = None,
    buf_carousel: float | None = None,
    buf_locker: float | None = None,
    carousel_fill_ceiling: float = 1.0,
) -> list[Any]:
    """Identify Carousel items whose size keeps them out of a Helix (L or XL)
    and which, if resized to fit a Helix (treated as M), would let the
    rebalancer drop a cabinet -- tools that are forcing an underused Carousel
    the user could repackage.

    This is pure detection. It never mutates ``df`` and never changes the
    shipped plan. For one bucket it answers a single question -- "would resizing
    the Helix-ineligible Carousel items to M remove a cabinet?" -- by running
    the rebalancer on a resized copy and comparing the cabinet count to a
    re-run of the unmodified bucket. Because the comparison runs through the
    rebalancer, the empty-cabinet threshold is honoured automatically: a
    Carousel that sits above the threshold (needed for its volume) yields
    no reduction and nothing is flagged. Returns the DataFrame indices of the
    items a resize would unblock, or an empty list when no resize would help.
    """
    if df is None or len(df) == 0:
        return []
    if "CabinetType" not in df.columns or "SizeCategory" not in df.columns:
        return []

    # Candidates: Carousel rows whose size is not Helix-eligible (anything other
    # than S/M). The true locker sizes never land in a Carousel, so in practice
    # this is L and XL.
    helix_sizes = {"S", "M", ""}
    cab = df["CabinetType"].astype(str)
    size = df["SizeCategory"].astype(str).str.upper()
    cand_mask = (cab == "Carousel") & (~size.isin(helix_sizes))
    cand_idx = list(df.index[cand_mask])
    if not cand_idx:
        return []

    # Baseline: re-run the rebalancer on the unmodified bucket. (The input is
    # already post-rebalance, so this returns the same counts -- re-running just
    # guarantees the comparison is apples-to-apples regardless of how the caller
    # produced df.)
    base_out, _ = rebalance_cabinets(
        df,
        buf_pct=buf_pct,
        minimum_carousel_allocation=minimum_carousel_allocation,
        underuse_threshold_pct=underuse_threshold_pct,
        carousel_reserve_factor=carousel_reserve_factor,
        overfill_factor=overfill_factor,
        buf_helix=buf_helix, buf_carousel=buf_carousel, buf_locker=buf_locker,
        carousel_fill_ceiling=carousel_fill_ceiling,
    )
    base_plan = compute_plan_for_subset(
        base_out, buf_pct, overfill_factor=overfill_factor,
        buf_helix=buf_helix, buf_carousel=buf_carousel, buf_locker=buf_locker,
        carousel_fill_ceiling=carousel_fill_ceiling,
        empty_cabinet_threshold_pct=underuse_threshold_pct,
    )
    # Nothing to consolidate into: no Carousel, or the bucket is already a single
    # cabinet (resizing can never remove the only cabinet).
    if base_plan.get("car_cabs", 0) < 1 or base_plan.get("total_cabs", 0) < 2:
        return []

    # Trial: resize the candidates to M (Helix-fit) on a COPY and re-run the
    # rebalancer. If the cabinet count drops, those items were the blockers.
    trial = df.copy()
    trial.loc[cand_idx, "SizeCategory"] = "M"
    trial_out, _ = rebalance_cabinets(
        trial,
        buf_pct=buf_pct,
        minimum_carousel_allocation=minimum_carousel_allocation,
        underuse_threshold_pct=underuse_threshold_pct,
        carousel_reserve_factor=carousel_reserve_factor,
        overfill_factor=overfill_factor,
        buf_helix=buf_helix, buf_carousel=buf_carousel, buf_locker=buf_locker,
        carousel_fill_ceiling=carousel_fill_ceiling,
    )
    trial_plan = compute_plan_for_subset(
        trial_out, buf_pct, overfill_factor=overfill_factor,
        buf_helix=buf_helix, buf_carousel=buf_carousel, buf_locker=buf_locker,
        carousel_fill_ceiling=carousel_fill_ceiling,
        empty_cabinet_threshold_pct=underuse_threshold_pct,
    )
    if trial_plan.get("total_cabs", 0) < base_plan.get("total_cabs", 0):
        return cand_idx
    return []


# ---------------------------------------------------------------------------
# Operational Mode (global cabinet-composition override)
# ---------------------------------------------------------------------------
# Standard mode (no Operational Mode set) leaves routing untouched. The three
# modes below override the per-tool best-fit decision with a global strategy:
#   "Helix"    -> every KTC vending tool stored in a Helix coil
#   "Carousel" -> every KTC vending tool stored in a Carousel slot
#   "Helix + Carousel (capped)" -> normal Helix/Carousel routing, then a hard
#       cap on the number of Carousels with the Helix-eligible overflow spilled
#       into Helix coils.
# Kanban / Bulk-Kanban rows (shelf items, not in a machine) are never touched;
# the mode governs only the cabinet type of items that go into a machine.

_VENDING_CABINETS = ("Helix", "Carousel", "Locker A", "Locker B", "Locker C")
_HELIX_FIT_SIZES = {"S", "M", ""}
# Sizes too large for a Carousel slot (they need a locker in Standard mode).
_LOCKER_ONLY_SIZES = {"XXL", "XLS", "XXLS"}


def _force_helix_resources(
    monthly_packs: Any,
    size_cat: str,
    prod_cat: str,
    helix_overfill_factor: float,
    regrind: bool = False,
) -> tuple[int, int]:
    """Spiral capacity + spiral count for a tool forced onto a Helix, using the
    same primitives as route_and_size_row. Every size yields a capacity (see
    decide_spiral_capacity), so oversize tools size without error -- the
    Operational Mode assumes physical fit and flags it separately."""
    mp = float(monthly_packs) if not pd.isna(monthly_packs) else 0.0
    cap = decide_spiral_capacity(str(size_cat), str(prod_cat))
    spirals = int(max(1, compute_helix_spirals_needed(mp, cap, float(helix_overfill_factor))))
    spirals = regrind_spiral_floor(spirals, bool(regrind))
    return cap, spirals


def _force_carousel_resources(
    target_packs: Any,
    min_carousel_compartments: int,
    carousel_reserve_factor: float,
) -> int:
    """Carousel stockpile count for a tool forced onto a Carousel (same formula
    as route_and_size_row's Carousel branch)."""
    tp = float(target_packs) if not pd.isna(target_packs) else 0.0
    return max(
        int(min_carousel_compartments),
        max(1, math.ceil(tp * float(carousel_reserve_factor))),
    )


def apply_operational_mode(
    df: pd.DataFrame,
    mode: str,
    *,
    min_carousel_compartments: int,
    carousel_reserve_factor: float,
    helix_overfill_factor: float,
) -> pd.DataFrame:
    """Force every KTC vending row onto a single cabinet type and recompute its
    resources. ``mode`` is "Helix" or "Carousel". Kanban/Bulk rows and any row
    not currently in a vending cabinet are left untouched. Returns a new
    DataFrame; never mutates ``df``.
    """
    out = df.copy()
    if mode not in ("Helix", "Carousel"):
        return out
    if "CabinetType" not in out.columns:
        return out
    mask = out["CabinetType"].astype(str).isin(_VENDING_CABINETS)
    for idx in list(out.index[mask]):
        size = out.at[idx, "SizeCategory"] if "SizeCategory" in out.columns else ""
        pcat = out.at[idx, "ProductCategory"] if "ProductCategory" in out.columns else ""
        regr = bool(out.at[idx, "Regrind"]) if "Regrind" in out.columns else False
        if mode == "Helix":
            cap, spirals = _force_helix_resources(
                out.at[idx, "Monthly_packs"], size, pcat, helix_overfill_factor, regr
            )
            out.at[idx, "CabinetType"] = "Helix"
            out.at[idx, "Spiral_capacity"] = cap
            out.at[idx, "Spirals_needed"] = spirals
            out.at[idx, "Carousel_stockpiles"] = 0
        else:  # Carousel
            stock = _force_carousel_resources(
                out.at[idx, "Target_packs"] if "Target_packs" in out.columns else 0,
                min_carousel_compartments,
                carousel_reserve_factor,
            )
            out.at[idx, "CabinetType"] = "Carousel"
            out.at[idx, "Carousel_stockpiles"] = int(stock)
            out.at[idx, "Spirals_needed"] = 0
            out.at[idx, "Spiral_capacity"] = pd.NA
    return out


def flag_unfit_for_mode(df: pd.DataFrame, mode: str) -> "pd.Series":
    """Boolean Series: True where a row's size does not physically fit the
    cabinet type the Operational Mode forces. Helix mode flags anything bigger
    than M (a spiral is small); Carousel mode flags the locker sizes
    (XXL/XLS/XXLS). Other modes flag nothing."""
    if "SizeCategory" not in df.columns or "CabinetType" not in df.columns:
        return pd.Series(False, index=df.index)
    size = df["SizeCategory"].astype(str).str.upper()
    cab = df["CabinetType"].astype(str)
    if mode == "Helix":
        return (cab == "Helix") & (~size.isin(_HELIX_FIT_SIZES))
    if mode == "Carousel":
        return (cab == "Carousel") & (size.isin(_LOCKER_ONLY_SIZES))
    return pd.Series(False, index=df.index)


def apply_carousel_cap(
    df: pd.DataFrame,
    max_carousels: int,
    *,
    helix_overfill_factor: float,
    carousel_fill_ceiling: float = 1.0,
    empty_cabinet_threshold_pct: float = 0.0,
) -> tuple[pd.DataFrame, list[Any]]:
    """Cap the number of Carousels at ``max_carousels`` for this subset and spill
    the Helix-eligible (S/M) Carousel overflow -- slowest movers first -- into
    Helix coils. L/XL Carousel tools cannot spill (a spiral is too small); if
    they keep the Carousel count above the cap they are returned as the overflow
    list so the caller can flag them. Returns (out, overflow_indices); never
    mutates ``df``.

    The carousel count honours ``carousel_fill_ceiling`` /
    ``empty_cabinet_threshold_pct`` so the cap agrees with the rest of the plan;
    the defaults (1.0 and 0.0) reproduce the original physical-capacity count.
    """
    out = df.copy()
    if "CabinetType" not in out.columns or int(max_carousels) < 0:
        return out, []
    cap_cabs = int(max_carousels)

    def _car_cabs() -> int:
        slots = pd.to_numeric(
            out.loc[out["CabinetType"] == "Carousel", "Carousel_stockpiles"],
            errors="coerce",
        ).fillna(0).sum()
        return carousel_cabinets_needed(
            int(slots),
            fill_ceiling=carousel_fill_ceiling,
            empty_threshold_pct=empty_cabinet_threshold_pct,
        )

    if _car_cabs() <= cap_cabs:
        return out, []

    # Spill the slowest-moving Helix-eligible Carousel tools to Helix until the
    # Carousel count is within the cap or nothing eligible remains.
    car_mask = out["CabinetType"].astype(str) == "Carousel"
    size = out["SizeCategory"].astype(str).str.upper() if "SizeCategory" in out.columns \
        else pd.Series("", index=out.index)
    movable = out[car_mask & size.isin(_HELIX_FIT_SIZES)].sort_values(
        "Monthly_packs", ascending=True
    )
    for idx in list(movable.index):
        if _car_cabs() <= cap_cabs:
            break
        pcat = out.at[idx, "ProductCategory"] if "ProductCategory" in out.columns else ""
        szc = out.at[idx, "SizeCategory"] if "SizeCategory" in out.columns else ""
        regr = bool(out.at[idx, "Regrind"]) if "Regrind" in out.columns else False
        cap, spirals = _force_helix_resources(
            out.at[idx, "Monthly_packs"], szc, pcat, helix_overfill_factor, regr
        )
        out.at[idx, "CabinetType"] = "Helix"
        out.at[idx, "Spiral_capacity"] = cap
        out.at[idx, "Spirals_needed"] = spirals
        out.at[idx, "Carousel_stockpiles"] = 0

    overflow: list[Any] = []
    if _car_cabs() > cap_cabs:
        # The remaining over-cap demand is L/XL Carousel tools that can't spill.
        size2 = out["SizeCategory"].astype(str).str.upper() if "SizeCategory" in out.columns \
            else pd.Series("", index=out.index)
        overflow = list(
            out.index[(out["CabinetType"] == "Carousel") & (~size2.isin(_HELIX_FIT_SIZES))]
        )
    return out, overflow
