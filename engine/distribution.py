"""kromi_app.engine.distribution — per-supply-point summary and distribution helpers.

Pure functions; no streamlit/UI dependencies. Build the data structures that
populate the Per-SP drilldown on screen, the per-SP PDF pages, and the
Distribution Excel sheets.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .constants import (
    CAROUSEL_SLOTS_PER_CAB,
    HELIX_SPIRALS_PER_CAB,
    LOCKER_A_CAP,
    LOCKER_B_CAP,
    LOCKER_C_CAP,
    SLIDE_BUCKET_ORDER,
    SLIDE_DISTRIBUTION_BUCKETS,
    TOOLCLASS_TO_BUCKET,
)


def build_per_sp_summary(
    work: pd.DataFrame,
    bucket_plans: list[tuple[str, dict[str, Any]]],
    program_to_sp_map: dict[str, int],
    buffer_pct: float,
    listings: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (compact_df, detail_df) for the per-SP presentation summary.

    When ``listings`` is provided (Separated Tools+PPE mode), the function
    emits one row per listing instead of grouping by SupplyPoint. Each
    listing's cabinet counts are looked up from ``bucket_plans`` by the
    listing name; the row counts and consumption sums are computed by
    filtering ``work`` on its ``Listing`` column. No Grand Total row is
    emitted in this mode. A listing with zero KTC items still gets a row
    with cabinet counts at zero and its Kanban count preserved on the
    detail df.

    When ``listings`` is None (Combined mode, the dominant case), the
    function behaves exactly as before: groups by SupplyPoint, labels rows
    "All" or "SP N", and appends a Grand Total row when present in
    bucket_plans.
    """
    plans_by_label = {lbl: plan for lbl, plan in bucket_plans}

    # ---- Separated mode: one row per listing -----------------------------
    if listings:
        compact_rows: list[dict[str, Any]] = []
        detail_rows: list[dict[str, Any]] = []
        for listing in listings:
            if "Listing" in work.columns:
                listing_work = work[work["Listing"].astype(str) == listing]
            else:
                listing_work = work.iloc[0:0]  # empty
            plan = plans_by_label.get(listing, {})

            helix_cabs = int(plan.get("helix_cabs", 0))
            carousel_cabs = int(plan.get("car_cabs", 0))
            locker_a = int(plan.get("cabA", 0))
            locker_b = int(plan.get("cabB", 0))
            locker_c = int(plan.get("cabC", 0))
            total_cabs = int(plan.get(
                "total_cabs", helix_cabs + carousel_cabs + locker_a + locker_b + locker_c
            ))
            ktc_items = int(plan.get("ktc_count", 0))
            kanban_items = int(plan.get("kanban_count", 0))

            annual = int(round(float(
                pd.to_numeric(listing_work.get("Consumption_pcs", 0), errors="coerce")
                .fillna(0).sum()
            )))
            monthly = int(round(float(
                pd.to_numeric(listing_work.get("Monthly_pcs", 0), errors="coerce")
                .fillna(0).sum()
            )))

            base_total = int(plan.get("total_cabs_base", total_cabs))
            buffer_headroom = max(0, total_cabs - base_total)

            compact_rows.append({
                "Supply Point": listing,
                "Rows": len(listing_work),
                "Annual consumption": annual,
                "# programmes": 0,
                "Programmes (first 5)": "—",
                "Helix": helix_cabs,
                "Carousel": carousel_cabs,
                "Locker A": locker_a,
                "Locker B": locker_b,
                "Locker C": locker_c,
                "Total cabinets": total_cabs,
            })
            detail_rows.append({
                "Supply Point": listing,
                "KTC items": ktc_items,
                "Kanban items": kanban_items,
                "Annual pcs": annual,
                "Monthly pcs": monthly,
                "Cabinets (base)": base_total,
                "Cabinets (buffered)": total_cabs,
                "Buffer headroom (cabinets)": buffer_headroom,
            })
        return pd.DataFrame(compact_rows), pd.DataFrame(detail_rows)

    # ---- Combined mode: original SupplyPoint-grouped path (unchanged) ----
    # Build a SP -> programmes list mapping from the program_to_sp_map
    sp_progs: dict[int, list[str]] = {}
    if program_to_sp_map:
        for prog, sp in program_to_sp_map.items():
            sp_progs.setdefault(int(sp), []).append(prog if prog else "(blank)")

    # Index bucket_plans by label for easy lookup
    plans_by_label = {lbl: plan for lbl, plan in bucket_plans}

    # Figure out per-SP consumption/row counts directly from work
    if "SupplyPoint" in work.columns:
        by_sp = (
            work.groupby("SupplyPoint", dropna=False)
            .agg(
                rows=("Code", "count"),
                annual_pcs=("Consumption_pcs", "sum"),
                monthly_pcs=("Monthly_pcs", "sum"),
            )
            .reset_index()
        )
    else:
        # Single-bucket fallback
        by_sp = pd.DataFrame(
            [
                {
                    "SupplyPoint": 1,
                    "rows": len(work),
                    "annual_pcs": float(
                        pd.to_numeric(work.get("Consumption_pcs", 0), errors="coerce")
                        .fillna(0)
                        .sum()
                    ),
                    "monthly_pcs": float(
                        pd.to_numeric(work.get("Monthly_pcs", 0), errors="coerce").fillna(0).sum()
                    ),
                }
            ]
        )

    compact_rows = []
    detail_rows = []

    for _, srow in by_sp.iterrows():
        sp_num = int(srow["SupplyPoint"]) if pd.notna(srow["SupplyPoint"]) else 1
        label = f"SP {sp_num}" if len(by_sp) > 1 else "All"

        progs = sp_progs.get(sp_num, [])
        progs_sorted = sorted(progs)
        progs_display = ", ".join(progs_sorted[:5]) + (
            f" (+{len(progs_sorted) - 5} more)" if len(progs_sorted) > 5 else ""
        )

        plan = plans_by_label.get(label, {})
        # Cabinet counts — use buffered values (what actually goes on the floor)
        # Plan dict field names: helix_cabs, car_cabs, cabA, cabB, cabC
        helix_cabs = int(plan.get("helix_cabs", 0))
        carousel_cabs = int(plan.get("car_cabs", 0))
        locker_a = int(plan.get("cabA", 0))
        locker_b = int(plan.get("cabB", 0))
        locker_c = int(plan.get("cabC", 0))
        total_cabs = int(
            plan.get("total_cabs", helix_cabs + carousel_cabs + locker_a + locker_b + locker_c)
        )

        ktc_items = int(plan.get("ktc_count", 0))
        kanban_items = int(plan.get("kanban_count", 0))

        annual = int(round(float(srow["annual_pcs"])))
        monthly = int(round(float(srow["monthly_pcs"])))

        # Base (pre-buffer) cabinets — when a row benefits from buffer, this
        # is smaller than the buffered total. Headroom = buffered - base.
        base_total = int(plan.get("total_cabs_base", total_cabs))
        buffer_headroom = max(0, total_cabs - base_total)

        compact_rows.append(
            {
                "Supply Point": label,
                "Rows": int(srow["rows"]),
                "Annual consumption": annual,
                "# programmes": len(progs_sorted),
                "Programmes (first 5)": progs_display,
                "Helix": helix_cabs,
                "Carousel": carousel_cabs,
                "Locker A": locker_a,
                "Locker B": locker_b,
                "Locker C": locker_c,
                "Total cabinets": total_cabs,
            }
        )
        detail_rows.append(
            {
                "Supply Point": label,
                "KTC items": ktc_items,
                "Kanban items": kanban_items,
                "Annual pcs": annual,
                "Monthly pcs": monthly,
                "Cabinets (base)": base_total,
                "Cabinets (buffered)": total_cabs,
                "Buffer headroom (cabinets)": buffer_headroom,
            }
        )

    # Grand-total row (from bucket_plans "Grand total" if present)
    grand = plans_by_label.get("Grand total", {})
    if grand:
        total_cabs_g = int(grand.get("total_cabs", 0))
        base_total_g = int(grand.get("total_cabs_base", total_cabs_g))
        compact_rows.append(
            {
                "Supply Point": "Grand total",
                "Rows": int(by_sp["rows"].sum()),
                "Annual consumption": int(round(float(by_sp["annual_pcs"].sum()))),
                "# programmes": sum(len(v) for v in sp_progs.values()),
                "Programmes (first 5)": "—",
                "Helix": int(grand.get("helix_cabs", 0)),
                "Carousel": int(grand.get("car_cabs", 0)),
                "Locker A": int(grand.get("cabA", 0)),
                "Locker B": int(grand.get("cabB", 0)),
                "Locker C": int(grand.get("cabC", 0)),
                "Total cabinets": total_cabs_g,
            }
        )
        detail_rows.append(
            {
                "Supply Point": "Grand total",
                "KTC items": int(grand.get("ktc_count", 0)),
                "Kanban items": int(grand.get("kanban_count", 0)),
                "Annual pcs": int(round(float(by_sp["annual_pcs"].sum()))),
                "Monthly pcs": int(round(float(by_sp["monthly_pcs"].sum()))),
                "Cabinets (base)": base_total_g,
                "Cabinets (buffered)": total_cabs_g,
                "Buffer headroom (cabinets)": max(0, total_cabs_g - base_total_g),
            }
        )

    return pd.DataFrame(compact_rows), pd.DataFrame(detail_rows)


def _slide_bucket_for_category(cat: str) -> str:
    """Map a classifier category (inserts/drills/mills/...) to one of the
    4 slide buckets. Case-insensitive, unknown values -> Others."""
    c = str(cat or "").strip().lower()
    return SLIDE_DISTRIBUTION_BUCKETS.get(c, "Others")


def build_per_sp_distribution(
    work: pd.DataFrame,
    listings: list[str] | None = None,
) -> dict[Any, dict[str, int]]:
    """Return {key: {bucket_name: count}} for the per-SP pie charts.

    Default behaviour (Combined mode): keys are SupplyPoint values, plus
    a synthetic ``'__all__'`` key for the grand total.

    When ``listings`` is provided (Separated Tools+PPE mode), keys are
    the listing names instead of SupplyPoint values; each listing's
    distribution is computed by filtering ``work`` on its ``Listing``
    column. The ``'__all__'`` aggregate is still emitted.
    """
    out: dict[Any, dict[str, int]] = {}

    if "SystemCategory" in work.columns:
        ktc_only = work[work["SystemCategory"] == "KTC"].copy()
    else:
        ktc_only = work.copy()

    if len(ktc_only) == 0:
        return out

    ktc_only["_bucket"] = ktc_only["ProductCategory"].apply(_slide_bucket_for_category)

    if listings and "Listing" in ktc_only.columns:
        # Per-listing mode (Separated Tools+PPE)
        for listing in listings:
            grp = ktc_only[ktc_only["Listing"].astype(str) == listing]
            out[listing] = {b: 0 for b in SLIDE_BUCKET_ORDER}
            for b, n in grp["_bucket"].value_counts().items():
                out[listing][b] = int(n)
    elif "SupplyPoint" in ktc_only.columns:
        for sp_val, grp in ktc_only.groupby("SupplyPoint"):
            try:
                sp_key = int(sp_val)
            except Exception:
                sp_key = sp_val
            out[sp_key] = {b: 0 for b in SLIDE_BUCKET_ORDER}
            for b, n in grp["_bucket"].value_counts().items():
                out[sp_key][b] = int(n)

    # Always add grand total
    out["__all__"] = {b: 0 for b in SLIDE_BUCKET_ORDER}
    for b, n in ktc_only["_bucket"].value_counts().items():
        out["__all__"][b] = int(n)

    return out


def build_per_sp_subclass_breakdown(
    work: pd.DataFrame,
    listings: list[str] | None = None,
) -> dict[Any, dict[str, dict[str, int]]]:
    """Return {key: {bucket: {tool_class: count}}} mirroring the shape of
    :func:`build_per_sp_distribution`.

    Default behaviour (Combined mode): keys are SupplyPoint values, plus
    the synthetic ``'__all__'`` aggregate.

    When ``listings`` is provided (Separated Tools+PPE mode), keys are
    the listing names; each listing's subclass breakdown is computed by
    filtering ``work`` on its ``Listing`` column.

    Rows without a ToolClass land in the bucket they would have landed
    in based on ProductCategory, with a synthetic '(unclassified)'
    tool_class label. Zero-count subclasses are omitted from the output.
    """
    out: dict[Any, dict[str, dict[str, int]]] = {}

    if "SystemCategory" in work.columns:
        ktc_only = work[work["SystemCategory"] == "KTC"].copy()
    else:
        ktc_only = work.copy()

    if len(ktc_only) == 0 or "ToolClass" not in ktc_only.columns:
        return out

    ktc_only["_bucket"] = ktc_only["ProductCategory"].apply(_slide_bucket_for_category)

    def _bucket_with_tc(row) -> tuple[str, str]:
        tc = str(row.get("ToolClass") or "").strip()
        if tc and tc in TOOLCLASS_TO_BUCKET:
            return TOOLCLASS_TO_BUCKET[tc], tc
        # Empty ToolClass — fall back to the primary bucket from ProductCategory
        return row["_bucket"], "(unclassified)"

    pairs = ktc_only.apply(_bucket_with_tc, axis=1)
    ktc_only["_bucket_final"] = [p[0] for p in pairs]
    ktc_only["_tc_final"] = [p[1] for p in pairs]

    def _summarize(df: pd.DataFrame) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {b: {} for b in SLIDE_BUCKET_ORDER}
        for (bucket, tc), n in df.groupby(["_bucket_final", "_tc_final"]).size().items():
            if bucket not in result:
                result[bucket] = {}
            result[bucket][str(tc)] = int(n)
        # Drop empty buckets to keep the output tidy
        return {k: v for k, v in result.items() if v}

    if listings and "Listing" in ktc_only.columns:
        # Per-listing mode (Separated Tools+PPE)
        for listing in listings:
            grp = ktc_only[ktc_only["Listing"].astype(str) == listing]
            out[listing] = _summarize(grp)
    elif "SupplyPoint" in ktc_only.columns:
        for sp_val, grp in ktc_only.groupby("SupplyPoint"):
            try:
                sp_key = int(sp_val)
            except Exception:
                sp_key = sp_val
            out[sp_key] = _summarize(grp)

    out["__all__"] = _summarize(ktc_only)
    return out


def build_per_sp_cabinet_occupation(
    plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """For a single supply-point plan dict, return a list of per-cabinet occupation records: [{cabinet, type, capacity, used, occupation_pct}, ."""
    records: list[dict[str, Any]] = []
    if not plan:
        return records

    cab_idx = 0  # Numbering across all cabinets in this SP

    # Helix
    helix_cabs = int(plan.get("helix_cabs", 0))
    total_spirals_buf = float(plan.get("total_spirals_buf", 0))
    if helix_cabs > 0:
        capacity_per_cab = HELIX_SPIRALS_PER_CAB
        even_used = total_spirals_buf / helix_cabs
        occ = (even_used / capacity_per_cab) * 100.0 if capacity_per_cab > 0 else 0.0
        for _i in range(helix_cabs):
            cab_idx += 1
            records.append(
                {
                    "cabinet_no": cab_idx,
                    "cabinet_type": "Helix",
                    "capacity": capacity_per_cab,
                    "capacity_unit": "spirals",
                    "used": round(even_used, 1),
                    "occupation_pct": round(occ, 1),
                }
            )

    # Carousel
    car_cabs = int(plan.get("car_cabs", 0))
    total_slots_buf = float(plan.get("car_slots_buf", 0))
    if car_cabs > 0:
        capacity_per_cab = CAROUSEL_SLOTS_PER_CAB
        even_used = total_slots_buf / car_cabs
        occ = (even_used / capacity_per_cab) * 100.0 if capacity_per_cab > 0 else 0.0
        for _i in range(car_cabs):
            cab_idx += 1
            records.append(
                {
                    "cabinet_no": cab_idx,
                    "cabinet_type": "Carousel",
                    "capacity": capacity_per_cab,
                    "capacity_unit": "slots",
                    "used": round(even_used, 1),
                    "occupation_pct": round(occ, 1),
                }
            )

    # Lockers A/B/C
    for locker_type, n_cabs_key, count_buf_key, cap_const in [
        ("Locker A", "cabA", "countA_buf", LOCKER_A_CAP),
        ("Locker B", "cabB", "countB_buf", LOCKER_B_CAP),
        ("Locker C", "cabC", "countC_buf", LOCKER_C_CAP),
    ]:
        n = int(plan.get(n_cabs_key, 0))
        used_total = float(plan.get(count_buf_key, 0))
        if n > 0:
            even_used = used_total / n
            occ = (even_used / cap_const) * 100.0 if cap_const > 0 else 0.0
            for _i in range(n):
                cab_idx += 1
                records.append(
                    {
                        "cabinet_no": cab_idx,
                        "cabinet_type": locker_type,
                        "capacity": cap_const,
                        "capacity_unit": "items",
                        "used": round(even_used, 1),
                        "occupation_pct": round(occ, 1),
                    }
                )

    return records
