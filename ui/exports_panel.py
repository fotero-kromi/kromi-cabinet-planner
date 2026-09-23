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
from engine.cabinet_math import SPECIAL_KTC_REASON
from engine.deck import DeckStats
from engine.fixed_config import FIXED_MODE, run_meta_rows as fixed_run_meta_rows
from engine.kromi_numbering import augment_for_export
from engine.routing_rules import classify_standard_special
from engine.sizing_factors import SP_MODE_REPLICATE
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

    # Summary sheet: one row per bucket + grand total
    summary_rows = []
    for label, p in bucket_plans:
        summary_rows.append({
            "Bucket": label,
            "KTC items": p["ktc_count"],
            "Kanban items": p["kanban_count"],
            "Helix refs": p["helix_refs"], "Helix spirals (base)": p["total_spirals"], "Helix spirals (buf)": p["total_spirals_buf"],
            "Helix cabs (base)": p["helix_cabs_base"], "Helix cabs (buf)": p["helix_cabs"],
            "Carousel refs": p["carousel_refs"], "Carousel slots (base)": p["car_slots"], "Carousel slots (buf)": p["car_slots_buf"],
            "Carousel cabs (base)": p["car_cabs_base"], "Carousel cabs (buf)": p["car_cabs"],
            "Locker A refs": p["locker_a_refs"], "Locker A cabs (base)": p["cabA_base"], "Locker A cabs (buf)": p["cabA"],
            "Locker B refs": p["locker_b_refs"], "Locker B cabs (base)": p["cabB_base"], "Locker B cabs (buf)": p["cabB"],
            "Locker C refs": p["locker_c_refs"], "Locker C cabs (base)": p["cabC_base"], "Locker C cabs (buf)": p["cabC"],
            "Total cabs (base)": p["total_cabs_base"], "Total cabs (buf)": p["total_cabs"],
        })
    if len(bucket_plans) > 1:
        summary_rows.append({
            "Bucket": "Grand total",
            "KTC items": grand["ktc_count"],
            "Kanban items": grand["kanban_count"],
            "Helix refs": grand["helix_refs"], "Helix spirals (base)": grand["total_spirals"], "Helix spirals (buf)": grand["total_spirals_buf"],
            "Helix cabs (base)": grand["helix_cabs_base"], "Helix cabs (buf)": grand["helix_cabs"],
            "Carousel refs": grand["carousel_refs"], "Carousel slots (base)": grand["car_slots"], "Carousel slots (buf)": grand["car_slots_buf"],
            "Carousel cabs (base)": grand["car_cabs_base"], "Carousel cabs (buf)": grand["car_cabs"],
            "Locker A refs": grand["locker_a_refs"], "Locker A cabs (base)": grand["cabA_base"], "Locker A cabs (buf)": grand["cabA"],
            "Locker B refs": grand["locker_b_refs"], "Locker B cabs (base)": grand["cabB_base"], "Locker B cabs (buf)": grand["cabB"],
            "Locker C refs": grand["locker_c_refs"], "Locker C cabs (base)": grand["cabC_base"], "Locker C cabs (buf)": grand["cabC"],
            "Total cabs (base)": grand["total_cabs_base"], "Total cabs (buf)": grand["total_cabs"],
        })
    df_summary = pd.DataFrame(summary_rows)
    df_summary["Capacity buffer (%)"] = buf_pct

    # Run metadata sheet
    _run_meta_rows = [
        {"Key": "Build",                 "Value": BUILD},
        {"Key": "Timestamp (UTC)",       "Value": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        {"Key": "Model",                 "Value": OPENAI_MODEL},
        {"Key": "Calc mode",             "Value": calc_mode},
        {"Key": "Operational mode",      "Value": operational_mode},
        {"Key": "Max carousels (capped mode)", "Value": (int(max_carousels_cap) if op_mode == "Capped" else "")},
        {"Key": "Supply points",         "Value": n_sp},
        {"Key": "SP mode",               "Value": sp_mode},
        {"Key": "Capacity buffer (%)",   "Value": buf_pct},
        {"Key": "KTC threshold",         "Value": usage_threshold},
        {"Key": "Helix threshold",       "Value": helix_threshold},
        {"Key": "Consumption months",    "Value": consumption_period_months},
        {"Key": "Coverage window (days)","Value": coverage_days},
        {"Key": "Carousel reserve factor","Value": _plan_cfg.carousel_reserve_factor},
        {"Key": "Carousel fill ceiling", "Value": _plan_cfg.carousel_fill_ceiling},
        {"Key": "Min carousel alloc",    "Value": minimum_carousel_allocation},
        {"Key": "Helix overfill factor", "Value": _plan_cfg.helix_overfill_factor},
        {"Key": "Pack-hint extraction",  "Value": bool(enable_pack_hint_extraction)},
        {"Key": "Per-class thresholds", "Value": (", ".join(f"{k}={v:g}" for k, v in sorted(per_class_thresholds.items())) if optional_thresholds_active else "off")},
        {"Key": "Coverage special (days)", "Value": (int(coverage_days_special) if _split_coverage else "n/a")},
        {"Key": "Consolidate underused cabinets", "Value": "on" if enable_rebalancer else "off"},
        {"Key": "Empty-cabinet threshold (%)", "Value": float(underuse_threshold_pct)},
        {"Key": "Force screws/accessories Kanban", "Value": "on" if force_screws_accessories_kanban else "off"},
        {"Key": "Regrind handling (Helix +1 spiral)", "Value": "on" if col_regrind else "off"},
        {"Key": "System type override (Lagersystem)", "Value": "on" if col_systemtyp else "off"},
        {"Key": "Use Description_2", "Value": "yes" if use_description_2 else "no"},
        {"Key": "AI fallback", "Value": "on" if use_ai else "off"},
        {"Key": "Restocking column", "Value": (col_restock or "off")},
        {"Key": "Restockable categories (rule)", "Value": (", ".join(_restock_categories) if _restock_categories else "off")},
        {"Key": "Restock buffer compartments", "Value": int(_restock_slots_total)},
        {"Key": "Bulk routing enabled",  "Value": bool(enable_bulk_routing)},
        {"Key": "Bulk routed rows",      "Value": vend_stats.get("routed_rows", 0)},
        {"Key": "Bulk removed spirals",  "Value": vend_stats.get("removed_spirals", 0)},
        {"Key": "Bulk removed slots",    "Value": vend_stats.get("removed_carousel_slots", 0)},
        {"Key": "Overrides blocked bulk", "Value": vend_stats.get("overridden_bulk_candidates", 0)},
        {"Key": "Program→SP mapping",    "Value": "active" if program_mapping_active else "off"},
        {"Key": "Programmes mapped",     "Value": len(program_to_sp_map) if program_mapping_active else 0},
        {"Key": "Customer",              "Value": effective_customer},
        {"Key": "Site",                  "Value": effective_site},
        {"Key": "Overrides applied",     "Value": ("NO - override database unreadable" if override_store_unavailable else ("yes" if apply_overrides_ui else "no"))},
        {"Key": "Overrides rows touched","Value": override_stats["rows_touched"]},
        {"Key": "Overrides stale",       "Value": len(override_stats["unmatched_overrides"])},
        {"Key": "Overrides invalid",     "Value": len(override_stats["invalid_overrides"])},
        {"Key": "Listings loaded",       "Value": ", ".join(listings_in_data)},
        {"Key": "Tools sheet",           "Value": sheet_tools if sheet_tools else "—"},
        {"Key": "PPE sheet",             "Value": sheet_ppe if sheet_ppe else "—"},
        {"Key": "Rows before preproc",   "Value": base_info["rows_before"]},
        {"Key": "Rows after year filter","Value": base_info["rows_after_year_filter"]},
        {"Key": "Rows after dedup",      "Value": base_info["rows_after_dedup"]},
        {"Key": "AI batches run",        "Value": ai_batches_run},
        {"Key": "AI batches failed",     "Value": ai_batches_failed},
        {"Key": "AI items processed",    "Value": ai_items_run},
        {"Key": "AI missing responses",  "Value": ai_missing_responses},
        {"Key": "Input tokens",          "Value": total_in_tokens},
        {"Key": "Output tokens",         "Value": total_out_tokens},
        {"Key": "Validation issues",     "Value": "; ".join(validation_issues) if validation_issues else "none"},
    ]
    # Special-tools-as-KTC reporting (only when the Standard/Special column is
    # mapped, so a run without the feature keeps the metadata unchanged). Records
    # the toggle state and how many rows were classified Special vs forced,
    # so the toggle's effect is auditable from the file rather than invisible.
    if "StdSpecial" in work.columns and col_stdspecial:
        _special_total = int(
            work["StdSpecial"].map(classify_standard_special).eq("special").sum()
        )
        _special_forced_n = int(
            (work["SystemCategory_Reason"].astype(str) == SPECIAL_KTC_REASON).sum()
        )
        _run_meta_rows += [
            {"Key": "Set special tools as KTC", "Value": "on" if st.session_state.get("ks_special_ktc", False) else "off"},
            {"Key": "Special rows (marked Special)", "Value": _special_total},
            {"Key": "Special forced to KTC", "Value": _special_forced_n},
        ]
    # Fixed configuration (v34.52): the machines, headroom and fit counts.
    if op_mode == FIXED_MODE:
        _run_meta_rows += fixed_run_meta_rows(bucket_plans)
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
    _takeover_shared = bool(sp_mode == SP_MODE_REPLICATE and int(n_sp) > 1
                            and not program_mapping_active)
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
