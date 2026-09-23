"""kromi_app.ui.exports_panel — the Export and Presentation panel (v34.40).

Stage 2 of the structural project: the panel body moved verbatim out of the
page; every value it reads arrives as an explicit keyword parameter, which
is the honest measure of the coupling the page had hidden in closures. The
page keeps a thin fragment shell. The workbook cache wrapper travels inside
render, unchanged; the deck cache lives here at module level.
"""

import importlib.util
import json
import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from app_log import log_exception, log_warning
from engine.build_info import BUILD, build_stamp
from engine.deck import DeckStats
from engine.export_frames import (
    RunMetadataInputs,
    run_metadata_rows,
    summary_frame,
    takeover_shared_stock,
)
from engine.kromi_numbering import augment_for_export
from engine.takeover import (
    STOCK_COL,
    build_takeover_frames,
    build_takeover_workbook,
    takeover_summary,
)
from engine.workbook import build_result_workbook


@st.cache_data(max_entries=4, show_spinner=False)
def _cached_build_summary_deck(stats, logo_path: str) -> bytes:
    """Content-keyed cache around the presentation deck build (v34.29).

    The stats object is a small bundle of scalars, so streamlit's hashing
    is cheap here; a plain rerun serves the cached bytes instead of
    rebuilding the deck on every script pass. The import lives inside so
    the presentation module stays an optional dependency, gated where the
    deck section calls this."""
    from presentation import build_summary_deck

    return build_summary_deck(stats, logo_path=logo_path)


@st.cache_data(max_entries=4, show_spinner=False)
def _cached_takeover(work: pd.DataFrame, ktc_id: str, shared_stock: bool):
    """The takeover-only workbook and its per-supply-point totals (v34.56)."""
    frames = build_takeover_frames(augment_for_export(work, ktc_id),
                                   shared_stock=shared_stock)
    return build_takeover_workbook(frames), takeover_summary(frames)


def _fmt_qty(value) -> str:
    return f"{value:,}".replace(",", ".") if isinstance(value, int) else f"{value:,.2f}"


def _json_key_safe(obj):
    """Deterministic pre-pass for cache-key serialization: stringify every dict
    key (supply-point maps mix integer keys with the '__all__' sentinel, which
    sort_keys cannot order) and recurse into containers."""
    if isinstance(obj, dict):
        return {str(k): _json_key_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_key_safe(v) for v in obj]
    return obj


def render(
    *,
    OPENAI_MODEL,
    _SCRIPT_DIR,
    _plan_cfg,
    _plan_key,
    _restock_categories,
    _restock_slots_total,
    _split_coverage,
    ai_batches_failed,
    ai_batches_run,
    ai_items_run,
    ai_missing_responses,
    base_info,
    bucket_plans,
    buf_pct,
    calc_mode,
    col_regrind,
    col_restock,
    col_stdspecial,
    col_systemtyp,
    coverage_days,
    coverage_days_special,
    effective_customer,
    effective_site,
    enable_pack_hint_extraction,
    enable_rebalancer,
    force_screws_accessories_kanban,
    grand,
    helix_threshold,
    ktc_id_input,
    listings_arg,
    listings_in_data,
    max_carousels_cap,
    minimum_carousel_allocation,
    n_sp,
    n_supply_points,
    op_mode,
    operational_mode,
    optional_thresholds_active,
    override_stats,
    per_class_thresholds,
    program_mapping_active,
    program_to_sp_map,
    sheet_ppe,
    sheet_tools,
    sp_mode,
    total_in_tokens,
    total_out_tokens,
    underuse_threshold_pct,
    usage_threshold,
    use_ai,
    use_description_2,
    validation_issues,
    vend_stats,
    _export_name,
    apply_overrides_ui,
    consumption_period_months,
    df_audit,
    df_bucket_compare,
    dist_cabtype,
    dist_cat_rows,
    dist_cat_vol,
    dist_system,
    enable_bulk_routing,
    multiple_listings,
    presentation_compact_df,
    presentation_detail_df,
    work,
    override_store_unavailable=False,
):
    """Render the Export and Presentation panel; body verbatim from the page."""
    if st.session_state.get("_exports_key") != _plan_key:
        st.subheader("Export")
        st.caption(
            "Downloads build on demand, so plan recomputes stay fast. "
            "The workbook carries every table and chart of the plan."
        )
        if st.button("Prepare downloads", key="btn_prepare_exports", type="primary"):
            st.session_state["_exports_key"] = _plan_key
        else:
            return
    st.subheader("Export")

    # Summary and Run_Metadata sheets (engine/export_frames.py, v34.61).
    df_summary = summary_frame(bucket_plans, grand, buf_pct)
    _run_meta_rows = run_metadata_rows(RunMetadataInputs(
        build=BUILD, timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=OPENAI_MODEL, calc_mode=calc_mode, operational_mode=operational_mode,
        op_mode=op_mode, max_carousels_cap=max_carousels_cap, n_sp=n_sp, sp_mode=sp_mode,
        buf_pct=buf_pct, usage_threshold=usage_threshold, helix_threshold=helix_threshold,
        consumption_period_months=consumption_period_months, coverage_days=coverage_days,
        plan_cfg=_plan_cfg, minimum_carousel_allocation=minimum_carousel_allocation,
        enable_pack_hint_extraction=enable_pack_hint_extraction,
        optional_thresholds_active=optional_thresholds_active,
        per_class_thresholds=per_class_thresholds, split_coverage=_split_coverage,
        coverage_days_special=coverage_days_special, enable_rebalancer=enable_rebalancer,
        underuse_threshold_pct=underuse_threshold_pct,
        force_screws_accessories_kanban=force_screws_accessories_kanban,
        col_regrind=col_regrind, col_systemtyp=col_systemtyp,
        use_description_2=use_description_2, use_ai=use_ai, col_restock=col_restock,
        restock_categories=_restock_categories, restock_slots_total=_restock_slots_total,
        enable_bulk_routing=enable_bulk_routing, vend_stats=vend_stats,
        program_mapping_active=program_mapping_active, program_to_sp_map=program_to_sp_map,
        effective_customer=effective_customer, effective_site=effective_site,
        override_store_unavailable=override_store_unavailable,
        apply_overrides_ui=apply_overrides_ui, override_stats=override_stats,
        listings_in_data=listings_in_data, sheet_tools=sheet_tools, sheet_ppe=sheet_ppe,
        base_info=base_info, ai_batches_run=ai_batches_run,
        ai_batches_failed=ai_batches_failed, ai_items_run=ai_items_run,
        ai_missing_responses=ai_missing_responses, total_in_tokens=total_in_tokens,
        total_out_tokens=total_out_tokens, validation_issues=validation_issues,
        col_stdspecial=col_stdspecial,
        special_ktc=bool(st.session_state.get("ks_special_ktc", False)),
    ), work=work, bucket_plans=bucket_plans)
    df_run_meta = pd.DataFrame(_run_meta_rows)

    # Meaningful, dated filename (CPlanner_<source>_Result_<date>.xlsx).
    out_name = _export_name("Result", "xlsx")



    include_planogram = st.checkbox(
        "Include cabinet planogram sheet in Excel",
        value=True,
        help=(
            "Adds a 'Planogram' sheet that draws each proposed cabinet as a grid, places "
            "every tool in a numbered compartment grouped by family, and colours each by "
            "classification confidence (green = high, orange = low). Collapsible per cabinet."
        ),
    )

    include_technical = st.checkbox(
        "Include technical / diagnostic sheets",
        value=False,
        help=(
            "Off (default): a clean workbook for everyday use — Summary, the per-supply-point "
            "Presentation, the trimmed Result and KTC/Kanban/Helix/Carousel breakdowns, and the "
            "Planogram. On: also adds the full audit Result (every AI/source/confidence column), "
            "Run_Metadata, Audit_Summary, Bucket_Compare, the distribution sheets, and the "
            "overrides audit — useful for debugging and review, noise for normal users."
        ),
    )

    @st.cache_data(max_entries=4, show_spinner=False)
    def _cached_build_result_workbook(
        work: pd.DataFrame, df_summary: pd.DataFrame, df_audit: pd.DataFrame,
        df_bucket_compare: pd.DataFrame, presentation_compact_df: pd.DataFrame,
        presentation_detail_df: pd.DataFrame, dist_cat_rows: pd.DataFrame,
        dist_cat_vol: pd.DataFrame, dist_cabtype: pd.DataFrame,
        dist_system: pd.DataFrame, include_planogram: bool, include_technical: bool,
        ktc_id: str, apply_overrides_ui: bool, enable_bulk_routing: bool,
        multiple_listings: bool, consumption_period_months: float, content_key: str, *,
        _df_run_meta, _bucket_plans, _listings_arg, _listings_in_data,
        _base_info, _vend_stats, _override_stats, _takeover_shared_stock=False,
    ):
        """Content-addressed cache around the result-workbook build.

        Streamlit hashes the frames, the scalars, and ``content_key``; the
        underscore-prefixed composites travel unhashed. A plain rerun is a
        hit and serves the identical workbook. The body lives in
        engine.workbook (v34.39); this wrapper only carries the cache.
        """
        return build_result_workbook(work=work, df_summary=df_summary, df_audit=df_audit, df_bucket_compare=df_bucket_compare, presentation_compact_df=presentation_compact_df, presentation_detail_df=presentation_detail_df, dist_cat_rows=dist_cat_rows, dist_cat_vol=dist_cat_vol, dist_cabtype=dist_cabtype, dist_system=dist_system, include_planogram=include_planogram, include_technical=include_technical, ktc_id=ktc_id, apply_overrides_ui=apply_overrides_ui, enable_bulk_routing=enable_bulk_routing, multiple_listings=multiple_listings, consumption_period_months=consumption_period_months, content_key=content_key, _df_run_meta=_df_run_meta, _bucket_plans=_bucket_plans, _listings_arg=_listings_arg, _listings_in_data=_listings_in_data, _base_info=_base_info, _vend_stats=_vend_stats, _override_stats=_override_stats, _takeover_shared_stock=_takeover_shared_stock)



    _export_ktc_id = str(ktc_id_input or "").strip()
    # Replicate copies share one stock (v34.56); the SP mode and the Program
    # mapping are in the run metadata, so the content key below covers it.
    _takeover_shared = takeover_shared_stock(sp_mode, n_sp,
                                             program_mapping_active=program_mapping_active)
    _export_key = json.dumps(_json_key_safe({
        "run_meta": [r for r in _run_meta_rows if r["Key"] != "Timestamp (UTC)"],
        "bucket_plans": bucket_plans, "override_stats": override_stats,
        "vend_stats": vend_stats, "base_info": base_info,
        "listings_in_data": listings_in_data, "listings_arg": listings_arg,
        "ktc_id": _export_ktc_id, "apply_overrides": bool(apply_overrides_ui),
        "bulk": bool(enable_bulk_routing), "multi": bool(multiple_listings),
        "months": float(consumption_period_months),
    }), sort_keys=True, default=str)

    (_excel_bytes, _export_problems, _fi_passed, _fi_checks,
     _pg_note) = _cached_build_result_workbook(
        work, df_summary, df_audit, df_bucket_compare, presentation_compact_df,
        presentation_detail_df, dist_cat_rows, dist_cat_vol, dist_cabtype,
        dist_system, bool(include_planogram), bool(include_technical),
        _export_ktc_id, bool(apply_overrides_ui), bool(enable_bulk_routing),
        bool(multiple_listings), float(consumption_period_months), _export_key,
        _df_run_meta=df_run_meta, _bucket_plans=bucket_plans,
        _listings_arg=listings_arg, _listings_in_data=listings_in_data,
        _base_info=base_info, _vend_stats=vend_stats, _override_stats=override_stats,
        _takeover_shared_stock=_takeover_shared,
    )
    if _export_problems:
        st.error(
            "Export verification FAILED — the workbook below may be incorrect. "
            "Do not use it until resolved:")
        for _p in _export_problems:
            st.markdown(f"- {_p}")
        log_warning("Export verification failed: " + "; ".join(str(_p) for _p in _export_problems))
    else:
        st.success(
            f"Export verification passed: every row accounted for and "
            f"{_fi_passed}/{_fi_checks} final-state "
            "invariants hold.")
    if _pg_note:
        # Everything the export had to leave out (v34.48): skipped optional
        # sheets and KROMI numbers that could not be generated, with the reason.
        st.warning(_pg_note)
        log_warning(f"Export notes: {_pg_note}")
    # Excel download. Native single button; the workbook now carries every
    # table and chart the retired per-SP PDF used to hold (v34.25).
    st.download_button(
        "⬇ Download Excel (plan workbook)",
        data=_excel_bytes,
        file_name=out_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        key="dl_excel_workbook",
    )
    # Takeover list (v34.56): one sheet per supply point, in the workbook and
    # as its own file for the technicians.
    if STOCK_COL in work.columns:
        _tk_bytes, _tk_summary = _cached_takeover(work, _export_ktc_id, _takeover_shared)
        if _tk_summary:
            st.caption("Takeover sheets (whole packs into the KTC up to the maximum, "
                       "the rest at the HLO): " + " | ".join(
                           f"SP {r['sp']}: {r['articles']} articles, "
                           f"{_fmt_qty(r['ktc'])} pcs im KTC, {_fmt_qty(r['hlo'])} pcs am HLO"
                           for r in _tk_summary))
            st.download_button(
                "⬇ Download takeover list (.xlsx)",
                data=_tk_bytes,
                file_name=_export_name("Takeover", "xlsx"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_takeover_list",
            )

    # ---- KROMI presentation deck (.pptx) ----
    st.divider()
    st.subheader("KROMI presentation")
    st.caption(
        "Generate a KROMI-branded slide deck of this plan — a cover plus a plan-summary "
        "slide carrying the headline figures, in the corporate house style. Drop it into "
        "your full customer presentation, or use it as the starting point."
    )
    try:
        if importlib.util.find_spec("presentation") is None:
            raise ImportError("presentation module not installed")

        _deck_customer = "" if effective_customer == "default" else effective_customer
        _deck_site = "" if effective_site == "default" else effective_site
        _deck_stats = DeckStats(
            customer=_deck_customer,
            site=_deck_site,
            # Local wall-clock by design: the deck footer shows the reader's
            # calendar date (recorded exemption, audit #2 m3).
            date_str=f"{datetime.now().strftime('%d %b %Y')} · {build_stamp()}",
            supply_points=int(n_supply_points),
            total_cabinets=int(grand.get("total_cabs", 0)),
            helix=int(grand.get("helix_cabs", 0)),
            carousel=int(grand.get("car_cabs", 0)),
            lockers=(
                int(grand.get("cabA", 0))
                + int(grand.get("cabB", 0))
                + int(grand.get("cabC", 0))
            ),
            ktc_items=int(grand.get("ktc_count", 0)),
            kanban_items=int(grand.get("kanban_count", 0)),
            total_items=int(grand.get("rows_total", 0)),
        )
        _logo_path = str(_SCRIPT_DIR.parent / "assets" / "kromi_logo_green.png")
        if not os.path.exists(_logo_path):
            _logo_path = ""
        _deck_bytes = _cached_build_summary_deck(_deck_stats, _logo_path)
        _deck_name = _export_name("Presentation", "pptx")
        st.download_button(
            "⬇ Download KROMI presentation (.pptx)",
            data=_deck_bytes,
            file_name=_deck_name,
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            ),
            key="dl_kromi_deck",
        )
        st.caption(
            "Fonts render as MetaOT on machines that have the KROMI corporate font "
            "installed; elsewhere they fall back to a system font."
        )
    except ModuleNotFoundError:
        st.info(
            "Presentation export needs the `python-pptx` package. Install it with "
            "`pip install python-pptx` and restart the app."
        )
    except Exception as _deck_exc:  # never break the page on deck issues
        log_exception("Presentation deck could not be built", _deck_exc)
        st.warning(f"Could not generate the KROMI presentation ({_deck_exc}).")

    # Classifier quality — correction-rate analysis from the overrides library
    st.divider()
