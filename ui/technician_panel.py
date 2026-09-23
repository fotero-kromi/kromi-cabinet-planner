"""kromi_app.ui.technician_panel — the Technician review panel (v34.41).

Stage 3 of the structural project: the panel body moved verbatim out of the
page. The database module handle, its availability flag, the save dialog,
and the path resolver cross as parameters, keeping the optional-import
decision in exactly one place on the page.
"""

from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from app_log import log_exception

from engine.classification_tables import PC_VALID
from engine.overrides import merge_pending_overrides, pending_overrides_to_df
from engine.sizing_factors import LISTING_TOOLS


def render(
    *,
    work,
    effective_customer,
    effective_site,
    reviewer_name,
    _DB_AVAILABLE,
    _kromi_db,
    _save_override_set_dialog,
    _resolve_db_path,
):
    """Render the Technician review panel; body verbatim from the page."""
    st.header(" Technician review")

    with st.expander(
        f"Review rows and save corrections as a `{effective_customer}__{effective_site}` override set",
        expanded=False,
    ):
        if len(work) == 0:
            st.caption("No rows in the current dataset to review.")
        else:
            # --- Filters ---
            f_col1, f_col2, f_col3 = st.columns([2, 2, 3])
            with f_col1:
                review_filter_mode = st.selectbox(
                    "Show",
                    options=[
                        "All rows",
                        "In a vending machine (Helix / Carousel / Locker)",
                        "Kanban — low movers",
                        "Bulk/Kanban — routed families",
                        "With override already",
                        "Without override",
                    ],
                    index=0,
                    help=(
                        "Filters by where the row ends up. 'In a vending machine' = "
                        "Helix/Carousel/Locker. 'Kanban — low movers' = items below the "
                        "KTC throughput threshold (not placed in a machine). "
                        "'Bulk/Kanban — routed families' = bulk items (abrasives, PPE, "
                        "screws) pulled out of vending by bulk routing."
                    ),
                )
            with f_col2:
                review_filter_listing = st.selectbox(
                    "Listing",
                    options=["All"] + sorted(work["Listing"].astype(str).unique().tolist()) if "Listing" in work.columns else ["All"],
                    index=0,
                )
            with f_col3:
                review_search = st.text_input(
                    "Search (code or description contains)",
                    value="",
                    placeholder="e.g. CNMG, DISQUE, 4025",
                )

            # --- Build filtered view ---
            view = work.copy()
            # v33 fix: filter on the row's DISPOSITION, not on VendMode alone.
            # Two different "Kanban" concepts coexist:
            #   * CabinetType == "Kanban"  -> a low mover (below the KTC throughput
            #     threshold). It is NOT placed in a vending machine, but it keeps
            #     VendMode == "Vending" because bulk routing never touched it.
            #   * VendMode == "Bulk/Kanban" -> a bulk family (abrasives / PPE /
            #     screws) that bulk routing pulled OUT of vending.
            # The old "Vending only" filter tested VendMode == "Vending", so it
            # wrongly swept in every Kanban low mover. We now classify each row
            # into exactly one disposition.
            _VENDING_CABS = {"Helix", "Carousel", "Locker A", "Locker B", "Locker C"}
            if "VendMode" in view.columns:
                _is_bulk = view["VendMode"].astype(str) == "Bulk/Kanban"
            else:
                _is_bulk = pd.Series(False, index=view.index)
            if "CabinetType" in view.columns:
                _ct = view["CabinetType"].astype(str)
                _is_vending_cab = _ct.isin(_VENDING_CABS)
                _is_kanban_cab = _ct == "Kanban"
            else:
                _is_vending_cab = pd.Series(False, index=view.index)
                _is_kanban_cab = pd.Series(False, index=view.index)

            if review_filter_mode == "In a vending machine (Helix / Carousel / Locker)":
                view = view[_is_vending_cab & ~_is_bulk]
            elif review_filter_mode == "Kanban — low movers":
                view = view[_is_kanban_cab & ~_is_bulk]
            elif review_filter_mode == "Bulk/Kanban — routed families":
                view = view[_is_bulk]
            elif review_filter_mode == "With override already":
                if "Override_Applied" in view.columns:
                    view = view[view["Override_Applied"] == True]  # noqa: E712
                else:
                    view = view.iloc[0:0]  # no overrides column -> no override rows
            elif review_filter_mode == "Without override":
                if "Override_Applied" in view.columns:
                    view = view[view["Override_Applied"] == False]  # noqa: E712
                # If no Override_Applied column, every row is "without override" -> keep all
            # "All rows" -> no disposition filter applied

            if review_filter_listing != "All" and "Listing" in view.columns:
                view = view[view["Listing"].astype(str) == review_filter_listing]

            if review_search.strip():
                q = review_search.strip().lower()
                mask = (
                    view["Code"].astype(str).str.lower().str.contains(q, na=False)
                    | view["Description"].astype(str).str.lower().str.contains(q, na=False)
                )
                if "Description_2" in view.columns:
                    mask = mask | view["Description_2"].astype(str).str.lower().str.contains(q, na=False)
                view = view[mask]

            st.caption(f"**{len(view):,}** row(s) match the filters.")

            # clearer instructions so techs know how to actually drive the editor.
            with st.container():
                st.markdown(
                    "**How to use this editor:**\n"
                    "1. **Double-click** a Category / Size / CabinetType / VendMode cell to pick a new value from the dropdown.\n"
                    "2. **Single-click-and-type** in the New note column to add a comment.\n"
                    "3. The **\"In library\"** column is a read-only status — a tick means this row already has a saved override from an earlier session.\n"
                    "4. Click **Apply table edits** to register this view's edits and recompute. Edits batch until you click, and corrections **accumulate across filters and pages** — so always click Apply **before** you change the filter or page, or that view's un-applied edits are dropped.\n"
                    "5. Keep correcting under any filter or page; the running total is shown below the table, and you can tick **Show all accumulated corrections** to review them.\n"
                    "6. When you're done, click **Save ... correction(s) as override set** to store the whole set in the database for reuse. **Clear all corrections** removes them and recomputes without them."
                )

            # Page the editor instead of hard-capping it, so every row is reachable
            # (the table widget gets sluggish past a few hundred rows, so we render
            # one page at a time). Edits accumulate across pages, so paging through
            # and correcting a large list keeps every change.
            PAGE_SIZE = 500
            _total_rows = len(view)
            _n_pages = max(1, (_total_rows + PAGE_SIZE - 1) // PAGE_SIZE)
            if _n_pages > 1:
                _page = int(st.number_input(
                    f"Page (1–{_n_pages}) — {_total_rows:,} rows match, {PAGE_SIZE} per page. "
                    "Click 'Apply table edits' before changing page, or that page's edits are dropped.",
                    min_value=1, max_value=_n_pages, value=1, step=1, key="_editor_page",
                ))
                _start = (_page - 1) * PAGE_SIZE
                view = view.iloc[_start:_start + PAGE_SIZE]

            if len(view) == 0:
                st.caption("No rows match — adjust filters above.")
            else:
                # Build editor dataframe: read-only context columns + editable override fields
                editor_cols = [
                    "Code", "Listing", "Description",
                    "ProductCategory", "ToolClass", "PackUnits", "SizeCategory",
                    "CabinetType", "VendMode",
                    "ProductCategory_Reason",
                    "Monthly_pcs", "Monthly_packs",
                    "Override_Applied", "Override_Note",
                ]
                editor_cols = [c for c in editor_cols if c in view.columns]
                editor_df = view[editor_cols].copy().reset_index(drop=False).rename(columns={"index": "__row_index"})

                # Convert PackUnits / Monthly_* numerics for editor friendliness
                editor_df["PackUnits"] = pd.to_numeric(editor_df["PackUnits"], errors="coerce").fillna(1.0)
                # Current restocking state as yes/no, robust to the boolean frame
                # value and the Yes/empty display normalization (v34.28)
                if "Restockable" in view.columns:
                    editor_df["Restocking"] = view["Restockable"].map(
                        lambda v: "yes" if str(v).strip().lower() in ("true", "yes", "1") else "no"
                    ).values
                else:
                    editor_df["Restocking"] = "no"
                if "Monthly_pcs" in editor_df.columns:
                    editor_df["Monthly_pcs"] = pd.to_numeric(editor_df["Monthly_pcs"], errors="coerce").fillna(0.0)
                if "Monthly_packs" in editor_df.columns:
                    editor_df["Monthly_packs"] = pd.to_numeric(editor_df["Monthly_packs"], errors="coerce").fillna(0.0)

                # Note field starts as the existing Override_Note so techs can edit in place.
                if "Override_Note" in editor_df.columns:
                    editor_df["Note"] = editor_df["Override_Note"].astype(str).fillna("")
                else:
                    editor_df["Note"] = ""
                    editor_df["Override_Note"] = ""  # so the col_cfg below doesn't KeyError

                # same guard for Override_Applied — the review panel builds a
                if "Override_Applied" not in editor_df.columns:
                    editor_df["Override_Applied"] = False

                col_cfg = {
                    "__row_index": st.column_config.NumberColumn("idx", disabled=True, width="small"),
                    "Code": st.column_config.TextColumn("Code", disabled=True, width="small"),
                    "Listing": st.column_config.TextColumn("Listing", disabled=True, width="small"),
                    "Description": st.column_config.TextColumn("Description", disabled=True, width="large"),
                    "ProductCategory": st.column_config.SelectboxColumn(
                        "Category",
                        options=[""] + sorted(PC_VALID),
                        help="Set blank to leave unchanged. Saving an override stamps the chosen value.",
                        width="medium",
                    ),
                    "ToolClass": st.column_config.TextColumn(
                        "Tool class",
                        disabled=True,
                        width="medium",
                        help="Finer-grained tool subclass (turning_insert, solid_carbide_drill, etc.). Read-only.",
                    ),
                    "ProductCategory_Reason": st.column_config.TextColumn(
                        "AI reason",
                        disabled=True,
                        width="large",
                        help="One-sentence rationale from the AI for AI-classified rows. Empty when classification came from a heuristic.",
                    ),
                    "PackUnits": st.column_config.NumberColumn(
                        "Pack", min_value=1, max_value=10000, step=1, width="small",
                        help="Saving with this value stamps a pack-units override.",
                    ),
                    "SizeCategory": st.column_config.SelectboxColumn(
                        "Size", options=["", "S", "M", "L", "XL", "XXL"], width="small",
                    ),
                    "CabinetType": st.column_config.SelectboxColumn(
                        "CabinetType",
                        options=["", "Helix", "Carousel", "Locker A", "Locker B", "Locker C", "Kanban"],
                        width="medium",
                    ),
                    "VendMode": st.column_config.SelectboxColumn(
                        "VendMode", options=["", "Vending", "Bulk/Kanban"], width="medium",
                    ),
                    "Restocking": st.column_config.SelectboxColumn(
                        "Restocking", options=["", "yes", "no"], width="small",
                        help=(
                            "Restockable yes/no. A change here saves a restocking "
                            "override that beats the mapped column and the category "
                            "rule; the buffer compartment follows the item's cabinet "
                            "family on the next run."
                        ),
                    ),
                    "Monthly_pcs": st.column_config.NumberColumn("Mo pcs", disabled=True, width="small", format="%.1f"),
                    "Monthly_packs": st.column_config.NumberColumn("Mo packs", disabled=True, width="small", format="%.2f"),
                    "Override_Applied": st.column_config.CheckboxColumn(
                        "In library",
                        disabled=True,
                        width="small",
                        help=(
                            "Read-only status. Ticked = this row already has an override "
                            "saved in the library from an earlier session. Clicking does "
                            "nothing — edit the dropdowns above to create a NEW override."
                        ),
                    ),
                    "Override_Note": st.column_config.TextColumn("Existing note", disabled=True, width="medium"),
                    "Note": st.column_config.TextColumn("New note", width="medium",
                        help="Free-text note saved alongside the override."),
                }

                with st.form("technician_editor_form", border=False):
                    edited = st.data_editor(
                        editor_df,
                        column_config=col_cfg,
                        hide_index=True,
                        width="stretch",
                        key="technician_editor",
                        num_rows="fixed",
                    )
                    # Edits inside a form do not re-run the page on each cell change;
                    # they are held until this submit, so a batch of corrections costs
                    # one re-run instead of one (and one screen redraw) per cell.
                    _editor_applied = st.form_submit_button(
                        "Apply table edits", width="stretch", type="primary",
                    )

                # The diff walk only matters when the form was submitted; a plain
                # rerun skips it entirely (v34.29), which keeps per-click cost flat
                # as the row count grows.
                diffs: List[Dict[str, Any]] = []
                if _editor_applied:
                    # Compute diff: for each row, detect which fields the user actually changed
                    # versus the original view (to avoid stamping no-op overrides).
                    def _row_diff(orig: pd.Series, new: pd.Series) -> Dict[str, Any]:
                        changes: Dict[str, Any] = {}
                        if str(new.get("ProductCategory", "")).strip() and str(new.get("ProductCategory", "")).strip() != str(orig.get("ProductCategory", "")).strip():
                            changes["product_category_override"] = str(new["ProductCategory"]).strip().lower()
                        # PackUnits is always set; compare as int
                        try:
                            orig_pu = int(float(orig.get("PackUnits") or 1))
                        except Exception:
                            orig_pu = 1
                        try:
                            new_pu = int(float(new.get("PackUnits") or 1))
                        except Exception:
                            new_pu = 1
                        if new_pu != orig_pu:
                            changes["pack_units_override"] = str(new_pu)
                        if str(new.get("SizeCategory", "")).strip().upper() and str(new.get("SizeCategory", "")).strip().upper() != str(orig.get("SizeCategory", "")).strip().upper():
                            changes["size_category_override"] = str(new["SizeCategory"]).strip().upper()
                        if str(new.get("CabinetType", "")).strip() and str(new.get("CabinetType", "")).strip() != str(orig.get("CabinetType", "")).strip():
                            changes["cabinet_type_override"] = str(new["CabinetType"]).strip()
                        if str(new.get("VendMode", "")).strip() and str(new.get("VendMode", "")).strip() != str(orig.get("VendMode", "")).strip():
                            changes["vend_mode_override"] = str(new["VendMode"]).strip()
                        if str(new.get("Restocking", "")).strip() and str(new.get("Restocking", "")).strip().lower() != str(orig.get("Restocking", "")).strip().lower():
                            changes["restocking_override"] = str(new["Restocking"]).strip().lower()
                        return changes

                    # Collect diffs row-by-row
                    diffs: List[Dict[str, Any]] = []
                    edited_indexed = edited.set_index("__row_index")
                    for ridx, orig_row in editor_df.set_index("__row_index").iterrows():
                        if ridx not in edited_indexed.index:
                            continue
                        new_row = edited_indexed.loc[ridx]
                        ch = _row_diff(orig_row, new_row)
                        if ch:
                            diffs.append({
                                "row_index": int(ridx),
                                "code": str(orig_row["Code"]),
                                "listing": str(orig_row.get("Listing", LISTING_TOOLS)),
                                "note": str(new_row.get("Note", "")),
                                **ch,
                            })

                    # Apply table edits: fold THIS page/filter's edits into the running
                    # pending-corrections map (kept in session), then recompute so the
                    # plan and the editor both reflect every correction gathered so far.
                    # Folding by code is what lets edits made under one filter survive
                    # switching to another filter or page.
                if _editor_applied and diffs:
                    st.session_state["_pending_overrides"] = merge_pending_overrides(
                        st.session_state.get("_pending_overrides") or {}, diffs
                    )
                    st.session_state["has_results"] = False
                    st.session_state["_run_fingerprint"] = None
                    st.session_state["_force_run"] = True
                    st.rerun()
                elif _editor_applied and not diffs:
                    st.caption("No new changes on this page to apply.")

                _pending = st.session_state.get("_pending_overrides") or {}
                if _pending:
                    st.caption(
                        f"**{len(_pending)} tool(s) corrected** across all filters and "
                        "pages so far, applied to the plan now."
                    )
                    if st.checkbox("Show all accumulated corrections", key="_show_pending"):
                        st.dataframe(
                            pending_overrides_to_df(_pending), width="stretch", hide_index=True
                        )
                else:
                    st.caption("No corrections yet. Edit cells above, then click 'Apply table edits'.")

                # Persist the full accumulated correction set as a database override
                # set for reuse on a future run. The corrections already apply via the
                # live pending map, so saving only stores them.
                _save_disabled = not (
                    _DB_AVAILABLE
                    and _save_override_set_dialog is not None
                    and len(_pending) > 0
                )
                _btn_cols = st.columns([2, 1])
                with _btn_cols[0]:
                    if st.button(
                        f" Save {len(_pending)} correction(s) as override set…",
                        width="stretch",
                        key="_open_ovset_dialog",
                        disabled=_save_disabled,
                        type="primary" if not _save_disabled else "secondary",
                    ):
                        _pending_difflist = [
                            {"code": _c, **_fields} for _c, _fields in _pending.items()
                        ]
                        _save_override_set_dialog(
                            _pending_difflist, effective_customer, effective_site, reviewer_name
                        )
                with _btn_cols[1]:
                    if st.button(
                        "Clear all corrections",
                        width="stretch",
                        disabled=(len(_pending) == 0),
                        help="Remove every accumulated correction and recompute without them.",
                    ):
                        # v34.51: ask first; unsaved corrections cannot be recovered.
                        st.session_state["_confirm_clear_all"] = True
                if st.session_state.get("_confirm_clear_all") and len(_pending) > 0:
                    st.warning(
                        f"Discard all {len(_pending)} unsaved correction(s) and recompute "
                        "without them? This cannot be undone."
                    )
                    _cc = st.columns([1, 1, 3])
                    with _cc[0]:
                        if st.button("Yes, clear all", key="_clear_all_yes", type="primary"):
                            st.session_state.pop("_confirm_clear_all", None)
                            st.session_state.pop("_pending_overrides", None)
                            st.session_state["has_results"] = False
                            st.session_state["_run_fingerprint"] = None
                            st.session_state["_force_run"] = True
                            st.rerun()
                    with _cc[1]:
                        if st.button("Keep them", key="_clear_all_no"):
                            st.session_state.pop("_confirm_clear_all", None)
                            st.rerun()

                _ovset_msg = st.session_state.pop("_ovset_saved", None)
                if _ovset_msg:
                    st.success(_ovset_msg)

    # Manage saved override sets: inspect a set's rows and hard-delete either the
    # whole set or individual tool rows. Sibling to the review expander above
    # (Streamlit forbids nesting expanders), so it uses a selectbox to choose a set.
    if _DB_AVAILABLE:
        _manage_open = bool(st.session_state.get("_manage_ovset_open", False))
        with st.expander("Manage saved override sets (view and delete)", expanded=_manage_open):
            _mmsg = st.session_state.pop("_ovset_manage_msg", None)
            if _mmsg:
                st.success(_mmsg)
            # v34.48: an unreadable database degrades to a message instead of
            # crashing the page (which also skipped the run's save step).
            try:
                _mc = _kromi_db.init_db(_resolve_db_path())
            except Exception as _mc_exc:
                log_exception("Override database could not be opened", _mc_exc)
                _mc = None
                st.warning(
                    "Saved override sets could not be loaded: the override "
                    f"database could not be read ({type(_mc_exc).__name__})."
                )
            if _mc is not None:
                try:
                    try:
                        _msets = _kromi_db.list_override_sets(
                            _mc,
                            customer=(None if effective_customer == "default" else effective_customer),
                            site=(None if effective_site == "default" else effective_site),
                            active_only=False,
                        )
                    except Exception as _ml_exc:
                        log_exception("Saved override sets could not be listed", _ml_exc)
                        _msets = None
                        st.warning(
                            "Saved override sets could not be loaded: the override "
                            f"database could not be read ({type(_ml_exc).__name__})."
                        )
                    if _msets is None:
                        pass
                    elif not _msets:
                        st.caption("No saved override sets for this customer and site yet.")
                    else:
                        _mopts = {
                            (
                                f"#{s['set_id']} · {str(s['created_at'])[:16].replace('T', ' ')} · "
                                f"{s['override_count']} change(s)"
                                + (f" · {s['reviewer_name']}" if s["reviewer_name"] else "")
                            ): s["set_id"]
                            for s in _msets
                        }
                        _mpick = st.selectbox(
                            "Pick a set to inspect or delete",
                            list(_mopts.keys()),
                            key="_manage_ovset_pick",
                        )
                        _msid = _mopts[_mpick]

                        # Delete the whole set, behind a confirm step (it cannot be undone).
                        _dc = st.columns([1, 3])
                        with _dc[0]:
                            if st.button("Delete this set", key=f"_del_set_btn_{_msid}"):
                                st.session_state["_confirm_del_set"] = _msid
                        if st.session_state.get("_confirm_del_set") == _msid:
                            st.warning(
                                f"Delete override set #{_msid} and all its rows? "
                                "This cannot be undone."
                            )
                            _yc = st.columns([1, 1, 3])
                            with _yc[0]:
                                if st.button("Yes, delete set", key=f"_del_set_yes_{_msid}", type="primary"):
                                    _kromi_db.delete_override_set(_mc, _msid)
                                    st.session_state.pop("_confirm_del_set", None)
                                    st.session_state["_ovset_manage_msg"] = f"Deleted override set #{_msid}."
                                    st.session_state["_manage_ovset_open"] = True
                                    st.rerun()
                            with _yc[1]:
                                if st.button("Cancel", key=f"_del_set_no_{_msid}"):
                                    st.session_state.pop("_confirm_del_set", None)
                                    st.session_state["_manage_ovset_open"] = True
                                    st.rerun()

                        # The set's rows, each deletable on its own.
                        _mrows = _kromi_db.override_set_as_dataframe(_mc, _msid)
                        if len(_mrows) == 0:
                            st.caption("This set has no rows. Use 'Delete this set' to remove it.")
                        else:
                            _field_cols = [
                                c for c in _mrows.columns
                                if c != "code" and _mrows[c].astype(str).str.strip().ne("").any()
                            ]
                            st.markdown(
                                f"**Rows in set #{_msid}** ({len(_mrows)} tool(s)) — delete any individually:"
                            )
                            for _, _rr in _mrows.iterrows():
                                _code = str(_rr["code"])
                                _changes = "; ".join(
                                    f"{c}={_rr[c]}" for c in _field_cols if str(_rr[c]).strip()
                                ) or "(no fields)"
                                _rcols = st.columns([5, 1])
                                with _rcols[0]:
                                    st.text(f"{_code}: {_changes}")
                                with _rcols[1]:
                                    if st.button("Delete", key=f"_del_row_{_msid}_{_code}"):
                                        # v34.51: ask first, like deleting a whole set.
                                        st.session_state["_confirm_del_row"] = (_msid, _code)
                                        st.session_state["_manage_ovset_open"] = True
                                if st.session_state.get("_confirm_del_row") == (_msid, _code):
                                    st.warning(
                                        f"Delete the saved correction for {_code} from set "
                                        f"#{_msid}? This cannot be undone."
                                    )
                                    _rc = st.columns([1, 1, 3])
                                    with _rc[0]:
                                        if st.button("Yes, delete", key=f"_del_row_yes_{_msid}_{_code}", type="primary"):
                                            _n = _kromi_db.delete_override_set_row(_mc, _msid, _code)
                                            st.session_state.pop("_confirm_del_row", None)
                                            st.session_state["_ovset_manage_msg"] = (
                                                f"Deleted {_n} field row(s) for {_code} from set #{_msid}."
                                            )
                                            st.session_state["_manage_ovset_open"] = True
                                            st.rerun()
                                    with _rc[1]:
                                        if st.button("Cancel", key=f"_del_row_no_{_msid}_{_code}"):
                                            st.session_state.pop("_confirm_del_row", None)
                                            st.session_state["_manage_ovset_open"] = True
                                            st.rerun()
                finally:
                    _mc.close()
