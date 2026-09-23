"""kromi_app.engine.fixed_config - the fixed-configuration operating mode (v34.52).

In this mode the machines already exist. Per supply point the user states how
many Helix, Carousel and Locker cabinets stand there and how much headroom to
keep free; the planner fits the article list into that space instead of
sizing new cabinets.

Rules (owner decisions, v34.52):

* Demand per article follows the existing rules unchanged: the KTC/Kanban
  split, the Helix/Carousel preference, spirals per Helix article and slots
  per Carousel article come from the normal routing and sizing. Kanban
  articles do not go into machines and are never flagged.
* The most used articles are placed first: monthly pieces (the measure of the
  KTC/Kanban decision), ties broken by monthly packs, then by code.
* Headroom: each machine type is filled to at most (100 - headroom) % of its
  physical capacity, rounded down. The headroom replaces the capacity buffer,
  the Carousel fill ceiling and the cabinet consolidation of the other modes;
  none of them applies here.
* When an article's own machine type is full it may move to another type it
  physically fits (switchable, on by default): a Carousel article of size S or
  M into a Helix, a Helix article into a Carousel, a locker article into a
  locker with larger compartments (C -> B -> A). The moved article is re-sized
  with the same primitives the other modes use. A technician cabinet override
  never moves.
* An article that fits nowhere is flagged "Not placed" with the reason. It
  keeps its routing and stays in every list and export; it only takes no
  machine space.
* A restock buffer is reserved when space is left after the article itself;
  otherwise the article is placed without its buffer and the note says so.

Stock-based Helix promotion (v34.58, owner request, off by default): an
onboarding list often lacks the consumption of articles the customer clearly
uses, and a large stock on hand hints at it. After the fit, the Helix space
still free (the headroom stays empty) takes the Carousel articles whose stock
implies the highest demand: implied monthly packs = stock / VPE / the months
the stock is assumed to cover. A candidate is a KTC article placed in a
Carousel, of a size a spiral takes (as for the overflow move), without a
technician cabinet override, whose implied demand is above the Helix
threshold and above its recorded demand. Each gets the spirals the normal
Helix sizing gives for the implied demand, highest first, and is skipped when
they do not fit. The compartments it frees go to Carousel articles that found
no space, most used first. Only the cabinet type and the spirals change (and
with them the takeover maximum); the rule needs the stock column.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import pandas as pd

from .cabinet_math import (
    _force_carousel_resources,
    _force_helix_resources,
    compute_plan_for_subset,
)
from .constants import (
    CAROUSEL_SLOTS_PER_CAB,
    HELIX_SPIRALS_PER_CAB,
    LOCKER_A_CAP,
    LOCKER_B_CAP,
    LOCKER_C_CAP,
)

#: The op-mode token the page and PlanParams use for this mode.
FIXED_MODE = "Fixed"

MACHINE_TYPES: Tuple[str, ...] = ("Helix", "Carousel", "Locker A", "Locker B", "Locker C")
UNITS: Dict[str, str] = {
    "Helix": "spiral(s)", "Carousel": "slot(s)", "Locker A": "compartment(s)",
    "Locker B": "compartment(s)", "Locker C": "compartment(s)",
}
_PER_MACHINE: Dict[str, int] = {
    "Helix": HELIX_SPIRALS_PER_CAB, "Carousel": CAROUSEL_SLOTS_PER_CAB,
    "Locker A": LOCKER_A_CAP, "Locker B": LOCKER_B_CAP, "Locker C": LOCKER_C_CAP,
}

STATUS_PLACED = "Placed"
STATUS_MOVED = "Moved"
STATUS_NOT_PLACED = "Not placed"
STATUS_PROMOTED = "Promoted"

#: The stock column the takeover mapping creates (engine.takeover.STOCK_COL).
STOCK_COL = "Stock_pcs"

#: Row columns this mode adds to the plan frame (only in this mode).
PLACEMENT_COLUMNS: Tuple[str, ...] = ("Placement_Rank", "Placement_Status", "Placement_Note")

#: Headroom is clamped to this range so a typo cannot zero every machine.
MAX_HEADROOM_PCT = 90.0

_HELIX_FIT_SIZES = {"S", "M", ""}
_LOCKER_ONLY_SIZES = {"XXL", "XLS", "XXLS"}
# An article may move to a locker with larger compartments, never smaller.
_LOCKER_UPGRADES: Dict[str, Tuple[str, ...]] = {
    "Locker C": ("Locker B", "Locker A"),
    "Locker B": ("Locker A",),
    "Locker A": (),
}
_WRITE_BACK_COLUMNS: Tuple[str, ...] = (
    "CabinetType", "Spiral_capacity", "Spirals_needed", "Carousel_stockpiles",
    "Restock_slots", "Restock_target", "SizeIssue",
) + PLACEMENT_COLUMNS


@dataclass(frozen=True)
class MachineSet:
    """The machines standing at one supply point."""

    helix: int = 0
    carousel: int = 0
    locker_a: int = 0
    locker_b: int = 0
    locker_c: int = 0

    def counts(self) -> Dict[str, int]:
        return {
            "Helix": max(0, int(self.helix)),
            "Carousel": max(0, int(self.carousel)),
            "Locker A": max(0, int(self.locker_a)),
            "Locker B": max(0, int(self.locker_b)),
            "Locker C": max(0, int(self.locker_c)),
        }

    @property
    def total(self) -> int:
        return sum(self.counts().values())


def machines_by_sp(entries: Iterable[Sequence[int]]) -> Dict[int, MachineSet]:
    """``(sp, helix, carousel, locker_a, locker_b, locker_c)`` rows -> map."""
    out: Dict[int, MachineSet] = {}
    for e in entries or ():
        sp, h, c, a, b, cc = (int(v) for v in e)
        out[sp] = MachineSet(helix=h, carousel=c, locker_a=a, locker_b=b, locker_c=cc)
    return out


def clamp_headroom(headroom_pct: float) -> float:
    try:
        h = float(headroom_pct)
    except (TypeError, ValueError):
        h = 0.0
    if math.isnan(h):
        h = 0.0
    return min(max(h, 0.0), MAX_HEADROOM_PCT)


def physical_capacity(machines: MachineSet) -> Dict[str, int]:
    return {t: n * _PER_MACHINE[t] for t, n in machines.counts().items()}


def usable_capacity(machines: MachineSet, headroom_pct: float) -> Dict[str, int]:
    """Physical capacity minus the headroom, rounded down per machine type."""
    keep = (100.0 - clamp_headroom(headroom_pct)) / 100.0
    return {t: int(math.floor(cap * keep + 1e-9)) for t, cap in physical_capacity(machines).items()}


# ---- per-row helpers ------------------------------------------------------------

def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def _is_protected(row: pd.Series) -> bool:
    """A technician cabinet override pins the article to its machine type."""
    return _truthy(row.get("Override_Applied", False)) and (
        "cabinet_type" in str(row.get("Override_Fields", "")))


def _float(value: Any) -> float:
    v = pd.to_numeric(value, errors="coerce")
    return float(v) if pd.notna(v) else 0.0


def _int(value: Any) -> int:
    v = pd.to_numeric(value, errors="coerce")
    return int(v) if pd.notna(v) else 0


def _size(row: pd.Series) -> str:
    raw = row.get("SizeCategory", "")
    return "" if raw is None or (isinstance(raw, float) and math.isnan(raw)) else str(raw).strip().upper()


def _options(routed: str, size: str, protected: bool, allow_spill: bool) -> List[str]:
    opts = [routed]
    if protected or not allow_spill:
        return opts
    if routed == "Carousel" and size in _HELIX_FIT_SIZES:
        opts.append("Helix")
    elif routed == "Helix" and size not in _LOCKER_ONLY_SIZES:
        opts.append("Carousel")
    elif routed in _LOCKER_UPGRADES:
        opts.extend(_LOCKER_UPGRADES[routed])
    return opts


def _footprint(row: pd.Series, target: str, routed: str, *, helix_overfill_factor: float,
               min_carousel_compartments: int, carousel_reserve_factor: float
               ) -> Tuple[int, Dict[str, Any]]:
    """Space the article takes in ``target`` and the sizing fields it gets there."""
    if target.startswith("Locker"):
        return 1, {"CabinetType": target}
    if target == routed == "Helix":
        return max(1, _int(row.get("Spirals_needed"))), {}
    if target == routed == "Carousel":
        return max(1, _int(row.get("Carousel_stockpiles"))), {}
    if target == "Helix":
        cap, spirals = _force_helix_resources(
            row.get("Monthly_packs"), row.get("SizeCategory", ""),
            row.get("ProductCategory", ""), helix_overfill_factor,
            _truthy(row.get("Regrind", False)))
        return int(spirals), {"CabinetType": "Helix", "Spiral_capacity": cap,
                              "Spirals_needed": int(spirals), "Carousel_stockpiles": 0}
    stock = _force_carousel_resources(row.get("Target_packs", 0),
                                      min_carousel_compartments, carousel_reserve_factor)
    return int(stock), {"CabinetType": "Carousel", "Spiral_capacity": pd.NA,
                        "Spirals_needed": 0, "Carousel_stockpiles": int(stock)}


def _implied_monthly_packs(row: pd.Series, months: float) -> float:
    """Monthly packs the stock on hand implies when it covers ``months``."""
    stock = _float(row.get(STOCK_COL))
    vpe = _float(row.get("PackUnits"))
    if stock <= 0 or months <= 0:
        return 0.0
    return stock / (vpe if vpe > 0 else 1.0) / months


def _priority_order(cand: pd.DataFrame) -> List[Any]:
    """Most used first: monthly pieces, then monthly packs, then code."""
    if len(cand) == 0:
        return []
    pcs_col = "Monthly_pcs" if "Monthly_pcs" in cand.columns else "Consumption_pcs"
    key = pd.DataFrame({
        "pcs": pd.to_numeric(cand.get(pcs_col), errors="coerce"),
        "packs": pd.to_numeric(cand.get("Monthly_packs"), errors="coerce"),
        "code": cand["Code"].astype(str) if "Code" in cand.columns else "",
        "pos": range(len(cand)),
    }, index=cand.index)
    key["pcs"] = key["pcs"].fillna(0.0)
    key["packs"] = key["packs"].fillna(0.0)
    key = key.sort_values(["pcs", "packs", "code", "pos"],
                          ascending=[False, False, True, True], kind="mergesort")
    return list(key.index)


def _no_space_reason(target: str, units: int, free: int, machines: Dict[str, int]) -> str:
    if machines.get(target, 0) == 0:
        return f"no {target} configured"
    return f"{target} needs {units} {UNITS[target]}, {free} free"


# ---- the fit ----------------------------------------------------------------------

def fit_fixed_configuration(
    df: pd.DataFrame,
    machines: MachineSet,
    headroom_pct: float,
    *,
    allow_spill: bool = True,
    helix_overfill_factor: float,
    min_carousel_compartments: int,
    carousel_reserve_factor: float,
    stock_promotion_months: float = 0.0,
    helix_threshold: float = 0.0,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Fit one supply point's articles into its machines.

    Returns ``(frame, report)``. The frame is a copy of ``df`` with the
    placement columns added, moved articles re-sized, restock buffers that
    found no space (or whose article found none) released, and ``SizeIssue``
    set on the not-placed Carousel articles too large for a Helix that the
    Helix space left over could take if repackaged (most used first). The report carries machines, physical, usable,
    used and free capacity per machine type plus the placement counts.
    ``stock_promotion_months`` > 0 turns the stock-based Helix promotion on
    (see the module docstring); ``helix_threshold`` is the plan's Helix
    threshold in packs per month. Never mutates ``df``.
    """
    out = df.copy()
    out["Placement_Rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out["Placement_Status"] = ""
    out["Placement_Note"] = ""
    if "SizeIssue" not in out.columns:
        out["SizeIssue"] = False
    has_restock = "Restock_slots" in out.columns and "Restock_target" in out.columns
    counts = machines.counts()
    usable = usable_capacity(machines, headroom_pct)
    free = dict(usable)
    sizing: Dict[str, Any] = dict(helix_overfill_factor=float(helix_overfill_factor),
                  min_carousel_compartments=int(min_carousel_compartments),
                  carousel_reserve_factor=float(carousel_reserve_factor))

    system = (out["SystemCategory"].astype(str) if "SystemCategory" in out.columns
              else pd.Series("", index=out.index))
    cand_mask = (system == "KTC") & out["CabinetType"].astype(str).isin(MACHINE_TYPES)
    n_placed = n_moved = n_not = n_buf_dropped = 0
    not_placed_pcs = 0.0
    size_blocked: List[Tuple[Any, int]] = []

    order = _priority_order(out.loc[cand_mask])
    for rank, idx in enumerate(order, start=1):
        row = out.loc[idx]
        routed = str(row["CabinetType"])
        size = _size(row)
        protected = _is_protected(row)
        out.at[idx, "Placement_Rank"] = rank
        placed_at = None
        fields: Dict[str, Any] = {}
        units = 0
        misses: List[str] = []
        for target in _options(routed, size, protected, bool(allow_spill)):
            units, fields = _footprint(row, target, routed, **sizing)
            if units <= free[target]:
                placed_at = target
                break
            misses.append(_no_space_reason(target, units, free[target], counts))

        wants_buffer = has_restock and _int(row.get("Restock_slots")) > 0
        if placed_at is None:
            n_not += 1
            not_placed_pcs += float(pd.to_numeric(row.get("Monthly_pcs"), errors="coerce") or 0.0)
            why = "No space left: " + "; ".join(misses) + "."
            alternatives = _options(routed, size, False, True)[1:]
            if protected:
                why += f" The technician cabinet override keeps it in {routed}."
            elif not allow_spill and alternatives:
                why += " Moving to another machine type is switched off."
            elif routed == "Carousel" and size not in _HELIX_FIT_SIZES:
                why += f" Too large (size {size}) for a Helix spiral."
                if allow_spill and counts["Helix"] > 0:
                    helix_units, _ = _footprint(row, "Helix", routed, **sizing)
                    size_blocked.append((idx, helix_units))
            out.at[idx, "Placement_Status"] = STATUS_NOT_PLACED
            out.at[idx, "Placement_Note"] = why
            if has_restock:
                out.at[idx, "Restock_slots"] = 0
                out.at[idx, "Restock_target"] = ""
            continue

        free[placed_at] -= units
        notes: List[str] = []
        if placed_at != routed:
            for col, val in fields.items():
                out.at[idx, col] = val
            out.at[idx, "Placement_Status"] = STATUS_MOVED
            notes.append(f"{routed} full; moved to {placed_at}.")
            n_moved += 1
        else:
            out.at[idx, "Placement_Status"] = STATUS_PLACED
            n_placed += 1
        if wants_buffer:
            buf_target = "Carousel" if placed_at in ("Helix", "Carousel") else placed_at
            if free[buf_target] >= 1:
                free[buf_target] -= 1
                out.at[idx, "Restock_target"] = buf_target
            else:
                out.at[idx, "Restock_slots"] = 0
                out.at[idx, "Restock_target"] = ""
                notes.append(f"Restock buffer not reserved: no {UNITS[buf_target]} "
                             f"left in {buf_target}.")
                n_buf_dropped += 1
        out.at[idx, "Placement_Note"] = " ".join(notes)

    # Stock-based Helix promotion (v34.58): the free Helix space takes the
    # Carousel articles whose stock implies the highest demand; the Carousel
    # space they free goes to articles that found none.
    n_promoted = n_refilled = 0
    months = float(stock_promotion_months or 0.0)
    if months > 0 and STOCK_COL in out.columns and free["Helix"] > 0:
        promos: List[Tuple[float, str, Any]] = []
        for idx in order:
            row = out.loc[idx]
            if (str(row["CabinetType"]) != "Carousel"
                    or out.at[idx, "Placement_Status"] == STATUS_NOT_PLACED
                    or _size(row) not in _HELIX_FIT_SIZES or _is_protected(row)):
                continue
            implied = _implied_monthly_packs(row, months)
            recorded = _float(row.get("Monthly_packs"))
            if implied > float(helix_threshold) and implied > recorded:
                promos.append((-implied, str(row.get("Code", "")), idx))
        promos.sort(key=lambda t: (t[0], t[1]))
        for _neg, _code, idx in promos:
            row = out.loc[idx]
            implied = -_neg
            cap, spirals = _force_helix_resources(
                implied, row.get("SizeCategory", ""), row.get("ProductCategory", ""),
                float(helix_overfill_factor), _truthy(row.get("Regrind", False)))
            if spirals > free["Helix"]:
                continue
            freed = max(0, _int(row.get("Carousel_stockpiles")))
            free["Helix"] -= int(spirals)
            free["Carousel"] += freed
            if out.at[idx, "Placement_Status"] == STATUS_MOVED:
                n_moved -= 1
            else:
                n_placed -= 1
            n_promoted += 1
            for col, val in (("CabinetType", "Helix"), ("Spiral_capacity", cap),
                             ("Spirals_needed", int(spirals)), ("Carousel_stockpiles", 0)):
                out.at[idx, col] = val
            out.at[idx, "Placement_Status"] = STATUS_PROMOTED
            stock = _float(row.get(STOCK_COL))
            out.at[idx, "Placement_Note"] = (
                f"Stock-based Helix promotion: {stock:g} pcs in stock over {months:g} "
                f"months suggest about {implied:.1f} packs a month; moved from the "
                f"Carousel ({freed} compartments) to the Helix ({int(spirals)} "
                f"spiral(s)). {out.at[idx, 'Placement_Note']}").strip()
        if n_promoted:
            for idx in order:
                if out.at[idx, "Placement_Status"] != STATUS_NOT_PLACED:
                    continue
                row = out.loc[idx]
                routed = str(row["CabinetType"])
                if "Carousel" not in _options(routed, _size(row), _is_protected(row),
                                              bool(allow_spill)):
                    continue
                units, fields = _footprint(row, "Carousel", routed, **sizing)
                if units > free["Carousel"]:
                    continue
                free["Carousel"] -= units
                for col, val in fields.items():
                    out.at[idx, col] = val
                n_not -= 1
                n_refilled += 1
                not_placed_pcs -= _float(row.get("Monthly_pcs"))
                if routed == "Carousel":
                    out.at[idx, "Placement_Status"] = STATUS_PLACED
                    n_placed += 1
                else:
                    out.at[idx, "Placement_Status"] = STATUS_MOVED
                    n_moved += 1
                out.at[idx, "Placement_Note"] = (
                    "Placed in the Carousel space freed by the stock-based Helix promotion.")
            size_blocked = [(i, u) for i, u in size_blocked
                            if out.at[i, "Placement_Status"] == STATUS_NOT_PLACED]

    # Size hint: of the Carousel articles too large for a spiral, flag (most
    # used first) those the Helix space left over could still take if they
    # were repackaged to a Helix-fit size, so the fix offered is one that works.
    helix_left = free["Helix"]
    for idx, helix_units in size_blocked:
        if helix_units <= helix_left:
            out.at[idx, "SizeIssue"] = True
            helix_left -= helix_units

    report: Dict[str, Any] = {
        "machines": counts,
        "physical": physical_capacity(machines),
        "usable": usable,
        "used": {t: usable[t] - free[t] for t in MACHINE_TYPES},
        "free": free,
        "headroom_pct": clamp_headroom(headroom_pct),
        "allow_spill": bool(allow_spill),
        "placed": n_placed + n_moved + n_promoted,
        "moved": n_moved,
        "not_placed": n_not,
        "buffers_dropped": n_buf_dropped,
        "not_placed_monthly_pcs": round(not_placed_pcs, 6),
        "stock_promotion_months": months,
        "promoted": n_promoted,
        "placed_in_freed": n_refilled,
    }
    return out, report


def fixed_plan_for_subset(fitted: pd.DataFrame, report: Dict[str, Any], *,
                          overfill_factor: float) -> Dict[str, Any]:
    """The bucket plan of one supply point in fixed mode.

    Space use comes from the articles placed in machines; the article counts
    and consumption cover the whole list (not-placed articles are still KTC
    articles); cabinet counts are the configured machines. No buffer applies.
    """
    in_machine = fitted["Placement_Status"].astype(str) != STATUS_NOT_PLACED \
        if "Placement_Status" in fitted.columns else pd.Series(True, index=fitted.index)
    plan = compute_plan_for_subset(fitted.loc[in_machine], 0.0, overfill_factor=overfill_factor)
    system = fitted["SystemCategory"].astype(str) if "SystemCategory" in fitted.columns \
        else pd.Series("", index=fitted.index)
    plan["rows_total"] = len(fitted)
    plan["ktc_count"] = int((system == "KTC").sum())
    plan["kanban_count"] = int((system == "Kanban").sum())
    plan["total_consumption"] = float(
        pd.to_numeric(fitted["Consumption_pcs"], errors="coerce").fillna(0).sum()
    ) if "Consumption_pcs" in fitted.columns else 0.0
    m = report["machines"]
    for key, t in (("helix_cabs", "Helix"), ("car_cabs", "Carousel"),
                   ("cabA", "Locker A"), ("cabB", "Locker B"), ("cabC", "Locker C")):
        plan[key] = plan[f"{key}_base"] = int(m[t])
    plan["total_cabs"] = plan["total_cabs_base"] = int(sum(m.values()))
    plan["carousel_cap_exceeded_by_restock"] = False
    plan["fixed_config"] = report
    return plan


# ---- export and display helpers ----------------------------------------------------

def capacity_rows(bucket_plans: Sequence[Tuple[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """One row per supply point and configured machine type, for the page and
    the workbook: machines, capacity, usable after headroom, used, free."""
    rows: List[Dict[str, Any]] = []
    for label, plan in bucket_plans:
        rep = plan.get("fixed_config")
        if not rep:
            continue
        for t in MACHINE_TYPES:
            n = int(rep["machines"].get(t, 0))
            if n == 0 and int(rep["used"].get(t, 0)) == 0:
                continue
            phys = int(rep["physical"][t])
            used = int(rep["used"][t])
            rows.append({
                "Supply point": label,
                "Machine": t,
                "Machines": n,
                "Capacity": phys,
                "Unit": UNITS[t].replace("(s)", "s"),
                "Headroom %": rep["headroom_pct"],
                "Usable": int(rep["usable"][t]),
                "Used": used,
                "Free (usable)": int(rep["free"][t]),
                "Fill % of capacity": round(used / phys * 100.0, 1) if phys else 0.0,
            })
    return rows


def run_meta_rows(bucket_plans: Sequence[Tuple[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Run_Metadata rows describing the fixed configuration of a run."""
    reps = [(label, p["fixed_config"]) for label, p in bucket_plans if p.get("fixed_config")]
    if not reps:
        return []

    def _machines(rep: Dict[str, Any]) -> str:
        parts = [f"{n} {t}" for t, n in rep["machines"].items() if n]
        return ", ".join(parts) if parts else "none"

    first = reps[0][1]
    return [
        {"Key": "Fixed configuration machines",
         "Value": "; ".join(f"{label}: {_machines(rep)}" for label, rep in reps)},
        {"Key": "Fixed configuration headroom (%)", "Value": first["headroom_pct"]},
        {"Key": "Move overflow to another machine type",
         "Value": "on" if first["allow_spill"] else "off"},
        {"Key": "Articles placed", "Value": sum(int(r["placed"]) for _, r in reps)},
        {"Key": "Articles moved to another machine type",
         "Value": sum(int(r["moved"]) for _, r in reps)},
        {"Key": "Articles not placed (no space)",
         "Value": sum(int(r["not_placed"]) for _, r in reps)},
        {"Key": "Restock buffers not reserved (no space)",
         "Value": sum(int(r["buffers_dropped"]) for _, r in reps)},
    ] + ([
        {"Key": "Stock-based Helix promotion",
         "Value": f"on (stock covers {float(first['stock_promotion_months']):g} months)"},
        {"Key": "Articles promoted to the Helix (stock)",
         "Value": sum(int(r.get("promoted", 0)) for _, r in reps)},
        {"Key": "Articles placed in the freed Carousel space",
         "Value": sum(int(r.get("placed_in_freed", 0)) for _, r in reps)},
    ] if float(first.get("stock_promotion_months", 0.0) or 0.0) > 0 else [])


def write_back(work: pd.DataFrame, fitted: pd.DataFrame) -> None:
    """Copy the fit results of one bucket back into the plan frame, in place."""
    for col in _WRITE_BACK_COLUMNS:
        if col in fitted.columns:
            if col not in work.columns:
                work[col] = pd.Series(pd.NA, index=work.index, dtype=fitted[col].dtype) \
                    if col == "Placement_Rank" else ""
            work.loc[fitted.index, col] = fitted[col]
