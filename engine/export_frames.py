"""The tables the result workbook carries besides the plan rows (v34.61).

Moved out of the planner page and the exports panel so every front end builds
the Summary, Run_Metadata, Audit_Summary, Bucket_Compare and distribution
sheets the same way. Pure: the caller supplies the timestamp and every
setting; nothing here reads a clock, the environment or a session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from .cabinet_math import SPECIAL_KTC_REASON
from .fixed_config import FIXED_MODE
from .fixed_config import run_meta_rows as fixed_run_meta_rows
from .plan_config import PlanConfig
from .routing_rules import classify_standard_special
from .sizing_factors import SP_MODE_REPLICATE

BucketPlans = Sequence[Tuple[str, Dict[str, Any]]]


def _summary_row(label: str, p: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "Bucket": label,
        "KTC items": p["ktc_count"],
        "Kanban items": p["kanban_count"],
        "Helix refs": p["helix_refs"], "Helix spirals (base)": p["total_spirals"],
        "Helix spirals (buf)": p["total_spirals_buf"],
        "Helix cabs (base)": p["helix_cabs_base"], "Helix cabs (buf)": p["helix_cabs"],
        "Carousel refs": p["carousel_refs"], "Carousel slots (base)": p["car_slots"],
        "Carousel slots (buf)": p["car_slots_buf"],
        "Carousel cabs (base)": p["car_cabs_base"], "Carousel cabs (buf)": p["car_cabs"],
        "Locker A refs": p["locker_a_refs"], "Locker A cabs (base)": p["cabA_base"],
        "Locker A cabs (buf)": p["cabA"],
        "Locker B refs": p["locker_b_refs"], "Locker B cabs (base)": p["cabB_base"],
        "Locker B cabs (buf)": p["cabB"],
        "Locker C refs": p["locker_c_refs"], "Locker C cabs (base)": p["cabC_base"],
        "Locker C cabs (buf)": p["cabC"],
        "Total cabs (base)": p["total_cabs_base"], "Total cabs (buf)": p["total_cabs"],
    }


def summary_frame(bucket_plans: BucketPlans, grand: Mapping[str, Any],
                  buffer_pct: float) -> pd.DataFrame:
    """The Summary sheet: one row per bucket, a grand total when there are several."""
    rows = [_summary_row(label, p) for label, p in bucket_plans]
    if len(bucket_plans) > 1:
        rows.append(_summary_row("Grand total", grand))
    df = pd.DataFrame(rows)
    df["Capacity buffer (%)"] = buffer_pct
    return df


def _compare_row(label: str, p: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "Bucket": label,
        "KTC items": p["ktc_count"],
        "Kanban items": p["kanban_count"],
        "Helix cabs": p["helix_cabs"],
        "Carousel cabs": p["car_cabs"],
        "Locker A cabs": p["cabA"],
        "Locker B cabs": p["cabB"],
        "Locker C cabs": p["cabC"],
        "Total cabs": p["total_cabs"],
    }


def bucket_compare_frame(bucket_plans: BucketPlans, grand: Mapping[str, Any]) -> pd.DataFrame:
    """The Bucket_Compare sheet (and the page's bucket table)."""
    rows = [_compare_row(label, p) for label, p in bucket_plans]
    if len(bucket_plans) > 1:
        rows.append(_compare_row("Grand total", grand))
    return pd.DataFrame(rows)


def audit_frame(work: pd.DataFrame) -> pd.DataFrame:
    """The Audit_Summary sheet: where each classified field came from."""
    def counts(col: str) -> Dict[str, int]:
        vc = work[col].fillna("").astype(str).value_counts()
        return {k: int(v) for k, v in vc.items()}

    rows = []
    for field_name, consulted_col in (
        ("ProductCategory", "ProductCategory_AI_Consulted"),
        ("SizeCategory", "SizeCategory_AI_Consulted"),
        ("PackUnits", "PackUnits_AI_Consulted"),
    ):
        src = counts(f"{field_name}_Source")
        rows.append({
            "Field": field_name,
            "Provided": src.get("Provided", 0),
            "Heuristic": src.get("Heuristic", 0),
            "AI": src.get("AI", 0),
            "Default": src.get("Default", 0),
            "AI_Consulted (total)": int(work[consulted_col].fillna(False).astype(bool).sum()),
            "Total rows": len(work),
        })
    return pd.DataFrame(rows)


def distribution_counts(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """Count and share by Listing x ``group_col``; the share is within each listing."""
    if len(df) == 0:
        return pd.DataFrame(columns=["Listing", group_col, "Count", "Share"])
    g = df.groupby(["Listing", group_col], dropna=False).size().reset_index(name="Count")
    g["Share"] = g.groupby("Listing")["Count"].transform(
        lambda s: s / s.sum() if s.sum() > 0 else 0.0)
    return g


def distribution_volume(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """Monthly packs and share by Listing x ``group_col``."""
    if len(df) == 0:
        return pd.DataFrame(columns=["Listing", group_col, "MonthlyPacks", "Share"])
    g = (df.groupby(["Listing", group_col], dropna=False)["Monthly_packs"].sum()
         .reset_index(name="MonthlyPacks"))
    g["Share"] = g.groupby("Listing")["MonthlyPacks"].transform(
        lambda s: s / s.sum() if s.sum() > 0 else 0.0)
    return g


@dataclass(frozen=True)
class DistributionFrames:
    category_rows: pd.DataFrame
    category_volume: pd.DataFrame
    cabinet_type: pd.DataFrame  # KTC rows only
    system: pd.DataFrame


def distribution_frames(work: pd.DataFrame) -> DistributionFrames:
    """The four Dist_* sheets."""
    return DistributionFrames(
        category_rows=distribution_counts(work, "ProductCategory"),
        category_volume=distribution_volume(work, "ProductCategory"),
        cabinet_type=distribution_counts(work[work["SystemCategory"] == "KTC"], "CabinetType"),
        system=distribution_counts(work, "SystemCategory"),
    )


def listings_in_data(work: pd.DataFrame) -> List[str]:
    return sorted(work["Listing"].astype(str).unique().tolist())


def takeover_shared_stock(sp_mode: str, n_sp: int, *, program_mapping_active: bool) -> bool:
    """Replicated supply points share one stock pool, unless programmes split it."""
    return bool(sp_mode == SP_MODE_REPLICATE and int(n_sp) > 1 and not program_mapping_active)


@dataclass(frozen=True)
class RunMetadataInputs:
    """Everything the Run_Metadata sheet records about a run."""

    build: str
    timestamp_utc: str
    model: str
    calc_mode: str
    operational_mode: str
    op_mode: str
    max_carousels_cap: float
    n_sp: int
    sp_mode: str
    buf_pct: float
    usage_threshold: float
    helix_threshold: float
    consumption_period_months: float
    coverage_days: float
    plan_cfg: PlanConfig
    minimum_carousel_allocation: int
    enable_pack_hint_extraction: bool
    optional_thresholds_active: bool
    per_class_thresholds: Mapping[str, float]
    split_coverage: bool
    coverage_days_special: float
    enable_rebalancer: bool
    underuse_threshold_pct: float
    force_screws_accessories_kanban: bool
    col_regrind: Optional[str]
    col_systemtyp: Optional[str]
    use_description_2: bool
    use_ai: bool
    col_restock: Optional[str]
    restock_categories: Sequence[str]
    restock_slots_total: float
    enable_bulk_routing: bool
    vend_stats: Mapping[str, Any]
    program_mapping_active: bool
    program_to_sp_map: Mapping[str, int]
    effective_customer: str
    effective_site: str
    override_store_unavailable: bool
    apply_overrides_ui: bool
    override_stats: Mapping[str, Any]
    listings_in_data: Sequence[str]
    sheet_tools: Optional[str]
    sheet_ppe: Optional[str]
    base_info: Mapping[str, Any]
    ai_batches_run: int
    ai_batches_failed: int
    ai_items_run: int
    ai_missing_responses: int
    total_in_tokens: int
    total_out_tokens: int
    validation_issues: Sequence[str]
    col_stdspecial: Optional[str]
    special_ktc: bool


def run_metadata_rows(i: RunMetadataInputs, *, work: pd.DataFrame,
                      bucket_plans: BucketPlans) -> List[Dict[str, Any]]:
    """The Run_Metadata sheet as Key / Value rows, in sheet order."""
    cfg = i.plan_cfg
    rows: List[Dict[str, Any]] = [
        {"Key": "Build", "Value": i.build},
        {"Key": "Timestamp (UTC)", "Value": i.timestamp_utc},
        {"Key": "Model", "Value": i.model},
        {"Key": "Calc mode", "Value": i.calc_mode},
        {"Key": "Operational mode", "Value": i.operational_mode},
        {"Key": "Max carousels (capped mode)",
         "Value": (int(i.max_carousels_cap) if i.op_mode == "Capped" else "")},
        {"Key": "Supply points", "Value": i.n_sp},
        {"Key": "SP mode", "Value": i.sp_mode},
        {"Key": "Capacity buffer (%)", "Value": i.buf_pct},
        {"Key": "KTC threshold", "Value": i.usage_threshold},
        {"Key": "Helix threshold", "Value": i.helix_threshold},
        {"Key": "Consumption months", "Value": i.consumption_period_months},
        {"Key": "Coverage window (days)", "Value": i.coverage_days},
        {"Key": "Carousel reserve factor", "Value": cfg.carousel_reserve_factor},
        {"Key": "Carousel fill ceiling", "Value": cfg.carousel_fill_ceiling},
        {"Key": "Min carousel alloc", "Value": i.minimum_carousel_allocation},
        {"Key": "Helix overfill factor", "Value": cfg.helix_overfill_factor},
        {"Key": "Pack-hint extraction", "Value": bool(i.enable_pack_hint_extraction)},
        {"Key": "Per-class thresholds",
         "Value": (", ".join(f"{k}={v:g}" for k, v in sorted(i.per_class_thresholds.items()))
                   if i.optional_thresholds_active else "off")},
        {"Key": "Coverage special (days)",
         "Value": (int(i.coverage_days_special) if i.split_coverage else "n/a")},
        {"Key": "Consolidate underused cabinets", "Value": "on" if i.enable_rebalancer else "off"},
        {"Key": "Empty-cabinet threshold (%)", "Value": float(i.underuse_threshold_pct)},
        {"Key": "Force screws/accessories Kanban",
         "Value": "on" if i.force_screws_accessories_kanban else "off"},
        {"Key": "Regrind handling (Helix +1 spiral)", "Value": "on" if i.col_regrind else "off"},
        {"Key": "System type override (Lagersystem)",
         "Value": "on" if i.col_systemtyp else "off"},
        {"Key": "Use Description_2", "Value": "yes" if i.use_description_2 else "no"},
        {"Key": "AI fallback", "Value": "on" if i.use_ai else "off"},
        {"Key": "Restocking column", "Value": (i.col_restock or "off")},
        {"Key": "Restockable categories (rule)",
         "Value": (", ".join(i.restock_categories) if i.restock_categories else "off")},
        {"Key": "Restock buffer compartments", "Value": int(i.restock_slots_total)},
        {"Key": "Bulk routing enabled", "Value": bool(i.enable_bulk_routing)},
        {"Key": "Bulk routed rows", "Value": i.vend_stats.get("routed_rows", 0)},
        {"Key": "Bulk removed spirals", "Value": i.vend_stats.get("removed_spirals", 0)},
        {"Key": "Bulk removed slots", "Value": i.vend_stats.get("removed_carousel_slots", 0)},
        {"Key": "Overrides blocked bulk",
         "Value": i.vend_stats.get("overridden_bulk_candidates", 0)},
        {"Key": "Program→SP mapping", "Value": "active" if i.program_mapping_active else "off"},
        {"Key": "Programmes mapped",
         "Value": len(i.program_to_sp_map) if i.program_mapping_active else 0},
        {"Key": "Customer", "Value": i.effective_customer},
        {"Key": "Site", "Value": i.effective_site},
        {"Key": "Overrides applied",
         "Value": ("NO - override database unreadable" if i.override_store_unavailable
                   else ("yes" if i.apply_overrides_ui else "no"))},
        {"Key": "Overrides rows touched", "Value": i.override_stats["rows_touched"]},
        {"Key": "Overrides stale", "Value": len(i.override_stats["unmatched_overrides"])},
        {"Key": "Overrides invalid", "Value": len(i.override_stats["invalid_overrides"])},
        {"Key": "Listings loaded", "Value": ", ".join(i.listings_in_data)},
        {"Key": "Tools sheet", "Value": i.sheet_tools if i.sheet_tools else "\u2014"},
        {"Key": "PPE sheet", "Value": i.sheet_ppe if i.sheet_ppe else "\u2014"},
        {"Key": "Rows before preproc", "Value": i.base_info["rows_before"]},
        {"Key": "Rows after year filter", "Value": i.base_info["rows_after_year_filter"]},
        {"Key": "Rows after dedup", "Value": i.base_info["rows_after_dedup"]},
        {"Key": "AI batches run", "Value": i.ai_batches_run},
        {"Key": "AI batches failed", "Value": i.ai_batches_failed},
        {"Key": "AI items processed", "Value": i.ai_items_run},
        {"Key": "AI missing responses", "Value": i.ai_missing_responses},
        {"Key": "Input tokens", "Value": i.total_in_tokens},
        {"Key": "Output tokens", "Value": i.total_out_tokens},
        {"Key": "Validation issues",
         "Value": "; ".join(i.validation_issues) if i.validation_issues else "none"},
    ]
    # Special tools as KTC: only when the Standard/Special column is mapped, so
    # a run without the feature keeps the metadata unchanged.
    if "StdSpecial" in work.columns and i.col_stdspecial:
        special_total = int(work["StdSpecial"].map(classify_standard_special).eq("special").sum())
        forced = int((work["SystemCategory_Reason"].astype(str) == SPECIAL_KTC_REASON).sum())
        rows += [
            {"Key": "Set special tools as KTC", "Value": "on" if i.special_ktc else "off"},
            {"Key": "Special rows (marked Special)", "Value": special_total},
            {"Key": "Special forced to KTC", "Value": forced},
        ]
    # Fixed configuration (v34.52): the machines, headroom and fit counts.
    if i.op_mode == FIXED_MODE:
        rows += fixed_run_meta_rows(bucket_plans)
    return rows
