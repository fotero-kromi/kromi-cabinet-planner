import math
import os
import re
import time
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

import altair as alt
import pandas as pd
import streamlit as st
from engine.build_info import BUILD, build_stamp
from engine.ai_classifier import (
    build_classification_batches,
    AIRunDiagnostics,
)
from engine.ai_estimate import (
    estimate_ai_run,
    PRICE_INPUT_PER_1M,
    PRICE_OUTPUT_PER_1M,
)
from engine import run_restore as _run_restore
from dotenv import load_dotenv

# Engine modules — constants extracted to kromi_app/engine/constants.py.
# Keep this import together so domain taxonomy/constants live in one place.
from engine.constants import (
    HELIX_SPIRALS_PER_CAB,
    CAROUSEL_SLOTS_PER_CAB,
    LOCKER_A_CAP,
    LOCKER_B_CAP,
    LOCKER_C_CAP,
    LISTING_TOOLS,
    LISTING_PPE,
    SP_MODE_PARTITION,
    SP_MODE_REPLICATE,
    PC_VALID,
    THRESHOLD_CATEGORIES,
    SLIDE_BUCKET_ORDER,
    OVERRIDE_COLUMNS,
)

# Engine modules — text utilities extracted to kromi_app/engine/text_utils.py.
from engine.text_utils import (
    norm,
    _fmt_seconds,
)


load_dotenv()




OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


# Safety controls
DEFAULT_MAX_AI_ITEMS = int(os.getenv("MAX_AI_ITEMS", "400"))
DEFAULT_BATCH_SIZE = int(os.getenv("AI_BATCH_SIZE", "20"))
# AI retry attempts, call timeout and backoff live in ui/ai_calls.py (v34.48).

# Pricing and ETA assumptions live in engine/ai_estimate.py alongside the
# estimator that consumes them.

MAX_DESC_CHARS_FOR_AI = int(os.getenv("MAX_DESC_CHARS_FOR_AI", "220"))

# parallel AI execution
DEFAULT_AI_CONCURRENCY = int(os.getenv("AI_CONCURRENCY", "5"))
MAX_AI_CONCURRENCY = int(os.getenv("MAX_AI_CONCURRENCY", "20"))

# app directory (used to locate the technician overrides library)
_SCRIPT_DIR = Path(__file__).parent.resolve() if "__file__" in globals() else Path.cwd()

# technician overrides library


# Classification — extracted to engine/classification.py (19 functions).
# This is the biggest engine module: hard ISO insert detection, the
# evidence-tracking classifier, French SAP-shorthand (FO/FR/AL/ME),
# supplier-code patterns (Seco/Iscar/Sandvik/etc), supplier-specialty
# soft fallback, ToolClass derivation, size and pack-units heuristics,
# and bulk-family detection.
#
# Supplier-pattern design (constants in engine/constants.py):
#   1) SUPPLIER_CODE_PATTERNS — code-shape regexes paired with a brand
#      substring. Both the code shape AND the supplier brand must match
#      for the row to classify deterministically. Patterns are anchored so
#      substrings don't trigger.
#   2) SUPPLIER_SPECIALTY — brand-only soft fallback. Suppliers whose
#      entire catalog is dominated by one product type (Guhring=drills,
#      Mapal=reamers, Asahi Diamond=abrasives, Botek=drills). Consulted only
#      when no description keyword and no code pattern matched.
# Brand matching is case-insensitive substring on the supplier field
# ("SECO TOOLS FRANCE" matches "seco").

from engine.classification import is_weak_category, merge_classification_results

# Planning base preparation — extracted to engine/preprocessing.py.
# Pure function; calls engine.text_utils + engine.classification.
from engine.boundary import apply_pre_ai_heuristics, apply_post_ai_safety
from engine.preprocessing import prepare_planning_base
from engine.takeover import STOCK_COL

from engine.colmap import (
    headers_look_misplaced,
    suggest_header_row,
    build_colmap_prompt,
    colmap_response_schema,
    parse_colmap_response,
    resolve_optional_default,
    resolve_required_default,
    resolve_required_stored,
    reset_mapping_state_on_file_change,
    NOT_AVAILABLE as NOT_AVAIL,
)


# KROMI presentation deck — pure content model (engine) + renderer (top-level
# presentation.py, kept out of the engine because it does python-pptx I/O).

# Technician overrides library — extracted to engine/overrides.py.
# Overrides are read from the database only (v34.23); the engine file
# functions remain solely as the foundation of tools/migrate_override_files.py.
from engine.overrides import (
    _safe_scope_component,
    pending_overrides_to_df,
)


def _resolve_active_overrides(customer: str, site: str):
    """The default override source for a run, resolved in one place.

    The newest active database set for the exact customer and site applies;
    since v34.23 the database is the only runtime source (the legacy file
    library is retired; tools/migrate_override_files.py brings old files into
    the database). Both the apply path and the editor's merge base use this
    resolver, so the base a technician diffs against is always the base that
    applied. Explicit choices are handled by the callers and keep precedence:
    live pending edits, a picker reload with a chosen set, and a reload with
    overrides disabled all bypass this.

    Returns (frame, source, set_id) with source "db", "none", or
    "unavailable" when the database could not be read (v34.48: reported to
    the user instead of silently running without overrides).
    """
    if _DB_AVAILABLE:
        try:
            _rc = _kromi_db.init_db(_resolve_db_path())
            try:
                _sid = _kromi_db.latest_override_set(
                    _rc, customer=customer, site=site
                )
                if _sid is not None:
                    return (
                        _kromi_db.override_set_as_dataframe(_rc, _sid),
                        "db",
                        int(_sid),
                    )
            finally:
                _rc.close()
        except Exception as _ov_exc:
            # A broken database never blocks a run, but it must not look like
            # "no overrides exist": the caller warns the user.
            log_exception("Override database could not be read", _ov_exc)
            return pd.DataFrame(columns=OVERRIDE_COLUMNS), "unavailable", None
    return pd.DataFrame(columns=OVERRIDE_COLUMNS), "none", None


# Per-SP presentation summary — extracted to engine/distribution.py.
# All five functions are pure (no UI, no I/O).
from ui import exports_panel, technician_panel
from engine.export_shaping import frame_token
from engine.distribution import (
    build_per_sp_summary,
    build_per_sp_distribution,
    build_per_sp_subclass_breakdown,
    build_per_sp_cabinet_occupation,
)

# Classifier-quality validation (overrides-based correction-rate analysis).
from engine.evaluation import evaluate_classification
from engine.run_fingerprint import FingerprintInputs, compute_run_fingerprint
from engine.plan import run_plan, PlanParams, PlanResult
from engine.plan_config import PlanConfig
from engine.run_prefs import get_file_prefs, save_file_prefs, file_key_for
from engine.kromi_numbering import (
    build_article_setup,
    order_article_setup,
    resolve_article_system,
)
from engine.workbook import build_article_setup_workbook
from engine.planning_defaults import (
    CALC_MODE_LABELS,
    DEDUP_MODE_LABELS,
    DEFAULTS,
    FIXED_MACHINE_KINDS,
    FIXED_MAX_SUPPLY_POINTS,
    NUMBERING_SYSTEM_LABELS,
    OP_MODE_LABELS,
    OP_STANDARD,
    SP_MODE_LABELS,
    YEAR_MODE_LABELS,
    label_index,
    token_for,
)
from engine.column_suggest import raw_guesses, suggest_columns
from engine.run_settings import (
    RunSettings,
    build_plan_params,
    calc_mode_from_label,
    effective_settings,
    program_mapping_active as _program_mapping_active,
    restock_slots_total,
    sp_mode_from_label,
)
from engine.tool_list import (
    ColumnMapping,
    add_classification_audit_columns,
    apply_export_display_columns,
    assign_supply_points,
    build_tool_list,
    distinct_programs,
    effective_mapping,
    mapping_collisions,
    resolve_override_scope,
    scope_value,
    unassigned_programs,
)
from engine.export_frames import (
    audit_frame,
    bucket_compare_frame,
    distribution_counts,
    distribution_volume,
    listings_in_data as _listings_in_data,
)
from engine.export_safety import csv_safe_frame
from app_log import log_exception
from engine.invariants import check_kromi_uniqueness
from engine.fixed_config import (
    FIXED_MODE,
    STATUS_NOT_PLACED,
    MachineSet,
    capacity_rows as _fixed_capacity_rows,
    usable_capacity as _fixed_usable_capacity,
)

# Fixed configuration (v34.52). The label is the selectbox option; the keys
# below are the sidebar controls that do not apply in that mode (hidden
# there, their values kept for the other modes).
_FIXED_MODE_LABEL = OP_MODE_LABELS[FIXED_MODE]
_FIXED_HIDDEN_KEYS = ("ks_fill_ceiling", "ks_rebalancer", "ks_empty_cab",
                      "ks_buffer", "ks_calc_mode", "ks_max_carousels")
_FIXED_MACHINE_KINDS = FIXED_MACHINE_KINDS
_FIXED_MAX_SP = FIXED_MAX_SUPPLY_POINTS
_FIXED_KEYS = ("ks_fixed_headroom", "ks_fixed_spill", "ks_fixed_stock_promo",
               "ks_fixed_stock_months") + tuple(
    f"ks_fixed_{_k}_{_sp}" for _sp in range(1, _FIXED_MAX_SP + 1)
    for _k, _lbl, _dflt in _FIXED_MACHINE_KINDS)


def _keep_widget_state(keys) -> None:
    """Keep the values of widgets that are not drawn on this pass.

    Streamlit drops a keyed widget's value when the widget is not rendered;
    re-assigning the key detaches it from that cleanup, so a control hidden
    by the fixed configuration mode comes back with the user's value."""
    for _key in keys:
        if _key in st.session_state:
            st.session_state[_key] = st.session_state[_key]


def _restore_banner_text(summary: Optional[Dict[str, Any]]) -> str:
    """The recompute banner's restore line (v34.54, audit C9)."""
    if not summary or not summary.get("total"):
        return ""
    text = (f" Restored {summary['restored']} of {summary['total']} stored "
            "settings.")
    dropped = summary.get("dropped") or []
    if dropped:
        text += (" Not restored (no longer in the workbook): "
                 + ", ".join(str(k) for k in dropped[:8])
                 + (" ..." if len(dropped) > 8 else "") + ".")
    return text


def _default_unless_seeded(key: str, default: Any) -> Dict[str, Any]:
    """``value=`` only when the key holds no value yet (restore, kept state)."""
    return {} if key in st.session_state else {"value": default}

# OpenAI transport and the cached batch call live in ui/ai_calls.py (v34.48):
# only successful batches are cached, so a failed batch is retried next run.
from ui.ai_calls import (
    AI_CALL_TIMEOUT_SECONDS,
    ai_classify_batch_cached,
    call_openai_structured as _call_openai_structured,
    get_openai_client,
)

# Cabinet math — extracted to engine/cabinet_math.py. The functions that read the
# plan config's runtime sizing factors are imported under an
# _engine_ alias and wrapped in a shim below that forwards the current value; the
# rest are imported directly.
from engine.cabinet_math import compute_helix_needs as _engine_compute_helix_needs, apply_operational_mode as _engine_apply_operational_mode


def _arrow_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Return a display copy that Streamlit can serialize to Arrow cleanly.

    st.dataframe serializes to Arrow. A passthrough column from the source file
    can hold mixed Python types (e.g. an order-number column where some rows are
    int and some str), which Arrow cannot infer: it logs a noisy ArrowTypeError
    and then auto-casts to string anyway. This pre-casts only the object columns
    whose non-null values are not all strings to string, so the table renders
    identically without the serialization error. Numeric, bool, and datetime
    columns are left untouched, so display formatting is unchanged for them.
    Used for previews that show raw/full frames with arbitrary source columns.
    """
    out = df.copy()
    for c in out.columns:
        s = out[c]
        if s.dtype == object:
            nonnull = s.dropna()
            if len(nonnull) and not all(isinstance(v, str) for v in nonnull):
                out[c] = s.map(
                    lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v))
                    else str(v)
                )
    return out


def compute_helix_needs(df: pd.DataFrame) -> Tuple[int, int]:
    """Shim: inject the current helix overfill factor from the plan config."""
    return _engine_compute_helix_needs(
        df,
        overfill_factor=_plan_cfg.helix_overfill_factor,
    )


def apply_operational_mode(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Shim: forward the page's current sizing factors."""
    return _engine_apply_operational_mode(
        df,
        mode,
        min_carousel_compartments=int(minimum_carousel_allocation),
        carousel_reserve_factor=_plan_cfg.carousel_reserve_factor,
        helix_overfill_factor=_plan_cfg.helix_overfill_factor,
    )






def _frame_token(df: pd.DataFrame) -> str:
    """Page-side name for the engine's cheap frame digest (v34.29)."""
    return frame_token(df)


@st.cache_data(max_entries=4, show_spinner=False)
def _cached_run_plan(plan_key: str, _work_df: pd.DataFrame,
                     _overrides_df: pd.DataFrame,
                     _params: PlanParams) -> PlanResult:
    """Content-addressed cache around the pure engine pipeline (v34.29 keying).

    The key is ``plan_key``: the vectorized frame tokens of the work and
    overrides frames plus a digest of the frozen params, computed once per
    pass. The frames themselves arrive underscore-prefixed so streamlit
    never serializes them for hashing, which keeps the per-click key cost
    flat as customer files grow. Everything that changes the plan changes
    the key: a technician correction, a manual size fix, an AI merge into
    the work frame, or any settings change is a miss; a plain widget rerun
    is a hit. A hit returns an unpickled fresh copy, so downstream mutation
    cannot bleed between reruns. max_entries=4 keeps the last few plans
    without letting result frames accumulate.
    """
    return run_plan(_work_df, _overrides_df, _params)


@st.cache_data(max_entries=4, show_spinner=False)
def _cached_prepare_planning_base(df: pd.DataFrame, dedup_mode: str, year_mode: str,
                                  has_year: bool) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Content-addressed cache around the deterministic planning-base prep.

    Streamlit hashes the mapped frame plus the three scalars, so the key is the
    content of the inputs: a new upload, a mapping change, the program-to-SP
    assignment written into the frame, or a dedup/year toggle each alters an
    input and recomputes; a plain widget rerun is a hit. A hit returns a fresh
    unpickled copy, so downstream mutation cannot bleed between reruns. The
    dedup-conflict scan inside the preparation is the dominant per-rerun cost
    this removes.
    """
    return prepare_planning_base(df, dedup_mode=dedup_mode, year_mode=year_mode,
                                 has_year=has_year)


@st.cache_data(max_entries=4, show_spinner=False)
def _cached_pre_ai_heuristics(df: pd.DataFrame, enable_pack_hint_extraction: bool,
                              insert_default_pack_units: float) -> pd.DataFrame:
    """Content-addressed cache around the deterministic pre-AI boundary passes
    (engine.boundary.apply_pre_ai_heuristics). Streamlit hashes the frame and
    the two knobs; a plain rerun is a hit that returns a fresh unpickled copy,
    any data or knob change recomputes."""
    return apply_pre_ai_heuristics(
        df, enable_pack_hint_extraction=enable_pack_hint_extraction,
        insert_default_pack_units=insert_default_pack_units)


@st.cache_data(max_entries=4, show_spinner=False)
def _cached_post_ai_safety(df: pd.DataFrame,
                           insert_default_pack_units: float) -> pd.DataFrame:
    """Content-addressed cache around the final safety pass
    (engine.boundary.apply_post_ai_safety). Same key doctrine as above; the AI
    stage between the two passes changes the frame content whenever it applies
    anything, which changes this key and recomputes."""
    return apply_post_ai_safety(
        df, insert_default_pack_units=insert_default_pack_units)


@st.cache_data(max_entries=8, show_spinner=False)
def _cached_load_stored_classifications(db_path: str, content_sha: str) -> Dict[str, Dict[str, Any]]:
    """Classifications stored for the exact workbook identified by its digest
    (I4). Keyed on the database path plus the digest, so isolated databases
    (tests, golden drives on throwaway paths) never cross-hit. Returns an
    empty mapping when the database layer is unavailable, the file is unknown,
    or nothing is stored for it; the caller treats empty as "no reuse"."""
    if not _DB_AVAILABLE:
        return {}
    try:
        conn = _kromi_db.init_db(db_path)
        try:
            row = _kromi_db.get_file_by_hash(conn, content_sha)
            if row is None:
                return {}
            # Reuse only authoritative answers, the newest of them per code
            # (v34.53: a later heuristic run no longer hides an AI answer).
            # Heuristic, Provided, and Default rows re-derive identically from
            # the same bytes, and pinning a stored 'other' would also subtract
            # the row from the AI candidates, blocking a later AI-enabled
            # re-upload from ever improving it. The reload path is untouched:
            # a run snapshot is reused in full, since a recompute wants that
            # run's exact state.
            _all = _kromi_db.classifications_by_code(
                conn, file_id=int(row["file_id"]), sources=("ai", "manual"))
            return {
                c: rec for c, rec in _all.items()
                if str(rec.get("source", "")).strip().lower() in ("ai", "manual")
            }
        finally:
            conn.close()
    except Exception as _cls_exc:
        log_exception("Stored classifications could not be read", _cls_exc)
        return {}


# Database persistence (Phase 1 dual-write). Imported defensively: if the data
# layer is unavailable for any reason the planner must still run, so a failure
# here only disables the database copy, never the calculation or the export.
try:
    import db as _kromi_db
    _DB_AVAILABLE = True
except Exception:  # pragma: no cover - defensive
    _kromi_db = None
    _DB_AVAILABLE = False


def _resolve_db_path() -> str:
    """Local, non-synced path for the database. Overridable with KROMI_DB_PATH.
    Defaults to a per-user directory so it never lands in a synced folder."""
    env = os.getenv("KROMI_DB_PATH")
    if env:
        path = env
    else:
        path = os.path.join(
            os.path.expanduser("~"), ".kromi_cabinet_planner", "kromi.db"
        )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


class _BytesFile(BytesIO):
    """Minimal stand-in for an uploaded file, backed by stored workbook bytes.
    Carries a name and size so the parse and the content-hash path treat it
    exactly like a real upload."""

    def __init__(self, data: bytes, name: str, file_id: str | None = None):
        super().__init__(data)
        self.name = name
        self.size = len(data)
        # Content-true identity (audit C1): stored runs carry their content
        # hash, so two same-name, same-length files can never share an
        # identity the way (name, size) allowed.
        if file_id is not None:
            self.file_id = file_id


def _file_identity(f):
    """The one file-identity expression: the uploader's or shim's file_id
    when present, else (name, size). Shared by the upload memo, the
    mapping-state reset, and the pending-corrections signature (audit C1)."""
    return getattr(f, "file_id", None) or (
        getattr(f, "name", None), getattr(f, "size", None),
    )


def _stored_workbook_columns(content, sheet, header_row: Any = 1) -> list:
    """Column headers of a stored workbook's Tools sheet at the run's header
    row, used to validate a restored column mapping before it is seeded.
    Returns [] on any failure."""
    try:
        bio = BytesIO(bytes(content))
        try:
            hdr = max(0, int(header_row) - 1)
        except (TypeError, ValueError):
            hdr = 0
        if sheet and sheet not in ("— not used —",):
            df0 = pd.read_excel(bio, sheet_name=sheet, nrows=0, header=hdr)
        else:
            df0 = pd.read_excel(bio, nrows=0, header=hdr)
        return [str(c) for c in df0.columns]
    except Exception:
        return []


def _stored_workbook_sheets(content) -> list:
    """Sheet names of a stored workbook ([] on any failure)."""
    try:
        return [str(n) for n in pd.ExcelFile(BytesIO(bytes(content))).sheet_names]
    except Exception:
        return []


def _render_loaded_snapshot(snap: dict) -> None:
    """Render a stored run exactly as it was delivered. Read-only: every number
    comes from the stored snapshot, nothing is recomputed."""
    run = snap["run"]
    snap_build = snap.get("build_version")
    if snap_build and snap_build != BUILD:
        st.warning(
            f"This run was saved on {snap_build}; the engine is now {BUILD}. "
            "The result below is the stored snapshot as it was delivered. To "
            "recompute on the current engine, switch to 'Upload a new file' and "
            "run the file again."
        )
    elif not snap_build:
        st.info(
            f"This run predates build-version tracking; the engine is now {BUILD}. "
            "The result below is the stored snapshot as it was delivered."
        )
    else:
        st.caption(f"Saved on build {snap_build}, which matches the current engine.")

    st.subheader(
        f"Run #{run['run_id']} — {snap.get('customer') or '?'} / {snap.get('site') or '?'}"
    )
    st.caption(
        f"Saved {snap.get('created_at')}  ·  file: {snap.get('filename') or '?'}  ·  "
        f"mode: {snap.get('operational_mode') or 'Standard'}  ·  status: {snap.get('status')}"
    )

    grand = snap.get("grand") or {}
    if grand:
        m = st.columns(5)
        m[0].metric("Total cabinets", grand.get("total_cabs", 0))
        m[1].metric("Helix", grand.get("helix_cabs", 0))
        m[2].metric("Carousel", grand.get("car_cabs", 0))
        m[3].metric(
            "Lockers",
            grand.get("cabA", 0) + grand.get("cabB", 0) + grand.get("cabC", 0),
        )
        m[4].metric("Spirals", grand.get("total_spirals", 0))

    bucket_plans = snap.get("bucket_plans") or []
    if bucket_plans:
        st.markdown("**Plan by bucket**")
        bp_df = pd.DataFrame([{
            "Bucket": lbl,
            "Helix": p.get("helix_cabs", 0),
            "Carousel": p.get("car_cabs", 0),
            "Locker A": p.get("cabA", 0),
            "Locker B": p.get("cabB", 0),
            "Locker C": p.get("cabC", 0),
            "Total": p.get("total_cabs", 0),
            "Spirals": p.get("total_spirals", 0),
            "Carousel slots": p.get("car_slots", 0),
        } for lbl, p in bucket_plans])
        st.dataframe(bp_df, width="stretch", hide_index=True)

    work = snap.get("work")
    if work is not None and len(work) > 0:
        st.markdown("**Result**")
        st.dataframe(work, width="stretch", hide_index=True)
        # Text that Excel would evaluate is apostrophe-quoted (v34.48).
        csv = csv_safe_frame(work).to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download result (CSV)",
            csv,
            file_name=f"run_{run['run_id']}_result.csv",
            mime="text/csv",
            key="_load_dl",
        )


def _render_load_previous_run() -> None:
    """Picker for stored runs plus the snapshot view for the selected one. Opens
    and closes its own database connection so the rest of the page is unaffected."""
    st.header("Load a previous run")
    st.caption(
        "Shows a saved run exactly as it was delivered. The cabinet sizing is "
        "read from the stored result, not recomputed."
    )
    conn = None
    try:
        conn = _kromi_db.init_db(_resolve_db_path())
        c1, c2 = st.columns(2)
        with c1:
            q_customer = st.text_input("Filter by customer", key="_load_q_customer")
        with c2:
            q_site = st.text_input("Filter by site", key="_load_q_site")

        runs = _kromi_db.list_runs_for_picker(
            conn,
            customer=(q_customer.strip() or None),
            site=(q_site.strip() or None),
            limit=100,
        )
        if not runs:
            st.info(
                "No saved runs found. Completed runs are saved automatically; "
                "run a plan and it will appear here."
            )
            return

        runs_df = pd.DataFrame([{
            "Run": r["run_id"],
            "Saved (UTC)": r["created_at"],
            "Customer": r["customer"] or "",
            "Site": r["site"] or "",
            "KTC": r["ktc_id"] or "",
            "File": r["filename"] or "",
            "Mode": r["operational_mode"] or "Standard",
            "Cabinets": r["total_cabs"] if r["total_cabs"] is not None else "",
            "Build": r["build_version"] or "—",
            "Status": r["status"] or "",
        } for r in runs])
        st.dataframe(runs_df, width="stretch", hide_index=True)

        ids = [r["run_id"] for r in runs]
        labels = {
            r["run_id"]: f"#{r['run_id']} · {r['customer'] or '?'} / {r['site'] or '?'} · {r['created_at']}"
            for r in runs
        }
        sel = st.selectbox(
            "Select a run",
            ids,
            format_func=lambda i: labels.get(i, str(i)),
            key="_load_sel",
        )

        # Override source for the recompute. The plain snapshot ignores this; it
        # only affects "Load & recompute". Options are the file library, no
        # overrides, or any database override set saved for the run's scope.
        _sel_run = next((r for r in runs if r["run_id"] == sel), None)
        _ov_map = {"Newest saved set for this customer and site (default)": ("file", None),
                   "No overrides": ("none", None)}
        if _sel_run is not None:
            for s in _kromi_db.list_override_sets(
                conn, customer=_sel_run["customer"], site=_sel_run["site"]
            ):
                label = _kromi_db.format_override_set_label(s)
                _ov_map[label] = ("db", s["set_id"])
        # v34.54 (audit C9): preselect what the run itself applied - its
        # override set if it still exists, "No overrides" if it ran without.
        _ov_labels = list(_ov_map.keys())
        _ov_default = 0
        try:
            _sel_row = _kromi_db.get_run(conn, sel)
            _sel_ov = ((json.loads(_sel_row["settings_json"] or "{}") or {}).get("overrides")
                       if _sel_row is not None else None) or {}
        except Exception:
            _sel_ov = {}
        if _sel_ov.get("source") in ("none", "off"):
            _ov_default = _ov_labels.index("No overrides")
        elif _sel_ov.get("source") == "db":
            _ov_default = next((i for i, lbl in enumerate(_ov_labels)
                                if _ov_map[lbl] == ("db", _sel_ov.get("set_id"))), 0)
        _ov_choice = st.selectbox(
            "Overrides for recompute",
            _ov_labels,
            index=_ov_default,
            key=f"_recompute_ov_source_{sel}",
            help=("Used only by 'Load & recompute'. The plain snapshot is "
                  "unaffected. Preselected: what the run applied."),
        )
        _ov_mode, _ov_set_id = _ov_map[_ov_choice]

        b1, b2 = st.columns(2)
        with b1:
            if st.button("Load (plain snapshot)", type="primary", key="_load_btn"):
                st.session_state["_loaded_run_id"] = sel
        with b2:
            if st.button("Load & recompute (current engine)", key="_load_recompute_btn"):
                run_row = _kromi_db.get_run(conn, sel)
                file_row = (
                    _kromi_db.get_file(conn, run_row["file_id"])
                    if run_row is not None else None
                )
                if file_row is not None and file_row["content"] is not None:
                    # Restore the run's controls and column mapping so the
                    # recompute reproduces the original (only the engine differs).
                    # Older runs that predate the saved snapshot restore nothing,
                    # which is fine — they fall back to the current controls.
                    _restore_bundle = {}
                    _restore_report = None
                    _settings = {}
                    try:
                        _sj = (
                            run_row["settings_json"]
                            if "settings_json" in run_row.keys() else None
                        )
                        _settings = (json.loads(_sj) or {}) if _sj else {}
                        _ui = _settings.get("ui_state")
                        if _ui:
                            # Validate at the run's own header row (v34.54: a
                            # banner-row file lost its whole mapping because
                            # the columns were read from row 1).
                            _cols = _stored_workbook_columns(
                                file_row["content"], _ui.get("ks_sheet_tools"),
                                header_row=_ui.get("ks_header_row") or 1,
                            )
                            _restore_bundle = _run_restore.build_seed(
                                _ui, _cols,
                                sheet_names=_stored_workbook_sheets(file_row["content"]),
                            )
                            _restore_report = _run_restore.restore_summary(_ui, _restore_bundle)
                            # The picker's override choice governs the apply.
                            _restore_bundle["ks_apply_overrides"] = _ov_mode != "none"
                            # Same workbook: keep the restored optional mapping
                            # instead of the new-file reset (v34.54).
                            _restore_bundle["_mapping_file_id"] = ("content", file_row["sha256"])
                            # Render the restored mapping and never fire an AI
                            # column-mapping call during a recompute.
                            _restore_bundle["ks_hide_optional"] = False
                            _restore_bundle["ks_ai_colmap"] = False
                            # Match the standard/special coverage layout on the
                            # first recompute render (the flag is otherwise set
                            # only after the mapping resolves, one rerun later).
                            _ss = _ui.get("cm_stdspecial")
                            _restore_bundle["_std_special_mapped"] = bool(
                                isinstance(_ss, str)
                                and _ss not in ("", _run_restore.NOT_AVAIL)
                                and _ss in _cols
                            )
                    except Exception as _rb_exc:
                        log_exception("Stored run settings could not be restored", _rb_exc)
                        _restore_bundle = {}
                        _restore_report = None
                        _settings = {}
                    if _restore_bundle:
                        st.session_state["_pending_restore"] = _restore_bundle
                    st.session_state["_reload_ctx"] = {
                        "run_id": sel,
                        "bytes": bytes(file_row["content"]),
                        "filename": file_row["original_filename"] or "stored_run.xlsx",
                        "customer": run_row["customer"],
                        "site": run_row["site"],
                        "ktc_id": run_row["ktc_id"],
                        "customer_label": _settings.get("customer_label"),
                        "restore_summary": _restore_report,
                        "classifications": _kromi_db.classifications_by_code(conn, run_id=sel),
                        "override_mode": _ov_mode,
                        "override_set_id": _ov_set_id,
                        "sha256": file_row["sha256"],
                    }
                    # A picker reload is a deliberate fresh choice of overrides,
                    # so drop any corrections accumulated in the editor; the
                    # picker's own override_mode now governs the apply.
                    st.session_state.pop("_pending_overrides", None)
                    # A run switch is a new source of truth: never let the
                    # previous file's memoized bytes survive it (audit C1).
                    st.session_state.pop("_upload_bytes_memo", None)
                    st.rerun()
                else:
                    st.warning(
                        "This run has no stored workbook (older imported runs do "
                        "not keep one), so it can only be shown as a plain snapshot."
                    )

        loaded_id = st.session_state.get("_loaded_run_id")
        if loaded_id is not None:
            snap = _kromi_db.load_run_snapshot(conn, loaded_id)
            st.divider()
            if snap is None:
                st.error("That run could not be loaded.")
            else:
                _render_loaded_snapshot(snap)
    finally:
        if conn is not None:
            conn.close()


def _save_override_set_dialog_body(diffs, customer, site, reviewer_default) -> None:
    """Dialog body: capture reviewer, scope, and notes, then save the corrections
    as a database override set. Saves the full snapshot (the current file library
    plus these edits) so the set is self-contained."""
    st.write(f"{len(diffs)} correction(s) will be saved as a versioned set.")
    reviewer = st.text_input("Your name", value=reviewer_default or "", key="_ovset_reviewer")
    cust = st.text_input(
        "Customer", value=("" if customer == "default" else customer), key="_ovset_customer"
    )
    site_in = st.text_input(
        "Site", value=("" if site == "default" else site), key="_ovset_site"
    )
    notes = st.text_area("Notes (optional)", key="_ovset_notes")

    # Destination choice (v33.67): re-saving a scope can either create a new set
    # or replace an existing one in place, so corrections for the same customer
    # and site stop piling up as duplicate sets. The lookup uses the scope as
    # currently typed, and "Save as a new set" stays the default so nothing
    # changes unless the reviewer deliberately picks an existing set to update.
    _existing_sets: list = []
    try:
        _scope_conn = _kromi_db.init_db(_resolve_db_path())
        try:
            # Exact scope (v34.50): a blank field means "no customer/site",
            # never "every set", and partial names match nothing.
            _existing_sets = _kromi_db.list_override_sets(
                _scope_conn,
                customer=cust.strip(),
                site=site_in.strip(),
            )
        finally:
            _scope_conn.close()
    except Exception:
        _existing_sets = []

    _update_target = None
    if _existing_sets:
        _mode = st.radio(
            "Destination",
            ("Save as a new set", "Update an existing set"),
            key="_ovset_mode",
            horizontal=True,
            help=(
                "Updating replaces the chosen set's corrections in place (same "
                "set, refreshed contents) instead of adding another set for this "
                "customer and site."
            ),
        )
        if _mode == "Update an existing set":
            _set_labels = {
                _kromi_db.format_override_set_label(s): s["set_id"]
                for s in _existing_sets
            }
            _chosen = st.selectbox(
                "Set to update", list(_set_labels.keys()), key="_ovset_update_pick"
            )
            _update_target = _set_labels.get(_chosen)

    if st.button("Save to database", type="primary", key="_ovset_save_btn"):
        now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
        new_rows = []
        for d in diffs:
            row = {c: "" for c in OVERRIDE_COLUMNS}
            row["code"] = d["code"]
            row["listing"] = d["listing"]
            row["product_category_override"] = d.get("product_category_override", "")
            row["pack_units_override"] = d.get("pack_units_override", "")
            row["size_category_override"] = d.get("size_category_override", "")
            row["cabinet_type_override"] = d.get("cabinet_type_override", "")
            row["vend_mode_override"] = d.get("vend_mode_override", "")
            row["restocking_override"] = d.get("restocking_override", "")
            row["note"] = d.get("note", "")
            row["reviewed_by"] = reviewer.strip() or "unknown"
            row["reviewed_at"] = now_utc
            new_rows.append(row)
        edits_df = pd.DataFrame(new_rows, columns=OVERRIDE_COLUMNS)
        if _update_target is None:
            # A new set starts from the corrections that currently apply to
            # this scope, plus the edits.
            current, _cur_ov_source, _cur_ov_set_id = _resolve_active_overrides(customer, site)
            if _cur_ov_source == "unavailable":
                # Saving on top of an empty stand-in base would drop every
                # stored correction of the current set (v34.48).
                st.error(
                    "The override database could not be read, so nothing was saved. "
                    "Your corrections are still pending in this session; try again "
                    "once the database is reachable.")
                return
            merged = pd.concat([current, edits_df], ignore_index=True)
        try:
            with st.spinner("Saving override set to the database…"):
                conn = _kromi_db.init_db(_resolve_db_path())
                try:
                    if _update_target is not None:
                        # v34.50 (audit C12): the edits merge onto the chosen
                        # set's own rows, not onto the newest set of the
                        # page's scope.
                        _n_saved = _kromi_db.update_override_set_with_edits(
                            conn,
                            _update_target,
                            edits_df=edits_df,
                            customer=(cust.strip() or None),
                            site=(site_in.strip() or None),
                            reviewer_name=(reviewer.strip() or None),
                            notes=(notes.strip() or None),
                        )
                        set_id = _update_target
                        _verb = "Updated"
                    else:
                        set_id = _kromi_db.save_override_set(
                            conn,
                            customer=(cust.strip() or None),
                            site=(site_in.strip() or None),
                            reviewer_name=(reviewer.strip() or None),
                            notes=(notes.strip() or None),
                            overrides_df=merged,
                        )
                        _verb = "Saved"
                        _n_saved = len(merged)
                finally:
                    conn.close()
            st.session_state["_ovset_saved"] = (
                f"{_verb} override set #{set_id} with {_n_saved} correction(s) "
                "to the database. The corrections stay applied to the plan."
            )
            # The accumulated corrections already apply via the editor's live
            # pending map, so saving only persists them for reuse; no separate
            # recompute is needed.
            st.rerun()
        except Exception as exc:  # pragma: no cover - UI path
            log_exception("Override set could not be saved", exc)
            st.error(f"Could not save to the database: {exc}")


# The decorator runs at import, so guard it: a Streamlit without st.dialog must
# not break the page. When unavailable, the database-save button is simply hidden.
if hasattr(st, "dialog"):
    _save_override_set_dialog = st.dialog("Save overrides as a database set")(
        _save_override_set_dialog_body
    )
else:  # pragma: no cover - depends on Streamlit version
    _save_override_set_dialog = None


# STREAMLIT UI
st.set_page_config(
    page_title="Cabinet Planner — Kromi Logistik",
    page_icon="assets/kromi_favicon.png",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "Cabinet Planner — Kromi Logistik GmbH",
    },
)

from styling import apply_kromi_theme
apply_kromi_theme(
    page_title="Kromi Cabinet Planner",
    tagline=build_stamp(),
    version=BUILD,
)

# Landing choice: upload a new file or load a stored run (Phase 3). The default
# is the existing upload flow, which runs untouched. Choosing to load a run
# renders the stored snapshot read-only and stops before the upload/compute
# path. When a recompute is requested, a reload context is set and the page
# falls through to the real compute flow, which reads the stored workbook bytes
# and reuses the saved classifications instead of calling the model.
_reload_ctx = st.session_state.get("_reload_ctx")

# Apply a one-shot widget restore, set by "Load & recompute", before any control
# or column-mapping widget is created. Seeding a widget's session_state is only
# legal before that widget is instantiated, so this runs at the top of the script
# and clears itself; the user can still change any control afterwards.
_pending_restore = st.session_state.pop("_pending_restore", None)
if _pending_restore:
    for _rk, _rv in _pending_restore.items():
        st.session_state[_rk] = _rv

if _reload_ctx:
    st.info(
        f"Recomputing stored run #{_reload_ctx['run_id']} on the current engine "
        f"({BUILD}), reusing its saved classifications (no AI call). "
        + (
            "No technician overrides are applied."
            if _reload_ctx.get("override_mode") == "none" else
            f"Override set #{_reload_ctx.get('override_set_id')} is applied."
            if _reload_ctx.get("override_mode") == "db" and _reload_ctx.get("override_set_id") else
            "The newest saved override set for the run's customer and site "
            "applies, if there is one."
        )
        + _restore_banner_text((_reload_ctx or {}).get("restore_summary"))
    )
    if st.button("Clear and return to upload / picker", key="_clear_reload"):
        del st.session_state["_reload_ctx"]
        st.rerun()
else:
    _start_mode = "Upload a new file"
    if _DB_AVAILABLE:
        _start_mode = st.radio(
            "Start from",
            ["Upload a new file", "Load a previous run"],
            horizontal=True,
            key="_start_mode",
        )

    if _start_mode == "Load a previous run":
        with st.sidebar:
            if st.button("← Back to picker", key="back_to_home_load", width="stretch"):
                st.switch_page("Home.py")
        _render_load_previous_run()
        st.stop()


# The operational mode is chosen on the main screen, below the sidebar in
# script order; the sidebar reads its current value to show only the
# controls that apply (v34.52).
_fixed_mode_ui = st.session_state.get("ks_op_mode") == _FIXED_MODE_LABEL

with st.sidebar:
    if st.button("← Back to picker", key="back_to_home_kromi", width="stretch"):
        st.switch_page("Home.py")
    st.header("Controls")

    usage_threshold = st.number_input(
        "KTC / Kanban threshold (pieces per month)",
        key="ks_ktc_threshold",
        min_value=0.0,
        value=DEFAULTS.ktc_threshold,
        step=0.1,
        help=(
            "Items below this monthly piece rate are routed to Kanban "
            "(warehouse), not the vending machine. The KTC/Kanban decision is "
            "based on monthly pieces; physical sizing (spirals, slots) still "
            "uses packs."
        ),
    )

    # Optional per-tool-class thresholds, edited in a popup so they don't crowd
    # the sidebar. Every class (inserts included) defaults to the standard
    # threshold; the routing only diverges for classes the user changes here, and
    # only while these controls are active. Committed values + the active flag
    # live in session_state and survive reruns.
    _adv_active = bool(st.session_state.get("adv_thr_active", False))
    _adv_vals = dict(st.session_state.get("adv_thr_vals", {}))

    def _threshold_controls_body(commit_label: str, cancel_label: str):
        st.caption(
            "Per-tool-class KTC/Kanban thresholds (pieces per month). Each "
            "defaults to the standard threshold above; change only the classes "
            "that should differ. Applies to inserts too."
        )
        _vals = {}
        _cur = dict(st.session_state.get("adv_thr_vals", {}))
        _cols = st.columns(2)
        for _i, _cat in enumerate(THRESHOLD_CATEGORIES):
            with _cols[_i % 2]:
                _vals[_cat] = float(st.number_input(
                    _cat.replace("_", " ").title(),
                    min_value=0.0,
                    value=float(_cur.get(_cat, usage_threshold)),
                    step=0.5,
                    key=f"adv_thr_in_{_cat}",
                ))
        _bcols = st.columns(3)
        if _bcols[0].button(commit_label, type="primary", key="adv_thr_commit"):
            st.session_state["adv_thr_vals"] = _vals
            st.session_state["adv_thr_active"] = True
            st.rerun()
        # v34.51: closing no longer switches active thresholds off; that is
        # the separate, explicitly labelled reset button.
        if _bcols[1].button("Close without changes", key="adv_thr_close"):
            st.rerun()
        if _bcols[2].button(cancel_label, key="adv_thr_cancel"):
            st.session_state["adv_thr_active"] = False
            st.rerun()

    _btn_label = "Threshold controls" + ("  ✓ active" if _adv_active else "")
    _st_dialog = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if _st_dialog is not None:
        @_st_dialog("Threshold controls")
        def _open_threshold_dialog():
            _threshold_controls_body("OK", "Use standard for all")
        if st.button(_btn_label, key="adv_thr_open"):
            _open_threshold_dialog()
    else:
        # Streamlit < 1.37 has no modal dialog; fall back to an anchored popover.
        with st.popover(_btn_label):
            _threshold_controls_body("Apply", "Use standard for all")

    optional_thresholds_active = bool(st.session_state.get("adv_thr_active", False))
    per_class_thresholds: dict = (
        dict(st.session_state.get("adv_thr_vals", {})) if optional_thresholds_active else {}
    )
    if optional_thresholds_active:
        _diff = {k: v for k, v in per_class_thresholds.items()
                 if abs(float(v) - float(usage_threshold)) > 1e-9}
        st.caption(
            "Per-class thresholds active: "
            + (", ".join(f"{k}={v:g}" for k, v in sorted(_diff.items()))
               if _diff else "all classes at the standard value")
        )

    insert_default_pack_units = st.number_input(
        "Insert default packing unit",
        key="ks_insert_pack",
        min_value=1,
        value=DEFAULTS.insert_pack_units,
        step=1,
        help=(
            "Inserts are standardised to this many pieces per pack for sizing "
            "(KROMI inserts ship in fixed boxes). This value replaces the pack "
            "size on every row classified as an insert. Set it to match your "
            "insert box size; the default is 10."
        ),
    )

    helix_threshold = st.number_input(
        "Helix threshold (packs per month)",
        key="ks_helix_threshold",
        min_value=0.0,
        value=DEFAULTS.helix_threshold,
        step=0.5,
        help="Items above this monthly pack rate go to Helix (spiral dispensing); below go to Carousel (slot stockpiles).",
    )

    consumption_period_months = st.number_input(
        "Consumption period in months",
        key="ks_consumption_months",
        min_value=1.0,
        value=DEFAULTS.consumption_months,
        step=1.0,
        help="How many months the consumption figures cover. 12 for annual, 3 for quarter, 1 for monthly.",
    )

    helix_single_spiral_overfill_factor_ui = st.number_input(
        "Helix single-spiral overfill factor",
        key="ks_overfill",
        min_value=1.0,
        value=DEFAULTS.helix_overfill_factor,
        step=0.01,
        help="Allow one spiral to hold up to capacity x this factor before adding a second spiral.",
    )

    minimum_carousel_allocation = st.number_input(
        "Minimum Carousel compartments per KTC item",
        key="ks_min_carousel",
        min_value=1,
        value=DEFAULTS.min_carousel_allocation,
        step=1,
        help="Every KTC item routed to Carousel gets at least this many compartments. Protects against stockouts on refill day. Truly low-volume items should be filtered to Kanban via the KTC threshold.",
    )

    _std_special_mapped = st.session_state.get("_std_special_mapped", False)
    if _std_special_mapped:
        coverage_days = st.number_input(
            "On-machine stock coverage (standard, in days)",
            min_value=1, max_value=90, value=DEFAULTS.coverage_days, step=1, key="cov_days_standard",
            help="Days of stock between refills for tools marked Standard. Affects sizing only, not the KTC/Kanban split.",
        )
        coverage_days_special = st.number_input(
            "On-machine stock coverage (special, in days)",
            min_value=1, max_value=90, value=DEFAULTS.coverage_days_special, step=1, key="cov_days_special",
            help="Days of stock between refills for tools marked Special (from the mapped Standard/Special column).",
        )
        st.checkbox(
            "Set special tools as KTC",
            value=DEFAULTS.special_ktc, key="ks_special_ktc",
            help=(
                "Force every tool marked Special (in the mapped Standard/Special "
                "column) onto a vending machine regardless of its consumption. "
                "This raises the cabinet count and storage sizing accordingly. "
                "Rows already fixed by a mapped System type column keep that "
                "decision. Left off, the Standard/Special column only splits "
                "coverage days and does not change the KTC/Kanban routing."
            ),
        )
    else:
        coverage_days = st.number_input(
            "On-machine stock coverage (days)",
            min_value=1, max_value=90, value=DEFAULTS.coverage_days, step=1, key="cov_days_standard",
            help="Days of stock to keep in the cabinet between refills. Affects sizing only, not KTC/Kanban split. Map a Standard/Special column to split this into two values.",
        )
        coverage_days_special = coverage_days

    carousel_reserve_factor_ui = st.number_input(
        "Carousel reserve factor",
        key="ks_reserve",
        min_value=0.05,
        max_value=2.00,
        value=DEFAULTS.carousel_reserve_factor,
        step=0.05,
        help="Multiplier on Target_packs when sizing Carousel stockpiles. Lower for fast replenishment, higher for deep buffer.",
    )

    if _fixed_mode_ui:
        # Fixed configuration (v34.52): the machines exist and the headroom is
        # set with them, so the capacity buffer, the fill ceiling and the
        # cabinet consolidation do not apply. They are not shown; their
        # values are kept for the other modes.
        _keep_widget_state(_FIXED_HIDDEN_KEYS)
        carousel_fill_ceiling_ui = 1.0
        enable_rebalancer = False
        underuse_threshold_pct = float(st.session_state.get("ks_empty_cab", DEFAULTS.underuse_threshold_pct))
        capacity_buffer_pct = 0.0
        st.caption(
            "Fixed configuration: the headroom set with the machines replaces "
            "the capacity buffer, the Carousel fill ceiling and the cabinet "
            "consolidation.")
    else:
        carousel_fill_ceiling_ui = st.number_input(
            "Carousel fill ceiling",
            key="ks_fill_ceiling",
            min_value=0.50,
            max_value=1.00,
            value=DEFAULTS.carousel_fill_ceiling,
            step=0.05,
            help="Fraction of a Carousel's physical slots the plan may fill before opening the next cabinet. 1.00 packs cabinets fully; lower values leave operational headroom per cabinet at the cost of more cabinets.",
        )

        enable_rebalancer = st.checkbox(
            "Consolidate underused cabinets",
            key="ks_rebalancer",
            value=DEFAULTS.enable_rebalancer,
            help="When a cabinet ends up below the empty-cabinet threshold, try to move its items into other cabinets with headroom. The audit shows what moved.",
        )

        underuse_threshold_pct = st.number_input(
            "Empty-cabinet threshold (%)",
            key="ks_empty_cab",
            min_value=5.0,
            max_value=80.0,
            value=DEFAULTS.underuse_threshold_pct,
            step=5.0,
            help="If the last cabinet of a type is below this occupation, the rebalancer tries to absorb its items elsewhere.",
            disabled=not enable_rebalancer,
        )

        capacity_buffer_pct = st.number_input(
            "Capacity buffer (%)",
            key="ks_buffer",
            min_value=0.0,
            max_value=200.0,
            value=DEFAULTS.capacity_buffer_pct,
            step=5.0,
            help="Extra capacity on top of calculated need. Applied to spirals, stockpiles and locker items before the final cabinet count.",
        )

    st.divider()
    st.subheader("Vend-mode controls")

    enable_pack_hint_extraction = st.checkbox(
        "Extract pack sizes from descriptions (qte 50, carton de 60, ...)",
        key="ks_pack_hint",
        value=DEFAULTS.pack_hint_extraction,
        help="Scans descriptions for packaging hints before falling back to category defaults. Only fills PackUnits that would otherwise default to 1.",
    )

    enable_bulk_routing = st.checkbox(
        "Route bulk-consumable families out of vending (abrasives, paint cups, tapes, wipes)",
        key="ks_bulk_routing",
        value=DEFAULTS.bulk_routing,
        help="Tags abrasive discs, paint cups, tapes, wipes and sealants as Bulk/Kanban and removes their spirals/stockpiles from the vending plan. These belong on shelf, not in the machine.",
    )

    force_screws_accessories_kanban = st.checkbox(
        "Set screws and accessories as Kanban",
        key="ks_force_screws",
        value=DEFAULTS.force_screws_kanban,
        help="Forces every item classified as screws or accessories into Kanban, regardless of consumption rate.",
    )

    st.divider()
    st.subheader("Supply points & listings")

    n_supply_points = st.number_input(
        "Number of supply points",
        key="ks_n_sp",
        min_value=1,
        max_value=10,
        value=DEFAULTS.n_supply_points,
        step=1,
        help="Physical supply locations in the plant. When greater than 1, items are split per supply point per the mode below.",
    )

    sp_mode_ui = st.radio(
        "Supply-point mode",
        key="ks_sp_mode",
        options=list(SP_MODE_LABELS.values()),
        index=label_index(SP_MODE_LABELS, DEFAULTS.sp_mode),
        help=(
            "Replicate: the same item is stocked at every supply point; consumption is divided by N. "
            "Partition: each item lives at one supply point only (rare; for highly area-specific tooling)."
        ),
    )

    if _fixed_mode_ui:
        # The configured machines serve every listing (v34.52).
        calc_mode_ui = "Combined (one vending machine plan for both)"
    else:
        calc_mode_ui = st.radio(
            "Tools + PPE handling (only applies when both listings are provided)",
            key="ks_calc_mode",
            options=list(CALC_MODE_LABELS.values()),
            index=label_index(CALC_MODE_LABELS, DEFAULTS.calc_mode),
        )

    use_description_2 = st.checkbox(
        "Use Description_2 (if available)",
        key="ks_use_desc2",
        value=DEFAULTS.use_description_2,
    )

    st.divider()
    st.subheader("Planning base")

    year_mode_ui = st.selectbox(
        "Year handling",
        key="ks_year_mode",
        options=list(YEAR_MODE_LABELS.values()),
        index=label_index(YEAR_MODE_LABELS, DEFAULTS.year_mode),
        help="Only applied if a Year column is mapped and contains usable years.",
    )

    dedup_mode_ui = st.selectbox(
        "Deduplicate planning rows",
        key="ks_dedup_mode",
        options=list(DEDUP_MODE_LABELS.values()),
        index=label_index(DEDUP_MODE_LABELS, DEFAULTS.dedup_mode),
        help="Recommended when the source contains repeated rows across years, suppliers, or transactions.",
    )

    if _reload_ctx:
        # Recompute reuses the run's saved classifications, so the model is not
        # called; the checkbox is hidden in this mode.
        use_ai = False
        st.caption("Reusing saved classifications from the stored run (no AI call).")
    else:
        # v34.51: on by default only when a key is configured; without one
        # every batch failed after Run and the user learned it only then.
        _ai_key_present = bool(os.getenv("OPENAI_API_KEY", "").strip())
        use_ai = st.checkbox(
            "Use AI for unresolved Category/Size/PackUnits",
            value=_ai_key_present,
            help=("Sends code, description and supplier of rows the deterministic "
                  "classifier could not resolve to OpenAI."),
        )
        if not _ai_key_present:
            st.caption("No OpenAI API key found (.env), so the AI fallback is off.")

    max_ai_items = st.number_input(
        "Max AI items per run",
        min_value=0,
        max_value=max(20000, DEFAULT_MAX_AI_ITEMS),
        value=DEFAULT_MAX_AI_ITEMS,
        step=50,
    )

    trim_ai_reason = st.checkbox(
        "Trim AI reasons (faster, lower cost)",
        value=False, key="ks_trim_reason",
        help=(
            "Ask the model only for the classification, not a written reason for "
            "each item. The reason is the bulk of the per-item output, so trimming "
            "it noticeably cuts AI time and cost. The category, size, and pack "
            "results are unchanged; the 'AI reason' column is just left blank."
        ),
    )

    batch_size = st.number_input(
        "AI batch size",
        min_value=5,
        max_value=50,
        value=DEFAULT_BATCH_SIZE,
        step=5,
        help=(
            "Items per AI call. Bigger = fewer calls but slightly slower per call. "
            "20 is a safe default. 50 roughly halves API round-trips — try if you have "
            "a stable connection and many rows to classify."
        ),
    )

    ai_concurrency = st.number_input(
        "AI parallel workers",
        min_value=1,
        max_value=MAX_AI_CONCURRENCY,
        value=DEFAULT_AI_CONCURRENCY,
        step=1,
        help=(
            "Number of batches fired in parallel. 5 is a safe default for OpenAI's "
            "rate limits on gpt-5-mini. Higher values speed up large runs proportionally "
            "(5× workers ≈ 5× faster AI wall-clock time). Drop to 1 for strict sequential "
            "behavior (matches old sequential behavior)."
        ),
    )

    st.divider()
    st.subheader("Scope & overrides")

    site_default = st.text_input(
        "Site",
        key="ks_site",
        placeholder="e.g. Plant1",
        **_default_unless_seeded("ks_site", os.getenv("KROMI_DEFAULT_SITE", "")),
        help="Combined with 'Customer' as <Customer>__<Site> to pick which overrides library to load. Non-alphanumeric characters get replaced with underscores.",
    )

    apply_overrides_ui = st.checkbox(
        "Apply overrides from library",
        key="ks_apply_overrides",
        **_default_unless_seeded("ks_apply_overrides", DEFAULTS.apply_overrides),
        help=(
            "When ON, the newest saved override set for this customer and site "
            "(or the corrections you are editing) is applied between AI "
            "classification and bulk routing. Technician decisions on vend mode, "
            "pack sizes, categories etc. override everything the automatic "
            "pipeline would otherwise compute. Turn OFF for a clean baseline run."
        ),
    )
    st.caption(
        "File-library overrides are being superseded by database override sets "
        "(used today by 'Load & recompute'). This toggle stays active for fresh "
        "runs for now."
    )

    reviewer_name = st.text_input(
        "Reviewer name (stamped into new overrides)",
        value=os.getenv("USER", "") or os.getenv("USERNAME", ""),
        placeholder="e.g. J.Dupont",
        help=(
            "Stamped into the 'reviewed_by' field of any new overrides you save "
            "from the Technician review panel. Defaults to your OS username."
        ),
    )

# Translate the radio choice into an internal constant
sp_mode = sp_mode_from_label(sp_mode_ui)

# Bundle the two runtime sizing factors into one frozen config, built once from
# the UI values; every reader below reads from it, not a mutable global.
_plan_cfg = PlanConfig(
    helix_overfill_factor=float(helix_single_spiral_overfill_factor_ui),
    carousel_reserve_factor=float(carousel_reserve_factor_ui),
    carousel_fill_ceiling=float(carousel_fill_ceiling_ui),
)

if _reload_ctx:
    file = _BytesFile(
        _reload_ctx["bytes"], _reload_ctx["filename"],
        file_id=_reload_ctx.get("sha256") or f"stored-run:{_reload_ctx.get('run_id')}",
    )
else:
    file = st.file_uploader("Upload Excel file", type=["xlsx", "xls"])


def _export_name(kind: str, ext: str) -> str:
    """Build a meaningful export filename: ``CPlanner_<source>_<kind>_<date>.<ext>``.

    ``<source>`` is the uploaded file's stem (e.g. ``my_catalog``), sanitised for
    filesystem use; ``<date>`` is today as ``YYYY-MM-DD``. Replaces the old
    ``CabinetPlanner_*`` names so a file says at a glance what it is and when it
    was produced.
    """
    raw = getattr(file, "name", "") or "plan"
    stem = _safe_scope_component(os.path.splitext(os.path.basename(raw))[0]) or "plan"
    # Local wall-clock by design: a user-facing filename date should match the
    # user's calendar, not UTC (recorded exemption, audit #2 m3).
    return f"CPlanner_{stem}_{kind}_{datetime.now().strftime('%Y-%m-%d')}.{ext}"


if not file:
    st.info("Upload an Excel file containing one sheet for Tools and (optionally) one sheet for PPE.")
    st.stop()

# Content-true source identity (I7), digested once per distinct file
# (v34.32): the bytes copy and the sha over the full upload happen when a
# file is first seen and are memoized against the uploader's file identity,
# so a plain rerun on a very large workbook stops paying a full scan per
# click. A new upload (new file id) recomputes; the reload path carries
# session-stable bytes and behaves the same way.
_upload_fid = _file_identity(file)
_upload_memo = st.session_state.get("_upload_bytes_memo")
if _upload_memo is not None and _upload_memo[0] == _upload_fid:
    _uploaded_bytes, _input_sha = _upload_memo[1], _upload_memo[2]
else:
    _uploaded_bytes = file.getvalue()
    _input_sha = hashlib.sha256(_uploaded_bytes).hexdigest()
    st.session_state["_upload_bytes_memo"] = (_upload_fid, _uploaded_bytes, _input_sha)

# E6: when the uploaded file's CONTENT changes, clear mapping-scoped session
# state so a new file starts from clean auto-detection instead of inheriting
# a previous file's column mappings or the sticky manual-mode flag. Keyed by
# the content hash (v34.42), so a same-content re-upload or a stored-run
# switch onto the same workbook keeps the technician's state, exactly as the
# contract documents, while a different file always resets.
reset_mapping_state_on_file_change(
    st.session_state,
    ("content", _input_sha),
)

# When the uploaded file's content changes, drop any corrections accumulated
# in the editor on the previous file, so they cannot bleed onto a different
# file. Same content, same corrections: a re-upload or a same-file run
# switch keeps them (v34.42).
_apply_set_sig = ("content", _input_sha)
if st.session_state.get("_apply_set_file_sig") != _apply_set_sig:
    _had_previous_file = st.session_state.get("_apply_set_file_sig") is not None
    _n_dropped_corr = len(st.session_state.get("_pending_overrides") or {})
    _n_dropped_fix = len(st.session_state.get("manual_size_fix") or {})
    st.session_state["_apply_set_file_sig"] = _apply_set_sig
    st.session_state.pop("_pending_overrides", None)
    # Manual Helix-fit size fixes belong to the file they were made on, like
    # the pending corrections (v34.50): they used to carry over to the next
    # customer's articles with the same codes.
    st.session_state.pop("manual_size_fix", None)
    for _k in [k for k in list(st.session_state.keys()) if str(k).startswith("sizefit_cb_")]:
        del st.session_state[_k]
    if _had_previous_file and (_n_dropped_corr or _n_dropped_fix):
        st.info(
            f"A different file was loaded: {_n_dropped_corr} unsaved technician "
            f"correction(s) and {_n_dropped_fix} manual size fix(es) from the "
            "previous file were discarded.")


try:
    xls = pd.ExcelFile(file)
except ImportError:
    # Legacy .xls needs the optional xlrd reader (v34.49: a message, not a traceback).
    st.error(
        "This looks like a legacy .xls workbook, which needs the optional "
        "'xlrd' reader. Open it in Excel and save it as .xlsx, then upload "
        "it again.")
    st.stop()
except Exception as _upload_exc:
    log_exception("Uploaded workbook could not be read", _upload_exc)
    st.error(
        "The uploaded file could not be read as an Excel workbook. It may be "
        "damaged, password-protected, or not an Excel file. Open it in Excel, "
        "save it as .xlsx, and upload it again.")
    st.stop()
sheet_names = list(xls.sheet_names)

# --- Run setup (main screen, above the listing) -----------------------------
# KTC-ID, customer label, and archive options live here rather than in the
# sidebar because they describe the run, not the calculation. Values are
# remembered per uploaded file: re-uploading a known catalog pre-fills the
# KTC-ID and customer entered last time.
st.subheader("Run setup")

_file_key = file_key_for(getattr(file, "name", ""))
_saved_prefs = get_file_prefs(_file_key)
# A recompute starts from the stored run's own KTC-ID and customer label
# (v34.54, audit C9); a fresh upload from the values remembered for the file.
_run_ktc = str((_reload_ctx or {}).get("ktc_id") or "").strip()
_run_label = (_reload_ctx or {}).get("customer_label")
_default_ktc = _run_ktc or _saved_prefs.get("ktc_id") or os.getenv("KROMI_DEFAULT_KTC_ID", DEFAULTS.ktc_id)
_default_customer = (
    _run_label if _run_label is not None
    else (_saved_prefs.get("customer") or os.getenv("KROMI_DEFAULT_CUSTOMER", ""))
)

_rs_col1, _rs_col2 = st.columns(2)
with _rs_col1:
    ktc_id_input = st.text_input(
        "KTC-ID",
        value=_default_ktc,
        max_chars=3,
        placeholder="e.g. 191",
        help=(
            "The 3-digit customer/installation ID that forms the first three "
            "digits of every generated KROMI article number. The numbering "
            "logic is identical for all customers; only this prefix changes. "
            "Must be exactly 3 digits."
        ),
    )
    _ktc_typed = str(ktc_id_input or "").strip()
    if not (_ktc_typed.isdigit() and len(_ktc_typed) == 3):
        st.warning(
            "The KTC-ID must be exactly 3 digits. Until it is, no KROMI article "
            "numbers are generated and the Article setup sheet is left out of "
            "the export.")
with _rs_col2:
    customer_default = st.text_input(
        "Customer name / label",
        value=_default_customer,
        placeholder="e.g. ACME",
        help=(
            "Customer name shown on the PDF cover and used (with 'Site' in the "
            "sidebar) to scope the technician overrides library. Remembered per "
            "uploaded file."
        ),
    )

# The database saves every completed run automatically (see end of script).
st.caption("Completed runs are saved to the database automatically.")
# Customer label used for export filenames and metadata.
archive_label = (customer_default or "").strip()

# Persist the KTC-ID + customer for this file so the next upload pre-fills them.
if _file_key and (ktc_id_input != _saved_prefs.get("ktc_id")
                  or customer_default != _saved_prefs.get("customer")):
    save_file_prefs(_file_key, ktc_id_input, customer_default)

# --- Operational mode (main screen, just below Run setup) -------------------
# Governs the cabinet composition above the per-tool routing. Standard leaves the
# pipeline untouched; the other modes override the composition for the whole
# catalog. Lives here rather than in the sidebar so it sits with the run-level
# decisions; the value is still consumed downstream when the plan is computed.
st.subheader("Operational mode")
st.caption(
    "Governs the cabinet composition above the per-tool routing. Standard keeps "
    "today's best-fit-per-tool logic; the other modes override it for every "
    "vending tool in the catalog."
)
_om_col1, _om_col2 = st.columns(2)
with _om_col1:
    operational_mode = st.selectbox(
        "Cabinet composition",
        key="ks_op_mode",
        options=list(OP_MODE_LABELS.values()),
        index=label_index(OP_MODE_LABELS, DEFAULTS.op_mode),
        help=(
            "Helix only stores every vending tool in a coil; Carousel only stores "
            "every vending tool in a slot; the capped mode keeps normal routing but "
            "limits the number of Carousels, spilling the overflow into Helix. "
            "Fixed configuration fits the articles into machines that already "
            "exist, most used first. Tools whose size does not fit the chosen "
            "cabinet are highlighted, not dropped."
        ),
    )
with _om_col2:
    if operational_mode == _FIXED_MODE_LABEL:
        _keep_widget_state(("ks_max_carousels",))
        max_carousels_cap = int(st.session_state.get("ks_max_carousels", DEFAULTS.max_carousels))
        fixed_headroom_pct = float(st.number_input(
            "Headroom to keep free (%)",
            key="ks_fixed_headroom",
            min_value=0.0,
            max_value=90.0,
            step=5.0,
            help=(
                "Share of every machine left empty. At 10 % a Helix holds up "
                "to 63 of its 70 spirals and a Carousel up to 648 of its 720 "
                "slots."
            ),
            **_default_unless_seeded("ks_fixed_headroom", DEFAULTS.fixed_headroom_pct),
        ))
    else:
        max_carousels_cap = st.number_input(
            "Max Carousels per supply point",
            key="ks_max_carousels",
            min_value=1,
            max_value=50,
            value=DEFAULTS.max_carousels,
            step=1,
            help="Only used in 'Helix + Carousel (capped)'. Carousel demand above this "
            "many cabinets is spilled into Helix coils.",
            disabled=(operational_mode != "Helix + Carousel (capped)"),
        )
        fixed_headroom_pct = 0.0

# Normalize the UI label to a compact mode token used downstream.
op_mode = token_for(OP_MODE_LABELS, operational_mode, default=OP_STANDARD)

# Fixed configuration (v34.52): the machines per supply point. Articles reach
# a supply point the usual way (the Program -> Supply Point mapping, or the
# supply-point mode in the sidebar).
fixed_machines: Tuple[Tuple[int, int, int, int, int, int], ...] = ()
fixed_allow_spill = True
fixed_stock_months = 0.0
if op_mode == FIXED_MODE:
    st.caption(
        "**Fixed configuration**: the machines already stand at each supply "
        "point. Enter them below; the planner keeps the headroom free, places "
        "the most used articles first and flags the ones that do not fit. "
        "Articles reach a supply point through the Program column mapping "
        "(or the supply-point mode in the sidebar)."
    )
    fixed_allow_spill = bool(st.checkbox(
        "Move overflow to another machine type when the article fits it",
        key="ks_fixed_spill",
        help=(
            "When an article's own machine type is full: a Carousel article of "
            "size S or M may go into a Helix, a Helix article into a Carousel, "
            "a locker article into a locker with larger compartments. Off: "
            "articles stay in their own type and are flagged when it is full."
        ),
        **_default_unless_seeded("ks_fixed_spill", DEFAULTS.fixed_allow_spill),
    ))
    # Stock-based Helix promotion (v34.58): off by default.
    _promo_c1, _promo_c2 = st.columns([2, 1])
    _stock_promo = bool(_promo_c1.checkbox(
        "Stock-based Helix promotion",
        key="ks_fixed_stock_promo",
        help=(
            "For lists with missing consumption: a large stock on hand hints at "
            "a high use. After the normal fit, the Helix space still free (the "
            "headroom stays empty) takes the S/M Carousel articles whose stock, "
            "spread over the months below, means more packs a month than the "
            "Helix threshold and than the recorded use; highest first, each with "
            "the spirals the normal Helix sizing gives. The Carousel space they "
            "free goes to articles that found none. Only the machine type and "
            "the takeover maximum change. Needs the Current stock column."
        ),
        **_default_unless_seeded("ks_fixed_stock_promo", DEFAULTS.fixed_stock_promotion),
    ))
    if _stock_promo:
        fixed_stock_months = float(_promo_c2.number_input(
            "Stock covers (months)",
            key="ks_fixed_stock_months",
            min_value=0.5, max_value=24.0, step=0.5,
            help="The customer's stock on hand is assumed to last this many months.",
            **_default_unless_seeded("ks_fixed_stock_months", DEFAULTS.fixed_stock_months),
        ))
    else:
        _keep_widget_state(("ks_fixed_stock_months",))
    _fixed_rows: List[Tuple[int, int, int, int, int, int]] = []
    _n_fixed_sp = int(n_supply_points)
    for _sp in range(1, _n_fixed_sp + 1):
        _mc = st.columns([1.2, 1, 1, 1, 1, 1])
        _mc[0].markdown(f"**SP {_sp}**" if _n_fixed_sp > 1 else "**Machines**")
        _vals = []
        for _i, (_kind, _label, _dflt) in enumerate(_FIXED_MACHINE_KINDS, start=1):
            _key = f"ks_fixed_{_kind}_{_sp}"
            _vals.append(int(_mc[_i].number_input(
                _label, key=_key, min_value=0, max_value=20, step=1,
                **_default_unless_seeded(_key, _dflt),
            )))
        _fixed_rows.append((_sp, *_vals))
    # Supply points beyond the current count keep their entries.
    _keep_widget_state(
        f"ks_fixed_{_k}_{_sp}" for _sp in range(_n_fixed_sp + 1, _FIXED_MAX_SP + 1)
        for _k, _lbl, _dflt in _FIXED_MACHINE_KINDS)
    fixed_machines = tuple(_fixed_rows)
    _cap_bits = []
    for _sp, _h, _c, _a, _b, _cc in fixed_machines:
        _usable = _fixed_usable_capacity(
            MachineSet(helix=_h, carousel=_c, locker_a=_a, locker_b=_b, locker_c=_cc),
            fixed_headroom_pct)
        _parts = [f"{_usable[_t]} {_u}" for _t, _u in (
            ("Helix", "spirals"), ("Carousel", "slots"), ("Locker A", "A compartments"),
            ("Locker B", "B compartments"), ("Locker C", "C compartments"))
            if _usable[_t] > 0]
        _cap_bits.append(f"SP {_sp}: " + (", ".join(_parts) if _parts else "no machines"))
    st.caption(
        f"Usable space after {fixed_headroom_pct:g} % headroom - " + " | ".join(_cap_bits))
    if sum(sum(_r[1:]) for _r in fixed_machines) == 0:
        st.error("Enter at least one machine to fit the articles into.")
        st.stop()
else:
    _keep_widget_state(_FIXED_KEYS)

# Numbering-only controls (v34.44). No plan exists in this mode to decide
# KTC vs Kanban, so a default property system is chosen per run (a mapped
# System type column still overrides per row), and the header row lets KDS
# import templates with banner rows above the real headers map cleanly.
if op_mode == "NumberingOnly":
    st.caption(
        "**Numbering-only mode**: the pipeline classifies the articles and "
        "assigns KROMI article numbers; no cabinets are planned and nothing "
        "is saved to the database. Map at least the article code and the "
        "description; consumption is optional here."
    )
    _nb_col1, _nb_col2 = st.columns(2)
    with _nb_col1:
        _numbering_system_ui = st.radio(
            "Articles are",
            options=list(NUMBERING_SYSTEM_LABELS.values()),
            index=label_index(NUMBERING_SYSTEM_LABELS, DEFAULTS.numbering_system),
            key="ks_numbering_system",
            help=(
                "Default property system for every article in this run. A "
                "mapped 'System type available' column overrides it per row: "
                "KTC or Locker markers force the KTC pair; anything else "
                "keeps this default."
            ),
        )
    numbering_default_system = (
        "KTC" if str(_numbering_system_ui).startswith("KTC") else "Kanban"
    )
else:
    numbering_default_system = DEFAULTS.numbering_system

st.subheader("Listings")
st.caption("Select which sheet is Tools and which (if any) is PPE. Both sheets must share the same column structure.")

col_t, col_p = st.columns(2)
with col_t:
    # Try to auto-default to a sheet named Tools/Werkzeug/etc
    tools_default_idx = 0
    for i, s in enumerate(sheet_names):
        if re.search(r"tool|werkzeug|outil|herramienta", str(s), re.IGNORECASE):
            tools_default_idx = i
            break
    sheet_tools = st.selectbox("Tools sheet", ["— not used —"] + sheet_names, index=tools_default_idx + 1, key="ks_sheet_tools")

with col_p:
    # PPE is opt-in: default to "— not used —" so a Tools-only catalog shows
    # its content immediately without the user having to clear an auto-picked
    # PPE sheet. The user selects a PPE sheet explicitly when they have one.
    sheet_ppe = st.selectbox(
        "PPE sheet (optional)", ["— not used —"] + sheet_names, key="ks_sheet_ppe",
        **({} if "ks_sheet_ppe" in st.session_state else {"index": 0}))

sheet_tools = None if sheet_tools == "— not used —" else sheet_tools
sheet_ppe = None if sheet_ppe == "— not used —" else sheet_ppe

if sheet_tools is None and sheet_ppe is None:
    st.error("Select at least one sheet (Tools or PPE).")
    st.stop()

if sheet_tools is not None and sheet_ppe is not None and sheet_tools == sheet_ppe:
    st.error("Tools and PPE cannot be the same sheet. Pick different sheets or set one to '— not used —'.")
    st.stop()

# Header row, in every mode (v34.50, audit C11; numbering-only since v34.44).
# Import templates often carry banner rows above the real column names.
_hr_kwargs: Dict[str, Any] = {} if "ks_header_row" in st.session_state else {"value": DEFAULTS.header_row}
_header_row_ui = st.number_input(
    "Header row in the sheet",
    min_value=1, max_value=50, step=1, key="ks_header_row",
    help=(
        "Row that carries the column names. Import templates often put "
        "banner rows above the real headers (a KDS template: row 4); files "
        "with headers on the first row keep 1."
    ),
    **_hr_kwargs,
)
_sheet_header_row = int(_header_row_ui)

# Load the selected sheets. The full workbook parse is the largest cost repeated
# on every rerun, so it is memoized by file content and sheet name: a rerun, or a
# re-upload of the same file, reuses the parsed frame instead of re-reading it.
@st.cache_data(show_spinner=False, max_entries=8)
def _read_sheet(input_sha: str, sheet_name, header_row: int,
                _file_bytes: bytes) -> pd.DataFrame:
    """Keyed on the upload digest plus the sheet name and the header row; the
    bytes arrive underscore-prefixed so streamlit never hashes the full
    upload for the cache key (v34.32). ``header_row`` is 1-based; 1 is the
    historical behaviour (v34.44 adds the knob for the numbering-only mode's
    banner-row templates)."""
    return pd.read_excel(BytesIO(_file_bytes), sheet_name=sheet_name,
                         header=max(0, int(header_row) - 1))


# Reuse-by-SHA (I4): when this exact workbook is already stored, its
# classifications flow into the run through the same stored_classifications
# parameter the reload path uses; a reload context keeps precedence, since it
# carries the snapshot of the specific stored run being recomputed.
_sha_reuse_cls: Dict[str, Dict[str, Any]] = {}
if not (_reload_ctx and _reload_ctx.get("classifications")):
    # Fresh upload, or a reload of a run stored without a classification
    # snapshot (older archives): the file-level store answers by digest.
    _sha_reuse_cls = _cached_load_stored_classifications(_resolve_db_path(), _input_sha)
_restock_categories: Tuple[str, ...] = tuple(
    str(c) for c in (st.session_state.get("ks_restock_categories") or [])
)
_stored_source_cls = (
    (_reload_ctx.get("classifications") if _reload_ctx else None)
    or _sha_reuse_cls
    or {}
)
df_tools = _read_sheet(_input_sha, sheet_tools, _sheet_header_row, _uploaded_bytes) if sheet_tools is not None else None
df_ppe = _read_sheet(_input_sha, sheet_ppe, _sheet_header_row, _uploaded_bytes) if sheet_ppe is not None else None

# The primary frame for column-mapping UI is whichever is loaded (Tools preferred)
df = df_tools if df_tools is not None else df_ppe


@st.cache_data(show_spinner=False, max_entries=8)
def _read_sheet_head(input_sha: str, sheet_name, _file_bytes: bytes) -> pd.DataFrame:
    """The first rows of a sheet without a header, for header-row detection."""
    return pd.read_excel(BytesIO(_file_bytes), sheet_name=sheet_name,
                         header=None, nrows=30)


# A sheet whose data columns are mostly unnamed was read with the wrong header
# row (v34.50): mapping "Unnamed: n" columns would plan nonsense. When another
# row clearly holds the column names, stop and say which; otherwise warn.
if headers_look_misplaced(df):
    _hint_row = suggest_header_row(_read_sheet_head(
        _input_sha, sheet_tools if sheet_tools is not None else sheet_ppe,
        _uploaded_bytes))
    if _hint_row != _sheet_header_row:
        st.error(
            f"Most columns of this sheet have no header name ('Unnamed'), so "
            f"the column names are probably not on row {_sheet_header_row}. "
            f"They look like they are on row {_hint_row}: set 'Header row in "
            f"the sheet' above to {_hint_row}.")
        st.stop()
    st.warning(
        "Most columns of this sheet have no header name ('Unnamed'). Check "
        "'Header row in the sheet' above before mapping the columns.")

# Validate PPE has the same columns as Tools if both are loaded
if df_tools is not None and df_ppe is not None:
    missing_in_ppe = set(df_tools.columns) - set(df_ppe.columns)
    missing_in_tools = set(df_ppe.columns) - set(df_tools.columns)
    if missing_in_ppe or missing_in_tools:
        diffs = []
        if missing_in_ppe:
            diffs.append(f"Missing in PPE: {sorted(missing_in_ppe)}")
        if missing_in_tools:
            diffs.append(f"Missing in Tools: {sorted(missing_in_tools)}")
        st.warning(
            "Tools and PPE sheets have different columns. Column mapping will use the Tools sheet; "
            "any mapped columns missing from PPE will be filled with empty values on PPE rows. "
            + " | ".join(diffs)
        )

# Derive the calc_mode effective value
both_listings = (df_tools is not None) and (df_ppe is not None)
if not both_listings or op_mode == FIXED_MODE:
    # No choice to make when only one listing is present; in the fixed
    # configuration mode every listing shares the configured machines.
    calc_mode = "Combined (one vending machine plan for both)"
else:
    calc_mode = calc_mode_ui

st.caption(
    f"Effective config — Listings: "
    f"{'Tools ' if df_tools is not None else 'Tools –'} | "
    f"{'PPE ' if df_ppe is not None else 'PPE –'} | "
    f"Mode: {calc_mode.split('(')[0].strip()} | "
    f"Supply points: {n_supply_points}"
)

st.subheader("Data preview")
st.dataframe(_arrow_safe(df.head(25)), width='stretch')

@st.cache_data(show_spinner=False)
def _ai_suggest_colmap_cached(cache_key: Tuple) -> Dict[str, str]:
    """Cached AI column-mapping suggestion.

    Keyed on (headers, sample rows, model) so Streamlit reruns and re-uploads of
    the same file reuse the result instead of re-calling (and re-charging) the API.
    Returns {canonical_field: column_name} for the columns the model mapped.
    """
    headers_t, sample_json, model = cache_key
    headers = list(headers_t)
    client = get_openai_client()
    prompt = build_colmap_prompt(headers, json.loads(sample_json))
    content, _, _ = _call_openai_structured(
        client,
        model,
        prompt,
        "column_mapping",
        colmap_response_schema(),
        AI_CALL_TIMEOUT_SECONDS,
    )
    return parse_colmap_response(json.loads(content), headers)


# Column mapping
st.subheader("Column mapping")

cols = list(df.columns)

ai_colmap = st.checkbox(
    "Suggest column mapping with AI",
    key="ks_ai_colmap",
    value=False,
    help=(
        "Ask the AI model to propose which column is which, based on the headers "
        "and a few sample rows. You still confirm every field below. Requires an "
        "OpenAI API key."
    ),
)

hide_optional_cols = st.checkbox(
    "Hide optional columns",
    key="ks_hide_optional",
    value=False,
    help=(
        "When ON, every optional column mapping is hidden and left unassigned "
        "(not auto-detected). Only the required fields — Code, Description, and "
        "Consumption — are shown. Use this for clean catalogs where you only "
        "want the essentials mapped."
    ),
)
ai_guess: Dict[str, str] = {}
if ai_colmap:
    try:
        _sample = df.head(5).astype(str).to_dict(orient="records")
        _ck = (
            tuple(cols),
            json.dumps(_sample, ensure_ascii=False, sort_keys=True),
            OPENAI_MODEL,
        )
        ai_guess = _ai_suggest_colmap_cached(_ck)
        if ai_guess:
            st.caption(
                "AI proposed the mapping below — please review each field before running."
            )
        else:
            st.caption(
                "AI couldn't confidently map any columns; using automatic header matching."
            )
    except Exception as exc:  # never block the mapping UI on an AI failure
        log_exception("AI column mapping failed", exc)
        st.info(f"AI mapping unavailable ({exc}). Falling back to automatic header matching.")
        ai_guess = {}

# Suggested columns (engine/column_suggest.py, v34.62): the AI proposal, else
# the synonym match; the stock column has its own rule (never a min, max,
# safety level or location). Optional defaults never take a column a required
# field (or an earlier optional field) already uses (v34.50, audit C11), so
# "Year" does not grab "Jahresverbrauch". A user's explicit pick is untouched;
# the conflict guard below remains the safety net.
_raw_guess = raw_guesses(df, ai_guess)
default_code = _raw_guess["Code"]
default_desc1 = _raw_guess["Description"]
default_cons = _raw_guess["Consumption_pcs"]


def _effective_required(key: str, default: Optional[str]) -> Optional[str]:
    _v = st.session_state.get(key)
    return _v if _v in cols else default


_suggested = suggest_columns(df, ai_guess, required={
    "Code": _effective_required("cm_code", default_code),
    "Description": _effective_required("cm_desc1", default_desc1),
    "Consumption_pcs": _effective_required("cm_cons", default_cons),
})
default_prod = _suggested["ProductCategory"]
default_year = _suggested["Year"]
default_desc2 = _suggested["Description_2"]
default_program = _suggested["Program"]
default_restock = _suggested["Restocking"]
default_sup = _suggested["SupplierCode"]
default_size = _suggested["SizeCategory"]
default_site = _suggested["Site"]
default_stdspecial = _suggested["StdSpecial"]
default_pack = _suggested["PackUnits"]
default_dims = _suggested["PackageDimensions"]
default_regrind = _suggested["Regrind"]
default_systemtyp = _suggested["SystemTyp"]
default_stock = _suggested["Stock_pcs"]

# Once the user hides optional columns, optional mapping switches to manual
# mode: any earlier optional assignment is cleared and auto-detection is
# suppressed, so re-showing the fields never silently re-grabs a column (a
# ghost mapping that would otherwise run unnoticed). The user re-picks
# optional columns deliberately after that.
if hide_optional_cols:
    st.session_state["_optional_manual_mode"] = True
optional_manual_mode = st.session_state.get("_optional_manual_mode", False)


def pick(label: str, default: Optional[str], allow_none: bool = False, help: Optional[str] = None, key: Optional[str] = None) -> Optional[str]:
    # When "Hide optional columns" is on, optional fields (allow_none=True)
    # are neither rendered nor auto-assigned. Any stored pick is cleared so
    # that unhiding starts from a blank (unassigned) state.
    if allow_none and hide_optional_cols:
        if key is not None:
            st.session_state.pop(key, None)
        return None
    options = [NOT_AVAIL] + cols if allow_none else cols
    if allow_none:
        # In manual mode, ignore the auto-detected default so a re-shown field
        # starts unassigned unless the user explicitly picks (their pick is
        # held in session_state under `key`). Decision logic lives in the
        # tested engine.colmap.resolve_optional_default helper.
        eff_default = resolve_optional_default(
            hidden=False, manual_mode=optional_manual_mode, auto_default=default)
        # Drop a stored pick that is stale (e.g. a column from a previously
        # uploaded file that no longer exists) so the selectbox can't crash.
        if key is not None and key in st.session_state and st.session_state[key] not in options:
            st.session_state.pop(key, None)
        if key is not None and key in st.session_state:
            chosen = st.selectbox(label, options, help=help, key=key)
        else:
            idx = options.index(eff_default) if eff_default in options else 0
            chosen = st.selectbox(label, options, index=idx, help=help, key=key)
        return None if chosen == NOT_AVAIL else chosen
    # Required field. Honour a seeded session_state pick (used to restore a
    # recomputed run's mapping), dropping it first if it names a column the
    # current file does not have so the selectbox can never crash.
    if key is not None and key in st.session_state and st.session_state[key] not in cols:
        st.session_state.pop(key, None)
    if key is not None and key in st.session_state:
        # Collision-safe: a stored pick that duplicates a column an earlier
        # required field already claimed is a stale or seeded collision (e.g.
        # restored from a run saved before the collision guard, whose three
        # required fields were all written onto the first column). Re-resolve it
        # to a non-colliding auto-detected column instead of honouring the
        # collision and tripping the conflict guard. A genuine, distinct stored
        # pick (a real restore or the user's own earlier choice) is preserved.
        _eff = resolve_required_stored(st.session_state[key], default, _required_taken, cols)
        if _eff in cols and _eff != st.session_state[key]:
            st.session_state[key] = _eff
        chosen = st.selectbox(label, cols, help=help, key=key)
        _required_taken.add(chosen)
        return chosen
    # No stored/auto value: choose a fallback that does not collide with a column
    # already claimed by an earlier required field, so Code and Description never
    # silently collapse onto the same column (which trips the conflict guard)
    # when auto-detection returns nothing for this file's headers.
    eff_default = resolve_required_default(default, _required_taken, cols)
    idx = cols.index(eff_default) if eff_default in cols else 0
    chosen = st.selectbox(label, cols, index=idx, help=help, key=key)
    _required_taken.add(chosen)
    return chosen

# Tracks columns already claimed by a required field this render, so the
# collision-safe fallback in `pick` can avoid handing the same column to two
# required fields. Reset every run (the script re-executes top to bottom).
_required_taken: set = set()

c1, c2, c3, c4 = st.columns(4)
with c1:
    col_code = pick(
        "Code", default_code, key="cm_code",
        help="Unique identifier for each article (SAP number, internal ID, SKU). Used to deduplicate rows and to look up per-item overrides. Required.",
    )
    col_prod = pick(
        "ProductCategory (optional)", default_prod, allow_none=True, key="cm_prod",
        help="A pre-existing category column (drills, mills, taps…) if your file already carries one. When mapped, the classifier uses it as a hint instead of re-classifying from the description.",
    )
    col_year = pick(
        "Year (optional)", default_year, allow_none=True, key="cm_year",
        help="Year associated with the consumption row. Lets the planner restrict to a single year or use only the latest year. Leave unmapped to use all rows.",
    )
with c2:
    col_desc1 = pick(
        "Description", default_desc1, key="cm_desc1",
        help="The primary free-text description of each article. The deterministic classifier and the AI fallback both read this to assign ProductCategory, ToolClass, and SizeCategory. Required.",
    )
    col_desc2 = pick(
        "Description_2 (optional)", default_desc2, allow_none=True, key="cm_desc2",
        help="A secondary description column, if your catalog splits long descriptions across two fields. When mapped, it is concatenated with the primary description before classification.",
    )
    col_program = pick(
        "Program / Area (optional)", default_program, allow_none=True, key="cm_program",
        help="The programme, project, or workshop area each row belongs to. Used for per-programme breakdowns in the report; does not affect cabinet count.",
    )
    if op_mode not in ("Helix", "NumberingOnly"):
        col_restock = pick(
            "Restocking yes/no (optional)", default_restock, allow_none=True, key="cm_restock",
            help="A yes/no column marking items the customer restocks. A "
                 "restockable vending item reserves one buffer compartment: "
                 "Helix and Carousel items buffer in a Carousel, Locker items "
                 "in their own locker class. Kanban items are unaffected.",
        )
        st.multiselect(
            "Restockable categories (rule)",
            options=sorted(PC_VALID),
            key="ks_restock_categories",
            help="Categories assumed restockable when the column above gives "
                 "no answer for a row. A mapped yes or no always wins.",
        )
    else:
        # The Helix operational mode has no compartment cabinets to buffer
        # in, so restocking is hidden entirely and the segment stays inert.
        # Numbering-only mode plans nothing, so restocking is moot there too.
        col_restock = None
with c3:
    col_sup = pick(
        "SupplierCode (optional)", default_sup, allow_none=True, key="cm_sup",
        help="Supplier-side article code. When mapped, deduplication can key on (Code + SupplierCode) instead of Code alone, so the same internal code from two suppliers stays as two rows.",
    )
    col_size = pick(
        "SizeCategory (optional)", default_size, allow_none=True, key="cm_size",
        help="A pre-existing size label (S/M/L/XL/XXL) if your file already carries one. When mapped, the planner uses it directly and skips the description-based size heuristic for that row.",
    )
    col_site = pick(
        "Site (optional)", default_site, allow_none=True, key="cm_site",
        help="Physical site or plant code. Used to scope per-supply-point breakdowns when running in Partition mode.",
    )
    col_stdspecial = pick(
        "Standard / Special (optional)", default_stdspecial, allow_none=True, key="cm_stdspecial",
        help=(
            "A column marking each tool as Standard or Special. When mapped, the "
            "On-machine stock coverage control splits into a Standard value and a "
            "Special value, and each tool is sized with the coverage for its class. "
            "Values are recognised in French, Polish, German, Spanish, English, "
            "Slovak, and Slovenian. Unrecognised values are treated as Standard. "
            "Hidden when 'Hide optional columns' is on."
        ),
    )
with c4:
    if op_mode == "NumberingOnly":
        # Numbering needs no demand: consumption is optional here; unmapped
        # rows scaffold to zero, which the skipped planning never reads.
        col_cons = pick(
            "Consumption pcs (optional in this mode)", default_cons,
            allow_none=True, key="cm_cons",
            help="Not needed for article-number assignment; map it only if you want it parsed along.",
        )
    else:
        col_cons = pick(
            "Consumption pcs", default_cons, key="cm_cons",
            help="Annual or per-period consumption in pieces. Combined with PackUnits and the Consumption-period setting to compute Monthly_packs, which drives the KTC/Kanban and Helix/Carousel splits. Required.",
        )
    col_pack = pick(
        "PackUnits (optional)", default_pack, allow_none=True, key="cm_pack",
        help="Pieces per pack / VPE. Many catalog rows count consumption in pieces but are dispensed in packs (e.g. 100 abrasive discs per pack). When unmapped, the planner assumes PackUnits=1 and may overstate cabinet count.",
    )
    col_dims = pick(
        "Package dimensions (optional)", default_dims, allow_none=True, key="cm_dims",
        help="Package width × depth × height or Ø × length (e.g. 'Ø 16 x 88 mm', '120 x 90 x 250'). When mapped, the planner runs an advisory dimensional fit-check against real compartment envelopes and writes Fit_status / Fit_recommended columns. Plan routing is not changed.",
    )
    col_regrind = pick(
        "Regrind YES/NO (optional)", default_regrind, allow_none=True, key="cm_regrind",
        help="A YES/NO column marking tools that can be reground/resharpened. When mapped, a reground tool kept in a Helix is given at least two spirals (one for new, one for reground) since the two cannot share a coil. Carousel/Locker sizing is unchanged.",
    )
    col_systemtyp = pick(
        "System type available (optional)", default_systemtyp, allow_none=True, key="cm_systemtyp",
        help="A customer-specified storage system per tool. Recognised values: 'KTC' (force a vending machine, never Kanban), 'KTC or Kanban' (the monthly-pieces threshold decides), and 'Locker' (force a size-matched locker). When mapped, the customer's choice overrides the planner's own KTC/Kanban/cabinet decision; fixed rows (KTC, Locker) are protected from bulk routing and consolidation. When left unmapped, nothing changes.",
    )
    if op_mode != "NumberingOnly":
        col_stock = pick(
            "Current stock pcs (optional)", default_stock, allow_none=True, key="cm_stock",
            help="The customer's current stock of each article in pieces. When mapped, "
                 "the workbook adds one takeover sheet per supply point: whole packs go "
                 "into the KTC up to the article's maximum (the compartments allocated "
                 "to it times the packaging unit), the rest stays at the main stock "
                 "location (HLO). The plan itself does not change.",
        )
    else:
        col_stock = None

if not use_description_2:
    col_desc2 = None

# Tell the sidebar whether the Standard/Special column is mapped, so the
# coverage control can split into standard/special. The sidebar renders
# before this point, so flip the flag and rerun once when it changes.
_now_std_special_mapped = col_stdspecial is not None
if st.session_state.get("_std_special_mapped", False) != _now_std_special_mapped:
    st.session_state["_std_special_mapped"] = _now_std_special_mapped
    st.rerun()

# One mapping for the engine (v34.61): Description 2 is dropped when switched off.
_mapping = effective_mapping(ColumnMapping(
    code=col_code, description=col_desc1, consumption=col_cons, description_2=col_desc2,
    category=col_prod, supplier_code=col_sup, size=col_size, pack_units=col_pack,
    year=col_year, program=col_program, restocking=col_restock, site=col_site,
    std_special=col_stdspecial, dimensions=col_dims, regrind=col_regrind,
    system_type=col_systemtyp, stock=col_stock,
), use_description_2=use_description_2)

# Column-mapping guard
_collisions = mapping_collisions(_mapping)
if _collisions:
    st.error(
        " Column-mapping conflict detected — the same source column is mapped to multiple target fields. "
        "This silently drops one of the mappings (the bug that caused empty Descriptions in earlier runs). "
        "Please correct the mapping before running:"
    )
    for col, fields in _collisions.items():
        st.markdown(f"- **`{col}`** is mapped to: {', '.join(fields)} — pick ONE field for this column, and set the others to `— not available —`")
    st.stop()

# Build working dataframe (Tools + PPE concatenation) in the engine (v34.61).
_tool_list = build_tool_list(df_tools, df_ppe, _mapping, use_description_2=use_description_2)

# Per-listing column-existence check. The column mapping is chosen from the
# Tools sheet headers; a selected PPE sheet (or a differently-structured
# sheet) may not contain every mapped column. A missing Consumption or Code
# column would route those rows to Kanban with zero demand: stop. Otherwise warn.
for _gap in _tool_list.missing:
    _msg = "; ".join(f"{dst} (expected column '{src}')" for src, dst in _gap.missing)
    if _gap.critical:
        st.error(
            f"The **{_gap.listing}** sheet is missing mapped column(s) that are "
            f"required for correct planning: {_msg}. Rows from this sheet "
            "would be treated as having no "
            + (" / ".join(_gap.critical))
            + ". Map columns that exist in this sheet, or remove it from "
            "the run."
        )
        st.stop()
    else:
        st.warning(
            f"The **{_gap.listing}** sheet does not contain mapped column(s): "
            f"{_msg}. Rows from this sheet will have those fields empty."
        )

work = _tool_list.work

# Empty-code guard (the rows were dropped by build_tool_list)
_dropped_codes = _tool_list.dropped_empty_codes
n_empty = len(_dropped_codes)
if n_empty > 0:
    st.warning(
        f" **Empty Code guard**: dropped {n_empty} row(s) with blank/missing Code "
        f"after whitespace cleanup. These rows cannot be safely deduplicated \u2014 their "
        f"consumption would otherwise collapse into a single phantom row. "
        f"If these are real items, assign SAP codes in the source data and re-run."
    )
    # Show a sample so the user can verify
    sample_cols = [c for c in ["Listing", "Description", "Description_2", "Consumption_pcs"] if c in _dropped_codes.columns]
    if sample_cols:
        with st.expander(f"Show dropped rows ({min(20, n_empty)} shown)"):
            st.dataframe(
                _dropped_codes[sample_cols].head(20),
                width="stretch",
                hide_index=True,
            )

# Resolve effective (customer, site) scope
effective_customer, effective_site, site_vals = resolve_override_scope(
    customer_default, site_default, work, site_mapped=bool(col_site))
if len(site_vals) > 1:
    # Multiple sites in the same upload: the sidebar default is kept to
    # avoid an ambiguous auto-pick. Show an informational caption.
    st.caption(
        f"ℹ Source Excel contains multiple Site values "
        f"({', '.join(site_vals[:5])}{' …' if len(site_vals) > 5 else ''}). "
        f"Using sidebar Site '{effective_site}' for overrides scope."
    )

if _reload_ctx:
    # Recompute uses the stored run's own customer and site, so the matching
    # override set resolves. This wins over the sidebar inputs and any Site
    # column in the workbook.
    effective_customer = scope_value(_reload_ctx.get("customer"))
    effective_site = scope_value(_reload_ctx.get("site"))

# Show the active scope so the user can confirm before clicking Run
st.caption(
    f" **Overrides scope**: `{effective_customer}__{effective_site}`"
)

# Program → Supply Point mapping
program_to_sp_map: Dict[str, int] = {}
program_mapping_active = _program_mapping_active(
    work, _mapping, n_supply_points=int(n_supply_points), op_mode=op_mode)

if program_mapping_active:
    st.subheader("Program → Supply Point mapping")
    st.caption(
        f"You have chosen **{int(n_supply_points)} supply points** and a Program column "
        f"(`{col_program}`). Assign every distinct programme to the supply point that will "
        f"physically stock its tools. Consumption will flow into the matched SP; same-SKU "
        f"used across multiple programmes at the same SP will accumulate."
    )

    # Distinct programmes, sorted with "" (missing) last
    _programs = distinct_programs(work)

    # Show a hint about how many rows / what consumption is in each programme
    prog_stats = (
        work.groupby("Program", dropna=False)
        .agg(rows=("Code", "count"), consumption=("Consumption_pcs", "sum"))
        .reset_index()
    )
    prog_stats["Program"] = prog_stats["Program"].astype(str)
    prog_stats_lookup = prog_stats.set_index("Program")

    # Bulk-assign helpers — without these, 80+ programmes per run is painful
    bulk_col1, bulk_col2 = st.columns([2, 3])
    with bulk_col1:
        bulk_target_sp = st.number_input(
            "Bulk-assign unassigned programmes to SP",
            min_value=1,
            max_value=int(n_supply_points),
            value=1,
            step=1,
            key="bulk_target_sp",
            help="When a plant has many small/noisy programmes (e.g. one-off tooling items), use this to lump them into a single supply point quickly.",
        )
    with bulk_col2:
        if st.button(
            f"Apply SP {int(bulk_target_sp)} to all programmes below",
            help="Sets every programme dropdown below to the chosen SP. You can still override individual rows afterwards.",
        ):
            for p in _programs:
                st.session_state[f"prog_sp::{p}"] = int(bulk_target_sp)

    # Per-programme dropdowns — grouped so the list is scannable
    st.caption(f"Assign each of the **{len(_programs)} programme(s)** to a supply point:")

    # Render in a compact grid to avoid page-long scroll
    cols_per_row = 3
    for i in range(0, len(_programs), cols_per_row):
        batch = _programs[i : i + cols_per_row]
        row_cols = st.columns(cols_per_row)
        for j, prog in enumerate(batch):
            with row_cols[j]:
                prog_label = "(blank / missing)" if prog == "" else prog
                stats = prog_stats_lookup.loc[prog] if prog in prog_stats_lookup.index else None
                if stats is not None:
                    help_txt = f"{int(stats['rows'])} row(s), {float(stats['consumption']):,.0f} pcs/yr"
                else:
                    help_txt = None
                key = f"prog_sp::{prog}"
                assigned_sp = st.selectbox(
                    prog_label,
                    options=list(range(1, int(n_supply_points) + 1)),
                    format_func=lambda n: f"SP {n}",
                    key=key,
                    help=help_txt,
                )
                program_to_sp_map[prog] = int(assigned_sp)

    # Summary of the mapping
    with st.expander("Mapping summary (consumption per SP after programme routing)"):
        sp_totals: Dict[int, Dict[str, float]] = {
            sp: {"rows": 0, "consumption": 0.0, "programmes": []}
            for sp in range(1, int(n_supply_points) + 1)
        }
        for prog, sp in program_to_sp_map.items():
            stats = prog_stats_lookup.loc[prog] if prog in prog_stats_lookup.index else None
            if stats is not None:
                sp_totals[sp]["rows"] += int(stats["rows"])
                sp_totals[sp]["consumption"] += float(stats["consumption"])
                sp_totals[sp]["programmes"].append(
                    "(blank)" if prog == "" else prog
                )
        sp_summary_rows = []
        for sp, data in sp_totals.items():
            sp_summary_rows.append({
                "Supply Point": f"SP {sp}",
                "Rows": data["rows"],
                "Annual consumption": int(data["consumption"]),
                "# programmes": len(data["programmes"]),
                "Programmes (first 5)": ", ".join(data["programmes"][:5])
                    + (f" + {len(data['programmes']) - 5} more" if len(data["programmes"]) > 5 else ""),
            })
        st.dataframe(
            pd.DataFrame(sp_summary_rows),
            width="stretch",
            hide_index=True,
        )

    # Validation: every distinct programme must have an SP picked.
    unassigned = unassigned_programs(_programs, program_to_sp_map)
    if unassigned:
        st.error(
            f" {len(unassigned)} programme(s) are unassigned. Every programme must "
            f"be mapped to a supply point before running. Unassigned: "
            f"{', '.join(repr(p) for p in unassigned[:10])}"
            + (f" (+{len(unassigned)-10} more)" if len(unassigned) > 10 else "")
        )
        st.stop()

    # Apply the mapping to the working dataframe — BEFORE dedup.
    # Any unmapped rows (shouldn't happen after validation) get SP 1 as safety
    _n_default_sp = assign_supply_points(work, program_to_sp_map)
    if _n_default_sp:
        st.warning(
            f"Safety net: {_n_default_sp} row(s) did not match any mapped programme "
            f"and were assigned to SP 1 by default."
        )
else:
    # No program mapping path: the existing single-supply-point behavior
    pass

# Planning base preparation
year_mode = token_for(YEAR_MODE_LABELS, year_mode_ui, default="all_rows")
dedup_mode = token_for(DEDUP_MODE_LABELS, dedup_mode_ui)

has_year = work["Year"].notna().any() if "Year" in work.columns else False

# Master-file order for the numbering-only mode (v34.46): the planning-base
# dedup deliberately sorts articles so results never depend on input row
# order, but the Article setup download should follow the source file. Capture
# each code's first-occurrence order BEFORE the dedup sorts the frame.
_nb_code_order: list = []
if op_mode == "NumberingOnly" and "Code" in work.columns:
    _nb_code_order = list(dict.fromkeys(str(c) for c in work["Code"]))

planning_base, base_info = _cached_prepare_planning_base(
    work,
    dedup_mode=dedup_mode,
    year_mode=year_mode,
    has_year=has_year,
)

st.subheader("Planning base summary")
_n_neg_clamped = int(base_info.get("negative_consumption_clamped") or 0)
if _n_neg_clamped:
    st.warning(
        f"**Negative consumption guard**: {_n_neg_clamped} row(s) had negative "
        f"consumption (ERP credit/return artifacts) and were clamped to 0 before "
        f"deduplication and sizing, so they route by zero movement instead of "
        f"corrupting aggregated totals."
    )
base_msg = (
    f"Rows before preprocessing: {base_info['rows_before']:,} | "
    f"after year filter: {base_info['rows_after_year_filter']:,} | "
    f"after deduplication: {base_info['rows_after_dedup']:,}"
)
if base_info["latest_year_used"] is not None:
    base_msg += f" | latest year used: {base_info['latest_year_used']}"
st.caption(base_msg)

# Halt early on an empty planning base. A 0-row base can arise from an upload
# with headers but no data rows, or from a Code column that is entirely blank
# (those rows are dropped upstream). Stopping here gives a clear message instead
# of carrying an empty plan through classification, sizing, and export.
if len(planning_base) == 0:
    st.error(
        "No usable rows after preprocessing. The upload appears to have no data "
        "rows, or the column mapped as the article code is empty. Check the file "
        "and the column mapping, then run again."
    )
    st.stop()

# Surface dedup attribute conflicts: when rows that merge into one code disagree
# on ProductCategory or PackUnits, the kept value depends on input row order, so
# the same data in a different order could classify/size differently. Consumption
# is still summed correctly; only the kept attribute is order-dependent.
_conflicts = base_info.get("dedup_conflict_groups") or {}
_conf_msgs = []
if _conflicts.get("ProductCategory", 0) > 0:
    _conf_msgs.append(f"{_conflicts['ProductCategory']} code(s) with differing ProductCategory")
if _conflicts.get("PackUnits", 0) > 0:
    _conf_msgs.append(f"{_conflicts['PackUnits']} code(s) with differing PackUnits")
if _conf_msgs:
    st.warning(
        "Deduplication merged rows that disagree on an attribute: "
        + "; ".join(_conf_msgs)
        + ". The kept value is taken from the first matching row, so a different "
        "input row order could change classification or sizing for these codes. "
        "Consumption totals are unaffected. Consider mapping a Year column and "
        "using 'Keep latest year only', or harmonising these rows in the source."
    )

# Stale latest-year metadata (B4): the latest year's value was blank for some
# codes, so an earlier year's value was retained. Detection only.
_stale = base_info.get("stale_latest_year_groups") or {}
_stale_msgs = []
if _stale.get("ProductCategory", 0) > 0:
    _stale_msgs.append(f"{_stale['ProductCategory']} code(s) (ProductCategory)")
if _stale.get("SizeCategory", 0) > 0:
    _stale_msgs.append(f"{_stale['SizeCategory']} code(s) (SizeCategory)")
if _stale_msgs:
    st.warning(
        "For some codes the latest year's value was blank, so an earlier year's "
        "value was kept: " + "; ".join(_stale_msgs) + ". If a code was "
        "re-classified in the latest year, verify these; the plan currently uses "
        "the earlier-year value. Consumption totals are unaffected."
    )

# Guard: empty planning base
if len(planning_base) == 0:
    st.error("Planning base is empty after preprocessing. Check your year filter and deduplication settings.")
    st.stop()

work = planning_base.copy()

# Audit columns: classification provenance (engine/tool_list.py, v34.61).
# ToolClass is a finer subclass surfaced in the Technician Review and the
# export; it does not drive sizing.
add_classification_audit_columns(work)

# Run button
st.divider()
run = st.button("Run cabinet planning", type="primary", width='stretch')

# invalidate cached results when the user changes any setting that
_current_fingerprint = compute_run_fingerprint(FingerprintInputs(
    file_name=getattr(file, "name", None) if file else None,
    file_size=getattr(file, "size", None) if file else None,
    content_sha=_input_sha,
    sheet_tools=sheet_tools, sheet_ppe=sheet_ppe, calc_mode=calc_mode,
    columns=(
        col_code, col_desc1, col_desc2, col_cons, col_prod, col_sup, col_size,
        col_pack, col_year, col_program, col_site, col_dims, col_stdspecial,
        col_regrind, col_systemtyp, col_restock,
    ) + ((col_stock,) if col_stock else ()),
    restock_categories=_restock_categories,
    usage_threshold=usage_threshold, helix_threshold=helix_threshold,
    consumption_period_months=consumption_period_months,
    optional_thresholds_active=optional_thresholds_active,
    per_class_thresholds=per_class_thresholds,
    insert_default_pack_units=insert_default_pack_units,
    minimum_carousel_allocation=minimum_carousel_allocation,
    coverage_days=coverage_days, coverage_days_special=coverage_days_special,
    helix_single_spiral_overfill_factor=_plan_cfg.helix_overfill_factor,
    carousel_reserve_factor=_plan_cfg.carousel_reserve_factor,
    carousel_fill_ceiling=_plan_cfg.carousel_fill_ceiling,
    enable_rebalancer=enable_rebalancer, underuse_threshold_pct=underuse_threshold_pct,
    capacity_buffer_pct=capacity_buffer_pct, n_supply_points=n_supply_points, sp_mode=sp_mode,
    enable_pack_hint_extraction=enable_pack_hint_extraction, enable_bulk_routing=enable_bulk_routing,
    force_screws_accessories_kanban=force_screws_accessories_kanban, use_description_2=use_description_2,
    year_mode=year_mode_ui, dedup_mode=dedup_mode_ui, use_ai=use_ai,
    max_ai_items=max_ai_items, batch_size=batch_size,
    trim_ai_reason=trim_ai_reason, ai_concurrency=ai_concurrency,
    program_to_sp_map=program_to_sp_map, program_mapping_active=program_mapping_active,
    op_mode=op_mode, max_carousels_cap=max_carousels_cap,
    special_ktc_enabled=st.session_state.get("ks_special_ktc", False),
    effective_customer=effective_customer, effective_site=effective_site,
    apply_overrides=apply_overrides_ui,
    fixed_config=((fixed_machines, float(fixed_headroom_pct), bool(fixed_allow_spill))
                  + ((float(fixed_stock_months),) if fixed_stock_months > 0 else ())
                  if op_mode == FIXED_MODE else None),
))

if st.session_state.get("_run_fingerprint") != _current_fingerprint:
    # Settings changed — previous results no longer valid
    st.session_state["has_results"] = False

# Saving an override set (and a few other actions) sets this one-shot flag to
# force one pipeline run on the next rerun.
_force_run = bool(st.session_state.pop("_force_run", False))

# Gate: proceed if the user just clicked Run, OR a force-run was just requested,
if not run and not _force_run and not st.session_state.get("has_results"):
    st.info("Set your mapping and controls, then click 'Run cabinet planning'.")
    st.stop()

# Remember this fingerprint so the next rerun knows results are valid
st.session_state["_run_fingerprint"] = _current_fingerprint

# Boundary steps A through D moved verbatim to engine.boundary (v34.14);
# routed through the content-addressed cache so a plain rerun never repeats
# the per-row classification and resolution loops.
work = _cached_pre_ai_heuristics(
    work,
    enable_pack_hint_extraction=bool(enable_pack_hint_extraction),
    insert_default_pack_units=float(insert_default_pack_units),
)

# STEP E) Decide which rows need AI
def needs_ai_pack_check(prod_cat: str, pack_units: float, pack_source: str) -> bool:
    """Return True only if pack_units is suspicious AND wasn't reliably provided."""
    # Trust user-provided valid pack counts
    if pack_source == "Provided":
        try:
            if float(pack_units) > 0:
                return False
        except Exception:
            pass

    try:
        pu = int(pack_units)
    except Exception:
        pu = 0
    pc = norm(prod_cat)

    # Inserts should normally be 10-packs; anything else is suspicious
    if pc == "inserts" and pu != 10:
        return True
    # Unusually large packs with no trusted source — worth verifying
    if pu >= 50:
        return True
    return False

need_ai_rows: List[int] = []
per_row_ai_fields: Dict[int, Dict[str, bool]] = {}

for idx, row in work.iterrows():
    pc_weak = is_weak_category(str(row.get("ProductCategory", "")))
    # ALSO send rows whose heuristic confidence is 'unknown' or source 'Default'
    pc_low_conf = (
        str(row.get("ProductCategory_Confidence", "")) in ("unknown", "low")
        or str(row.get("ProductCategory_Source", "")) == "Default"
    )
    size_missing_now = str(row.get("SizeCategory", "")).strip() == ""
    pack_suspicious = needs_ai_pack_check(
        str(row.get("ProductCategory", "")),
        float(row.get("PackUnits", 1.0)),
        str(row.get("PackUnits_Source", "")),
    )
    if pc_weak or pc_low_conf or size_missing_now or pack_suspicious:
        need_ai_rows.append(idx)
        per_row_ai_fields[idx] = {
            "pc": pc_weak or pc_low_conf,
            "size": size_missing_now,
            "pack": pack_suspicious,
        }

need_ai_count = len(need_ai_rows)
if _sha_reuse_cls:
    st.info(
        f"Known workbook: {len(_sha_reuse_cls)} stored classification(s) for this "
        f"exact file are reused; covered items skip the AI stage."
    )
if _stored_source_cls:
    # Covered codes are answered by the store inside run_plan, so sending them
    # to the model would spend tokens on rows whose answer is already fixed.
    need_ai_rows = [
        _i for _i in need_ai_rows
        if str(work.at[_i, "Code"]) not in _stored_source_cls
    ]
    need_ai_count = len(need_ai_rows)

capped_rows = need_ai_rows[: int(max_ai_items)] if (use_ai and max_ai_items > 0) else []
skipped_ai = max(0, need_ai_count - len(capped_rows))

# Stamp AI_Consulted flags BEFORE we send — so the audit trail captures
for idx in capped_rows:
    fields = per_row_ai_fields.get(idx, {})
    if fields.get("pc"):
        work.at[idx, "ProductCategory_AI_Consulted"] = True
    if fields.get("size"):
        work.at[idx, "SizeCategory_AI_Consulted"] = True
    if fields.get("pack"):
        work.at[idx, "PackUnits_AI_Consulted"] = True

if use_ai and len(capped_rows) > 0:
    _est = estimate_ai_run(len(capped_rows), batch_size, ai_concurrency, trim_ai_reason)
    batches = _est["batches"]
    est_seconds = _est["seconds"]
    est_cost = _est["cost"]

    st.info(
        f"AI plan: {len(capped_rows)} item(s) in {batches} batch(es). "
        f"Initial ETA (rough): ~{_fmt_seconds(est_seconds)}. "
        f"Initial cost estimate: ~${est_cost:.4f} (rough)."
    )
    if skipped_ai > 0:
        st.warning(f"{skipped_ai} item(s) require AI but will be skipped due to 'Max AI items per run'.")
elif use_ai and need_ai_count == 0:
    st.success("No AI needed: deterministic rules covered Category/Size/PackUnits.")

# STEP F) Batched AI execution
ai_batches_run = 0
ai_items_run = 0
ai_batches_failed = 0
ai_missing_responses = 0
total_in_tokens = 0
total_out_tokens = 0
ai_errors: List[str] = []

if use_ai and len(capped_rows) > 0:
    total_batches = math.ceil(len(capped_rows) / int(batch_size))
    progress = st.progress(0, text="Starting AI classification…")
    status = st.empty()
    cost_line = st.empty()

    # Show an immediate "working" message so the user isn't staring at a
    # frozen 0% bar while the first batch is in flight. Without this, the gap
    # between clicking Run and the first OpenAI response (which can be many
    # seconds) looks like the app has hung, prompting refreshes / double-clicks.
    status.info(
        f"Classifying {len(capped_rows)} item(s) with AI in {total_batches} "
        f"batch(es), up to {int(ai_concurrency)} in parallel — contacting "
        f"OpenAI now. This can take a little while; please don't refresh or "
        f"click Run again."
    )

    # Prepare all batches upfront so workers can run in parallel (engine/ai_classifier.py).
    # Each plan knows its position, row indices, item count, and the cache key
    # derived from the per-item payload the model is asked to classify.
    batch_plans: List[Dict[str, Any]] = build_classification_batches(
        work, capped_rows,
        batch_size=int(batch_size), model=OPENAI_MODEL,
        trim_reason=trim_ai_reason, max_desc_chars=MAX_DESC_CHARS_FOR_AI,
    )

    def _run_one_batch(plan: Dict[str, Any]) -> Dict[str, Any]:
        """Worker function — executes in a thread. Never writes to ``work``
        directly (merging happens in the main thread after the future
        completes, to keep pandas operations single-threaded)."""
        t0 = time.monotonic()
        result_map, in_tok, out_tok, err, missing_count = ai_classify_batch_cached(plan["cache_key"])
        return {
            "b": plan["b"],
            "batch_idx": plan["batch_idx"],
            "n_items": plan["n_items"],
            "result_map": result_map,
            "in_tok": int(in_tok or 0),
            "out_tok": int(out_tok or 0),
            "err": err,
            "missing": missing_count,
            "duration": time.monotonic() - t0,
        }

    # fire batches in parallel via ThreadPoolExecutor. OpenAI's rate
    start_all = time.monotonic()
    completed_batches = 0
    diag = AIRunDiagnostics()

    with ThreadPoolExecutor(max_workers=int(ai_concurrency)) as executor:
        future_to_plan = {executor.submit(_run_one_batch, p): p for p in batch_plans}

        for future in as_completed(future_to_plan):
            try:
                res = future.result()
            except Exception as e:
                # Thread raised an unhandled exception (shouldn't happen,
                # ai_classify_batch_cached catches internally, but be safe)
                log_exception("AI batch crashed", e)
                plan = future_to_plan[future]
                diag.record_crash(plan["b"] + 1, total_batches, e)
                completed_batches += 1
                progress.progress(completed_batches / max(total_batches, 1))
                continue

            batch_idx = res["batch_idx"]
            result_map = res["result_map"]
            diag.record_batch(res, total_batches)

            now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

            # Merge this batch's AI results into work (engine/classification.py).
            # Main thread only, so pandas operations stay single-threaded.
            merge_classification_results(
                work, batch_idx, result_map,
                model=OPENAI_MODEL, timestamp_utc=now_utc,
            )

            completed_batches += 1

            # Progress + ETA (batches complete out-of-order when parallel, so
            # we base ETA on wall-clock completion rate, not batch ordinal)
            elapsed = time.monotonic() - start_all
            if completed_batches > 0:
                avg_wall = elapsed / completed_batches
                remaining_eta = (total_batches - completed_batches) * avg_wall / int(ai_concurrency)
            else:
                remaining_eta = 0.0
            avg_dur = diag.avg_duration

            status_msg = (
                f"{completed_batches}/{total_batches} batches done  |  "
                f"avg {avg_dur:.1f}s/batch  |  "
                f"elapsed {_fmt_seconds(elapsed)}  |  "
                f"ETA {_fmt_seconds(remaining_eta)}  |  "
                f"parallel workers: {int(ai_concurrency)}"
            )
            if diag.batches_failed > 0:
                status_msg += f"  |  failed: {diag.batches_failed}"
            status.info(status_msg)

            if diag.total_tokens > 0:
                real_cost = diag.cost(PRICE_INPUT_PER_1M, PRICE_OUTPUT_PER_1M)
                cost_line.caption(
                    f"Token usage so far: input {diag.in_tokens:,} | output {diag.out_tokens:,} | "
                    f"Estimated cost so far: ${real_cost:.4f}"
                )

            progress.progress(completed_batches / max(total_batches, 1))

    # Expose the accumulated diagnostics under the names the rest of the page
    # reads (summary line, Run_Metadata, run persistence). The object is the
    # source of truth; these are a thin compatibility view for now.
    ai_batches_run = diag.batches_run
    ai_items_run = diag.items_run
    ai_batches_failed = diag.batches_failed
    ai_missing_responses = diag.missing_responses
    total_in_tokens = diag.in_tokens
    total_out_tokens = diag.out_tokens
    ai_errors = diag.errors


    # Surface AI errors prominently
    if ai_errors:
        st.error(
            f"AI processing encountered errors in {ai_batches_failed} of {total_batches} batch(es). "
            "Affected rows kept their heuristic / default values — this usually means a configuration, "
            "network, or API-version issue. Details below."
        )
        with st.expander(f"Show AI error details ({len(ai_errors)} message(s))"):
            for e in ai_errors[:50]:
                st.caption(f"• {e}")
            if len(ai_errors) > 50:
                st.caption(f"... and {len(ai_errors) - 50} more not shown")
    if ai_missing_responses > 0:
        st.warning(
            f"{ai_missing_responses} row(s) were sent to AI but the model returned no result for them. "
            "They kept their heuristic / default values."
        )

# Final safety pass and default size fill moved verbatim to engine.boundary
# (v34.14), cached on frame content plus the insert default pack size.
work = _cached_post_ai_safety(
    work,
    insert_default_pack_units=float(insert_default_pack_units),
)

# ---------------------------------------------------------------------------
# Numbering-only mode (v34.44): assign the article numbers and stop. The
# classification above resolved ToolClass (the Kromi code source); the chosen
# default property system (with a mapped System type column overriding per
# row) decides which articles get the customer-property predecessor + KROMI
# successor pair and which get one KROMI-standard number. No cabinet is
# planned, nothing is persisted, and the only output is the Article setup
# sheet as its own workbook.
if op_mode == "NumberingOnly":
    st.subheader("Article setup")
    st.caption(
        "Numbering-only mode: no cabinets are planned and nothing is saved "
        "to the database. KTC articles receive the customer-property "
        "predecessor and the KROMI-property successor; Kanban articles "
        "receive one KROMI-standard number."
    )
    _nb_ktc_id = str(ktc_id_input or "").strip()
    _nb_setup = None
    if not (_nb_ktc_id.isdigit() and len(_nb_ktc_id) == 3):
        st.error(
            "Enter a valid 3-digit KTC-ID in Run setup; it forms the first "
            "three digits of every generated number."
        )
        st.stop()
    try:
        _nb_setup = build_article_setup(
            resolve_article_system(work, numbering_default_system), _nb_ktc_id
        )
        if _nb_setup is not None:
            # Master-file order: one row per article as the source lists
            # them; KTC successor duplicates follow after the last row.
            _nb_setup = order_article_setup(_nb_setup, _nb_code_order)
    except ValueError as _nb_exc:
        st.error(
            f"Could not assign the numbers: {_nb_exc} Map a description "
            "column with more distinguishing digits (the dimension field "
            "comes from the mapped Description) and run again."
        )
        st.stop()
    if _nb_setup is None:
        st.error(
            "Could not build the article setup: the run needs a mapped "
            "Description column and the classification's ToolClass."
        )
        st.stop()

    _nb_problems = check_kromi_uniqueness(_nb_setup)
    if _nb_problems:
        st.error("Number verification FAILED — do not import this list:")
        for _p in _nb_problems:
            st.markdown(f"- {_p}")
    else:
        st.success(
            f"{len(_nb_setup)} number(s) assigned; all unique, 12-digit, "
            "and well-formed."
        )
    # Successors are the only KROMI-property rows (v34.45: Kanban stock is
    # customer property too), so they count the KTC pairs.
    _nb_pairs = int((_nb_setup["Property"] == "KROMI property").sum())
    _nb_single = int(len(_nb_setup)) - 2 * _nb_pairs
    st.caption(
        f"{_nb_pairs} KTC article(s) with predecessor + successor pair, "
        f"{_nb_single} article(s) with one KROMI-standard number."
    )
    st.dataframe(_arrow_safe(_nb_setup), width="stretch", hide_index=True)
    st.download_button(
        "⬇ Download Article setup (Excel)",
        data=build_article_setup_workbook(_nb_setup),
        file_name=_export_name("ArticleSetup", "xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        key="dl_article_setup",
    )
    st.session_state["has_results"] = True
    st.stop()

# The deterministic pipeline: one composed engine call (engine/plan.run_plan),
# wrapped by _cached_run_plan (st.cache_data). The page resolves session state,
# widgets, mapping choices, and I/O into explicit inputs first; the engine call
# is a pure function of those inputs, so a rerun with unchanged inputs is a
# cache hit that replays nothing. Every status message the old inline pipeline
# rendered is rendered below from PlanResult, same content, same order.

# Gather the effective technician override set (live editor > database set >
# file library; an explicit "none" recompute stays empty). I/O stays here in
# the page; only the resulting frame crosses into the engine, and the frame is
# never mutated, so the persist section's override signature hashes exactly
# what was gathered here.
overrides_active_df = pd.DataFrame(columns=OVERRIDE_COLUMNS)
_override_store_unavailable = False
# What this run applied, recorded with the run (v34.54, audit C9): "off",
# "editor" (unsaved corrections), "db" with the set id, "none", "unavailable".
_ov_applied: Dict[str, Any] = {"source": "off", "set_id": None}
if apply_overrides_ui:
    _pending_now = st.session_state.get("_pending_overrides") or {}
    if _pending_now:
        _ov_applied = {"source": "editor", "set_id": None}
        # Live editing: the technician's accumulated corrections (gathered across
        # every filter and page in the editor) apply to this run. They outrank a
        # picker override choice because editing is the more recent, deliberate
        # action; the picker's "Load & recompute" and a new file upload both
        # clear them so those flows are not shadowed.
        overrides_active_df = pending_overrides_to_df(_pending_now)
    elif _reload_ctx and _reload_ctx.get("override_mode") == "db" and _reload_ctx.get("override_set_id"):
        # Recompute draws overrides from the chosen database set. The user
        # asked for exactly this set, so an unreadable database stops the run
        # with an explanation instead of crashing or running without it.
        try:
            _oc = _kromi_db.init_db(_resolve_db_path())
            try:
                overrides_active_df = _kromi_db.override_set_as_dataframe(
                    _oc, _reload_ctx["override_set_id"]
                )
                _ov_applied = {"source": "db", "set_id": int(_reload_ctx["override_set_id"])}
            finally:
                _oc.close()
        except Exception as _oc_exc:
            log_exception("Chosen override set could not be read", _oc_exc)
            st.error(
                "The chosen override set could not be read from the database "
                f"({type(_oc_exc).__name__}), so this recompute cannot apply it. "
                "Choose 'No overrides' to recompute without it, or retry once "
                "the database is reachable.")
            st.stop()
    elif _reload_ctx and _reload_ctx.get("override_mode") == "none":
        # Recompute explicitly without overrides: an empty set is a no-op apply.
        overrides_active_df = pd.DataFrame(columns=OVERRIDE_COLUMNS)
        _ov_applied = {"source": "none", "set_id": None}
    else:
        overrides_active_df, _ov_source, _ov_set_id = _resolve_active_overrides(
            effective_customer, effective_site
        )
        _ov_applied = {
            "source": _ov_source,
            "set_id": int(_ov_set_id) if (_ov_source == "db" and _ov_set_id is not None) else None,
        }
        if len(overrides_active_df) > 0 and _ov_source == "db":
            st.caption(f"Overrides applied from database set #{_ov_set_id}.")
        elif _ov_source == "unavailable":
            _override_store_unavailable = True
            st.warning(
                "The override database could not be read, so this run uses NO "
                "technician overrides. Results and exports may differ from the "
                "corrected plan. Check the database file (KROMI_DB_PATH or the "
                "default folder in your user profile) and run again.")

# Resolve every non-frame input into the frozen PlanParams. Maps travel as
# sorted tuples so the object is hashable and the cache key is content-true: a
# live technician correction changes the overrides frame, a manual Helix-fit
# changes the fix tuple, an AI merge changes the work frame, any settings
# change alters these params -- each of those is a miss; a plain widget rerun
# changes nothing and is a hit.
_manual_size_fix = dict(st.session_state.get("manual_size_fix", {}))
_stored_cls: Tuple = ()
if _stored_source_cls:
    _stored_cls = tuple(sorted(
        ((_c, _rec.get("size_category"), _rec.get("product_category"))
         for _c, _rec in _stored_source_cls.items()),
        key=lambda t: str(t[0]),
    ))
# The run's settings, after the mode rules, and the planner parameters built
# from them (engine/run_settings.py, v34.62).
_run_settings = effective_settings(RunSettings(
    use_description_2=bool(use_description_2), year_mode=year_mode, dedup_mode=dedup_mode,
    ktc_threshold=usage_threshold,
    optional_thresholds_active=bool(optional_thresholds_active),
    per_class_thresholds=tuple(sorted(per_class_thresholds.items())),
    insert_pack_units=insert_default_pack_units, helix_threshold=helix_threshold,
    consumption_months=consumption_period_months,
    helix_overfill_factor=helix_single_spiral_overfill_factor_ui,
    min_carousel_allocation=minimum_carousel_allocation,
    coverage_days=coverage_days, coverage_days_special=coverage_days_special,
    special_ktc=bool(st.session_state.get("ks_special_ktc", False)),
    carousel_reserve_factor=carousel_reserve_factor_ui,
    carousel_fill_ceiling=carousel_fill_ceiling_ui,
    enable_rebalancer=bool(enable_rebalancer), underuse_threshold_pct=underuse_threshold_pct,
    capacity_buffer_pct=capacity_buffer_pct, restock_categories=_restock_categories,
    pack_hint_extraction=bool(enable_pack_hint_extraction),
    bulk_routing=bool(enable_bulk_routing),
    force_screws_kanban=bool(force_screws_accessories_kanban),
    n_supply_points=int(n_supply_points), sp_mode=sp_mode,
    calc_mode=calc_mode_from_label(calc_mode), op_mode=op_mode,
    max_carousels=max_carousels_cap, fixed_headroom_pct=fixed_headroom_pct,
    fixed_allow_spill=fixed_allow_spill, fixed_stock_promotion=fixed_stock_months > 0,
    fixed_stock_months=fixed_stock_months, fixed_machines=fixed_machines,
), stdspecial_mapped=bool(col_stdspecial), both_listings=both_listings)
_plan_params = build_plan_params(
    _run_settings, mapping=_mapping, base_info=base_info,
    manual_size_fixes=_manual_size_fix, stored_classifications=_stored_cls,
)

import hashlib as _hashlib

_plan_key = "|".join((
    _frame_token(work),
    _frame_token(overrides_active_df),
    _hashlib.sha256(repr(_plan_params).encode()).hexdigest(),
))
_plan_t0 = time.perf_counter()
_plan_result = _cached_run_plan(_plan_key, work, overrides_active_df, _plan_params)
# Wall time of this pass's plan retrieval: engine time on a miss, copy time
# on a hit. Persisted as duration_ms (v34.33); persistence only fires on the
# pass that produced a new run, so the archived value is the compute cost.
_plan_wall_ms = int((time.perf_counter() - _plan_t0) * 1000)
work = _plan_result.work
_sp_conservation = _plan_result.sp_conservation
_split_coverage = _plan_result.split_coverage
override_stats = _plan_result.override_stats
_rerouted_flips = _plan_result.rerouted_flips
_routing_override_counts = _plan_result.routing_override_counts
vend_stats = _plan_result.vend_stats
validation_issues = _plan_result.validation_issues
_integrity = _plan_result.integrity
bucket_plans = _plan_result.bucket_plans
rebalance_audit_all = _plan_result.rebalance_audit
grand = _plan_result.grand

# ---- Status rendering: the same messages the inline pipeline produced, in
# ---- the same relative order, now read from PlanResult.

# Supply point assignment (Partition OR Replicate)
_n_sp = int(n_supply_points)
if _sp_conservation:
    st.error("Supply-point conservation check FAILED: " + "; ".join(_sp_conservation))
if sp_mode == SP_MODE_REPLICATE and _n_sp > 1 and not program_mapping_active:
    st.caption(
        f"Replicate mode: each of the {len(work) // _n_sp} unique items has been duplicated "
        f"across {_n_sp} supply points with consumption divided by {_n_sp}. "
        f"Working dataframe now has {len(work):,} rows ({len(work) // _n_sp:,} × {_n_sp} SPs)."
    )

# Routing & coverage diagnostics — make any silent no-op visible. If a feature
# is switched on in the UI but matches nothing in the data, say so explicitly
# rather than letting it appear active while having no effect.
if _plan_result.n_pack_default > 0:
    st.warning(
        f"{_plan_result.n_pack_default} row(s) had no usable pack size and were assumed "
        "to be 1 piece per pack. This affects pack-based sizing (spirals/slots) "
        "and capacity; check those rows if this is unexpected."
    )
if optional_thresholds_active:
    _set_classes = {k: v for k, v in per_class_thresholds.items()
                    if abs(float(v) - float(usage_threshold)) > 1e-9}
    if _set_classes:
        st.caption(
            "Optional per-class thresholds active (pcs/mo): "
            + ", ".join(f"{k}={v:g}" for k, v in _set_classes.items())
        )
    else:
        st.caption(
            "Optional thresholds shown, but every class is at the standard "
            f"{float(usage_threshold):g} pcs/mo — same as the standard threshold."
        )

if col_stdspecial is not None:
    if _plan_result.stdspecial_missing:
        st.warning(
            "A Standard/Special column is mapped, but it did not survive "
            "preprocessing, so the coverage split had no effect. This should not "
            "happen; please send the input file to the Cabinet Planner maintainer."
        )
    elif _plan_result.stdspecial_counts is not None:
        _n_std, _n_spec, _n_unk = _plan_result.stdspecial_counts
        if _n_spec == 0:
            st.warning(
                "A Standard/Special column is mapped but **no rows matched "
                "'special'** "
                f"({_n_unk} value(s) unrecognised, sized as standard). "
                "Expected values: the words standard/special (in "
                "fr/pl/de/es/en/sk/sl), 1 = standard / 2 = special, or yes = "
                "standard / no = special. The special coverage had no effect."
            )
        elif _split_coverage:
            st.caption(
                f"Standard/Special coverage active: {_n_std} standard, "
                f"{_n_spec} special, {_n_unk} unrecognised (sized as standard)."
            )
        else:
            st.caption(
                f"Standard/Special column mapped: {_n_std} standard, {_n_spec} "
                f"special, {_n_unk} unrecognised. Standard and special coverage "
                "are equal, so no split is applied."
            )

# Manual size fixes and the stored-classification reuse both applied inside
# run_plan at their historical pipeline positions; only the miss count is a
# visible message.
if _plan_params.stored_classifications and _plan_result.reuse_misses_n:
    st.caption(
        f"{_plan_result.reuse_misses_n} row(s) had no saved classification and kept "
        "the heuristic result."
    )

# Technician overrides: applied inside run_plan; summary rendered here.
if apply_overrides_ui:
    if len(overrides_active_df) > 0:
        if _rerouted_flips:
            st.info(
                f"{_rerouted_flips} overridden row(s) were re-routed across "
                "the KTC/Kanban threshold to reflect their changed attributes."
            )

        # Surface a one-line summary right after applying
        touched_n = override_stats["rows_touched"]
        unmatched_n = len(override_stats["unmatched_overrides"])
        invalid_n = len(override_stats["invalid_overrides"])
        msg_bits = [f" Overrides applied: **{touched_n}** row(s)"]
        if override_stats["fields_changed"]:
            changes = ", ".join(f"{k} ({v})" for k, v in override_stats["fields_changed"].items())
            msg_bits.append(f"Fields changed: {changes}")
        if unmatched_n > 0:
            msg_bits.append(f"{unmatched_n} stale override(s) matched no row")
        if invalid_n > 0:
            msg_bits.append(f"{invalid_n} invalid override(s) skipped")
        st.success("  |  ".join(msg_bits))
    else:
        # No stored set for this scope; quiet caption
        st.caption(
            " No stored override set for this scope yet. Use the Technician "
            "review panel below the dashboard to create corrections."
        )
else:
    st.caption(" Override application is OFF for this run.")

# Restocking summary (v34.24)
_ri = _plan_result.restock_info
_restock_slots_total = restock_slots_total(_ri)
if _restock_slots_total > 0:
    _n_flagged = int(_ri.get("provided_true", 0)) + int(_ri.get("rule_true", 0))
    _locker_slots = _restock_slots_total - int(_ri.get("slots_carousel", 0))
    st.info(
        f"Restocking: {_n_flagged} restockable item(s) "
        f"({_ri.get('provided_true', 0)} from the mapped column, "
        f"{_ri.get('rule_true', 0)} by category rule) — "
        f"{_ri.get('slots_carousel', 0)} Carousel and {_locker_slots} Locker "
        f"buffer compartment(s) reserved. "
        + ("In the fixed configuration a buffer is kept only where the "
           "machines have space left (see the fit below)."
           if op_mode == FIXED_MODE else
           "Buffers are exact reservations: the rebalancer and the cap never "
           "move or reduce them.")
    )
if int(_ri.get("flagged_kanban", 0)) > 0:
    st.caption(
        f" {_ri.get('flagged_kanban', 0)} restockable-flagged item(s) are "
        f"Kanban-routed; restocking does not apply to Kanban, so no buffer "
        f"is reserved for them."
    )
if int(_ri.get("unknown_values", 0)) > 0:
    st.caption(
        f" {_ri.get('unknown_values', 0)} value(s) in the restocking column "
        f"were not recognized as yes or no and count as no; check the file."
    )
_cap_exceeded = [
    _lbl for _lbl, _bp in _plan_result.bucket_plans
    if _bp.get("carousel_cap_exceeded_by_restock")
]
for _lbl in _cap_exceeded:
    st.warning(
        f"Carousel cap exceeded in {_lbl}: restock buffer compartments cannot "
        f"spill into Helix coils, so they pushed the Carousel count above the "
        f"configured cap. Nothing was dropped. Raise the cap, reduce the "
        f"restockable scope, or switch the operational mode, then recompute."
    )

# Customer-specified System type override (Lagersystem) and special-to-KTC ran
# inside run_plan (system type first, so a system-type-fixed row wins over the
# special rule); the counts come back so the status captions render here.
if _plan_result.force_system_type:
    _st_counts = _routing_override_counts["system_type"]
    _n_ktc, _n_locker, _n_flex = _st_counts["ktc"], _st_counts["locker"], _st_counts["flex"]
    if (_n_ktc + _n_locker + _n_flex) > 0:
        st.caption(
            f"System type override active: {_n_ktc} forced KTC, {_n_locker} forced Locker, "
            f"{_n_flex} flexible (KTC or Kanban). Fixed rows are protected from bulk "
            "routing and cabinet consolidation."
        )
    else:
        st.warning(
            "A System type column is mapped, but no row carried a recognised value "
            "(KTC / KTC or Kanban / Locker), so the override had no effect."
        )
if _plan_result.force_special_ktc:
    _n_special_forced = _routing_override_counts["special_forced"]
    if _n_special_forced > 0:
        st.caption(
            f"Special tools forced to KTC: {_n_special_forced} row(s) pinned to a "
            "vending machine regardless of consumption, and protected from bulk "
            "routing and cabinet consolidation."
        )
    else:
        st.warning(
            "'Set special tools as KTC' is on, but no row was marked Special "
            "(values 2 / 'special' / 'no'), so nothing was forced."
        )

# Plan integrity check — the invariant/reconciliation layer ran inside
# run_plan over the final plan; render its verdict here.
if _integrity.ok:
    st.success(f"Plan integrity check: {_integrity.n_passed}/{_integrity.n_checks} invariants hold.")
else:
    st.error(
        f"Plan integrity check FAILED ({_integrity.n_passed}/{_integrity.n_checks} "
        "invariants hold). The plan below may be incorrect — please review before "
        "using it:"
    )
    for _v in _integrity.violations:
        st.markdown(f"- {_v}")

# Results preview
st.subheader("Resulting classification (preview)")
preview_summary = (
    f"AI batches run: {ai_batches_run} | AI items processed: {ai_items_run} | "
    f"Failed batches: {ai_batches_failed} | Missing responses: {ai_missing_responses} | "
    f"Tokens: in {total_in_tokens:,}, out {total_out_tokens:,}"
)
st.caption(preview_summary)

if validation_issues:
    st.error("Pre-rollup data integrity issues detected:")
    for v in validation_issues:
        st.caption(f"• {v}")
    st.warning("Cabinet counts below may be inaccurate. Review the Result sheet in the export before sending to the customer.")
else:
    st.success("Data integrity checks passed.")

# Bulk-routing feedback
if enable_bulk_routing and vend_stats.get("routed_rows", 0) > 0:
    family_breakdown = vend_stats.get("by_family", {})
    fam_summary = ", ".join(f"{k}: {v}" for k, v in sorted(family_breakdown.items(), key=lambda kv: -kv[1]))
    ov_blocked = int(vend_stats.get("overridden_bulk_candidates", 0))
    extra = ""
    if ov_blocked > 0:
        extra = (
            f" | {ov_blocked} bulk-family row(s) were KEPT in vending because of "
            "technician overrides."
        )
    st.info(
        f" **Bulk routing**: moved {vend_stats['routed_rows']:,} row(s) out of vending "
        f"into Bulk/Kanban. Removed {vend_stats['removed_spirals']:,} spirals and "
        f"{vend_stats['removed_carousel_slots']:,} carousel stockpiles from the vending plan. "
        f"Families: {fam_summary}.{extra}"
    )
elif enable_bulk_routing:
    st.caption(" Bulk routing enabled — no rows matched bulk-consumable families in this dataset.")

# Program→SP mapping feedback
if program_mapping_active:
    sp_row_counts = work.groupby("SupplyPoint").size().to_dict()
    sp_lines = []
    for sp in sorted(sp_row_counts.keys()):
        sp_lines.append(f"SP {sp}: {sp_row_counts[sp]} row(s)")
    st.caption(
        f" Program→SP mapping active: {len(program_to_sp_map)} programmes mapped across "
        f"{int(n_supply_points)} supply points — " + " | ".join(sp_lines)
    )

# Spiral Hogs audit — the snapshot was taken inside run_plan at the historical
# position (before bucket planning writes rebalanced routing back), so the
# numbers match what the inline pipeline showed.
_sp_hog_threshold = 10.0
suspicious_pack = _plan_result.hogs
if not suspicious_pack.empty:
    total_spirals_from_hogs = int(pd.to_numeric(suspicious_pack["Spirals_needed"], errors="coerce").fillna(0).sum())
    total_car_from_hogs = int(pd.to_numeric(suspicious_pack["Carousel_stockpiles"], errors="coerce").fillna(0).sum())
    st.warning(
        f" **Pack-size audit**: {len(suspicious_pack)} row(s) have PackUnits defaulting to 1 "
        f"AND move more than {_sp_hog_threshold:.0f} packs/month. These rows alone account for "
        f"{total_spirals_from_hogs:,} spirals and {total_car_from_hogs:,} carousel stockpiles in the current plan. "
        f"If any are actually sold in packs (bags of 10, cartons of 50, rolls of 1900, etc.), "
        f"the cabinet count is likely inflated. Review the top items below and correct their "
        f"PackUnits in the source data before finalizing."
    )
    with st.expander(f"Show top suspicious items ({min(50, len(suspicious_pack))} shown)"):
        hog_cols = [
            "Listing", "Code", "Description",
            "Consumption_pcs", "PackUnits", "Monthly_packs", "Target_packs",
            "CabinetType", "Spirals_needed", "Carousel_stockpiles",
        ]
        hog_cols = [c for c in hog_cols if c in suspicious_pack.columns]
        st.dataframe(
            suspicious_pack[hog_cols].head(50),
            width='stretch',
            hide_index=True,
        )

# Classification review — eyeball-verify before trusting numbers
st.subheader("Classification review")
_nrows = len(work)
_other_n = (work["ProductCategory"].astype(str).str.lower() == "other").sum()
_other_pct = (_other_n / _nrows * 100) if _nrows else 0.0

if _other_pct > 20 and not use_ai:
    st.error(
        f" {_other_n} rows ({_other_pct:.1f}%) have category='other'. "
        f"This exceeds the 20% threshold for reliable cabinet sizing. "
        f"Please enable AI in the sidebar, or improve the source-data descriptions."
    )
elif _other_pct > 20:
    st.warning(
        f" {_other_n} rows ({_other_pct:.1f}%) ended up as 'other' even after AI. "
        f"Cabinet sizing for these rows may be inaccurate — consider improving descriptions."
    )

with st.expander(" Show classification review (by category, with samples)"):
    for cat in sorted(work["ProductCategory"].astype(str).unique()):
        subset = work[work["ProductCategory"] == cat]
        n = len(subset)
        # Evidence distribution
        if "ProductCategory_Evidence" in subset.columns:
            ev_counts = subset["ProductCategory_Evidence"].astype(str).value_counts().head(4)
            ev_summary = ", ".join(f"{k}: {v}" for k, v in ev_counts.items())
        else:
            ev_summary = ""
        st.markdown(f"**`{cat}`** — {n} rows ({n/_nrows*100:.1f}%)" + (f"  \n_Top evidence: {ev_summary}_" if ev_summary else ""))
        # 8 sample descriptions, prefer diverse
        sample = subset.drop_duplicates("Description").head(8)
        sample_cols = [c for c in ["Code", "Description", "ProductCategory_Source", "ProductCategory_Evidence", "ProductCategory_Confidence"] if c in sample.columns]
        st.dataframe(sample[sample_cols], width='stretch', hide_index=True)

# Classification-preview snapshot: taken inside run_plan at the historical
# position (before bucket planning), so it shows the same values as before.
st.dataframe(_plan_result.preview, width='stretch')

# Multi-bucket plan computation ran inside run_plan (operational-mode apply,
# bucket construction, per-bucket planning with the rebalancer and the carousel
# cap, grand total). The derived flags below feed the sections that follow.
# (KTC/Kanban/Helix/Carousel sub-frames for export are derived later from the
# FINAL `work` — after rebalancing/buffer — so the per-sheet values stay
# consistent with the Result sheet; see the export-verification block.)
buf_pct = float(capacity_buffer_pct)
buffer_active = buf_pct > 0
separated_mode = calc_mode.startswith("Separated")
n_sp = int(n_supply_points)
listings_arg: Optional[List[str]] = list(_plan_result.listings) if separated_mode else None

# Operational mode banner: make the active composition override explicit.
if op_mode == "Helix":
    st.info(
        "**Operational mode: Helix only.** Every vending tool is stored in a Helix "
        "coil; no Carousels or lockers are used. Tools too large for a spiral are "
        "highlighted below."
    )
elif op_mode == "Carousel":
    st.info(
        "**Operational mode: Carousel only.** Every vending tool is stored in a "
        "Carousel slot; no Helix or lockers are used. Locker-size tools are "
        "highlighted below."
    )
elif op_mode == "Capped":
    st.info(
        f"**Operational mode: Helix + Carousel, capped at {int(max_carousels_cap)} "
        "Carousel(s) per supply point.** Carousel demand above the cap spills into "
        "Helix coils; tools too large to spill are highlighted below."
    )
elif op_mode == FIXED_MODE:
    st.info(
        "**Operational mode: fixed configuration.** Articles are placed into "
        f"the configured machines, most used first, keeping {fixed_headroom_pct:g} % "
        "of every machine free. Articles that do not fit are flagged below, "
        "never dropped."
    )

# Rebalancer audit — show what got consolidated
if rebalance_audit_all:
    total_items_moved = sum(len(e["items_moved"]) for e in rebalance_audit_all)
    total_cabs_saved = sum(
        e["cabinets_before"] - e["cabinets_after"] for e in rebalance_audit_all
    )
    st.info(
        f"**Rebalancer**: consolidated {len(rebalance_audit_all)} underused cabinet(s), "
        f"moved {total_items_moved} item(s), saved {total_cabs_saved} cabinet(s) total. "
        f"Threshold: {underuse_threshold_pct:.0f}% occupation."
    )
    with st.expander("Rebalance details — what moved and why", expanded=False):
        for event in rebalance_audit_all:
            bucket = event.get("bucket", "")
            elim = event["eliminated_cabinet"]
            moved = event["items_moved"]
            st.markdown(
                f"**{bucket}** — eliminated 1 underused **{elim}** cabinet "
                f"({event['cabinets_before']} → {event['cabinets_after']} total cabinets)"
            )
            move_summary = pd.DataFrame(moved)
            if not move_summary.empty:
                st.dataframe(move_summary, hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Problematic-size detection: surface L/XL tools that force an underused
# Carousel a resize-to-Helix would eliminate, and offer a one-click fix.
_size_issue_rows = (
    # One row per unique code: in replicate mode a flagged tool exists once per
    # supply point, and the fix is per code (all replicas are repackaged
    # together), so the form must render it once. Also keeps the per-code
    # checkbox keys unique, which Streamlit enforces.
    work[work["SizeIssue"] == True].drop_duplicates("Code")  # noqa: E712
    if "SizeIssue" in work.columns
    else work.iloc[0:0]
)
_active_size_fixes = dict(st.session_state.get("manual_size_fix", {}))
if len(_size_issue_rows) > 0 or _active_size_fixes:
    st.subheader("Problematic size detected")
if len(_size_issue_rows) > 0:
    if op_mode == "Helix":
        _size_msg = (
            f"{len(_size_issue_rows)} item(s) are larger than a Helix spiral can "
            "hold (size L or bigger) but are placed in Helix because Helix-only mode "
            "is active. They are sized in anyway -- repackage them to fit a coil "
            "(set size to M or smaller) with **Treat as Helix-fit (M)**, or change "
            "the operational mode. Confirm the tool physically fits before applying."
        )
    elif op_mode == "Carousel":
        _size_msg = (
            f"{len(_size_issue_rows)} item(s) are a locker size (XXL/XLS/XXLS) that a "
            "Carousel slot can't hold but are placed in Carousel because Carousel-only "
            "mode is active. Repackage them to fit (set size to M or smaller) with "
            "**Treat as Helix-fit (M)**, or change the operational mode. Confirm the "
            "tool physically fits before applying."
        )
    elif op_mode == FIXED_MODE:
        _size_msg = (
            f"{len(_size_issue_rows)} item(s) did not fit the Carousel and are too "
            "large (L/XL) for a Helix spiral; the space left in the Helix could "
            "take them. If they can be repackaged to fit a spiral, use **Treat as "
            "Helix-fit (M)** to place them there. Confirm the tool physically fits "
            "a spiral before applying."
        )
    elif op_mode == "Capped":
        _size_msg = (
            f"{len(_size_issue_rows)} item(s) have a size (L/XL) that keeps the Carousel "
            "count above your limit -- they can't spill into a Helix because a spiral is "
            "too small. If they can be repackaged to fit a Helix, use **Treat as "
            "Helix-fit (M)** to bring the Carousel count within the cap. Confirm the "
            "tool physically fits a spiral before applying."
        )
    else:
        _size_msg = (
            f"{len(_size_issue_rows)} item(s) have a size that forces a lightly-used "
            "Carousel which can't merge into a Helix: an L or XL tool is too big for a "
            "spiral, so the rebalancer can't fold it in. If the tool can be repackaged "
            "to fit a Helix, use **Treat as Helix-fit (M)** to consolidate it and drop "
            "the cabinet. Otherwise the separate Carousel is needed for its volume. This "
            "only changes the size you assert for the tool -- confirm it physically fits "
            "a spiral before applying."
        )
    st.warning(_size_msg)
    # Batch the size fixes: tick every item you can repackage to fit a Helix
    # spiral and apply them in one submit. A form holds the checkboxes without
    # re-running the page on each tick, so the whole batch costs one rerun
    # instead of one rerun per item.
    with st.form("helix_fit_form"):
        _fit_codes = []
        for _si_idx, _si_row in _size_issue_rows.iterrows():
            _si_code = str(_si_row.get("Code", ""))
            _fit_codes.append(_si_code)
            st.checkbox(
                f"`{_si_code}` — {str(_si_row.get('Description', ''))[:60]} "
                f"(size {_si_row.get('SizeCategory', '')}, "
                f"in {_si_row.get('CabinetType', '')})",
                key=f"sizefit_cb_{_si_code}",
            )
        _ff_c1, _ff_c2 = st.columns(2)
        _apply_selected = _ff_c1.form_submit_button(
            "Treat selected as Helix-fit (M)", width='stretch'
        )
        _apply_all = _ff_c2.form_submit_button(
            "Select all and apply", width='stretch'
        )
    if _apply_selected or _apply_all:
        _fixes = dict(st.session_state.get("manual_size_fix", {}))
        for _code in _fit_codes:
            if _apply_all or st.session_state.get(f"sizefit_cb_{_code}"):
                _fixes[_code] = "M"
        st.session_state["manual_size_fix"] = _fixes
        st.rerun()
if _active_size_fixes:
    st.caption(
        "Manual Helix-fit override active for: "
        + ", ".join(f"{_k} → {_v}" for _k, _v in _active_size_fixes.items())
        + ". These items are sized to fit a Helix and consolidated accordingly."
    )
    if st.button("Reset manual size fixes", key="reset_size_fixes"):
        st.session_state["manual_size_fix"] = {}
        st.rerun()

# ---------------------------------------------------------------------------
# OPTIONAL dimensional fit-check results.
# Shown only when the package-dimensions column was mapped and the Fit_status
# column was produced. Purely informational — does not change any plan numbers.
if "Fit_status" in work.columns:
    st.subheader("Dimensional fit-check")
    ktc_fit = work[work["SystemCategory"] == "KTC"]
    n_checked = int((ktc_fit["Fit_status"] != "no-dims").sum() - (ktc_fit["Fit_status"] == "").sum())
    n_ok = int((ktc_fit["Fit_status"] == "ok").sum())
    n_misfit = int((ktc_fit["Fit_status"] == "misfit").sum())
    n_nodims = int((ktc_fit["Fit_status"] == "no-dims").sum())

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        st.metric("Fits its cabinet", n_ok)
    with fc2:
        st.metric("Does NOT fit", n_misfit)
    with fc3:
        st.metric("No dimensions (approximated)", n_nodims)

    st.caption(
        "Rows with package dimensions are checked against real compartment sizes "
        "(Helix coil, Carousel slots, Locker boxes). Rows without dimensions keep "
        "the category-size approximation. This panel is informational; it does not "
        "change the cabinet counts above."
    )

    if n_misfit > 0:
        misfits = ktc_fit[ktc_fit["Fit_status"] == "misfit"][
            [c for c in ["Code", "Description", "CabinetType", "Fit_recommended",
                         "Fit_package_mm", "Fit_evidence"] if c in ktc_fit.columns]
        ].rename(columns={
            "CabinetType": "Currently",
            "Fit_recommended": "Suggested",
            "Fit_package_mm": "Package (mm)",
            "Fit_evidence": "Evidence",
        })
        st.markdown(f"##### {n_misfit} item(s) that don't fit their assigned cabinet")
        st.dataframe(misfits, width='stretch', hide_index=True)
        st.caption(
            "‘Suggested’ is the smallest cabinet the package physically fits. "
            "Blank suggestion means the package fits no standard compartment "
            "(oversized — review manually)."
        )

# Fixed configuration (v34.52): how the articles fit the configured machines.
if op_mode == FIXED_MODE:
    st.subheader("Fit into the configured machines")
    _fx_reps = [p.get("fixed_config") or {} for _, p in bucket_plans]
    _fx_placed = sum(int(r.get("placed", 0)) for r in _fx_reps)
    _fx_moved = sum(int(r.get("moved", 0)) for r in _fx_reps)
    _fx_not = sum(int(r.get("not_placed", 0)) for r in _fx_reps)
    _fx_buf = sum(int(r.get("buffers_dropped", 0)) for r in _fx_reps)
    _fx1, _fx2, _fx3 = st.columns(3)
    _fx1.metric("Placed", _fx_placed)
    _fx2.metric("Moved to another machine type", _fx_moved)
    _fx3.metric("Not placed (no space)", _fx_not)
    _fx_labels = {}
    if program_mapping_active:
        for _prog, _sp in sorted(program_to_sp_map.items(), key=lambda kv: (kv[1], kv[0])):
            _fx_labels.setdefault(f"SP {_sp}", []).append(_prog or "(blank)")
    _fx_cap = pd.DataFrame(_fixed_capacity_rows(bucket_plans))
    if not _fx_cap.empty:
        _fx_cap["Supply point"] = _fx_cap["Supply point"].map(
            lambda lbl: f"{lbl} ({', '.join(_fx_labels[lbl])})" if lbl in _fx_labels else lbl)
        st.dataframe(_fx_cap, width="stretch", hide_index=True)
    if _fx_not:
        st.warning(
            f"{_fx_not} article(s) are not placed: no space was left in the "
            "configured machines after the more used articles. They stay in "
            "every list and export, marked 'Not placed'. Add a machine, lower "
            "the headroom, or review them below."
        )
        _fx_np = work[work.get("Placement_Status", pd.Series("", index=work.index))
                      == STATUS_NOT_PLACED]
        with st.expander(f"Articles not placed ({len(_fx_np)})", expanded=False):
            _fx_cols = [c for c in ("SupplyPoint", "Code", "Description", "Monthly_pcs",
                                    "SizeCategory", "CabinetType", "Spirals_needed",
                                    "Carousel_stockpiles", "Placement_Rank",
                                    "Placement_Note") if c in _fx_np.columns]
            st.dataframe(_arrow_safe(_fx_np[_fx_cols]), width="stretch", hide_index=True)
    else:
        st.success("Every vending article found space in the configured machines.")
    if _fx_moved:
        st.caption(
            f"{_fx_moved} article(s) moved to another machine type because their "
            "own was full (see Placement_Note in the Result sheet).")
    # Stock-based Helix promotion (v34.58).
    _fx_promo = sum(int(r.get("promoted", 0)) for r in _fx_reps)
    _fx_freed = sum(int(r.get("placed_in_freed", 0)) for r in _fx_reps)
    if fixed_stock_months > 0 and STOCK_COL not in work.columns:
        st.warning(
            "The stock-based Helix promotion needs the Current stock column: map "
            "it in the column mapping above.")
    elif fixed_stock_months > 0:
        st.caption(
            f"Stock-based Helix promotion (stock covers {fixed_stock_months:g} "
            f"months): {_fx_promo} article(s) moved from the Carousel into free "
            "Helix spirals; their takeover maximum follows the spirals (status "
            "'Promoted', see Placement_Note)."
            + (f" {_fx_freed} article(s) placed in the Carousel space this freed."
               if _fx_freed else ""))
    if _fx_buf:
        st.caption(
            f"{_fx_buf} restock buffer(s) could not be reserved for lack of space; "
            "their articles are placed.")

# Summary display
st.subheader("Configured machines (KTC only)" if op_mode == FIXED_MODE
             else "Required cabinets (KTC only)")

header_parts = []
if separated_mode:
    header_parts.append("Tools + PPE: **separated plans**")
elif set(work["Listing"].astype(str).unique()) == {LISTING_TOOLS, LISTING_PPE}:
    header_parts.append("Tools + PPE: **combined plan**")
else:
    only_listing = list(set(work["Listing"].astype(str).unique()))[0]
    header_parts.append(f"Listing: **{only_listing}** only")
if n_sp > 1:
    # v34.52: with the Program mapping active the supply point comes from the
    # mapping, not from the replicate/partition mode (the captions said so).
    header_parts.append(
        f"Supply points: **{n_sp}**"
        + (" (items assigned by the Program column)" if program_mapping_active
           else " (items partitioned with LPT greedy balancing)" if sp_mode == SP_MODE_PARTITION
           else " (every item replicated at each supply point)"))
if buffer_active:
    header_parts.append(f"Capacity buffer: **+{buf_pct:.0f}%** applied per bucket")

st.caption(" | ".join(header_parts))

def _line(label: str, base_val: int, buf_val: int) -> str:
    if buffer_active and buf_val != base_val:
        return f"{label}: **{base_val}** → **{buf_val}** with buffer"
    return f"{label}: **{base_val}**"

def _render_plan_detail(p: Dict[str, Any]) -> None:
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("KTC articles", p["ktc_count"])
    with m2:
        st.metric("Kanban articles", p["kanban_count"])
    with m3:
        st.metric(
            "Helix cabinets" + (f" (+{buf_pct:.0f}%)" if buffer_active else ""),
            p["helix_cabs"],
            delta=(f"+{p['helix_cabs'] - p['helix_cabs_base']} vs base"
                   if buffer_active and p["helix_cabs"] != p["helix_cabs_base"] else None),
            delta_color="off",
        )
    with m4:
        st.metric(
            "Carousel cabinets" + (f" (+{buf_pct:.0f}%)" if buffer_active else ""),
            p["car_cabs"],
            delta=(f"+{p['car_cabs'] - p['car_cabs_base']} vs base"
                   if buffer_active and p["car_cabs"] != p["car_cabs_base"] else None),
            delta_color="off",
        )
    st.markdown(
        f"""
**Helix** — {p['helix_refs']} refs | { _line("spirals", p['total_spirals'], p['total_spirals_buf']) } | { _line(f"cabinets ({HELIX_SPIRALS_PER_CAB}/cab)", p['helix_cabs_base'], p['helix_cabs']) }

**Carousel** — {p['carousel_refs']} refs | { _line("stockpiles", p['car_slots'], p['car_slots_buf']) } | { _line(f"cabinets ({CAROUSEL_SLOTS_PER_CAB}/cab)", p['car_cabs_base'], p['car_cabs']) }

**Locker A** ({LOCKER_A_CAP}) — {p['locker_a_refs']} refs → { _line("cabinets", p['cabA_base'], p['cabA']) }
**Locker B** ({LOCKER_B_CAP}) — {p['locker_b_refs']} refs → { _line("cabinets", p['cabB_base'], p['cabB']) }
**Locker C** ({LOCKER_C_CAP}) — {p['locker_c_refs']} refs → { _line("cabinets", p['cabC_base'], p['cabC']) }

**Total cabinets in this bucket**: { _line("", p['total_cabs_base'], p['total_cabs']).lstrip(': ') }
"""
    )

# Always show bucket tabs (even if one bucket — simpler code path)
tab_labels = [label for label, _ in bucket_plans]
if len(bucket_plans) > 1:
    tab_labels.append("Grand total")
tabs = st.tabs(tab_labels)

for i, (label, plan) in enumerate(bucket_plans):
    with tabs[i]:
        _render_plan_detail(plan)

if len(bucket_plans) > 1:
    with tabs[-1]:
        st.caption("Sum across all buckets. This is the total cabinet order for the customer.")
        _render_plan_detail(grand)

# Flat comparison table across all buckets — quick visual sanity check
st.markdown("##### Quick comparison across buckets")
if program_mapping_active and n_sp > 1:
    st.caption(
        "Program mapping: each item sits at the supply point its programme is "
        "mapped to. 'Grand total' sums cabinets and items across SPs."
    )
elif sp_mode == SP_MODE_REPLICATE and n_sp > 1:
    st.caption(
        "Replicate mode: each bucket (SP) carries the entire item list at "
        f"1/{n_sp} of total consumption. 'Grand total' sums cabinets across "
        "SPs; item counts per SP are the unique item count (same at each SP)."
    )
elif sp_mode == SP_MODE_PARTITION and n_sp > 1:
    st.caption(
        "Partition mode: items are split into disjoint subsets across SPs. "
        "'Grand total' item count = total unique items across all SPs."
    )
df_bucket_compare = bucket_compare_frame(bucket_plans, grand)
st.dataframe(df_bucket_compare, width='stretch', hide_index=True)

# Per-Supply-Point presentation summary + PDF export
st.subheader("Per-supply-point summary (presentation-ready)")

presentation_compact_df, presentation_detail_df = build_per_sp_summary(
    work=work,
    bucket_plans=bucket_plans,
    program_to_sp_map=program_to_sp_map if program_mapping_active else {},
    buffer_pct=float(buf_pct),
    listings=listings_arg,
)

st.markdown("**Headline — cabinets per supply point**")
st.dataframe(presentation_compact_df, width='stretch', hide_index=True)

st.markdown("**Detail — consumption, KTC/Kanban split, buffer headroom**")
st.dataframe(presentation_detail_df, width='stretch', hide_index=True)

# per-SP distribution (4 buckets) + cabinet occupation table
with st.expander("Per-SP drilldown (distribution + cabinet occupation)", expanded=False):
    _sp_distribution_ui = build_per_sp_distribution(work, listings=listings_arg)
    _sp_subclass_ui = build_per_sp_subclass_breakdown(work, listings=listings_arg)
    # Walk each SP bucket in the plan; show distribution table + occupation table side-by-side
    for _label, _plan in bucket_plans:
        if _label == "Grand total":
            continue
        # Resolve the lookup key for _sp_distribution_ui / _sp_subclass_ui.
        # In Separated Tools+PPE mode the dicts are keyed by listing name
        # (so the label itself is the key). In Combined mode labels are
        # "SP 1", "SP 2", or "All" and keys are SP integers; parse the
        # number out of the label. Fall back to the synthetic "__all__"
        # aggregate when neither resolves.
        _sp_key: Any = _label if _label in _sp_distribution_ui else None
        _sp_num: Any = None
        try:
            _last_token = _label.split()[-1]
            _sp_num = int(_last_token)
        except Exception:
            _sp_num = None
        if _sp_key is None and _sp_num is not None and _sp_num in _sp_distribution_ui:
            _sp_key = _sp_num

        st.markdown(f"### {_label}")

        if _sp_key is not None and _sp_key in _sp_distribution_ui:
            _dist_row = _sp_distribution_ui[_sp_key]
        else:
            # Single-SP or unparseable label — use the grand-total aggregate.
            _dist_row = _sp_distribution_ui.get("__all__", {b: 0 for b in SLIDE_BUCKET_ORDER})
        _dist_total = sum(_dist_row.values())

        _c1, _c2 = st.columns(2)
        with _c1:
            st.markdown("**Tool distribution (KTC items)**")
            _dist_df = pd.DataFrame([
                {"Bucket": b, "Items": _dist_row.get(b, 0),
                 "Share": f"{(_dist_row.get(b, 0) / _dist_total * 100.0):.1f}%" if _dist_total > 0 else "—"}
                for b in SLIDE_BUCKET_ORDER
            ])
            st.dataframe(_dist_df, width='stretch', hide_index=True)
        with _c2:
            st.markdown("**Cabinet occupation (estimated even fill)**")
            _occ_recs = build_per_sp_cabinet_occupation(_plan)
            if _occ_recs:
                _occ_df = pd.DataFrame([
                    {
                        "Cab #": f"Cab {r['cabinet_no']}",
                        "Type": r["cabinet_type"],
                        "Capacity": f"{r['capacity']} {r['capacity_unit']}",
                        "Used (est.)": f"{r['used']:.1f}",
                        "Occupation": f"{r['occupation_pct']:.1f}%",
                    }
                    for r in _occ_recs
                ])
                st.dataframe(_occ_df, width='stretch', hide_index=True)
            else:
                st.caption("No cabinets at this SP.")

        # Subclass breakdown — finer-grained view of the 4 primary buckets.
        # Populated by the heuristic (Patch 2b) and AI (Patch 2c). Empty for
        # archived runs predating those patches.
        if _sp_key is not None and _sp_key in _sp_subclass_ui:
            _sub_row = _sp_subclass_ui[_sp_key]
        else:
            _sub_row = _sp_subclass_ui.get("__all__", {})

        if _sub_row:
            with st.expander("Subclass breakdown (toolclass detail)", expanded=False):
                _sub_records = []
                for _bucket in SLIDE_BUCKET_ORDER:
                    _subclasses = _sub_row.get(_bucket, {})
                    if not _subclasses:
                        continue
                    _bucket_total = sum(_subclasses.values())
                    for _tc, _n in sorted(_subclasses.items(), key=lambda kv: -kv[1]):
                        _share = (_n / _bucket_total * 100.0) if _bucket_total > 0 else 0
                        _sub_records.append({
                            "Bucket": _bucket,
                            "Subclass": _tc,
                            "Items": _n,
                            "Share of bucket": f"{_share:.1f}%",
                        })
                if _sub_records:
                    st.dataframe(pd.DataFrame(_sub_records), width='stretch', hide_index=True)
                else:
                    st.caption("No subclass data for this supply point.")

# Audit: source distribution per field
df_audit = audit_frame(work)

with st.expander("Audit: source distribution per field"):
    st.dataframe(df_audit, width='stretch')

# Distribution analytics (charts + data for PowerPoint)
st.subheader("Distribution analysis")
st.caption(
    "Breakdowns of the planning base. All tables below are also exported to the "
    "Excel file on separate sheets — copy straight into PowerPoint and make the "
    "chart there, or screenshot the interactive chart."
)

@st.cache_data(max_entries=8, show_spinner=False)
def _cached_distribution(plan_key: str, group_col: str, by_volume: bool,
                         ktc_only: bool, _df: pd.DataFrame) -> pd.DataFrame:
    """Distribution tables keyed by the plan (audit P1): a plain rerun serves
    the cached frames instead of re-running four groupbys per click. The
    frame arrives underscore-prefixed; the plan key already carries its
    content identity."""
    frame = _df[_df["SystemCategory"] == "KTC"] if ktc_only else _df
    if by_volume:
        return distribution_volume(frame, group_col)
    return distribution_counts(frame, group_col)


dist_cat_rows = _cached_distribution(_plan_key, "ProductCategory", False, False, work)
dist_cat_vol = _cached_distribution(_plan_key, "ProductCategory", True, False, work)
dist_cabtype = _cached_distribution(_plan_key, "CabinetType", False, True, work)
dist_system = _cached_distribution(_plan_key, "SystemCategory", False, False, work)

listings_in_data = _listings_in_data(work)
multiple_listings = len(listings_in_data) > 1

@st.fragment
def _distribution_basis_fragment():
    """Category distribution display (v34.30). A fragment so the basis radio
    and the breakdown expander rerun this section alone; the frames it
    reads come from the latest full run."""
    # Basis toggle — by item count vs by monthly volume
    basis = st.radio(
        "Category distribution basis",
        options=["By item count", "By monthly pack volume"],
        index=0,
        horizontal=True,
        help="Item count answers 'how many SKUs in each category'. Monthly pack volume answers 'how much consumption is in each category'.",
    )

    dist_cat_active = dist_cat_rows if basis == "By item count" else dist_cat_vol
    value_col = "Count" if basis == "By item count" else "MonthlyPacks"

    chart_col, table_col = st.columns([3, 2])

    with chart_col:
        if len(dist_cat_active) > 0 and dist_cat_active[value_col].sum() > 0:
            # Pie chart — one per Listing if multiple
            pie_base = alt.Chart(dist_cat_active).mark_arc(innerRadius=55, outerRadius=110).encode(
                theta=alt.Theta(f"{value_col}:Q", stack=True),
                color=alt.Color("ProductCategory:N", legend=alt.Legend(title="Category")),
                tooltip=[
                    "Listing:N",
                    "ProductCategory:N",
                    alt.Tooltip(f"{value_col}:Q", title=value_col, format=".2f" if value_col == "MonthlyPacks" else ".0f"),
                    alt.Tooltip("Share:Q", format=".1%"),
                ],
            )
            if multiple_listings:
                pie = pie_base.facet(column=alt.Column("Listing:N", title=None)).properties(title=f"Product category — {basis.lower()}")
            else:
                pie = pie_base.properties(title=f"Product category — {basis.lower()}", width=320, height=320)
            st.altair_chart(pie, width='stretch')
        else:
            st.info("No data to chart.")

    with table_col:
        table_view = dist_cat_active.copy()
        if not table_view.empty:
            table_view["Share"] = (table_view["Share"] * 100).round(1).astype(str) + " %"
            if value_col == "MonthlyPacks":
                table_view[value_col] = table_view[value_col].round(2)
        st.dataframe(table_view, width='stretch', hide_index=True)

    # Secondary charts — horizontal bar rankings
    with st.expander("More breakdowns (Cabinet type, System category)"):
        colA, colB = st.columns(2)
        with colA:
            st.markdown("**Items by cabinet type (KTC only)**")
            if len(dist_cabtype) > 0:
                bar = alt.Chart(dist_cabtype).mark_bar().encode(
                    x=alt.X("Count:Q"),
                    y=alt.Y("CabinetType:N", sort="-x"),
                    color=alt.Color("Listing:N") if multiple_listings else alt.value("#4c78a8"),
                    tooltip=["Listing:N", "CabinetType:N", "Count:Q", alt.Tooltip("Share:Q", format=".1%")],
                ).properties(height=200)
                st.altair_chart(bar, width='stretch')
            st.dataframe(dist_cabtype, width='stretch', hide_index=True)
        with colB:
            st.markdown("**KTC vs Kanban**")
            if len(dist_system) > 0:
                bar2 = alt.Chart(dist_system).mark_bar().encode(
                    x=alt.X("Count:Q"),
                    y=alt.Y("SystemCategory:N"),
                    color=alt.Color("Listing:N") if multiple_listings else alt.value("#f58518"),
                    tooltip=["Listing:N", "SystemCategory:N", "Count:Q", alt.Tooltip("Share:Q", format=".1%")],
                ).properties(height=120)
                st.altair_chart(bar2, width='stretch')
            st.dataframe(dist_system, width='stretch', hide_index=True)

    # Export


_distribution_basis_fragment()


# Standard/Special visibility (v33.69): when the Standard/Special column is
# mapped, surface the per-row classification and whether the special→KTC
# toggle forced the row, so the toggle's effect is auditable from the file.
# Created only when the column is mapped, so a run without the feature
# exports exactly as before; _user_view additionally drops either column if
# it ends up entirely blank (e.g. the toggle was off, so nothing was forced).
# Applied here, before the cached workbook build, so the frame is identical
# whether the build runs or a cached copy is served.
apply_export_display_columns(work)

@st.fragment
def _exports_fragment():
    """Thin shell (v34.40): the panel lives in ui.exports_panel; every value
    it needs is passed explicitly."""
    exports_panel.render(OPENAI_MODEL=OPENAI_MODEL, _SCRIPT_DIR=_SCRIPT_DIR, _plan_cfg=_plan_cfg, _plan_key=_plan_key, _restock_categories=_restock_categories, _restock_slots_total=_restock_slots_total, _split_coverage=_split_coverage, ai_batches_failed=ai_batches_failed, ai_batches_run=ai_batches_run, ai_items_run=ai_items_run, ai_missing_responses=ai_missing_responses, base_info=base_info, bucket_plans=bucket_plans, buf_pct=buf_pct, calc_mode=calc_mode, col_regrind=col_regrind, col_restock=col_restock, col_stdspecial=col_stdspecial, col_systemtyp=col_systemtyp, coverage_days=coverage_days, coverage_days_special=coverage_days_special, effective_customer=effective_customer, effective_site=effective_site, enable_pack_hint_extraction=enable_pack_hint_extraction, enable_rebalancer=enable_rebalancer, force_screws_accessories_kanban=force_screws_accessories_kanban, grand=grand, helix_threshold=helix_threshold, ktc_id_input=ktc_id_input, listings_arg=listings_arg, listings_in_data=listings_in_data, max_carousels_cap=max_carousels_cap, minimum_carousel_allocation=minimum_carousel_allocation, n_sp=n_sp, n_supply_points=n_supply_points, op_mode=op_mode, operational_mode=operational_mode, optional_thresholds_active=optional_thresholds_active, override_stats=override_stats, per_class_thresholds=per_class_thresholds, program_mapping_active=program_mapping_active, program_to_sp_map=program_to_sp_map, sheet_ppe=sheet_ppe, sheet_tools=sheet_tools, sp_mode=sp_mode, total_in_tokens=total_in_tokens, total_out_tokens=total_out_tokens, underuse_threshold_pct=underuse_threshold_pct, usage_threshold=usage_threshold, use_ai=use_ai, use_description_2=use_description_2, validation_issues=validation_issues, vend_stats=vend_stats, _export_name=_export_name, apply_overrides_ui=apply_overrides_ui, consumption_period_months=consumption_period_months, df_audit=df_audit, df_bucket_compare=df_bucket_compare, dist_cabtype=dist_cabtype, dist_cat_rows=dist_cat_rows, dist_cat_vol=dist_cat_vol, dist_system=dist_system, enable_bulk_routing=enable_bulk_routing, multiple_listings=multiple_listings, presentation_compact_df=presentation_compact_df, presentation_detail_df=presentation_detail_df, work=work, override_store_unavailable=_override_store_unavailable)



_exports_fragment()


st.header("Classifier quality")
with st.expander(
    "How often technicians corrected the classifier (from the overrides library)",
    expanded=False,
):
    if "ProductCategory_PreOverride" not in work.columns:
        st.caption(
            "No overrides were applied to this run, so there's nothing to measure yet. "
            "As technicians review rows and save corrections (panel below), this builds "
            "into a running picture of where the classifier is weak — turn on "
            "'Apply overrides library' and re-run once a library exists."
        )
    else:
        _pre = work["ProductCategory_PreOverride"].astype(str).str.strip()
        _post = work["ProductCategory"].astype(str).str.strip()
        _conf = (
            work["ProductCategory_ConfidencePreOverride"].astype(str).str.strip().str.lower()
        )
        # "Classified" = the classifier actually produced a category (not blank/unknown).
        _classified = _pre.ne("") & _pre.str.lower().ne("unknown")
        _corrected = _classified & _pre.ne(_post) & _post.ne("")
        n_classified = int(_classified.sum())
        n_corrected = int(_corrected.sum())

        if n_classified == 0:
            st.caption("No classified rows in this run to evaluate.")
        else:
            rate = n_corrected / n_classified
            c1, c2, c3 = st.columns(3)
            c1.metric("Classified rows", f"{n_classified}")
            c2.metric("Corrected by technicians", f"{n_corrected}")
            c3.metric("Correction rate", f"{rate * 100:.1f}%")
            st.caption(
                "Correction rate = share of the classifier's category guesses that a "
                "technician later changed via the overrides library. Lower is better. "
                "This only sees rows someone reviewed, so treat it as 'where it's weak', "
                "not an overall accuracy score."
            )

            # Correction rate by the classifier's own confidence — a calibration sanity
            # check: a well-behaved classifier should be corrected MORE in 'low' than 'high'.
            _conf_order = ["high", "medium", "low", "unknown"]
            rows = []
            for bucket in _conf_order:
                m = _classified & _conf.eq(bucket)
                tot = int(m.sum())
                if tot == 0:
                    continue
                corr = int((_corrected & m).sum())
                rows.append(
                    {
                        "Confidence": bucket,
                        "Classified": tot,
                        "Corrected": corr,
                        "Correction rate": f"{(corr / tot) * 100:.1f}%",
                    }
                )
            if rows:
                st.markdown("**Correction rate by confidence** (expect high < low)")
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

            # Most common (predicted -> corrected) confusions, via the evaluation engine.
            if n_corrected > 0:
                rep = evaluate_classification(
                    y_true=_post[_corrected].tolist(),
                    y_pred=_pre[_corrected].tolist(),
                )
                conf_rows = [
                    {"Classifier said": p, "Technician changed to": t, "Times": c}
                    for (t, p, c) in rep.top_confusions(limit=12)
                ]
                if conf_rows:
                    st.markdown("**Most common corrections** (classifier → technician)")
                    st.dataframe(
                        pd.DataFrame(conf_rows), hide_index=True, width="stretch"
                    )

# Optimized cabinet allocation (experimental) — solver vs heuristic routing
st.divider()
st.header("Optimized cabinet allocation")
with st.expander(
    "Solver-optimized KTC routing vs the heuristic (experimental)", expanded=False
):
    try:
        from optimization import OptItem, helix_units_for_routing, solve_ktc_allocation

        _ktc = work[
            (work["SystemCategory"] == "KTC")
            & (work["CabinetType"].isin(["Helix", "Carousel"]))
        ]
        if op_mode == FIXED_MODE:
            st.caption(
                "Not used in the fixed configuration mode: the machines are given.")
        elif len(_ktc) == 0:
            st.caption("No KTC Helix/Carousel items in this run to optimize.")
        else:
            # v34.51: the solver runs on request and its result is kept for
            # this plan. A collapsed expander still executes its body, so it
            # used to re-solve (up to 20 s) after every widget click.
            _opt_state = st.session_state.get("_opt_result")
            _opt_ready = isinstance(_opt_state, dict) and _opt_state.get("plan_key") == _plan_key
            if st.button(
                "Run optimizer comparison" if not _opt_ready else "Run again",
                key="btn_run_optimizer",
                help="Solves a small optimization model (up to 20 seconds).",
            ):
                _reserve = float(_plan_cfg.carousel_reserve_factor)
                _overfill = float(_plan_cfg.helix_overfill_factor)
                _min_car = int(minimum_carousel_allocation)
                _opt_items: list = []
                _current_route: dict[str, str] = {}
                _heur_helix_units = 0
                _heur_car_units = 0
                for _i, (_idx, _row) in enumerate(_ktc.iterrows()):
                    _tp = float(pd.to_numeric(_row.get("Target_packs"), errors="coerce") or 0.0)
                    # v33 fix: stored Spiral_capacity is None for non-Helix rows, so
                    # derive what the item would cost in a Helix (see
                    # helix_units_for_routing). Without this, carousel items got
                    # helix_units=0 and the solver packed them into a Helix for free,
                    # producing phantom cabinet savings (405 items collapsing 3->1).
                    # v34.51: the run's own overfill factor, not the 1.10 default.
                    _h = helix_units_for_routing(
                        _tp,
                        _row.get("Spiral_capacity"),
                        _row.get("SizeCategory", ""),
                        _row.get("ProductCategory", ""),
                        overfill_factor=_overfill,
                    )
                    _c = max(max(1, math.ceil(_tp * _reserve)), _min_car) if _tp > 0 else 0
                    _id = str(_i)
                    _opt_items.append(
                        OptItem(item_id=_id, helix_units=float(_h), carousel_units=float(_c))
                    )
                    _route = "Helix" if str(_row.get("CabinetType")) == "Helix" else "Carousel"
                    _current_route[_id] = _route
                    if _route == "Helix":
                        _heur_helix_units += _h
                    else:
                        _heur_car_units += _c

                _heur_h_cabs = (
                    math.ceil(_heur_helix_units / HELIX_SPIRALS_PER_CAB)
                    if _heur_helix_units
                    else 0
                )
                _heur_c_cabs = (
                    math.ceil(_heur_car_units / CAROUSEL_SLOTS_PER_CAB)
                    if _heur_car_units
                    else 0
                )
                _res = solve_ktc_allocation(
                    _opt_items,
                    helix_capacity=HELIX_SPIRALS_PER_CAB,
                    carousel_capacity=CAROUSEL_SLOTS_PER_CAB,
                    time_limit_s=20,
                )
                _opt_state = {
                    "plan_key": _plan_key,
                    "heur_total": _heur_h_cabs + _heur_c_cabs,
                    "heur_h": _heur_h_cabs, "heur_c": _heur_c_cabs,
                    "opt_total": int(_res.total_cabinets),
                    "opt_h": int(_res.helix_cabinets), "opt_c": int(_res.carousel_cabinets),
                    "rerouted": sum(
                        1 for _id, r in _current_route.items() if _res.routing.get(_id) != r),
                    "status": _res.status, "optimal": bool(_res.optimal),
                }
                st.session_state["_opt_result"] = _opt_state
                _opt_ready = True

            if not _opt_ready:
                st.caption(
                    "Compares the heuristic KTC routing of this plan with a solver-"
                    "optimized routing on the same per-item costs. Runs on request.")
            else:
                _delta = _opt_state["heur_total"] - _opt_state["opt_total"]
                _c1, _c2, _c3 = st.columns(3)
                _c1.metric(
                    "Heuristic routing",
                    f"{_opt_state['heur_total']} cab",
                    help=f"{_opt_state['heur_h']} Helix + {_opt_state['heur_c']} Carousel",
                )
                _c2.metric(
                    "Optimized routing",
                    f"{_opt_state['opt_total']} cab",
                    help=f"{_opt_state['opt_h']} Helix + {_opt_state['opt_c']} Carousel",
                )
                _c3.metric("Cabinets saved", f"{max(_delta, 0)}")

                st.caption(
                    f"Pure routing comparison on the same per-item costs, before the capacity "
                    f"buffer and pooled across supply points, so the totals can differ from "
                    f"the plan's headline. Items rerouted: {_opt_state['rerouted']}. "
                    f"Solver status: {_opt_state['status']}."
                )
                if not _opt_state["optimal"]:
                    st.caption(
                        "Solver hit the time limit: the result is the best found so far, "
                        "not proven optimal."
                    )
                if _delta <= 0:
                    st.caption(
                        "The heuristic routing is already optimal (or tied) for this dataset, "
                        "so there are no cabinets to recover here. That's a good sign, not a bug."
                    )
    except ModuleNotFoundError:
        st.info(
            "The optimizer needs the `pulp` package. Install it with `pip install pulp` "
            "and restart the app."
        )
    except Exception as _opt_exc:  # never break the page on solver issues
        log_exception("Optimizer comparison failed", _opt_exc)
        st.warning(f"Could not run the optimizer ({_opt_exc}).")

# Technician review panel
st.divider()
@st.fragment
def _technician_review_fragment():
    """Thin shell (v34.41): the panel lives in ui.technician_panel."""
    technician_panel.render(work=work, effective_customer=effective_customer, effective_site=effective_site, reviewer_name=reviewer_name, _DB_AVAILABLE=_DB_AVAILABLE, _kromi_db=_kromi_db, _save_override_set_dialog=_save_override_set_dialog, _resolve_db_path=_resolve_db_path)


    # session-state flag so the dashboard survives reruns


_technician_review_fragment()


st.session_state["has_results"] = True

# One save per distinct run: key on the full run fingerprint (file, sheets,
# column mapping, and every control), plus the KTC-ID and a signature of the
# effective override rows, which the fingerprint deliberately leaves out but
# which change what is archived. The fingerprint carries only the
# apply-overrides flag and the scope, so without the content signature a run
# corrected in the live editor, or recomputed against a different database
# set, would share its key with the uncorrected run and never be archived.
# A rerun with the same settings (a download-button click, a widget touch)
# keeps the same key and is not saved again; any real change produces a new
# key. The previous hand-picked field tuple leaned on outcome proxies (total
# cabinets, row count) and let two runs collide whenever their totals matched.
_ov_sig = (
    hashlib.sha256(overrides_active_df.to_csv(index=False).encode("utf-8")).hexdigest()
    if len(overrides_active_df) > 0
    else ""
)
# v34.54 (audit C9): the build and the classifications the run used are part
# of the key, so after an upgrade (or with other AI answers) the same inputs
# are archived again instead of being reported as "already archived".
_cls_sig = frame_token(work[[c for c in (
    "Code", "SizeCategory", "ProductCategory", "PackUnits") if c in work.columns]])
_save_key = (
    _current_fingerprint,
    str(ktc_id_input or "").strip(),
    _ov_sig,
    BUILD,
    OPENAI_MODEL if use_ai else "",
    _cls_sig,
)

# Pack every setting we know about so the stored run is self-describing,
# including the ui_state snapshot used to restore the controls and column
# mapping on "Load & recompute".
_run_settings = {
    "listings_loaded": ", ".join(listings_in_data),
    "tools_sheet": sheet_tools if sheet_tools else "—",
    "ppe_sheet": sheet_ppe if sheet_ppe else "—",
    "calc_mode": calc_mode,
    "n_supply_points": int(n_sp),
    "sp_mode": sp_mode,
    "program_mapping": "active" if program_mapping_active else "off",
    "programmes_mapped": len(program_to_sp_map) if program_mapping_active else 0,
    "coverage_days": int(coverage_days),
    "_plan_cfg.carousel_reserve_factor": float(_plan_cfg.carousel_reserve_factor),
    "capacity_buffer_pct": float(buf_pct),
    "ktc_threshold": float(usage_threshold),
    "helix_threshold": float(helix_threshold),
    "consumption_months": float(consumption_period_months),
    "bulk_routing": "on" if enable_bulk_routing else "off",
    "pack_hint_extraction": "on" if enable_pack_hint_extraction else "off",
    "bulk_routed_rows": int(vend_stats.get("routed_rows", 0)),
    "ai_used": bool(use_ai),
    "ai_batches_run": int(ai_batches_run),
    "ai_batches_failed": int(ai_batches_failed),
    "ai_concurrency": int(ai_concurrency),
    "ai_items_processed": int(ai_items_run),
    "ai_input_tokens": int(total_in_tokens),
    "ai_output_tokens": int(total_out_tokens),
    "validation_issues": "; ".join(validation_issues) if validation_issues else "none",
    "ktc_id": str(ktc_id_input or "").strip(),
    "customer_label": (customer_default or "").strip(),
    "ui_state": _run_restore.capture_ui_state(st.session_state),
    "build_version": BUILD,
    "overrides": _ov_applied,
}
if op_mode == FIXED_MODE:
    _run_settings["fixed_configuration"] = {
        "machines": [list(_r) for _r in fixed_machines],
        "headroom_pct": float(fixed_headroom_pct),
        "move_overflow": bool(fixed_allow_spill),
        "stock_promotion_months": float(fixed_stock_months),
    }

# Persist the completed run to the database, once per distinct run, behind an
# independent guard. A failure here never affects the run or the exports.
# Skip while manual Helix-fit size overrides are active: those are session-only
# repackaging assertions that do not survive a reload, so the natural computed
# plan (saved on the pre-override run) stays the canonical stored run rather than
# writing a fresh run for every adjusted state.
_manual_fixes_active = bool(st.session_state.get("manual_size_fix"))
if _DB_AVAILABLE and _manual_fixes_active:
    st.caption(
        "This run is not saved to the database while manual Helix-fit size "
        "fixes are active; the run without them is the stored one.")
_inputs_hash = hashlib.sha256(repr(_save_key).encode()).hexdigest()
if (
    _DB_AVAILABLE
    and not _manual_fixes_active
    and st.session_state.get("_last_db_save_key") != _save_key
):
    try:
        _db_conn = _kromi_db.init_db(_resolve_db_path())
        try:
            _cfg = _kromi_db.get_active_machine_config(_db_conn)
            _file_bytes = _uploaded_bytes if file is not None else None
            _sha = _input_sha if _file_bytes else None
            _dup_run_id = _kromi_db.run_id_by_inputs_hash(_db_conn, _inputs_hash)
            if _dup_run_id is not None:
                # The database, not just the session's last key, is the dedup
                # authority: an A-B-A settings round trip never re-archives
                # the same run (audit M3).
                st.session_state["_last_db_save_key"] = _save_key
                st.caption(f"Already archived as run #{_dup_run_id}; not saved again.")
            elif _sha:
                _file_payload = {
                    "sha256": _sha,
                    "original_filename": getattr(file, "name", None),
                    "content": _file_bytes,
                    "byte_size": len(_file_bytes),
                    "sheet_tools": sheet_tools,
                    "sheet_ppe": sheet_ppe,
                    "row_count": int(len(work)),
                    "first_seen_customer": effective_customer,
                    "first_seen_ktc_id": str(ktc_id_input or "").strip() or None,
                }
                _run_payload = {
                    "machine_config_id": int(_cfg["config_id"]) if _cfg else None,
                    "build_version": BUILD,
                    "customer": effective_customer,
                    "site": effective_site,
                    "ktc_id": str(ktc_id_input or "").strip() or None,
                    "calc_mode": calc_mode,
                    "operational_mode": operational_mode,
                    "max_carousels": int(max_carousels_cap) if op_mode == "Capped" else None,
                    "supply_points": int(n_sp),
                    "sp_mode": sp_mode,
                    "settings_json": json.dumps(_run_settings, ensure_ascii=False),
                    "applied_override_set_id": (
                        _ov_applied["set_id"] if _ov_applied["source"] == "db" else None),
                    "status": "completed",
                }
                _moves = sum(len(e.get("items_moved", [])) for e in rebalance_audit_all)
                _saved = sum(
                    int(e.get("cabinets_before", 0)) - int(e.get("cabinets_after", 0))
                    for e in rebalance_audit_all
                )
                _exec_payload = {
                    "build_version": BUILD,
                    "duration_ms": max(1, _plan_wall_ms),
                    "rows_processed": int(len(work)),
                    "rebalance_moves": int(_moves),
                    "cabinets_saved": int(_saved),
                    "size_issues_found": int(work["SizeIssue"].sum())
                    if "SizeIssue" in work.columns else 0,
                    "grand_total_cabs": int(grand.get("total_cabs", 0)) if grand else 0,
                    "inputs_hash": _inputs_hash,
                }
                _kromi_db.persist_run(
                    _db_conn,
                    file=_file_payload,
                    run=_run_payload,
                    tools=_kromi_db.tools_from_dataframe(work),
                    plan_rows=_kromi_db.summary_rows_from_plans(bucket_plans, grand),
                    rebalance_events=_kromi_db.rebalance_events_from_audit(rebalance_audit_all),
                    execution=_exec_payload,
                )
                st.session_state["_last_db_save_key"] = _save_key
                st.caption("Run saved to the database.")
        finally:
            _db_conn.close()
    except Exception as _db_err:
        log_exception("Database copy skipped", _db_err)
        st.caption(
            f"Database copy skipped ({type(_db_err).__name__}); "
            "the run and its files are unaffected."
        )
