"""Plan integrity checks — runtime invariant and reconciliation layer.

These functions verify the conservation rules and state invariants that must
hold after the planning pipeline runs. They turn silent miscalculations into
visible, reported failures: any future change that breaks a previously-correct
invariant (a dropped column, an unapplied setting, a stale routing decision)
will trip a check on the very next run instead of shipping a wrong plan.

Each check is pure and returns a list of human-readable violation strings
(empty == passed). `verify_plan` runs them all and returns a structured report
the page renders as a "Plan integrity check" panel.

Design notes:
- Checks are defensive: a column that does not exist is skipped, never assumed.
- Comparisons coerce to numeric and treat NaN conservatively so a check never
  raises on messy data — it reports, it does not crash.
- Tolerances are explicit for floating-point conservation checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

CONSUMPTION_TOL = 1e-6
VALID_SYSTEM = {"KTC", "Kanban"}
VENDING_TYPES = {"Helix", "Carousel", "Locker A", "Locker B", "Locker C"}


@dataclass
class InvariantReport:
    checks: dict[str, list[str]] = field(default_factory=dict)

    @property
    def violations(self) -> list[str]:
        out: list[str] = []
        for name, msgs in self.checks.items():
            out.extend(msgs)
        return out

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def n_checks(self) -> int:
        return len(self.checks)

    @property
    def n_passed(self) -> int:
        return sum(1 for msgs in self.checks.values() if not msgs)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


# --- conservation -----------------------------------------------------------

def check_consumption_conservation(consumption_before: float,
                                   consumption_after_year: float,
                                   consumption_after_dedup: float,
                                   tol: float = CONSUMPTION_TOL) -> list[str]:
    """Deduplication must conserve total consumption; the year filter is the
    only stage allowed to reduce it (and only by dropping non-latest years)."""
    out: list[str] = []
    if abs(consumption_after_dedup - consumption_after_year) > max(tol, abs(consumption_after_year) * 1e-9):
        out.append(
            f"Consumption not conserved by deduplication: "
            f"{consumption_after_year:.4f} before dedup vs "
            f"{consumption_after_dedup:.4f} after."
        )
    if consumption_after_year - consumption_before > max(tol, abs(consumption_before) * 1e-9):
        out.append(
            f"Consumption increased during year filtering "
            f"({consumption_before:.4f} -> {consumption_after_year:.4f}); "
            "filtering must never add consumption."
        )
    return out


def check_row_accounting(rows_before: int, rows_after_year: int,
                         rows_after_dedup: int) -> list[str]:
    """Row counts must be non-increasing through filtering and dedup."""
    out: list[str] = []
    if rows_after_year > rows_before:
        out.append(f"Year filter increased row count ({rows_before} -> {rows_after_year}).")
    if rows_after_dedup > rows_after_year:
        out.append(f"Deduplication increased row count ({rows_after_year} -> {rows_after_dedup}).")
    return out


# --- routing ----------------------------------------------------------------

def check_routing_partition(df: pd.DataFrame) -> list[str]:
    """Every row must be routed to exactly one valid system (KTC or Kanban)."""
    out: list[str] = []
    if "SystemCategory" not in df.columns:
        return ["SystemCategory column is missing after routing."]
    sysc = df["SystemCategory"].astype(str)
    bad = sorted(set(sysc.unique()) - VALID_SYSTEM)
    if bad:
        out.append(f"Unexpected SystemCategory value(s): {bad}. Allowed: KTC, Kanban.")
    n_null = int(df["SystemCategory"].isna().sum())
    if n_null:
        out.append(f"{n_null} row(s) have no SystemCategory (null).")
    return out


# --- pack sizes -------------------------------------------------------------

def check_pack_units(df: pd.DataFrame) -> list[str]:
    """PackUnits must be present and >= 1 (used as a divisor for Monthly_packs)."""
    if "PackUnits" not in df.columns:
        return ["PackUnits column is missing."]
    pu = _num(df["PackUnits"])
    out: list[str] = []
    n_nan = int(pu.isna().sum())
    if n_nan:
        out.append(f"{n_nan} row(s) have a non-numeric PackUnits.")
    n_lt1 = int((pu < 1).sum())
    if n_lt1:
        out.append(f"{n_lt1} row(s) have PackUnits < 1 (would distort the monthly pack rate).")
    return out


# --- coverage ---------------------------------------------------------------

def check_coverage(df: pd.DataFrame) -> list[str]:
    """Per-row coverage must be positive and Target_packs must be finite >= 0."""
    out: list[str] = []
    if "Coverage_days" in df.columns:
        cov = _num(df["Coverage_days"])
        n_bad = int((cov.isna() | (cov < 1)).sum())
        if n_bad:
            out.append(f"{n_bad} row(s) have invalid Coverage_days (< 1 or null).")
    if "Target_packs" in df.columns:
        tp = _num(df["Target_packs"])
        n_bad = int((tp.isna() | (tp < 0) | ~np.isfinite(tp.fillna(np.inf))).sum())
        if n_bad:
            out.append(f"{n_bad} row(s) have invalid Target_packs (null, negative, or non-finite).")
    return out


# --- sizing consistency -----------------------------------------------------

def check_sizing_consistency(df: pd.DataFrame) -> list[str]:
    """Cabinet type and the vending counts must agree, and Kanban rows must
    carry no vending capacity."""
    out: list[str] = []
    if "CabinetType" not in df.columns:
        return ["CabinetType column is missing after routing."]
    ct = df["CabinetType"].astype(str)
    spir = _num(df["Spirals_needed"]).fillna(0) if "Spirals_needed" in df.columns else pd.Series(0, index=df.index)
    cars = _num(df["Carousel_stockpiles"]).fillna(0) if "Carousel_stockpiles" in df.columns else pd.Series(0, index=df.index)

    if "SystemCategory" in df.columns:
        kanban = df["SystemCategory"].astype(str) == "Kanban"
        n_kan_cap = int(((kanban) & ((spir > 0) | (cars > 0))).sum())
        if n_kan_cap:
            out.append(f"{n_kan_cap} Kanban row(s) carry vending capacity (spirals or stockpiles > 0).")
        ktc = df["SystemCategory"].astype(str) == "KTC"
        n_ktc_kanbin = int((ktc & (ct == "Kanban")).sum())
        if n_ktc_kanbin:
            out.append(f"{n_ktc_kanbin} KTC row(s) have CabinetType 'Kanban' (contradiction).")

    n_helix_zero = int(((ct == "Helix") & (spir < 1)).sum())
    if n_helix_zero:
        out.append(f"{n_helix_zero} Helix row(s) have 0 spirals (Helix needs >= 1).")
    n_car_zero = int(((ct == "Carousel") & (cars < 1)).sum())
    if n_car_zero:
        out.append(f"{n_car_zero} Carousel row(s) have 0 stockpiles (Carousel needs >= 1).")
    return out


# --- export reconciliation --------------------------------------------------

def check_export_partition(total_rows: int, subset_rows: dict[str, int]) -> list[str]:
    """The KTC-only and Kanban-only export sheets must together account for
    every planned row exactly once."""
    out: list[str] = []
    ktc = subset_rows.get("KTC", 0)
    kanban = subset_rows.get("Kanban", 0)
    if ktc + kanban != total_rows:
        out.append(
            f"Export partition mismatch: KTC ({ktc}) + Kanban ({kanban}) "
            f"= {ktc + kanban}, expected {total_rows} total rows."
        )
    return out


def reconcile_export_frames(*, n_plan: int, n_result: int,
                            n_ktc: int, n_kanban: int) -> list[str]:
    """Validate the ACTUAL exported datasets (after augment/user-view), not the
    pre-transform frames: the Result sheet must keep every plan row, and the
    KTC-only + Kanban-only sheets must partition the Result sheet exactly."""
    out: list[str] = []
    if n_result != n_plan:
        out.append(
            f"Result sheet has {n_result} rows but the plan has {n_plan} "
            "(augment/user-view changed the row count).")
    if n_ktc + n_kanban != n_result:
        out.append(
            f"KTC_only ({n_ktc}) + Kanban_only ({n_kanban}) = {n_ktc + n_kanban} "
            f"does not equal Result ({n_result}).")
    return out


# --- arithmetic identities (E1) ---------------------------------------------

def check_target_packs_identity(df: pd.DataFrame, days_per_month: float,
                                tol: float = CONSUMPTION_TOL) -> list[str]:
    """Target_packs must equal Monthly_packs x Coverage_days / days_per_month.
    Catches a coverage edit that did not propagate to Target_packs."""
    if not {"Target_packs", "Monthly_packs", "Coverage_days"} <= set(df.columns):
        return []
    if days_per_month <= 0:
        return ["days_per_month must be positive for the Target_packs identity."]
    mp = _num(df["Monthly_packs"]); cov = _num(df["Coverage_days"]); tp = _num(df["Target_packs"])
    expected = mp * cov / float(days_per_month)
    diff = (tp - expected).abs()
    ok = diff <= (tol + expected.abs() * 1e-6)
    n_bad = int((~ok & tp.notna() & expected.notna()).sum())
    if n_bad:
        return [f"{n_bad} row(s) violate Target_packs = Monthly_packs x Coverage_days / {days_per_month:g}."]
    return []


def check_monthly_packs_identity(df: pd.DataFrame, period_months: float,
                                 tol: float = CONSUMPTION_TOL) -> list[str]:
    """Monthly_packs must equal Consumption_pcs / period_months / PackUnits
    (PackUnits floored at 1, matching the pipeline). Catches a broken
    monthly-rate formula that would otherwise pass the range checks."""
    if not {"Monthly_packs", "Consumption_pcs", "PackUnits"} <= set(df.columns):
        return []
    if period_months <= 0:
        return ["Consumption period (months) must be positive for the Monthly_packs identity."]
    cons = _num(df["Consumption_pcs"]); pack = _num(df["PackUnits"]).clip(lower=1.0)
    mp = _num(df["Monthly_packs"])
    expected = cons / float(period_months) / pack
    diff = (mp - expected).abs()
    ok = diff <= (tol + expected.abs() * 1e-6)
    n_bad = int((~ok & mp.notna() & expected.notna()).sum())
    if n_bad:
        return [f"{n_bad} row(s) violate Monthly_packs = Consumption_pcs / {period_months:g} / PackUnits."]
    return []


# --- supply-point conservation (E4) -----------------------------------------

def check_supply_point_conservation(pre_total: float, post_total: float,
                                    tol: float = CONSUMPTION_TOL) -> list[str]:
    """Assigning rows to supply points must conserve total consumption: the
    partition mode reassigns rows, and the replication mode divides each row's
    consumption equally across its copies — neither may change the sum."""
    if abs(post_total - pre_total) > max(tol, abs(pre_total) * 1e-9):
        return [
            f"Supply-point assignment changed total consumption "
            f"({pre_total:.4f} -> {post_total:.4f}); it must conserve the total."
        ]
    return []


# --- KROMI article-number uniqueness (E3) -----------------------------------

def check_kromi_uniqueness(df: pd.DataFrame, col: str = "Kromi_Art_No") -> list[str]:
    """Assigned KROMI numbers must be unique and well-formed (12 digits, all
    numeric, ending in 0). Blanks (rows that did not receive a number) are
    ignored. Catches a variant-counter overflow or two fingerprints colliding."""
    if col not in df.columns:
        return []
    out: list[str] = []
    vals = df[col].fillna("").astype(str).str.strip()
    nonblank = vals[(vals != "") & (~vals.str.lower().isin(["nan", "none"]))]
    dups = nonblank[nonblank.duplicated(keep=False)]
    if not dups.empty:
        examples = ", ".join(sorted(dups.unique())[:3])
        out.append(f"{dups.nunique()} KROMI number(s) are assigned to more than one row (e.g. {examples}).")
    malformed = nonblank[~nonblank.str.fullmatch(r"\d{11}0")]
    if not malformed.empty:
        out.append(f"{len(malformed)} KROMI number(s) are malformed (not 12 digits ending in 0).")
    return out


# --- VendMode <-> SystemCategory consistency (A5) ---------------------------

def check_vendmode_consistency(df: pd.DataFrame) -> list[str]:
    """A KTC (in-cabinet) row must not carry VendMode 'Bulk/Kanban', which
    means warehouse/bulk dispensing and implies SystemCategory Kanban. The
    reverse (a Kanban row defaulted to 'Vending') is not flagged: it is the
    pipeline's documented default and is not a contradiction."""
    if not {"SystemCategory", "VendMode"} <= set(df.columns):
        return []
    sysc = df["SystemCategory"].astype(str)
    vm = df["VendMode"].astype(str)
    n_bad = int(((sysc == "KTC") & (vm == "Bulk/Kanban")).sum())
    if n_bad:
        return [f"{n_bad} KTC row(s) have VendMode 'Bulk/Kanban' (warehouse mode contradicts an in-cabinet row)."]
    return []


# --- top-level --------------------------------------------------------------

_RESTOCK_TARGETS = ("Carousel", "Locker A", "Locker B", "Locker C")


def check_restock_frame(df: pd.DataFrame) -> list[str]:
    """Frame-level restocking consistency (v34.27).

    Frames without the feature columns pass silently: the checks only apply
    once the restock segment has written its columns. Rules: a slot count is
    0 or 1; a reserved slot implies the row is restockable, sits on a KTC
    cabinet row, and names a valid buffer target; a named target implies a
    reserved slot; Kanban rows never carry a slot.
    """
    issues: list[str] = []
    needed = ("Restock_slots", "Restock_target", "Restockable")
    if any(c not in df.columns for c in needed):
        return issues
    slots = pd.to_numeric(df["Restock_slots"], errors="coerce").fillna(0)
    target = df["Restock_target"].fillna("").astype(str)
    flag = df["Restockable"].map(
        lambda v: str(v).strip().lower() in ("true", "yes", "1")
    )
    bad_range = ~slots.isin((0, 1))
    if bad_range.any():
        issues.append(f"{int(bad_range.sum())} row(s) have a restock slot count outside 0..1.")
    has_slot = slots == 1
    if (has_slot & ~flag).any():
        issues.append(f"{int((has_slot & ~flag).sum())} row(s) reserve a buffer without being restockable.")
    if (has_slot & ~target.isin(_RESTOCK_TARGETS)).any():
        issues.append(f"{int((has_slot & ~target.isin(_RESTOCK_TARGETS)).sum())} row(s) reserve a buffer with an invalid target.")
    if ((target != "") & ~has_slot).any():
        issues.append(f"{int(((target != '') & ~has_slot).sum())} row(s) name a buffer target without a slot.")
    if "SystemCategory" in df.columns:
        kanban = df["SystemCategory"].astype(str) == "Kanban"
        if (kanban & has_slot).any():
            issues.append(f"{int((kanban & has_slot).sum())} Kanban row(s) carry a restock buffer.")
    return issues


def check_restock_bucket_consistency(
    df: pd.DataFrame, bucket_plans: list[tuple[str, dict[str, Any]]]
) -> list[str]:
    """Bucket-level restocking consistency (v34.27).

    Floors: any bucket with reserved Carousel buffers holds at least one
    Carousel, and the same per locker class. Conservation: the buffer slots
    the frame reserves, summed per target family, equal what the bucket
    plans consumed, so nothing was dropped or invented between the segment
    and the math.
    """
    issues: list[str] = []
    plan_car = plan_a = plan_b = plan_c = 0
    for label, p in bucket_plans:
        rc = int(p.get("restock_car_slots", 0) or 0)
        ra = int(p.get("restock_lockerA", 0) or 0)
        rb = int(p.get("restock_lockerB", 0) or 0)
        rcC = int(p.get("restock_lockerC", 0) or 0)
        plan_car += rc; plan_a += ra; plan_b += rb; plan_c += rcC
        if rc > 0 and int(p.get("car_cabs", 0) or 0) < 1:
            issues.append(f"{label}: {rc} Carousel buffer slot(s) but no Carousel cabinet.")
        for cls, need, cabs in (("A", ra, p.get("cabA", 0)),
                                ("B", rb, p.get("cabB", 0)),
                                ("C", rcC, p.get("cabC", 0))):
            if need > 0 and int(cabs or 0) < 1:
                issues.append(f"{label}: {need} Locker {cls} buffer slot(s) but no Locker {cls} cabinet.")
    if "Restock_slots" in df.columns and "Restock_target" in df.columns:
        slots = pd.to_numeric(df["Restock_slots"], errors="coerce").fillna(0)
        target = df["Restock_target"].fillna("").astype(str)
        frame_car = int(slots.where(target == "Carousel", 0).sum())
        frame_a = int(slots.where(target == "Locker A", 0).sum())
        frame_b = int(slots.where(target == "Locker B", 0).sum())
        frame_c = int(slots.where(target == "Locker C", 0).sum())
        for fam, f_n, p_n in (("Carousel", frame_car, plan_car),
                              ("Locker A", frame_a, plan_a),
                              ("Locker B", frame_b, plan_b),
                              ("Locker C", frame_c, plan_c)):
            if f_n != p_n:
                issues.append(
                    f"Restock conservation broken for {fam}: the frame reserves "
                    f"{f_n} slot(s) but the bucket plans consumed {p_n}."
                )
    return issues


def verify_plan(df: pd.DataFrame, base_info: dict[str, Any] | None = None,
                *, days_per_month: float | None = None,
                consumption_period_months: float | None = None) -> InvariantReport:
    """Run every applicable check against the final planning dataframe."""
    report = InvariantReport()
    report.checks["routing_partition"] = check_routing_partition(df)
    report.checks["pack_units"] = check_pack_units(df)
    report.checks["coverage"] = check_coverage(df)
    report.checks["sizing_consistency"] = check_sizing_consistency(df)
    report.checks["vendmode_consistency"] = check_vendmode_consistency(df)
    report.checks["restock_frame"] = check_restock_frame(df)
    if days_per_month is not None:
        report.checks["target_packs_identity"] = check_target_packs_identity(df, days_per_month)
    if consumption_period_months is not None:
        report.checks["monthly_packs_identity"] = check_monthly_packs_identity(df, consumption_period_months)
    if base_info:
        cb = base_info.get("consumption_before")
        cy = base_info.get("consumption_after_year")
        cd = base_info.get("consumption_after_dedup")
        if cb is not None and cy is not None and cd is not None:
            report.checks["consumption_conservation"] = check_consumption_conservation(cb, cy, cd)
        report.checks["row_accounting"] = check_row_accounting(
            int(base_info.get("rows_before", 0)),
            int(base_info.get("rows_after_year_filter", 0)),
            int(base_info.get("rows_after_dedup", 0)),
        )
    return report
