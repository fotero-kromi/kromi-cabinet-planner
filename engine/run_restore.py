"""Restore a stored run's control settings and column mapping when it is
recomputed on the current engine.

The planner page captures the value of every restorable control and
column-mapping widget into a small ``ui_state`` snapshot and stores it in the
run's settings JSON. When that run is later recomputed, the page reads the
snapshot back and seeds it into ``st.session_state`` once, so the sidebar
controls and the column mapping match the values the run was produced with
(only the engine version differs).

This module is pure: it never imports Streamlit. It only knows the set of
widget keys and how to turn a stored snapshot plus the columns present in the
file being recomputed into the dict the page writes into session_state.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

# The sentinel a column-mapping selectbox shows when a field is left unmapped.
NOT_AVAIL = "— not available —"

# Column-mapping selectbox keys. Their seed value is a column name, so it must
# exist in the file being recomputed or the selectbox would have no such option.
MAPPING_KEYS = (
    "cm_code",
    "cm_prod",
    "cm_year",
    "cm_desc1",
    "cm_desc2",
    "cm_program",
    "cm_restock",
    "cm_sup",
    "cm_size",
    "cm_site",
    "cm_stdspecial",
    "cm_cons",
    "cm_pack",
    "cm_dims",
    "cm_regrind",
    "cm_systemtyp",
    "cm_stock",
)

# The three mapping fields that are required and therefore have no "unmapped"
# sentinel option. They may only be seeded with a real column.
REQUIRED_MAPPING_KEYS = frozenset({"cm_code", "cm_desc1", "cm_cons"})

# Control widget keys (numbers, radios, selectboxes, toggles, sheet pickers).
CONTROL_KEYS = (
    "ks_ktc_threshold",
    "ks_insert_pack",
    "ks_helix_threshold",
    "ks_consumption_months",
    "ks_overfill",
    "ks_min_carousel",
    "cov_days_standard",
    "cov_days_special",
    "ks_special_ktc",
    "ks_restock_categories",
    "ks_reserve",
    "ks_fill_ceiling",
    "ks_rebalancer",
    "ks_empty_cab",
    "ks_buffer",
    "ks_pack_hint",
    "ks_bulk_routing",
    "ks_force_screws",
    "ks_n_sp",
    "ks_sp_mode",
    "ks_calc_mode",
    "ks_use_desc2",
    "ks_year_mode",
    "ks_dedup_mode",
    "ks_trim_reason",
    "ks_op_mode",
    "ks_max_carousels",
    "ks_sheet_tools",
    "ks_header_row",
    # v34.54 (audit C9): the PPE sheet, the site, the override toggle and the
    # per-class threshold switch; the threshold values, the restockable
    # categories and the Program -> supply point map are structured values
    # handled below.
    "ks_sheet_ppe",
    "ks_site",
    "ks_apply_overrides",
    "adv_thr_active",
    "adv_thr_vals",
    # Fixed configuration (v34.52): headroom, move toggle, and the machines
    # per supply point (the sidebar allows up to 10 supply points).
    "ks_fixed_headroom",
    "ks_fixed_spill",
    "ks_fixed_stock_promo",
    "ks_fixed_stock_months",
) + tuple(
    f"ks_fixed_{kind}_{sp}"
    for sp in range(1, 11)
    for kind in ("helix", "carousel", "locker_a", "locker_b", "locker_c")
)

_MAPPING_SET = frozenset(MAPPING_KEYS)
_ALL_KEYS = frozenset(CONTROL_KEYS) | _MAPPING_SET

_SCALAR = (str, int, float, bool)

# Structured values (v34.54): a list of names, a name -> number map, and the
# per-programme supply point selectboxes, whose keys carry the programme name.
LIST_KEYS = frozenset({"ks_restock_categories"})
DICT_KEYS = frozenset({"adv_thr_vals"})
PROGRAM_SP_PREFIX = "prog_sp::"
# Sheet pickers are validated against the stored workbook's sheet names.
SHEET_KEYS = frozenset({"ks_sheet_tools", "ks_sheet_ppe"})
SHEET_NOT_USED = "\u2014 not used \u2014"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _clean_list(value: Any) -> Optional[list]:
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return list(value)
    return None


def _clean_dict(value: Any) -> Optional[Dict[str, float]]:
    if isinstance(value, dict) and all(
            isinstance(k, str) and _is_number(v) for k, v in value.items()):
        return {k: float(v) for k, v in value.items()}
    return None


def _is_program_sp(key: Any, value: Any) -> bool:
    return (isinstance(key, str) and key.startswith(PROGRAM_SP_PREFIX)
            and isinstance(value, int) and not isinstance(value, bool))


def capture_ui_state(session_state: Mapping[str, Any]) -> Dict[str, Any]:
    """Snapshot the restorable widget values from a session-state-like mapping.

    Only known keys are captured, and only JSON-safe scalar values; anything
    missing or non-scalar is skipped. Returns a plain dict suitable for storing
    in the run's settings JSON.
    """
    snap: Dict[str, Any] = {}
    if not session_state:
        return snap
    for key in _ALL_KEYS:
        if key in session_state:
            value = session_state[key]
            if key in LIST_KEYS:
                cleaned_list = _clean_list(value)
                if cleaned_list is not None:
                    snap[key] = cleaned_list
            elif key in DICT_KEYS:
                cleaned_dict = _clean_dict(value)
                if cleaned_dict is not None:
                    snap[key] = cleaned_dict
            elif value is None or isinstance(value, _SCALAR):
                snap[key] = value
    for key in list(session_state.keys()):
        if isinstance(key, str) and key.startswith(PROGRAM_SP_PREFIX):
            value = session_state[key]
            if _is_program_sp(key, value):
                snap[key] = int(value)
    return snap


def build_seed(
    ui_state: Optional[Mapping[str, Any]],
    available_columns: Optional[Iterable[str]],
    *,
    sheet_names: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Turn a stored ``ui_state`` snapshot into the session_state seed dict.

    ``available_columns`` are the columns present in the file being recomputed.
    When that list is non-empty, a column-mapping key whose stored column is not
    among them is dropped so a selectbox is never seeded with an option it does
    not offer; auto-detection then handles that field. When the list is empty or
    None the columns could not be read, so the stored mapping is kept as-is (the
    page validates it again at render time). Optional mapping fields stored as
    unmapped seed the sentinel. Control values pass through unless they are
    ``None``. Structured values pass only in their expected shape. With
    ``sheet_names`` (the stored workbook's sheets) a sheet picker whose sheet
    is not in the workbook is dropped.
    """
    sheets = set(sheet_names or [])
    cols_list = list(available_columns or [])
    cols = set(cols_list)
    # `cols_known` distinguishes "the file's columns were read and this column is
    # not among them" (a stale mapping, which we drop) from "the column
    # list could not be read" (empty/None, which we must NOT treat as proof the
    # column is gone). The recompute reads the same stored file, so an unreadable
    # column list means "could not verify", and the stored mapping is kept; the
    # page's render-time stale-column guard remains the final check. Dropping the
    # mapping here on an empty read is what collapsed Code/Description onto the
    # first column and tripped a spurious conflict on recompute.
    cols_known = bool(cols_list)
    seed: Dict[str, Any] = {}
    for key, value in (ui_state or {}).items():
        if isinstance(key, str) and key.startswith(PROGRAM_SP_PREFIX):
            if _is_program_sp(key, value):
                seed[key] = int(value)
            continue
        if key not in _ALL_KEYS:
            continue
        if key in LIST_KEYS:
            cleaned_list = _clean_list(value)
            if cleaned_list is not None:
                seed[key] = cleaned_list
            continue
        if key in DICT_KEYS:
            cleaned_dict = _clean_dict(value)
            if cleaned_dict is not None:
                seed[key] = cleaned_dict
            continue
        if key in SHEET_KEYS and sheets:
            if value == SHEET_NOT_USED or value in sheets:
                seed[key] = value
            continue
        if key in _MAPPING_SET:
            if key in REQUIRED_MAPPING_KEYS:
                if isinstance(value, str) and (not cols_known or value in cols):
                    seed[key] = value
                # column read and confirmed absent -> drop, let auto-detect run
            else:
                if value is None or value == NOT_AVAIL:
                    seed[key] = NOT_AVAIL
                elif isinstance(value, str) and (not cols_known or value in cols):
                    seed[key] = value
                # column read and confirmed absent -> drop
        else:
            if value is not None:
                seed[key] = value
    return seed


def restore_summary(
    ui_state: Optional[Mapping[str, Any]], seed: Mapping[str, Any]
) -> Dict[str, Any]:
    """How much of a stored snapshot a seed restores (v34.54).

    Counts the restorable settings the run stored (an unset control does not
    count) and names the ones the seed leaves out, for the recompute banner.
    """
    total = [
        key for key, value in (ui_state or {}).items()
        if (isinstance(key, str) and key.startswith(PROGRAM_SP_PREFIX))
        or (key in _ALL_KEYS and (key in _MAPPING_SET or value is not None))
    ]
    dropped = sorted(key for key in total if key not in seed)
    return {"restored": len(total) - len(dropped), "total": len(total), "dropped": dropped}
