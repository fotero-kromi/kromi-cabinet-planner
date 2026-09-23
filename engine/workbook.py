"""kromi_app.engine.workbook — the result-workbook builder (v34.39).

Extracted verbatim from the page as the first stage of the structural
project: the 374-line builder body plus its two planogram helpers, pure and
Streamlit-free, so the page keeps only a thin cached wrapper. The
parameters, including the underscore-prefixed composites, are unchanged so
the wrapper's cache-key semantics are identical.
"""

from io import BytesIO
from typing import Any, Dict, List

import pandas as pd

from .classification_tables import SLIDE_BUCKET_ORDER
from .distribution import (
    build_per_sp_cabinet_occupation,
    build_per_sp_distribution,
    build_per_sp_subclass_breakdown,
)
from .export_shaping import (
    build_pie_series,
    build_sp_kpi_frame,
    build_sp_subclass_frame,
    user_view as _user_view,
)
from .invariants import (
    check_export_partition,
    check_kromi_uniqueness,
    reconcile_export_frames,
    verify_plan,
)
from .export_safety import neutralize_formula_cells
from .fixed_config import STATUS_NOT_PLACED, capacity_rows
from .kromi_numbering import (
    augment_for_export,
    build_article_setup,
    numbering_omission_reason,
)
from .layout import (
    GRID_DIMS,
    RESTOCK_FILL_HEX,
    LayoutItem,
    allocate_plan,
    confidence_fill_hex,
    fill_hex_for_cell,
    restock_layout_items,
)
from .sizing_factors import DAYS_PER_MONTH
from .takeover import build_takeover_frames, write_takeover_sheets


def _build_layout_items(work_df):
    """Turn the planned KTC rows into LayoutItems for the planogram allocator.

    Skips non-cabinet rows (Kanban/Bulk). Compartment count = spirals for Helix,
    stockpiles for Carousel, 1 for lockers. Confidence carries the product-category
    confidence for colouring.
    """
    items = []
    for _, row in work_df.iterrows():
        ctype = str(row.get("CabinetType", "") or "").strip()
        if ctype not in GRID_DIMS:
            continue
        if row.get("Placement_Status") == STATUS_NOT_PLACED:
            continue  # fixed configuration (v34.52): not in a machine
        if ctype == "Helix":
            comp = pd.to_numeric(row.get("Spirals_needed", 1), errors="coerce")
        elif ctype == "Carousel":
            comp = pd.to_numeric(row.get("Carousel_stockpiles", 1), errors="coerce")
        else:
            comp = 1
        comp = int(comp) if pd.notna(comp) else 1
        items.append(
            LayoutItem(
                identifier=str(row.get("Code", "") or "").strip(),
                cabinet_type=ctype,
                compartments=max(1, comp),
                category=str(row.get("ProductCategory", "") or "").strip(),
                confidence=str(row.get("ProductCategory_Confidence", "") or "").strip(),
            )
        )
    # Restock buffers (v34.26): one blue one-compartment cell per reserved
    # slot, placed after the regular items of the target cabinet type.
    items.extend(restock_layout_items(work_df))
    return items


def _render_planogram_sheet(workbook, plan):
    """Render a LayoutPlan into one collapsible 'Planogram' sheet on `workbook`."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    if not plan.cabinets:
        return

    ws = workbook.create_sheet("Planogram")
    ws.sheet_properties.outlinePr.summaryBelow = False
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    title_font = Font(name="Arial", bold=True, size=11)
    small_font = Font(name="Arial", size=8)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    r = 1
    ws.cell(row=r, column=1, value="Confidence:").font = title_font
    for i, (key, lab) in enumerate(
        [("high", "High"), ("medium", "Medium"), ("low", "Low"), ("unknown", "Unknown")]
    ):
        c = ws.cell(row=r, column=2 + i, value=lab)
        c.fill = PatternFill("solid", fgColor=confidence_fill_hex(key))
        c.font = small_font
        c.alignment = center
    c = ws.cell(row=r, column=7, value="Restock buffer")
    c.fill = PatternFill("solid", fgColor=RESTOCK_FILL_HEX)
    c.font = small_font
    c.alignment = center
    r += 2

    max_cabs = 100  # safety cap for pathological plans
    for cab in plan.cabinets[:max_cabs]:
        hdr = ws.cell(
            row=r,
            column=1,
            value=(
                f"{cab.cabinet_type} — cabinet {cab.cabinet_index} — "
                f"used {cab.used}/{cab.capacity} ({cab.occupation * 100:.0f}%)"
            ),
        )
        hdr.font = title_font
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=min(cab.cols, 30))
        r += 1
        for rr in range(cab.rows):
            for cc in range(cab.cols):
                comp = cab.compartments[rr * cab.cols + cc]
                cell = ws.cell(row=r, column=cc + 1)
                if comp.item_id:
                    cell.value = (
                        f"{comp.label}\n{comp.item_id}"
                        if comp.is_item_start
                        else f"{comp.label}\n\u21b3"
                    )
                    cell.fill = PatternFill(
                        "solid", fgColor=fill_hex_for_cell(
                            getattr(comp, "kind", None), comp.confidence or ""
                        )
                    )
                else:
                    cell.value = comp.label
                cell.font = small_font
                cell.alignment = center
                cell.border = border
            ws.row_dimensions[r].outlineLevel = 1
            ws.row_dimensions[r].height = 26
            r += 1
        r += 1  # spacer between cabinets

    ws.column_dimensions["A"].width = 16
    for cc in range(2, 31):
        ws.column_dimensions[get_column_letter(cc)].width = 11


def build_article_setup_workbook(setup_df: pd.DataFrame) -> bytes:
    """Minimal workbook for the numbering-only mode (v34.44): exactly one
    sheet, the Article setup frame as built. Pure and Streamlit-free."""
    buffer_io = BytesIO()
    with pd.ExcelWriter(buffer_io, engine="openpyxl") as writer:
        setup_df.to_excel(writer, index=False, sheet_name="Article setup")
        # Customer text is stored as text, never as a live formula (v34.48).
        neutralize_formula_cells(writer.book)
    buffer_io.seek(0)
    return buffer_io.getvalue()


def build_result_workbook(
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
    """Build the result workbook: every table, chart, and planogram sheet.

    Pure and Streamlit-free (v34.39): the page keeps a thin cached wrapper
    with this exact signature, so the cache key semantics are unchanged;
    ``content_key`` is a deterministic serialization of every
    underscore-prefixed composite except the Run_Metadata timestamp.
    A plain rerun is a hit and serves the identical workbook, timestamp
    included, because it IS that build; any change to the plan, the settings,
    the overrides, or the export toggles alters an input and rebuilds. Returns
    the workbook bytes plus the export-verification findings and the export
    notes, which the caller renders in the historical order.

    v34.48: the notes string collects everything the export left out instead
    of dropping it silently - a skipped planogram, Presentation or Charts
    sheet, skipped size-issue highlighting, and KROMI numbers that could not be
    generated (with the reason). Every formula-typed cell is stored as text so
    customer data never becomes a live formula.

    v34.56: when a stock column is mapped, one takeover sheet per supply
    point follows the Article setup (engine.takeover);
    ``_takeover_shared_stock`` marks a Replicate run whose copies share one
    stock (the caller's content key carries the supply-point mode).
    """
    _notes: List[str] = []
    buffer_io = BytesIO()
    with pd.ExcelWriter(buffer_io, engine="openpyxl") as writer:
        df_summary.to_excel(writer, index=False, sheet_name="Summary")
        # Always emit Run_Metadata so every Excel export carries the Build label
        # and the run timestamp — the toggleable "technical" extras still gate the
        # full audit/bucket-compare sheets.
        _df_run_meta.to_excel(writer, index=False, sheet_name="Run_Metadata")
        # Fixed configuration (v34.52): machines, capacity after headroom, use.
        _fixed_rows = capacity_rows(_bucket_plans)
        if _fixed_rows:
            pd.DataFrame(_fixed_rows).to_excel(
                writer, index=False, sheet_name="Fixed_Configuration")
        if include_technical:
            df_audit.to_excel(writer, index=False, sheet_name="Audit_Summary")
            df_bucket_compare.to_excel(writer, index=False, sheet_name="Bucket_Compare")
        # Presentation sheet — compact + detail tables stacked, ready for
        try:
            _pres_startrow = 0
            presentation_compact_df.to_excel(
                writer, index=False, sheet_name="Presentation", startrow=_pres_startrow,
            )
            _pres_startrow += len(presentation_compact_df) + 3
            # Small section header before detail table
            pd.DataFrame([{"Detail": "Consumption / KTC / buffer headroom"}]).to_excel(
                writer, index=False, sheet_name="Presentation", startrow=_pres_startrow,
                header=False,
            )
            _pres_startrow += 2
            presentation_detail_df.to_excel(
                writer, index=False, sheet_name="Presentation", startrow=_pres_startrow,
            )
            _pres_startrow += len(presentation_detail_df) + 3

            # per-SP drilldown tables (one block per SP)
            _sp_distribution_xl = build_per_sp_distribution(work, listings=_listings_arg)
            _sub_all_xl = build_per_sp_subclass_breakdown(work, listings=_listings_arg)
            for _label_xl, _plan_xl in _bucket_plans:
                if _label_xl == "Grand total":
                    continue
                # Resolve the lookup key. Separated mode: label is the listing
                # name and is the key. Combined mode: parse the SP number out.
                _sp_key_xl: Any = _label_xl if _label_xl in _sp_distribution_xl else None
                _sp_num_xl: Any = None
                try:
                    _sp_num_xl = int(_label_xl.split()[-1])
                except Exception:
                    _sp_num_xl = None
                if _sp_key_xl is None and _sp_num_xl is not None and _sp_num_xl in _sp_distribution_xl:
                    _sp_key_xl = _sp_num_xl

                # Section header per SP
                pd.DataFrame([{"Section": f"Drilldown — {_label_xl}"}]).to_excel(
                    writer, index=False, sheet_name="Presentation",
                    startrow=_pres_startrow, header=False,
                )
                _pres_startrow += 2

                # KPI strip (five headline metrics, from the retired PDF)
                _kpi_xl_df = build_sp_kpi_frame(_plan_xl)
                _kpi_xl_df.to_excel(
                    writer, index=False, sheet_name="Presentation",
                    startrow=_pres_startrow,
                )
                _pres_startrow += len(_kpi_xl_df) + 3

                # Distribution (4 buckets) — listing key in Separated mode,
                # SP integer in Combined mode, '__all__' fallback otherwise.
                if _sp_key_xl is not None and _sp_key_xl in _sp_distribution_xl:
                    _dist_xl = _sp_distribution_xl[_sp_key_xl]
                else:
                    _dist_xl = _sp_distribution_xl.get("__all__", {b: 0 for b in SLIDE_BUCKET_ORDER})
                _dist_total_xl = sum(_dist_xl.values()) or 1
                _dist_xl_df = pd.DataFrame([
                    {"Bucket": b, "Items": _dist_xl.get(b, 0),
                     "Share %": round(_dist_xl.get(b, 0) / _dist_total_xl * 100.0, 1)}
                    for b in SLIDE_BUCKET_ORDER
                ])
                _dist_xl_df.to_excel(
                    writer, index=False, sheet_name="Presentation",
                    startrow=_pres_startrow,
                )
                _pres_startrow += len(_dist_xl_df) + 2

                # Cabinet occupation
                _occ_recs_xl = build_per_sp_cabinet_occupation(_plan_xl)
                if _occ_recs_xl:
                    _occ_xl_df = pd.DataFrame([
                        {
                            "Cabinet": f"Cab {r['cabinet_no']}",
                            "Type": r["cabinet_type"],
                            "Capacity": f"{r['capacity']} {r['capacity_unit']}",
                            "Used (est.)": r["used"],
                            "Occupation %": r["occupation_pct"],
                        }
                        for r in _occ_recs_xl
                    ])
                    _occ_xl_df.to_excel(
                        writer, index=False, sheet_name="Presentation",
                        startrow=_pres_startrow,
                    )
                    _pres_startrow += len(_occ_xl_df) + 3
                else:
                    _pres_startrow += 3

                # Subclass breakdown (toolclass detail, from the retired PDF)
                if _sp_key_xl is not None and _sp_key_xl in _sub_all_xl:
                    _sub_buckets_xl = _sub_all_xl[_sp_key_xl]
                else:
                    _sub_buckets_xl = _sub_all_xl.get("__all__", {})
                _sub_xl_df = build_sp_subclass_frame(_sub_buckets_xl)
                if not _sub_xl_df.empty:
                    pd.DataFrame([{"Section": "Subclass breakdown (toolclass detail)"}]).to_excel(
                        writer, index=False, sheet_name="Presentation",
                        startrow=_pres_startrow, header=False,
                    )
                    _pres_startrow += 1
                    _sub_xl_df.to_excel(
                        writer, index=False, sheet_name="Presentation",
                        startrow=_pres_startrow,
                    )
                    _pres_startrow += len(_sub_xl_df) + 3
        except Exception as _pres_exc:
            # Presentation sheet is optional: if anything goes wrong the core
            # Excel file still downloads, and the user is told what is missing.
            _notes.append(f"Presentation sheet skipped ({_pres_exc}).")
        # Distribution sheets (technical / diagnostic)
        if include_technical:
            dist_cat_rows.to_excel(writer, index=False, sheet_name="Dist_Category_byItems")
            dist_cat_vol.to_excel(writer, index=False, sheet_name="Dist_Category_byVolume")
            dist_cabtype.to_excel(writer, index=False, sheet_name="Dist_CabinetType")
            dist_system.to_excel(writer, index=False, sheet_name="Dist_System")

        # Subclass distribution — finer breakdown by ToolClass. One row per
        # (supply point, bucket, subclass). Empty when older archives without
        # ToolClass are reloaded.
        try:
            _sub_xl = build_per_sp_subclass_breakdown(work, listings=_listings_arg)
            _sub_rows: List[Dict[str, Any]] = []
            for sp_key, buckets in _sub_xl.items():
                if sp_key == "__all__":
                    sp_label = "Grand total"
                elif isinstance(sp_key, str):
                    # Separated mode — sp_key is the listing name ("Tools" / "PPE")
                    sp_label = sp_key
                else:
                    sp_label = f"SP {sp_key}"
                for bucket_name in SLIDE_BUCKET_ORDER:
                    subclasses_in_bucket = buckets.get(bucket_name, {})
                    bucket_total = sum(subclasses_in_bucket.values())
                    for tc_name, tc_count in sorted(
                        subclasses_in_bucket.items(), key=lambda kv: -kv[1]
                    ):
                        share = (tc_count / bucket_total * 100.0) if bucket_total > 0 else 0.0
                        _sub_rows.append({
                            "Supply point": sp_label,
                            "Bucket": bucket_name,
                            "Subclass": tc_name,
                            "Items": int(tc_count),
                            "Share of bucket %": round(share, 1),
                        })
            if _sub_rows and include_technical:
                pd.DataFrame(_sub_rows).to_excel(
                    writer, index=False, sheet_name="Dist_Subclass"
                )
        except Exception as _sub_exc:
            # Subclass sheet is optional decoration; failing here must not block
            # the rest of the Excel export, but the user is told it is missing.
            _notes.append(f"Dist_Subclass sheet skipped ({_sub_exc}).")

        # Result keeps the full audit dump (all columns); the segregated views below
        # are trimmed to the user-facing columns by _user_view (engine/export_shaping),
        # which also drops per-sheet any column that is entirely empty.

        _ktc_id = ktc_id
        def _augment(frame):
            return augment_for_export(frame, _ktc_id)

        # Re-derive the export sub-frames from the FINAL `work` (post overrides,
        # re-route, bulk routing, rebalancing, buffer) so the per-sheet values are
        # consistent with the Result sheet rather than a pre-rebalance snapshot.
        df_ktc = work[work["SystemCategory"] == "KTC"].copy()
        df_kanban = work[work["SystemCategory"] == "Kanban"].copy()
        # Fixed configuration (v34.52): the machine sheets list what is in the
        # machines; articles that found no space get their own sheet.
        if "Placement_Status" in df_ktc.columns:
            _not_placed = df_ktc["Placement_Status"].astype(str) == STATUS_NOT_PLACED
        else:
            _not_placed = pd.Series(False, index=df_ktc.index)
        df_helix = df_ktc[(df_ktc["CabinetType"] == "Helix") & ~_not_placed].copy()
        df_car = df_ktc[(df_ktc["CabinetType"] == "Carousel") & ~_not_placed].copy()

        # Export verification (D1/D2 + final-state integrity). Validate the ACTUAL
        # frames being written (after _augment/_user_view), and re-run the plan
        # integrity checks on the final state — the rebalancer and capacity buffer
        # mutate `work` after the preview-stage check, so this is the authoritative
        # verification of what ships.
        _aug_work = _augment(work)
        _result_view = _user_view(_aug_work)
        _ktc_view = _user_view(_augment(df_ktc))
        _kanban_view = _user_view(_augment(df_kanban))
        _export_problems: List[str] = reconcile_export_frames(
            n_plan=len(work), n_result=len(_result_view),
            n_ktc=len(_ktc_view), n_kanban=len(_kanban_view))
        _export_problems += check_export_partition(
            len(work), {"KTC": len(df_ktc), "Kanban": len(df_kanban)})
        _export_problems += check_kromi_uniqueness(_aug_work)
        if "Kromi_Art_No" not in _aug_work.columns:
            _num_reason = numbering_omission_reason(work, _ktc_id)
            if _num_reason:
                _notes.append(
                    "KROMI article numbers were not generated: "
                    f"{_num_reason}. The Kromi_Art_No column and the Article "
                    "setup sheet are left out of this workbook.")
        _final_integrity = verify_plan(
            work, _base_info, days_per_month=DAYS_PER_MONTH,
            consumption_period_months=float(consumption_period_months))
        _export_problems += _final_integrity.violations

        # Result + breakdowns. Standard users get the trimmed view; the full audit
        # dump (every AI/source/confidence/override column) is added as Result_Full
        # only in technical mode.
        _result_view.to_excel(writer, index=False, sheet_name="Result")
        if include_technical:
            _aug_work.to_excel(writer, index=False, sheet_name="Result_Full")
        _ktc_view.to_excel(writer, index=False, sheet_name="KTC_only")
        _kanban_view.to_excel(writer, index=False, sheet_name="Kanban_only")
        _user_view(_augment(df_helix)).to_excel(writer, index=False, sheet_name="Helix_only")
        _user_view(_augment(df_car)).to_excel(writer, index=False, sheet_name="Carousel_only")
        if bool(_not_placed.any()):
            _user_view(_augment(df_ktc[_not_placed])).to_excel(
                writer, index=False, sheet_name="Not_placed")
        # Article setup (v34.43): every unique KTC article twice (customer-
        # property predecessor + KROMI-property successor), every unique
        # Kanban article once, with the Replaces / Replaced-by linkage. The
        # sheet is omitted exactly when the Kromi_Art_No column is (no valid
        # KTC-ID, no ToolClass/description, or a variant-field overflow), and
        # its numbers join the export verification's uniqueness check.
        try:
            _setup_df = build_article_setup(work, _ktc_id)
        except ValueError as _setup_exc:
            _setup_df = None  # dimension group too large for the variant field
            if "Kromi_Art_No" in _aug_work.columns:
                # v34.52: the Result numbers fit, but the KTC successors run
                # past the variant field; say so instead of dropping silently.
                _notes.append(
                    "The Article setup sheet was left out: the KROMI-property "
                    f"numbers of the KTC articles do not fit ({_setup_exc}). "
                    "Check that the description with the dimensions is mapped "
                    "as Description.")
        if _setup_df is not None:
            _setup_df.to_excel(writer, index=False, sheet_name="Article setup")
            _export_problems += check_kromi_uniqueness(_setup_df)
        # Takeover sheets (v34.56): only when a stock column is mapped.
        write_takeover_sheets(writer, build_takeover_frames(
            _aug_work, shared_stock=bool(_takeover_shared_stock)))
        # Bulk routed items (only when bulk routing produced output)
        if enable_bulk_routing and _vend_stats.get("routed_rows", 0) > 0:
            df_bulk = work[work["VendMode"] == "Bulk/Kanban"].copy()
            _user_view(_augment(df_bulk)).to_excel(writer, index=False, sheet_name="Bulk_Routed")
        # Overrides audit sheet — shows what was applied + what was stale/invalid
        if apply_overrides_ui and (
            _override_stats["rows_touched"] > 0
            or len(_override_stats["unmatched_overrides"]) > 0
            or len(_override_stats["invalid_overrides"]) > 0
        ):
            ov_rows: List[Dict[str, Any]] = []
            for e in _override_stats["applied_overrides"]:
                ov_rows.append({
                    "Status": "APPLIED",
                    "Code": e["code"],
                    "Listing": e["listing"],
                    "Rows matched": e["rows"],
                    "Fields changed": e["fields_changed"],
                    "Note": "",
                })
            for e in _override_stats["unmatched_overrides"]:
                ov_rows.append({
                    "Status": "STALE",
                    "Code": e["code"],
                    "Listing": e["listing"],
                    "Rows matched": 0,
                    "Fields changed": "",
                    "Note": "No row in this dataset matched this override",
                })
            for e in _override_stats["invalid_overrides"]:
                ov_rows.append({
                    "Status": "INVALID",
                    "Code": e["code"],
                    "Listing": e["listing"],
                    "Rows matched": 0,
                    "Fields changed": "",
                    "Note": e["reasons"],
                })
            if ov_rows and include_technical:
                pd.DataFrame(ov_rows).to_excel(writer, index=False, sheet_name="Overrides_Applied")
        # Per-listing breakdowns (if applicable)
        if multiple_listings:
            for listing_val in _listings_in_data:
                sheet_safe = listing_val[:28]  # excel sheet name limit is 31 chars
                _listing_df = work[work["Listing"] == listing_val]
                _listing_out = _listing_df if include_technical else _user_view(_listing_df)
                _listing_out.to_excel(
                    writer, index=False, sheet_name=f"Result_{sheet_safe}"
                )

        if include_planogram:
            try:
                _plan = allocate_plan(_build_layout_items(work))
                _render_planogram_sheet(writer.book, _plan)
            except Exception as _pg_exc:  # never break the main export on planogram issues
                _notes.append(f"Planogram sheet skipped ({_pg_exc}).")

        # Highlight problematic-size rows in the per-item allocation sheets. The
        # flagged tools (L/XL forcing an underused Carousel) are filled amber so they
        # stand out in the cabinet-allocation / stockpiles view. Never break the
        # export if styling fails.
        try:
            if "SizeIssue" in work.columns and bool(work["SizeIssue"].any()):
                from openpyxl.styles import PatternFill, Font

                _flagged_codes = {
                    str(c)
                    for c in work.loc[work["SizeIssue"] == True, "Code"].tolist()  # noqa: E712
                }
                _amber = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
                _amber_font = Font(color="7F6000")
                for _sheet in ("Result", "Carousel_only", "Result_Full"):
                    if _sheet not in writer.sheets:
                        continue
                    _ws = writer.sheets[_sheet]
                    _hdr = {
                        _ws.cell(row=1, column=_c).value: _c
                        for _c in range(1, _ws.max_column + 1)
                    }
                    _code_col = _hdr.get("Code")
                    if not _code_col:
                        continue
                    for _r in range(2, _ws.max_row + 1):
                        if str(_ws.cell(row=_r, column=_code_col).value) in _flagged_codes:
                            for _c in range(1, _ws.max_column + 1):
                                _cell = _ws.cell(row=_r, column=_c)
                                _cell.fill = _amber
                                _cell.font = _amber_font
        except Exception as _hl_exc:
            _notes.append(f"Size-issue row highlighting skipped ({_hl_exc}).")
        # Fixed configuration (v34.52): articles without space are filled red
        # in the Result and KTC sheets.
        try:
            if bool(_not_placed.any()):
                from openpyxl.styles import PatternFill, Font

                _np_codes = {str(c) for c in df_ktc.loc[_not_placed, "Code"].tolist()}
                _red = PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid")
                _red_font = Font(color="842029")
                for _sheet in ("Result", "KTC_only", "Result_Full"):
                    if _sheet not in writer.sheets:
                        continue
                    _ws = writer.sheets[_sheet]
                    _hdr = {_ws.cell(row=1, column=_c).value: _c
                            for _c in range(1, _ws.max_column + 1)}
                    _code_col = _hdr.get("Code")
                    _st_col = _hdr.get("Placement_Status")
                    if not _code_col or not _st_col:
                        continue
                    for _r in range(2, _ws.max_row + 1):
                        if (_ws.cell(row=_r, column=_st_col).value == STATUS_NOT_PLACED
                                and str(_ws.cell(row=_r, column=_code_col).value) in _np_codes):
                            for _c in range(1, _ws.max_column + 1):
                                _cell = _ws.cell(row=_r, column=_c)
                                _cell.fill = _red
                                _cell.font = _red_font
        except Exception as _np_exc:
            _notes.append(f"Not-placed row highlighting skipped ({_np_exc}).")
        # Charts sheet — one distribution pie per supply point, native Excel
        # charts referencing their own data block (v34.25, absorbed from the
        # retired PDF). Optional like Presentation: never break the download.
        try:
            from openpyxl.chart import PieChart, Reference

            _ws_ch = writer.book.create_sheet("Charts")
            _sp_dist_ch = build_per_sp_distribution(work, listings=_listings_arg)
            _ch_row = 1
            for _label_ch, _plan_ch in _bucket_plans:
                if _label_ch == "Grand total":
                    continue
                _key_ch: Any = _label_ch if _label_ch in _sp_dist_ch else None
                if _key_ch is None:
                    try:
                        _num_ch = int(_label_ch.split()[-1])
                    except Exception:
                        _num_ch = None
                    if _num_ch is not None and _num_ch in _sp_dist_ch:
                        _key_ch = _num_ch
                _dist_ch = (
                    _sp_dist_ch[_key_ch] if _key_ch is not None
                    else _sp_dist_ch.get("__all__", {})
                )
                _labels_ch, _values_ch = build_pie_series(_dist_ch)
                _ws_ch.cell(_ch_row, 1, f"Distribution — {_label_ch}")
                for _i_ch, (_lab_ch, _val_ch) in enumerate(zip(_labels_ch, _values_ch), 1):
                    _ws_ch.cell(_ch_row + _i_ch, 1, _lab_ch)
                    _ws_ch.cell(_ch_row + _i_ch, 2, _val_ch)
                if _values_ch:
                    _pie_ch = PieChart()
                    _pie_ch.title = f"Distribution — {_label_ch}"
                    _pie_ch.height, _pie_ch.width = 7.5, 11.0
                    _data_ref = Reference(
                        _ws_ch, min_col=2, min_row=_ch_row + 1,
                        max_row=_ch_row + len(_values_ch),
                    )
                    _cats_ref = Reference(
                        _ws_ch, min_col=1, min_row=_ch_row + 1,
                        max_row=_ch_row + len(_values_ch),
                    )
                    _pie_ch.add_data(_data_ref, titles_from_data=False)
                    _pie_ch.set_categories(_cats_ref)
                    _ws_ch.add_chart(_pie_ch, f"D{_ch_row}")
                _ch_row += max(len(_values_ch), 1) + 17
        except Exception as _ch_exc:
            _notes.append(f"Charts sheet skipped ({_ch_exc}).")

        # Customer text is stored as text, never as a live formula (v34.48).
        # The app writes no intentional formulas, so this runs last.
        neutralize_formula_cells(writer.book)

    buffer_io.seek(0)
    return (buffer_io.getvalue(), _export_problems,
            _final_integrity.n_passed, _final_integrity.n_checks, " ".join(_notes))
