"""The result workbook of a finished run, built by the engine's workbook builder
from the engine's export tables, in the order the Streamlit app builds them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from engine.build_info import BUILD
from engine.distribution import build_per_sp_summary
from engine.export_frames import (
    RunMetadataInputs,
    audit_frame,
    bucket_compare_frame,
    distribution_frames,
    listings_in_data,
    run_metadata_rows,
    summary_frame,
    takeover_shared_stock,
)
from engine.planning_defaults import CALC_MODE_LABELS, CALC_SEPARATED, OP_MODE_LABELS
from engine.run_settings import plan_config, restock_slots_total
from engine.tool_list import apply_export_display_columns
from engine.workbook import build_result_workbook

from ..settings import RunRequest
from .planning import PlanOutcome

#: The Run_Metadata "Model" row: this version never calls an AI model.
NO_AI_MODEL = "not used"


@dataclass
class ResultWorkbook:
    data: bytes
    problems: list[str]  # export verification failures (the workbook must not be used)
    checks_passed: int
    checks_total: int
    notes: str  # what the export had to leave out, with the reason


def result_workbook(outcome: PlanOutcome, request: RunRequest, *,
                    timestamp: datetime) -> ResultWorkbook:
    """The .xlsx for ``outcome``; ``timestamp`` goes into Run_Metadata (UTC)."""
    r = outcome.result
    s = outcome.settings
    buf_pct = float(s.capacity_buffer_pct)
    listings_arg = list(r.listings) if s.calc_mode == CALC_SEPARATED else None
    program_map = outcome.program_to_sp if outcome.program_mapping_active else {}

    # Tables built from the planner's frame (the page builds these before it adds
    # the display columns).
    plan_work = r.work
    df_bucket_compare = bucket_compare_frame(r.bucket_plans, r.grand)
    compact, detail = build_per_sp_summary(
        work=plan_work, bucket_plans=r.bucket_plans, program_to_sp_map=program_map,
        buffer_pct=buf_pct, listings=listings_arg)
    df_audit = audit_frame(plan_work)
    dist = distribution_frames(plan_work)
    listings = listings_in_data(plan_work)

    # The exported frame carries the display columns; the planner's stays untouched.
    work = plan_work.copy()
    apply_export_display_columns(work)

    df_summary = summary_frame(r.bucket_plans, r.grand, buf_pct)
    meta_rows = run_metadata_rows(RunMetadataInputs(
        build=BUILD, timestamp_utc=timestamp.isoformat(timespec="seconds"),
        model=NO_AI_MODEL, calc_mode=CALC_MODE_LABELS[s.calc_mode],
        operational_mode=OP_MODE_LABELS[s.op_mode], op_mode=s.op_mode,
        max_carousels_cap=s.max_carousels, n_sp=int(s.n_supply_points), sp_mode=s.sp_mode,
        buf_pct=buf_pct, usage_threshold=s.ktc_threshold, helix_threshold=s.helix_threshold,
        consumption_period_months=s.consumption_months, coverage_days=s.coverage_days,
        plan_cfg=plan_config(s), minimum_carousel_allocation=s.min_carousel_allocation,
        enable_pack_hint_extraction=s.pack_hint_extraction,
        optional_thresholds_active=s.optional_thresholds_active,
        per_class_thresholds=dict(s.per_class_thresholds), split_coverage=r.split_coverage,
        coverage_days_special=s.coverage_days_special, enable_rebalancer=s.enable_rebalancer,
        underuse_threshold_pct=s.underuse_threshold_pct,
        force_screws_accessories_kanban=s.force_screws_kanban,
        col_regrind=outcome.mapping.regrind, col_systemtyp=outcome.mapping.system_type,
        use_description_2=s.use_description_2, use_ai=False,
        col_restock=outcome.mapping.restocking, restock_categories=s.restock_categories,
        restock_slots_total=restock_slots_total(r.restock_info),
        enable_bulk_routing=s.bulk_routing, vend_stats=r.vend_stats,
        program_mapping_active=outcome.program_mapping_active, program_to_sp_map=program_map,
        effective_customer=outcome.customer, effective_site=outcome.site,
        override_store_unavailable=False, apply_overrides_ui=request.scope.apply_overrides,
        override_stats=r.override_stats, listings_in_data=listings,
        sheet_tools=request.sheet, sheet_ppe=None, base_info=outcome.base_info,
        ai_batches_run=0, ai_batches_failed=0, ai_items_run=0, ai_missing_responses=0,
        total_in_tokens=0, total_out_tokens=0, validation_issues=r.validation_issues,
        col_stdspecial=outcome.mapping.std_special, special_ktc=s.special_ktc,
    ), work=work, bucket_plans=r.bucket_plans)

    data, problems, passed, total, notes = build_result_workbook(
        work=work, df_summary=df_summary, df_audit=df_audit,
        df_bucket_compare=df_bucket_compare, presentation_compact_df=compact,
        presentation_detail_df=detail, dist_cat_rows=dist.category_rows,
        dist_cat_vol=dist.category_volume, dist_cabtype=dist.cabinet_type,
        dist_system=dist.system, include_planogram=request.export.include_planogram,
        include_technical=request.export.include_technical,
        ktc_id=str(request.scope.ktc_id or "").strip(),
        apply_overrides_ui=request.scope.apply_overrides,
        enable_bulk_routing=bool(s.bulk_routing), multiple_listings=len(listings) > 1,
        consumption_period_months=float(s.consumption_months), content_key="",
        _df_run_meta=pd.DataFrame(meta_rows), _bucket_plans=r.bucket_plans,
        _listings_arg=listings_arg, _listings_in_data=listings, _base_info=outcome.base_info,
        _vend_stats=r.vend_stats, _override_stats=r.override_stats,
        _takeover_shared_stock=takeover_shared_stock(
            s.sp_mode, s.n_supply_points, program_mapping_active=outcome.program_mapping_active),
    )
    return ResultWorkbook(data=data, problems=list(problems), checks_passed=int(passed),
                          checks_total=int(total), notes=str(notes or ""))
