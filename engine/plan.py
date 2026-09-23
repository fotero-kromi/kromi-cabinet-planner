"""Composition layer for the deterministic planning pipeline.

The planner runs the customer frame through a sequence of pure engine stages, each
already extracted and tested on its own. These functions compose contiguous runs
of those stages into named segments, and ``run_plan(work, overrides_df, params)``
composes the segments into the single deterministic entry point the page calls. Each segment here is pure: it
reads the frame and returns a new one, with no Streamlit dependency and no I/O.
The page keeps the UI, the AI classification wave, and the parts of the pipeline
that are still interleaved with previews and stats; those move into segments in
later steps. The non-deterministic AI classification stays outside this layer (it
is cached separately), so everything here is a deterministic function of its
inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .demand import compute_demand, assign_system_category
from .sizing import assign_cabinet_types, assign_physical_sizing
from .fitting import apply_fit_check
from .cabinet_math import (apply_system_type, force_special_to_ktc, apply_bulk_routing,
                           assign_supply_points, decide_spiral_capacity, regrind_spiral_floor,
                           route_and_size_row, compute_helix_spirals_needed,
                           flag_unfit_for_mode, locker_for_size, compute_plan_for_subset,
                           rebalance_cabinets, apply_carousel_cap, detect_size_locked_items,
                           apply_operational_mode)
from .fixed_config import (FIXED_MODE, MachineSet, fit_fixed_configuration,
                           fixed_plan_for_subset, machines_by_sp)
from .fixed_config import write_back as fixed_write_back
from .overrides import apply_overrides
from .plan_config import PlanConfig
from .classification import detect_item_family, apply_stored_classifications
from .constants import DAYS_PER_MONTH, LISTING_TOOLS, LISTING_PPE, SIZE_VALID
from .invariants import (check_restock_bucket_consistency,
                         check_supply_point_conservation, verify_plan, InvariantReport)
from .routing_rules import threshold_for_row, parse_system_type, classify_standard_special


def run_demand_segment(df, *, consumption_period_months, coverage_days,
                       coverage_days_special, usage_threshold, per_class_thresholds,
                       optional_thresholds_active):
    """Demand arithmetic and the base KTC/Kanban decision.

    Runs ``compute_demand`` (monthly figures, target packs, coverage) then
    ``assign_system_category`` (the base usage-threshold decision before any
    override layers). The override layers, screws/accessories, system type, and
    special-to-KTC, are applied later in the pipeline and are not part of this
    base decision.
    """
    out = compute_demand(
        df,
        consumption_period_months=consumption_period_months,
        coverage_days=coverage_days,
        coverage_days_special=coverage_days_special,
    )
    out = assign_system_category(
        out,
        usage_threshold=usage_threshold,
        per_class_thresholds=per_class_thresholds,
        optional_thresholds_active=optional_thresholds_active,
    )
    return out


def run_sizing_segment(df, *, helix_threshold, run_fit_check,
                       minimum_carousel_allocation, carousel_reserve_factor,
                       helix_overfill_factor):
    """Cabinet-type assignment, the optional fit-check, and physical sizing.

    Runs ``assign_cabinet_types`` (Helix vs Carousel vs Locker plus spiral
    capacity), then the advisory ``apply_fit_check`` only when ``run_fit_check`` is
    true (the caller passes the mapped-dimensions condition, so when no dimensions
    column was mapped the Fit_* columns are not created at all), then
    ``assign_physical_sizing`` (Helix spirals and Carousel stockpiles). The reserve
    and overfill factors are the caller's run-time settings, passed through
    explicitly rather than defaulted.
    """
    out = assign_cabinet_types(df, helix_threshold=helix_threshold)
    if run_fit_check:
        out = apply_fit_check(out)
    out = assign_physical_sizing(
        out,
        minimum_carousel_allocation=minimum_carousel_allocation,
        carousel_reserve_factor=carousel_reserve_factor,
        helix_overfill_factor=helix_overfill_factor,
    )
    return out


def run_routing_override_segment(df, *, force_system_type, force_special_ktc,
                                 threshold, helix_threshold, min_carousel_compartments,
                                 carousel_reserve_factor, helix_overfill_factor):
    """The two forcing-override steps: system type, then special-to-KTC.

    Both share the same routing parameters and both mutate ``df`` in place, pinning
    the rows they force (Routing_Pinned) so later bulk routing and consolidation
    leave them alone. System type runs first, so a system-type-fixed row wins over
    the special rule; special-to-KTC runs second. Each step runs only when its flag
    is set; the caller derives the flags from the mapped columns and the toggle.
    Returns the per-step counts (or None for a step that did not run) so the caller
    can report them. The frame itself is returned via in-place mutation, matching
    how the underlying engine functions work.
    """
    counts: Dict[str, Any] = {"system_type": None, "special_forced": None}
    params = dict(
        threshold=threshold,
        helix_threshold=helix_threshold,
        min_carousel_compartments=min_carousel_compartments,
        carousel_reserve_factor=carousel_reserve_factor,
        helix_overfill_factor=helix_overfill_factor,
    )
    if force_system_type:
        counts["system_type"] = apply_system_type(df, **params)
    if force_special_ktc:
        counts["special_forced"] = force_special_to_ktc(df, **params)
    return counts


def run_bulk_routing_segment(df, *, enable_bulk_routing):
    """Optional bulk routing, or the audit columns it would otherwise leave behind.

    When enabled, ``apply_bulk_routing`` consolidates high-volume item families onto
    bulk vending and returns the routing stats. When disabled, the rest of the
    pipeline still reads ItemFamily, VendMode, VendBlockReason, and the pre-route
    snapshots, so this fills them with no-routing defaults while preserving any
    technician VendMode override already on a row. Returns (frame, stats); the
    disabled path returns zeroed stats. The enabled path returns whatever
    apply_bulk_routing produces; the disabled path mutates the frame in place and
    returns it.
    """
    if enable_bulk_routing:
        return apply_bulk_routing(df)
    # Disabled: still create ItemFamily / VendMode columns for audit consistency,
    # but leave VendMode=Vending and don't touch Spirals/Stockpiles.
    df["ItemFamily"] = df.apply(
        lambda r: detect_item_family(
            r.get("Description", ""),
            r.get("Description_2", ""),
            r.get("Code", ""),
            r.get("SupplierCode", ""),
        ),
        axis=1,
    )
    # Respect overrides even when bulk routing is disabled: a technician may have
    # overridden VendMode on a row already.
    if "Override_Applied" in df.columns:
        has_override = df["Override_Applied"] == True  # noqa: E712
    else:
        has_override = pd.Series(False, index=df.index)
    # Default to Vending for non-overridden rows only.
    if "VendMode" not in df.columns:
        df["VendMode"] = "Vending"
    else:
        df.loc[~has_override, "VendMode"] = "Vending"
    if "VendBlockReason" not in df.columns:
        df["VendBlockReason"] = ""
    else:
        df.loc[~has_override, "VendBlockReason"] = ""
    df["CabinetType_pre_route"] = df["CabinetType"] if "CabinetType" in df.columns else ""
    if "Spirals_needed" in df.columns:
        df["Spirals_needed_pre_route"] = pd.to_numeric(df["Spirals_needed"], errors="coerce").fillna(0).astype(int)
    else:
        df["Spirals_needed_pre_route"] = 0
    if "Carousel_stockpiles" in df.columns:
        df["Carousel_stockpiles_pre_route"] = pd.to_numeric(df["Carousel_stockpiles"], errors="coerce").fillna(0).astype(int)
    else:
        df["Carousel_stockpiles_pre_route"] = 0
    return df, {"routed_rows": 0, "removed_spirals": 0, "removed_carousel_slots": 0, "by_family": {}}


def run_supply_point_segment(df, *, n_supply_points, mode):
    """Assign supply points and confirm total consumption is conserved.

    Replicate mode duplicates each item across the supply points at 1/N
    consumption; partition mode assigns each item to exactly one supply point,
    balanced by consumption. Either way the total consumption must be preserved.
    Returns (frame, conservation_issues); the issues list is empty unless the
    before/after totals disagree, in which case the caller surfaces it.
    """
    pre = float(pd.to_numeric(df["Consumption_pcs"], errors="coerce").fillna(0.0).sum())
    out = assign_supply_points(df, n_supply_points, mode=mode)
    post = float(pd.to_numeric(out["Consumption_pcs"], errors="coerce").fillna(0.0).sum())
    issues = check_supply_point_conservation(pre, post)
    return out, issues


def run_override_application_segment(df, overrides_active_df, *, usage_threshold, helix_threshold,
                                     minimum_carousel_allocation, carousel_reserve_factor,
                                     helix_overfill_factor, per_class_thresholds,
                                     optional_thresholds_active, force_screws_accessories_kanban):
    """Apply the gathered override set to the frame and reconcile sizing and routing.

    The caller gathers the override set (from the live editor, a database set, or
    the file library); this applies it and makes the rest of the frame consistent.
    It snapshots the pre-override prediction, recomputes Monthly_packs and
    Target_packs for touched rows, re-derives sizing for rows whose CabinetType was
    explicitly forced (Helix / Carousel / Kanban / Locker), and re-routes touched
    rows whose routing was not explicitly set, because a changed PackUnits or
    ProductCategory can flip the KTC/Kanban decision. Returns
    (frame, override_stats, rerouted_flips). An empty override set is a no-op and
    returns the frame untouched with zeroed stats.
    """
    default_stats = {
        "rows_touched": 0, "fields_changed": {}, "unmatched_overrides": [],
        "invalid_overrides": [], "applied_overrides": [],
    }
    if len(overrides_active_df) == 0:
        return df, default_stats, 0

    # Snapshot the classifier's prediction + confidence BEFORE corrections, so the
    # validation panel can compare predicted vs technician-corrected.
    df["ProductCategory_PreOverride"] = df["ProductCategory"].copy()
    df["ProductCategory_ConfidencePreOverride"] = df["ProductCategory_Confidence"].copy()
    df, override_stats = apply_overrides(df, overrides_active_df)

    rerouted_flips = 0
    # After applying, some fields (PackUnits, CabinetType) changed.
    touched = df["Override_Applied"] == True  # noqa: E712
    if touched.any():
        # Recompute Monthly_packs for touched rows.
        pack = pd.to_numeric(df.loc[touched, "PackUnits"], errors="coerce").fillna(1.0).clip(lower=1.0)
        monthly_pcs = pd.to_numeric(df.loc[touched, "Monthly_pcs"], errors="coerce").fillna(0.0)
        df.loc[touched, "Monthly_packs"] = (monthly_pcs / pack)

        # Recompute Target_packs (scaled by per-row coverage).
        df.loc[touched, "Target_packs"] = (
            df.loc[touched, "Monthly_packs"]
            * (df.loc[touched, "Coverage_days"] / DAYS_PER_MONTH)
        )

        # Rows whose CabinetType / VendMode was explicitly overridden keep that
        # forced type; only their sizing is (re)derived. Rows whose ProductCategory
        # / PackUnits changed but whose routing was NOT explicitly overridden are
        # re-routed below (HMA-1).
        routing_ov = touched & (df.get("Routing_Overridden") == True)  # noqa: E712

        # For rows where CabinetType was forced to Helix:
        helix_forced = routing_ov & (df["CabinetType"] == "Helix")
        if helix_forced.any():
            for idx in df[helix_forced].index:
                spiral_cap = decide_spiral_capacity(
                    str(df.at[idx, "SizeCategory"]),
                    str(df.at[idx, "ProductCategory"]),
                )
                df.at[idx, "Spiral_capacity"] = spiral_cap
                monthly_packs_val = float(pd.to_numeric(df.at[idx, "Monthly_packs"], errors="coerce") or 0.0)
                n_sp_req = compute_helix_spirals_needed(
                    monthly_packs_val, spiral_cap, overfill_factor=helix_overfill_factor)
                df.at[idx, "Spirals_needed"] = regrind_spiral_floor(
                    int(max(1, n_sp_req)), bool(df.at[idx, "Regrind"])
                )
                df.at[idx, "Carousel_stockpiles"] = 0

        # For rows where CabinetType was forced to Carousel: zero spirals, recompute
        # stockpiles from Target_packs using the same formula as the main pipeline
        # (reserve factor + min floor).
        carousel_forced = routing_ov & (df["CabinetType"] == "Carousel")
        if carousel_forced.any():
            target_cs = pd.to_numeric(df.loc[carousel_forced, "Target_packs"], errors="coerce").fillna(0.0)
            stockpiles = target_cs.apply(
                lambda t: max(int(minimum_carousel_allocation),
                              max(1, math.ceil(t * carousel_reserve_factor)))
            )
            df.loc[carousel_forced, "Carousel_stockpiles"] = stockpiles.astype(int)
            df.loc[carousel_forced, "Spirals_needed"] = 0
            df.loc[carousel_forced, "Spiral_capacity"] = pd.NA

        # For rows forced to Kanban or a Locker type: zero vending counts.
        kanban_forced = routing_ov & (df["CabinetType"] == "Kanban")
        if kanban_forced.any():
            df.loc[kanban_forced, "Spirals_needed"] = 0
            df.loc[kanban_forced, "Carousel_stockpiles"] = 0
            df.loc[kanban_forced, "Spiral_capacity"] = pd.NA
            df.loc[kanban_forced, "SystemCategory"] = "Kanban"

        locker_forced = routing_ov & df["CabinetType"].isin(["Locker A", "Locker B", "Locker C"])
        if locker_forced.any():
            df.loc[locker_forced, "Spirals_needed"] = 0
            df.loc[locker_forced, "Carousel_stockpiles"] = 0
            df.loc[locker_forced, "Spiral_capacity"] = pd.NA

        # HMA-1: re-route overridden rows whose routing was not explicitly set.
        # KTC/Kanban was decided before overrides; an override that changes
        # PackUnits (-> Monthly_packs) or ProductCategory (-> insert status) can
        # change that decision. Re-run routing + cabinet type + sizing from the
        # final attributes so the plan is consistent.
        reroute = touched & ~routing_ov
        if reroute.any():
            for idx in df[reroute].index:
                new_pc = df.at[idx, "ProductCategory"]
                tool_class = df.at[idx, "ToolClass"] if "ToolClass" in df.columns else ""
                thr = threshold_for_row(
                    product_category=new_pc,
                    tool_class=tool_class,
                    standard_threshold=float(usage_threshold),
                    per_class_thresholds=per_class_thresholds,
                    optional_active=bool(optional_thresholds_active),
                )
                force_k = bool(force_screws_accessories_kanban) and str(new_pc).strip().lower() in ("screws", "accessories")
                prev_sys = df.at[idx, "SystemCategory"]
                res = route_and_size_row(
                    monthly_packs=pd.to_numeric(df.at[idx, "Monthly_packs"], errors="coerce"),
                    monthly_pcs=pd.to_numeric(df.at[idx, "Monthly_pcs"], errors="coerce"),
                    target_packs=pd.to_numeric(df.at[idx, "Target_packs"], errors="coerce"),
                    size_cat=df.at[idx, "SizeCategory"],
                    product_category=new_pc,
                    threshold=thr,
                    helix_threshold=float(helix_threshold),
                    min_carousel_compartments=int(minimum_carousel_allocation),
                    carousel_reserve_factor=float(carousel_reserve_factor),
                    helix_overfill_factor=float(helix_overfill_factor),
                    force_kanban=force_k,
                    regrind=bool(df.at[idx, "Regrind"]),
                )
                df.at[idx, "SystemCategory"] = res["SystemCategory"]
                df.at[idx, "CabinetType"] = res["CabinetType"]
                df.at[idx, "Spiral_capacity"] = (
                    res["Spiral_capacity"] if res["Spiral_capacity"] is not None else pd.NA)
                df.at[idx, "Spirals_needed"] = int(res["Spirals_needed"])
                df.at[idx, "Carousel_stockpiles"] = int(res["Carousel_stockpiles"])
                if res["SystemCategory"] != prev_sys:
                    rerouted_flips += 1
                    # Keep the reason string consistent with the new routing rather
                    # than leaving the pre-override reason (A4/E5).
                    if "SystemCategory_Reason" in df.columns:
                        df.at[idx, "SystemCategory_Reason"] = (
                            f"Re-routed to {res['SystemCategory']} after override")

    return df, override_stats, rerouted_flips


def _consolidate_customer_lockers(subset: pd.DataFrame, work: pd.DataFrame) -> None:
    """Locker consolidation for one bucket, in place on ``subset`` and ``work``.

    Every position the customer fixed to "Locker" in this bucket goes into ONE
    locker tier (the one whose compartment fits the LARGEST such position) so
    the smaller positions share it instead of opening separate A/B/C lockers.
    Done per bucket and before the rebalancer, which leaves these rows alone.
    Moved verbatim out of run_bucket_planning_segment (v34.52) so the fixed
    configuration mode applies the same rule.
    """
    if "SystemTyp" not in subset.columns:
        return
    _lk = subset["SystemTyp"].map(parse_system_type) == "LOCKER"
    if _lk.any():
        _rank = {"Locker A": 3, "Locker B": 2, "Locker C": 1}
        _tier = max(
            (locker_for_size(s) for s in subset.loc[_lk, "SizeCategory"]),
            key=lambda t: _rank[t],
        )
        _idx = subset.index[_lk.to_numpy()]
        subset.loc[_idx, "CabinetType"] = _tier
        work.loc[_idx, "CabinetType"] = _tier
        work.loc[_idx, "SystemCategory_Reason"] = (
            f"System type fixed: Locker (consolidated into {_tier})"
        )


def run_fixed_configuration_segment(
    work: pd.DataFrame,
    sp_buckets: list,
    *,
    machines: Dict[int, MachineSet],
    headroom_pct: float,
    allow_spill: bool,
    helix_overfill_factor: float,
    carousel_reserve_factor: float,
    minimum_carousel_allocation: int,
    stock_promotion_months: float = 0.0,
    helix_threshold: float = 0.0,
) -> tuple:
    """Per-supply-point fit into the configured machines (v34.52).

    ``sp_buckets`` is a list of ``(label, supply_point, subset)``. Each bucket
    gets the customer locker consolidation, then ``fit_fixed_configuration``
    against the machines of its supply point; the fit results are written back
    into ``work`` in place and the bucket plan reports the configured machines.
    No rebalancer, carousel cap or capacity buffer runs in this mode.

    Returns ``(work, bucket_plans)``.
    """
    bucket_plans: list = []
    work["SizeIssue"] = False
    work["Placement_Rank"] = pd.Series(pd.NA, index=work.index, dtype="Int64")
    work["Placement_Status"] = ""
    work["Placement_Note"] = ""
    for label, sp, subset in sp_buckets:
        subset = subset.copy()
        _consolidate_customer_lockers(subset, work)
        fitted, report = fit_fixed_configuration(
            subset, machines.get(int(sp), MachineSet()), headroom_pct,
            allow_spill=allow_spill,
            helix_overfill_factor=helix_overfill_factor,
            min_carousel_compartments=int(minimum_carousel_allocation),
            carousel_reserve_factor=carousel_reserve_factor,
            stock_promotion_months=float(stock_promotion_months),
            helix_threshold=float(helix_threshold),
        )
        report["supply_point"] = int(sp)
        fixed_write_back(work, fitted)
        bucket_plans.append(
            (label, fixed_plan_for_subset(fitted, report, overfill_factor=helix_overfill_factor))
        )
    return work, bucket_plans


def run_bucket_planning_segment(
    work: pd.DataFrame,
    buckets: list,
    *,
    op_mode: str,
    enable_rebalancer: bool,
    buf_pct: float,
    minimum_carousel_allocation: int,
    underuse_threshold_pct: float,
    max_carousels_cap: int,
    helix_overfill_factor: float,
    carousel_reserve_factor: float,
    carousel_fill_ceiling: float,
) -> tuple:
    """Per-bucket planning loop: size each (listing, supply-point) bucket and roll
    the results up.

    For every bucket this consolidates customer-fixed Locker positions into a
    single tier, runs the bidirectional rebalancer (Standard/Capped modes),
    enforces the Carousel cap (Capped mode), computes the bucket's plan, and
    flags size-locked items. Cabinet routing changes (CabinetType, Spirals_needed,
    Carousel_stockpiles) and the SizeIssue / SystemCategory_Reason annotations are
    written back into ``work`` in place so the Excel export and per-SP PDFs reflect
    the final routing.

    Returns ``(work, bucket_plans, rebalance_audit_all)`` where ``bucket_plans`` is
    a list of ``(label, plan_dict)`` and ``rebalance_audit_all`` is the list of
    rebalance audit events (each tagged with its bucket).

    The two sizing factors the page injected through shims
    (``helix_overfill_factor`` and ``carousel_reserve_factor``) are explicit
    parameters here and forwarded to the engine functions directly, so the segment
    reads no module-level state.
    """
    bucket_plans: list = []
    rebalance_audit_all: list = []
    # Problematic-size flag: set True on Carousel items whose size (L/XL) forces an
    # underused Carousel that a resize-to-Helix would let the rebalancer eliminate.
    work["SizeIssue"] = False
    # Helix/Carousel modes flag size-unfit tools (too big for the forced cabinet)
    # up front; Standard/Capped flag consolidation-blocking tools per bucket below.
    if op_mode in ("Helix", "Carousel"):
        _unfit = flag_unfit_for_mode(work, op_mode)
        if _unfit.any():
            work.loc[_unfit[_unfit].index, "SizeIssue"] = True
    for label, subset in buckets:
        subset = subset.copy()
        # Locker consolidation (see _consolidate_customer_lockers). Skipped in
        # Helix/Carousel mode.
        if op_mode not in ("Helix", "Carousel"):
            _consolidate_customer_lockers(subset, work)

        # Rebalancer runs in Standard and Capped modes only (Helix/Carousel have a
        # single cabinet type, so there is nothing to relocate across types).
        _run_rebalancer = (
            enable_rebalancer and len(subset) > 0 and op_mode not in ("Helix", "Carousel")
        )
        if _run_rebalancer:
            rebalanced_subset, audit_events = rebalance_cabinets(
                subset,
                buf_pct=buf_pct,
                minimum_carousel_allocation=int(minimum_carousel_allocation),
                underuse_threshold_pct=float(underuse_threshold_pct),
                carousel_reserve_factor=carousel_reserve_factor,
                overfill_factor=helix_overfill_factor,
                carousel_fill_ceiling=carousel_fill_ceiling,
            )
            if audit_events:
                # Apply rebalanced changes back to `work` (using the bucket's indices)
                for col in ("CabinetType", "Spirals_needed", "Carousel_stockpiles"):
                    if col in rebalanced_subset.columns:
                        work.loc[rebalanced_subset.index, col] = rebalanced_subset[col]
                # Annotate each affected row with a rebalance audit note
                for event in audit_events:
                    # Tag the bucket so audit can show it
                    event["bucket"] = label
                    rebalance_audit_all.append(event)
            final_subset = rebalanced_subset
        else:
            final_subset = subset

        # Capped mode: enforce the per-supply-point Carousel limit, spilling the
        # Helix-eligible overflow into Helix coils. Runs whether or not the
        # rebalancer ran; L/XL tools that cannot spill are flagged as size issues.
        if op_mode == "Capped" and len(final_subset) > 0:
            final_subset, _overflow = apply_carousel_cap(
                final_subset,
                int(max_carousels_cap),
                helix_overfill_factor=helix_overfill_factor,
                carousel_fill_ceiling=carousel_fill_ceiling,
            )
            for col in ("CabinetType", "Spirals_needed", "Carousel_stockpiles"):
                if col in final_subset.columns:
                    work.loc[final_subset.index, col] = final_subset[col]
            if _overflow:
                work.loc[[i for i in _overflow if i in work.index], "SizeIssue"] = True

        # Recompute the plan for this bucket from its final routing. In capped mode
        # the carousel cap is a hard limit, so the capacity buffer must not add
        # carousels beyond it: suppress the buffer on the Carousel dimension (it
        # still applies to Helix and Locker). Other modes use the global buffer.
        _buf_carousel = 0.0 if op_mode == "Capped" else None
        _bplan = compute_plan_for_subset(
            final_subset,
            buf_pct,
            overfill_factor=helix_overfill_factor,
            buf_carousel=_buf_carousel,
            carousel_fill_ceiling=carousel_fill_ceiling,
        )
        # Restock buffers are exact reservations and cannot spill to Helix, so
        # in capped mode they are allowed to push the Carousel count above the
        # hard cap; the page explains the exceedance and asks for a recompute
        # instead of silently dropping anything (v34.24).
        _bplan["carousel_cap_exceeded_by_restock"] = bool(
            op_mode == "Capped"
            and _bplan["restock_car_slots"] > 0
            and _bplan["car_cabs"] > int(max_carousels_cap)
        )
        bucket_plans.append((label, _bplan))

        # Standard/Capped: flag size-locked items (L/XL Carousel tools that, if
        # resized to a Helix-fit, would let the rebalancer drop a cabinet).
        # Advisory only; never alters the plan and never breaks the run.
        if (
            enable_rebalancer
            and len(final_subset) > 0
            and op_mode not in ("Helix", "Carousel")
        ):
            _locked = detect_size_locked_items(
                final_subset,
                buf_pct=buf_pct,
                minimum_carousel_allocation=int(minimum_carousel_allocation),
                underuse_threshold_pct=float(underuse_threshold_pct),
                carousel_reserve_factor=carousel_reserve_factor,
                overfill_factor=helix_overfill_factor,
            )
            if _locked:
                work.loc[[i for i in _locked if i in work.index], "SizeIssue"] = True

    return work, bucket_plans, rebalance_audit_all


# ---------------------------------------------------------------------------
# run_plan: the composed deterministic pipeline
# ---------------------------------------------------------------------------

#: The columns of the classification-preview snapshot, in the page's display
#: order. Filtered against the frame at snapshot time; kept here so the snapshot
#: and its renderer share one definition.
PREVIEW_COLUMNS: Tuple[str, ...] = (
    "Listing", "SupplyPoint", "Program", "Code", "SupplierCode", "Year",
    "ProductCategory", "ProductCategory_Source", "ProductCategory_Evidence",
    "ProductCategory_Confidence", "ProductCategory_AI_Consulted",
    "ProductCategory_AI_Model", "ProductCategory_AI_TimestampUTC",
    "Description", "Description_2", "Consumption_pcs",
    "PackUnits", "PackUnits_Source", "PackUnits_Evidence", "PackUnits_Confidence",
    "PackUnits_AI_Consulted", "PackUnits_AI_Model", "PackUnits_AI_TimestampUTC",
    "Monthly_pcs", "Monthly_packs", "Target_packs",
    "SizeCategory", "SizeCategory_Source", "SizeCategory_AI_Consulted",
    "SizeCategory_AI_Model", "SizeCategory_AI_TimestampUTC",
    "SystemCategory", "SystemCategory_Reason", "ItemFamily", "VendMode",
    "VendBlockReason", "CabinetType_pre_route", "CabinetType", "Spiral_capacity",
    "Spirals_needed_pre_route", "Spirals_needed",
    "Carousel_stockpiles_pre_route", "Carousel_stockpiles",
)

#: The grand-total roll-up keys, summed across every bucket plan.
GRAND_TOTAL_KEYS: Tuple[str, ...] = (
    "rows_total", "ktc_count", "kanban_count", "helix_refs", "carousel_refs",
    "locker_a_refs", "locker_b_refs", "locker_c_refs",
    "total_spirals", "total_spirals_buf", "car_slots", "car_slots_buf",
    "countA", "countA_buf", "countB", "countB_buf", "countC", "countC_buf",
    "helix_cabs_base", "helix_cabs", "car_cabs_base", "car_cabs",
    "cabA_base", "cabA", "cabB_base", "cabB", "cabC_base", "cabC",
    "total_cabs_base", "total_cabs", "total_consumption",
)


@dataclass(frozen=True)
class BaseCounts:
    """The preprocessing row/consumption accounting the invariant layer checks.

    A frozen slice of the page's ``base_info`` dict: exactly the six values
    ``verify_plan`` reads, nothing presentation-only.
    """

    rows_before: int
    rows_after_year_filter: int
    rows_after_dedup: int
    consumption_before: Optional[float]
    consumption_after_year: Optional[float]
    consumption_after_dedup: Optional[float]

    def as_base_info(self) -> Dict[str, Any]:
        return {
            "rows_before": self.rows_before,
            "rows_after_year_filter": self.rows_after_year_filter,
            "rows_after_dedup": self.rows_after_dedup,
            "consumption_before": self.consumption_before,
            "consumption_after_year": self.consumption_after_year,
            "consumption_after_dedup": self.consumption_after_dedup,
        }


@dataclass(frozen=True)
class PlanParams:
    """Every non-frame input of one deterministic planning run, frozen.

    The page resolves session state, widgets, and mapping choices into this
    object before calling ``run_plan``; nothing inside the engine reads Streamlit
    state. Every field is hashable (maps travel as sorted tuples), so the object
    is usable directly as part of a content-addressed cache key: two runs with
    equal frames and equal ``PlanParams`` are the same run.

    ``system_type_mapped`` / ``stdspecial_mapped`` / ``dims_mapped`` carry the
    page's column-mapping choices; the corresponding pipeline steps additionally
    require the mapped column to have survived preprocessing, which ``run_plan``
    checks against the frame exactly as the page did.
    """

    n_supply_points: int
    sp_mode: str
    consumption_period_months: float
    coverage_days: int
    coverage_days_special: int
    usage_threshold: float
    per_class_thresholds: Tuple[Tuple[str, float], ...]
    optional_thresholds_active: bool
    force_screws_accessories_kanban: bool
    manual_size_fixes: Tuple[Tuple[str, str], ...]
    stored_classifications: Tuple[Tuple[str, Optional[str], Optional[str]], ...]
    # Restocking (v34.24): product categories assumed restockable by rule. The
    # mapped yes/no column travels in the frame itself; this tuple is the
    # rule half of the source precedence (Provided beats Rule beats Default).
    restock_categories: Tuple[str, ...]
    helix_threshold: float
    dims_mapped: bool
    minimum_carousel_allocation: int
    plan_cfg: PlanConfig
    system_type_mapped: bool
    special_ktc: bool
    stdspecial_mapped: bool
    enable_bulk_routing: bool
    op_mode: str
    calc_mode_separated: bool
    capacity_buffer_pct: float
    enable_rebalancer: bool
    underuse_threshold_pct: float
    max_carousels_cap: int
    base_counts: Optional[BaseCounts] = None
    # Fixed configuration (v34.52), used only when op_mode is FIXED_MODE:
    # (sp, helix, carousel, locker_a, locker_b, locker_c) per supply point,
    # the headroom to keep free, and whether overflow may move to another
    # machine type the article fits.
    fixed_machines: Tuple[Tuple[int, int, int, int, int, int], ...] = ()
    fixed_headroom_pct: float = 0.0
    fixed_allow_spill: bool = True
    # Stock-based Helix promotion (v34.58): the months the stock on hand is
    # assumed to cover; 0 keeps the rule off.
    fixed_stock_promotion_months: float = 0.0


@dataclass
class PlanResult:
    """Everything one planning run produces and the page renders or persists.

    ``work`` is the final frame (post-rebalance, post-cap). ``hogs`` and
    ``preview`` are snapshots taken at the page's original mid-pipeline
    positions, before bucket planning writes rebalanced routing back into the
    frame, so the rendered content is unchanged. Every field pickles, which is
    what lets a cache return a fresh copy per rerun.
    """

    work: "pd.DataFrame"
    sp_conservation: List[str]
    split_coverage: bool
    n_pack_default: int
    stdspecial_missing: bool
    stdspecial_counts: Optional[Tuple[int, int, int]]
    reuse_hits_n: int
    reuse_misses_n: int
    override_stats: Dict[str, Any]
    rerouted_flips: int
    force_system_type: bool
    force_special_ktc: bool
    routing_override_counts: Dict[str, Any]
    vend_stats: Dict[str, Any]
    validation_issues: List[str]
    integrity: InvariantReport
    hogs: "pd.DataFrame"
    preview: "pd.DataFrame"
    listings: Tuple[str, ...]
    bucket_plans: List[Tuple[str, Dict[str, Any]]]
    rebalance_audit: List[Dict[str, Any]]
    grand: Dict[str, Any]
    restock_info: Dict[str, Any]


def _bucket_label(listing: Optional[str], sp: Optional[int]) -> str:
    parts = []
    if listing is not None:
        parts.append(str(listing))
    if sp is not None:
        parts.append(f"SP {sp}")
    return " @ ".join(parts) if parts else "All"


def grand_total(bucket_plans: List[Tuple[str, Dict[str, Any]]]) -> Dict[str, Any]:
    """Sum every bucket's cabinet counts into the grand total."""
    out: Dict[str, Any] = {k: 0 for k in GRAND_TOTAL_KEYS}
    for _, p in bucket_plans:
        for k in GRAND_TOTAL_KEYS:
            out[k] = out[k] + p.get(k, 0)
    return out


_RESTOCK_CABINETS = ("Helix", "Carousel", "Locker A", "Locker B", "Locker C")


def run_restock_segment(
    df: pd.DataFrame, *, restock_categories: Tuple[str, ...], op_mode: str = ""
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Decide per-row restockability and reserve the buffer compartments (v34.24).

    Runs after overrides and the operational mode, so it sees the final
    routing: an override that moved a flagged item to Kanban has already done
    so, and the buffer is dropped with it. Source precedence: the technician
    override (Override) beats a mapped yes/no value (Provided) beats the
    category rule (Rule) beats the default of not restockable. Restocking is
    a vending concept, so only KTC rows in a cabinet carry a buffer; coil
    cabinets cannot restock, so a Helix item buffers in a Carousel while
    Carousel and Locker items buffer in their own class. The Helix
    operational mode is incompatible with restocking and makes the segment
    inert. Returns a new frame; never mutates ``df``.

    Vectorized in v34.38 (audit P2): layer masks replace the per-row loop,
    with the row-wise original frozen as the parity reference in
    tests/test_restock_vectorization.py; semantics are byte-identical,
    including the audit trail for file-answered "no", the double unknown
    count when both layers carry junk, and the Kanban flag counter.
    """
    from engine.preprocessing import normalize_restock_flag

    out = df.copy()
    out["Restockable"] = False
    out["Restockable_Source"] = ""
    out["Restock_target"] = ""
    out["Restock_slots"] = 0
    info: Dict[str, Any] = {
        "provided_true": 0, "rule_true": 0, "override_true": 0, "unknown_values": 0,
        "flagged_kanban": 0, "slots_carousel": 0,
        "slots_lockerA": 0, "slots_lockerB": 0, "slots_lockerC": 0,
        "inert_mode": False,
    }
    if str(op_mode) == "Helix":
        info["inert_mode"] = True
        return out, info

    has_ov = "Restocking_Override" in out.columns
    has_col = "Restocking" in out.columns
    cats = {str(c).strip().lower() for c in (restock_categories or ()) if str(c).strip()}
    if (not has_col and not cats and not has_ov) or len(out) == 0:
        return out, info

    idx = out.index
    source = pd.Series("", index=idx, dtype=object)
    flag = pd.Series(False, index=idx, dtype=bool)

    def _layer(series: pd.Series):
        """A yes/no layer: which cells carry a value, and what each
        normalizes to (True/False, or None for unrecognized).

        Normalization maps the callable per cell (v34.42): a dict keyed by
        value collapses hash-equal raws (True == 1 == 1.0) whose string
        tokens normalize differently, so a memo cannot stand in for the
        row-wise reference semantics; the function itself can."""
        present = series.notna() & (series.astype(str).str.strip() != "")
        return present, series.map(normalize_restock_flag)

    if has_ov:
        ov_present, ov_norm = _layer(out["Restocking_Override"])
        info["unknown_values"] += int((ov_present & ov_norm.isna()).sum())
        decided = ov_present & ov_norm.notna()
        flag = flag.where(~decided, ov_norm.eq(True))
        source = source.where(~decided, "Override")

    if has_col:
        prov_present, prov_norm = _layer(out["Restocking"])
        # The source is the audit trail of the decision, recorded even for a
        # file-answered "no" and for unrecognized values (which count and
        # resolve to False): it distinguishes "the file said no" from
        # "nothing said anything".
        consider = prov_present & (source == "")
        info["unknown_values"] += int((consider & prov_norm.isna()).sum())
        flag = flag.where(~consider, prov_norm.eq(True))
        source = source.where(~consider, "Provided")

    if cats and "ProductCategory" in out.columns:
        pc = out["ProductCategory"].astype(str).str.strip().str.lower()
        rule = (source == "") & pc.isin(cats)
        flag = flag.where(~rule, True)
        source = source.where(~rule, "Rule")

    sourced = source != ""
    out.loc[sourced, "Restockable_Source"] = source[sourced]
    out.loc[flag, "Restockable"] = True
    by_source = source[flag].value_counts()
    info["override_true"] = int(by_source.get("Override", 0))
    info["provided_true"] = int(by_source.get("Provided", 0))
    info["rule_true"] = int(by_source.get("Rule", 0))

    system = (out["SystemCategory"].astype(str)
              if "SystemCategory" in out.columns else pd.Series("", index=idx))
    cabinet = (out["CabinetType"].astype(str)
               if "CabinetType" in out.columns else pd.Series("", index=idx))
    eligible = flag & (system == "KTC") & cabinet.isin(_RESTOCK_CABINETS)
    info["flagged_kanban"] = int((flag & ~eligible & (system == "Kanban")).sum())

    target = pd.Series("", index=idx, dtype=object)
    coil = eligible & cabinet.isin(("Helix", "Carousel"))
    target[coil] = "Carousel"
    lock = eligible & ~coil
    target[lock] = cabinet[lock]
    out.loc[eligible, "Restock_target"] = target[eligible]
    out.loc[eligible, "Restock_slots"] = 1
    by_target = target[eligible].value_counts()
    info["slots_carousel"] = int(by_target.get("Carousel", 0))
    info["slots_lockerA"] = int(by_target.get("Locker A", 0))
    info["slots_lockerB"] = int(by_target.get("Locker B", 0))
    info["slots_lockerC"] = int(by_target.get("Locker C", 0))
    return out, info


def run_plan(work: pd.DataFrame, overrides_df: pd.DataFrame,
             params: PlanParams) -> PlanResult:
    """Run the full deterministic planning pipeline on a prepared work frame.

    ``work`` is the frame as the page prepared it (preprocessing done, AI results
    merged, the post-AI safety pass applied); ``overrides_df`` is the effective
    technician override set the page gathered (live editor, database set, file
    library, or empty). The stages run in the page's exact historical order --
    the order is pinned by the equivalence tests, which replicate the page's
    sequence literally and compare against this function.

    Pure: never mutates its arguments, touches no I/O, no Streamlit, no model
    call, and is deterministic in its inputs. Returns a ``PlanResult`` carrying
    the final frame plus every statistic, snapshot, and roll-up the page renders
    or persists.
    """
    if not work.index.is_unique:
        raise ValueError(
            "run_plan requires a unique row index; the frame carries "
            "duplicate labels"
        )
    work = work.copy()
    per_class = dict(params.per_class_thresholds)

    # Supply point assignment (Partition OR Replicate)
    work, sp_conservation = run_supply_point_segment(
        work, n_supply_points=int(params.n_supply_points), mode=params.sp_mode)

    # Demand arithmetic and the base KTC/Kanban decision
    work = run_demand_segment(
        work,
        consumption_period_months=params.consumption_period_months,
        coverage_days=params.coverage_days,
        coverage_days_special=params.coverage_days_special,
        usage_threshold=params.usage_threshold,
        per_class_thresholds=per_class,
        optional_thresholds_active=params.optional_thresholds_active,
    )
    split_coverage = ("StdSpecial" in work.columns) and (
        params.coverage_days_special != params.coverage_days)

    if params.force_screws_accessories_kanban:
        mask_force_kanban = work["ProductCategory"].astype(str).str.lower().isin(
            ["screws", "accessories"])
        work.loc[mask_force_kanban, "SystemCategory"] = "Kanban"
        work.loc[mask_force_kanban, "SystemCategory_Reason"] = (
            "Forced Kanban: screws/accessories")

    n_pack_default = (
        int((work["PackUnits_Source"].astype(str) == "Default").sum())
        if "PackUnits_Source" in work.columns else 0)

    stdspecial_missing = False
    stdspecial_counts: Optional[Tuple[int, int, int]] = None
    if params.stdspecial_mapped:
        if "StdSpecial" not in work.columns:
            stdspecial_missing = True
        else:
            _cls = work["StdSpecial"].apply(classify_standard_special)
            stdspecial_counts = (int((_cls == "standard").sum()),
                                 int((_cls == "special").sum()),
                                 int((_cls == "").sum()))

    # Stored-classification reuse (recompute path)
    reuse_hits_n = reuse_misses_n = 0
    if params.stored_classifications:
        lookup = {code: {"size_category": size, "product_category": prod}
                  for code, size, prod in params.stored_classifications}
        work, _reuse_hits, _reuse_misses = apply_stored_classifications(work, lookup)
        if "SizeCategory_Source" in work.columns:
            work.loc[work["Code"].astype(str).isin(_reuse_hits),
                     "SizeCategory_Source"] = "Reused from stored run"
        reuse_hits_n, reuse_misses_n = len(_reuse_hits), len(_reuse_misses)

    # Manual size fixes from the "problematic size" action. Applied after the
    # stored-classification reuse (v34.57): the technician's assertion wins
    # over a stored size, which used to put the old L/XL size back.
    manual_size_fix = dict(params.manual_size_fixes)
    if manual_size_fix and "Code" in work.columns:
        _codes = work["Code"].astype(str)
        for _fix_code, _fix_size in manual_size_fix.items():
            _fm = _codes == str(_fix_code)
            if _fm.any():
                work.loc[_fm, "SizeCategory"] = str(_fix_size).upper()
                work.loc[_fm, "SizeCategory_Source"] = "Manual (Helix-fit)"

    # Cabinet type, optional dimensional fit-check, and physical sizing
    work = run_sizing_segment(
        work,
        helix_threshold=params.helix_threshold,
        run_fit_check=bool(params.dims_mapped and "PackageDimensions" in work.columns),
        minimum_carousel_allocation=int(params.minimum_carousel_allocation),
        carousel_reserve_factor=float(params.plan_cfg.carousel_reserve_factor),
        helix_overfill_factor=float(params.plan_cfg.helix_overfill_factor),
    )

    # Apply the technician override set gathered by the caller
    override_stats: Dict[str, Any] = {
        "rows_touched": 0, "fields_changed": {}, "unmatched_overrides": [],
        "invalid_overrides": [], "applied_overrides": [],
    }
    rerouted_flips = 0
    if len(overrides_df) > 0:
        work, override_stats, rerouted_flips = run_override_application_segment(
            work, overrides_df,
            usage_threshold=params.usage_threshold,
            helix_threshold=params.helix_threshold,
            minimum_carousel_allocation=params.minimum_carousel_allocation,
            carousel_reserve_factor=params.plan_cfg.carousel_reserve_factor,
            helix_overfill_factor=params.plan_cfg.helix_overfill_factor,
            per_class_thresholds=per_class,
            optional_thresholds_active=params.optional_thresholds_active,
            force_screws_accessories_kanban=params.force_screws_accessories_kanban,
        )
    # Always ensure the override audit columns exist
    for _c, _default in [
        ("Override_Applied", False),
        ("Override_Fields", ""),
        ("Override_Note", ""),
        ("Override_ReviewedBy", ""),
        ("Override_ReviewedAt", ""),
    ]:
        if _c not in work.columns:
            work[_c] = _default

    # Forcing overrides: system type first, special-to-KTC second
    force_system_type = bool(params.system_type_mapped and "SystemTyp" in work.columns)
    force_special_ktc = bool(params.special_ktc and params.stdspecial_mapped
                             and "StdSpecial" in work.columns)
    routing_override_counts = run_routing_override_segment(
        work,
        force_system_type=force_system_type,
        force_special_ktc=force_special_ktc,
        threshold=float(params.usage_threshold),
        helix_threshold=float(params.helix_threshold),
        min_carousel_compartments=int(params.minimum_carousel_allocation),
        carousel_reserve_factor=float(params.plan_cfg.carousel_reserve_factor),
        helix_overfill_factor=float(params.plan_cfg.helix_overfill_factor),
    )

    # Optional bulk routing (or its audit-column defaults)
    work, vend_stats = run_bulk_routing_segment(
        work, enable_bulk_routing=params.enable_bulk_routing)

    # Pre-rollup data integrity validation
    validation_issues: List[str] = []
    ktc_rows = work[work["SystemCategory"] == "KTC"]
    bad_cabtype = ktc_rows[~ktc_rows["CabinetType"].isin(
        ["Helix", "Carousel", "Locker A", "Locker B", "Locker C"])]
    if not bad_cabtype.empty:
        validation_issues.append(
            f"{len(bad_cabtype)} KTC row(s) have an unexpected CabinetType.")
    helix_rows = ktc_rows[ktc_rows["CabinetType"] == "Helix"]
    bad_helix = helix_rows[
        pd.to_numeric(helix_rows["Spiral_capacity"], errors="coerce").fillna(0) <= 0]
    if not bad_helix.empty:
        validation_issues.append(
            f"{len(bad_helix)} Helix row(s) missing Spiral_capacity.")
    carousel_rows = ktc_rows[ktc_rows["CabinetType"] == "Carousel"]
    bad_carousel = carousel_rows[
        (carousel_rows["Monthly_packs"] > 0)
        & (pd.to_numeric(carousel_rows["Carousel_stockpiles"],
                         errors="coerce").fillna(0) <= 0)]
    if not bad_carousel.empty:
        validation_issues.append(
            f"{len(bad_carousel)} Carousel row(s) have 0 stockpiles despite positive consumption.")
    bad_pack = work[pd.to_numeric(work["PackUnits"], errors="coerce").fillna(0) <= 0]
    if not bad_pack.empty:
        validation_issues.append(f"{len(bad_pack)} row(s) have PackUnits <= 0.")
    bad_size = work[~work["SizeCategory"].astype(str).str.upper().isin(SIZE_VALID)]
    if not bad_size.empty:
        validation_issues.append(f"{len(bad_size)} row(s) have invalid SizeCategory.")
    nan_monthly = work[work["Monthly_packs"].isna()]
    if not nan_monthly.empty:
        validation_issues.append(f"{len(nan_monthly)} row(s) have NaN Monthly_packs.")

    # Plan integrity: the invariant/reconciliation layer over the final plan
    integrity = verify_plan(
        work,
        params.base_counts.as_base_info() if params.base_counts is not None else None,
        days_per_month=DAYS_PER_MONTH,
        consumption_period_months=float(params.consumption_period_months),
    )

    # Pack-size audit snapshot: taken here, before bucket planning writes
    # rebalanced routing back into the frame, so it shows what the page showed.
    _sp_hog_threshold = 10.0
    hogs = work[
        (work["PackUnits_Source"].astype(str) == "Default")
        & (pd.to_numeric(work["Monthly_packs"], errors="coerce").fillna(0) > _sp_hog_threshold)
    ].copy()
    if not hogs.empty:
        hogs = hogs.sort_values("Monthly_packs", ascending=False)

    # Classification-preview snapshot: same reasoning, same position.
    preview_cols = [c for c in PREVIEW_COLUMNS if c in work.columns]
    preview = work[preview_cols].head(300).copy()

    # Operational mode (Helix / Carousel) overrides the composition for every
    # vending tool BEFORE buckets are built
    buf_pct = float(params.capacity_buffer_pct)
    n_sp = int(params.n_supply_points)
    if params.op_mode in ("Helix", "Carousel"):
        work = apply_operational_mode(
            work, params.op_mode,
            min_carousel_compartments=int(params.minimum_carousel_allocation),
            carousel_reserve_factor=params.plan_cfg.carousel_reserve_factor,
            helix_overfill_factor=params.plan_cfg.helix_overfill_factor,
        )

    # Restocking (v34.24): decide restockability on the final routing and
    # reserve the buffer compartments; the bucket math below reads them from
    # the frame.
    work, restock_info = run_restock_segment(
        work,
        restock_categories=params.restock_categories,
        op_mode=str(params.op_mode or ""),
    )

    # Fixed configuration (v34.52): the machines exist, so every listing
    # shares them and each supply point is fitted into its own machines.
    if params.op_mode == FIXED_MODE:
        sp_buckets = []
        if n_sp > 1:
            for sp in range(1, n_sp + 1):
                sp_buckets.append((_bucket_label(None, sp), sp,
                                   work[work["SupplyPoint"] == sp]))
        else:
            sp_buckets.append((_bucket_label(None, None), 1, work))
        work, bucket_plans = run_fixed_configuration_segment(
            work, sp_buckets,
            machines=machines_by_sp(params.fixed_machines),
            headroom_pct=float(params.fixed_headroom_pct),
            allow_spill=bool(params.fixed_allow_spill),
            helix_overfill_factor=params.plan_cfg.helix_overfill_factor,
            carousel_reserve_factor=params.plan_cfg.carousel_reserve_factor,
            minimum_carousel_allocation=int(params.minimum_carousel_allocation),
            stock_promotion_months=float(params.fixed_stock_promotion_months),
            helix_threshold=float(params.helix_threshold),
        )
        integrity.checks["restock_buckets"] = check_restock_bucket_consistency(
            work, bucket_plans
        )
        return PlanResult(
            work=work,
            sp_conservation=sp_conservation,
            split_coverage=split_coverage,
            n_pack_default=n_pack_default,
            stdspecial_missing=stdspecial_missing,
            stdspecial_counts=stdspecial_counts,
            reuse_hits_n=reuse_hits_n,
            reuse_misses_n=reuse_misses_n,
            override_stats=override_stats,
            rerouted_flips=rerouted_flips,
            force_system_type=force_system_type,
            force_special_ktc=force_special_ktc,
            routing_override_counts=routing_override_counts,
            vend_stats=vend_stats,
            validation_issues=validation_issues,
            integrity=integrity,
            hogs=hogs,
            preview=preview,
            listings=(),
            bucket_plans=bucket_plans,
            rebalance_audit=[],
            grand=grand_total(bucket_plans),
            restock_info=restock_info,
        )

    # Build the list of buckets to compute
    buckets: List[Tuple[str, pd.DataFrame]] = []
    if params.calc_mode_separated:
        listings_iter = [l for l in [LISTING_TOOLS, LISTING_PPE]
                         if l in set(work["Listing"].astype(str).unique())]
    else:
        listings_iter = ["__ALL__"]
    listings = tuple(l for l in listings_iter if l != "__ALL__")
    for listing_val in listings_iter:
        if listing_val == "__ALL__":
            listing_subset = work
            listing_display = None
        else:
            listing_subset = work[work["Listing"] == listing_val]
            listing_display = listing_val
        if n_sp > 1:
            for sp in range(1, n_sp + 1):
                sp_subset = listing_subset[listing_subset["SupplyPoint"] == sp]
                buckets.append((_bucket_label(listing_display, sp), sp_subset))
        else:
            buckets.append((_bucket_label(listing_display, None), listing_subset))

    # Per-bucket planning with the rebalancer and the carousel cap
    work, bucket_plans, rebalance_audit = run_bucket_planning_segment(
        work, buckets,
        op_mode=params.op_mode,
        enable_rebalancer=params.enable_rebalancer,
        buf_pct=buf_pct,
        minimum_carousel_allocation=int(params.minimum_carousel_allocation),
        underuse_threshold_pct=float(params.underuse_threshold_pct),
        max_carousels_cap=params.max_carousels_cap,
        helix_overfill_factor=params.plan_cfg.helix_overfill_factor,
        carousel_reserve_factor=params.plan_cfg.carousel_reserve_factor,
        carousel_fill_ceiling=params.plan_cfg.carousel_fill_ceiling,
    )

    # Restocking bucket invariants (v34.27): floors and frame/plan
    # conservation, merged into the integrity report built above.
    integrity.checks["restock_buckets"] = check_restock_bucket_consistency(
        work, bucket_plans
    )

    return PlanResult(
        work=work,
        sp_conservation=sp_conservation,
        split_coverage=split_coverage,
        n_pack_default=n_pack_default,
        stdspecial_missing=stdspecial_missing,
        stdspecial_counts=stdspecial_counts,
        reuse_hits_n=reuse_hits_n,
        reuse_misses_n=reuse_misses_n,
        override_stats=override_stats,
        rerouted_flips=rerouted_flips,
        force_system_type=force_system_type,
        force_special_ktc=force_special_ktc,
        routing_override_counts=routing_override_counts,
        vend_stats=vend_stats,
        validation_issues=validation_issues,
        integrity=integrity,
        hogs=hogs,
        preview=preview,
        listings=listings,
        bucket_plans=bucket_plans,
        rebalance_audit=rebalance_audit,
        grand=grand_total(bucket_plans),
        restock_info=restock_info,
    )
