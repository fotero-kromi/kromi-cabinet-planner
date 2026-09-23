"""kromi_app.engine.colmap — AI-assisted column-mapping helpers (pure).

This module contains *only* pure, side-effect-free helpers for the optional
"suggest column mapping with AI" feature. It does NOT import streamlit or the
OpenAI client: the page builds the prompt with `build_colmap_prompt`, makes the
API call through its existing structured-output helper, and hands the parsed
JSON back to `parse_colmap_response` for validation.

Design notes
------------
* The model only ever *proposes* a mapping. The page uses the proposal as the
  default selection of each column-mapping dropdown; the user still confirms or
  overrides every field. Nothing is auto-committed.
* `parse_colmap_response` is strict: it discards any column the model invents
  that is not actually present in the uploaded file, and it never assigns the
  same source column to two target fields (which would otherwise trip the
  page's column-collision guard). Required fields are resolved first.
* When the feature is off — or the call fails, times out, or returns junk — the
  page falls back to the existing deterministic `guess_column` header matching,
  so default behaviour is unchanged.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # annotations only; the helpers take frames from the page
    import pandas as pd

# Canonical target fields, in resolution priority order (required first).
# Each entry: (field_key, human description used to guide the model, required?)
CANONICAL_FIELDS: list[tuple[str, str, bool]] = [
    ("Code", "Article / part number, SAP material number, or item code", True),
    ("Description", "Main free-text description of the article", True),
    (
        "Consumption_pcs",
        "Quantity consumed over the period as a number (e.g. annual usage in pieces)",
        True,
    ),
    ("Description_2", "A second / long description column, if one exists", False),
    ("ProductCategory", "Product category, commodity group, or Warengruppe", False),
    ("SupplierCode", "Supplier, manufacturer, or vendor identifier", False),
    ("SizeCategory", "Size class such as S / M / L / XL, if present", False),
    ("PackUnits", "Pack size / units per package (VPE / VE) as a number", False),
    ("Year", "Year or fiscal period of the consumption figure", False),
    ("Program", "Programme, project, area, or section", False),
    ("Site", "Site, plant, factory, or location", False),
    (
        "PackageDimensions",
        "Physical package dimensions, e.g. '25x30x10' mm or a diameter like 'Ø12'",
        False,
    ),
    (
        "Regrind",
        "Whether the tool can be reground / resharpened (yes/no column)",
        False,
    ),
    (
        "SystemTyp",
        "Customer-specified storage system per tool (KTC / KTC or Kanban / Locker)",
        False,
    ),
]

CANONICAL_FIELD_KEYS: list[str] = [f[0] for f in CANONICAL_FIELDS]

# Sentinel the model returns when no column matches a field.
_NONE_TOKEN = ""


def build_colmap_prompt(headers: list[str], sample_rows: list[dict[str, Any]]) -> str:
    """Build the user prompt: the available headers, a few sample rows, and the
    target fields the model should map them to."""
    field_lines = "\n".join(
        f"- {key}{' (required)' if required else ''}: {desc}"
        for key, desc, required in CANONICAL_FIELDS
    )
    headers_block = "\n".join(f"- {h}" for h in headers)
    # Keep the sample compact; the page is expected to pass only a handful of rows.
    sample_block = json.dumps(sample_rows[:5], ensure_ascii=False, indent=2)

    return (
        "You are mapping the columns of an uploaded spreadsheet to a fixed set of "
        "target fields for a tooling cabinet planner.\n\n"
        "AVAILABLE COLUMN HEADERS (you may only choose from these exact strings):\n"
        f"{headers_block}\n\n"
        "SAMPLE ROWS (first few records, to help you judge column meaning):\n"
        f"{sample_block}\n\n"
        "TARGET FIELDS to map to:\n"
        f"{field_lines}\n\n"
        "Rules:\n"
        "- For each target field, return the single best-matching header string, "
        f'or "{_NONE_TOKEN}" (empty string) if no column fits.\n'
        "- Use each header for at most one target field.\n"
        "- Headers must be copied verbatim from the AVAILABLE list above.\n"
        "- Base the decision on both the header name and the sample values "
        "(e.g. a numeric usage column is Consumption_pcs even if oddly named)."
    )


def colmap_response_schema() -> dict[str, Any]:
    """Strict JSON schema: an object with one string property per canonical field."""
    return {
        "type": "object",
        "properties": {key: {"type": "string"} for key in CANONICAL_FIELD_KEYS},
        "required": list(CANONICAL_FIELD_KEYS),
        "additionalProperties": False,
    }


def _normalize_header(h: str) -> str:
    return " ".join(str(h).strip().casefold().split())


def parse_colmap_response(
    raw: Any,
    available_cols: list[str],
) -> dict[str, str]:
    """Validate a model mapping response against the real columns.

    Returns a dict of {canonical_field: actual_column} containing only fields the
    model mapped to a genuine column. Invented columns are dropped, and no source
    column is assigned to more than one field (first wins, in CANONICAL_FIELDS
    priority order, so required fields are resolved first).
    """
    if not isinstance(raw, dict):
        return {}

    # Lookup from normalized header -> the real column name.
    norm_to_real: dict[str, str] = {}
    for real_col in available_cols:
        norm_to_real.setdefault(_normalize_header(real_col), real_col)

    real_set = set(available_cols)
    result: dict[str, str] = {}
    used_cols: set[str] = set()

    for key in CANONICAL_FIELD_KEYS:  # priority order
        proposed = raw.get(key, _NONE_TOKEN)
        if not isinstance(proposed, str):
            continue
        proposed = proposed.strip()
        if not proposed:
            continue

        # Resolve to a real column: exact match first, then normalized match.
        col: str | None = (
            proposed if proposed in real_set else norm_to_real.get(_normalize_header(proposed))
        )
        if not col:
            continue  # model invented a column that isn't in the file

        if col in used_cols:
            continue  # don't map the same column to two fields

        result[key] = col
        used_cols.add(col)

    return result


# Sentinel used by the column-mapping UI for an unassigned optional field.
NOT_AVAILABLE = "— not available —"


# Header synonyms for the three required column-mapping fields. Used by the page
# as the candidate list for the deterministic `guess_column` matcher. English
# terms come first so they keep priority on mixed files; the German tool-list
# headers (e.g. Kromi's WZIntNr / WZBez exports) are appended so auto-detection
# succeeds on those files instead of falling back to the first column. Full
# header strings are used rather than short fragments to avoid loose substring
# matches against unrelated columns.
CODE_SYNONYMS: list[str] = [
    "Code", "Artikel", "Article", "Item", "Material", "Artikelnummer",
    "WZIntNr", "Werkzeugnummer", "WerkzeugNr", "WkzNr", "Werkzeug-Nr",
]
DESCRIPTION_SYNONYMS: list[str] = [
    "Description", "Bezeichnung", "Kurztext", "Text",
    "WZBez", "Werkzeugbezeichnung", "Benennung",
]
CONSUMPTION_SYNONYMS: list[str] = [
    "Consumption", "Consumption_pcs", "Last_12m_consumption_pcs",
    "12m_consumption", "Consumption12m", "Jahresverbrauch",
    "CurrentYearConsumption", "Verbrauch",
]


def resolve_required_default(
    auto_default: str | None,
    taken_columns,
    all_columns,
) -> str | None:
    """Column a required mapping field should pre-select when the user has not
    picked one, chosen so two required fields never silently land on the same
    column.

    `guess_column` returns None for headers it cannot recognise (e.g. German
    tool-list names). With a plain ``index=0`` fallback every unrecognised
    required field defaults to the first column, so Code and Description collapse
    onto it and trip the column-collision guard on every render. This helper
    instead skips columns already claimed by an earlier required field:

    - if the auto-detected default is a real, unclaimed column, use it;
    - otherwise use the first column not already claimed by a required field;
    - if every column is claimed (degenerate), fall back to the first column;
    - with no columns at all, return None.

    The user still confirms or overrides the field; this only prevents an
    auto-fallback collision, never an explicit user choice.
    """
    cols = list(all_columns or [])
    if not cols:
        return None
    taken = set(taken_columns or ())
    if auto_default in cols and auto_default not in taken:
        return auto_default
    for col in cols:
        if col not in taken:
            return col
    return cols[0]


def resolve_required_stored(stored, auto_default, taken_columns, all_columns):
    """Column a required mapping field should show when it already has a stored
    pick (e.g. restored from a saved run, or carried over in session state).

    The stored pick is honoured unless it duplicates a column an earlier
    required field has already claimed, or it names a column the current file
    does not have. Either case is a stale or seeded collision rather than a
    deliberate choice -- most importantly a run saved before the column-collision
    guard existed, whose three required fields were all written onto the first
    column. Honouring it would re-create the very conflict the guard reports and
    let the (correct) auto-detection lose to a stale value. So on a collision or
    a missing column it re-resolves to a non-colliding auto-detected column via
    ``resolve_required_default``; otherwise it returns the stored pick unchanged.

    A genuine, distinct stored pick (a real restore, or the user's own earlier
    selection) is always preserved.
    """
    cols = list(all_columns or [])
    if not cols:
        return None
    taken = set(taken_columns or ())
    if stored in cols and stored not in taken:
        return stored
    return resolve_required_default(auto_default, taken, cols)


def resolve_optional_default(hidden: bool, manual_mode: bool,
                             auto_default: str | None) -> str | None:
    """Default value a freshly-rendered optional column-mapping field shows.

    Returns the column name to pre-select, or None for 'unassigned'
    (the "— not available —" option). The rules implement the agreed
    behaviour that hiding optional columns clears their assignment and
    prevents auto-detection from silently re-grabbing a column afterwards
    (a ghost mapping that would otherwise run unnoticed):

    - hidden:      the field is not shown and is treated as unassigned.
    - manual_mode: once the user has hidden optional columns, auto-detection
                   is suppressed so a re-shown field starts unassigned and
                   the user re-picks deliberately.
    - otherwise:   use the auto-detected default.

    A user's explicit pick is preserved separately by the widget's stored
    state and is not the concern of this function.
    """
    if hidden or manual_mode:
        return None
    return auto_default


# Session-state keys whose values are scoped to a single uploaded file: the
# optional/manual-mode flags and the per-field column-mapping widget keys.
# These must not carry over to a different file (E6 leakage).
MAPPING_SCOPED_STATE_KEYS = (
    "_optional_manual_mode",
    "_std_special_mapped",
    "cm_prod", "cm_year", "cm_desc2", "cm_program", "cm_restock", "cm_sup",
    "cm_size", "cm_site", "cm_stdspecial", "cm_pack", "cm_dims",
    "cm_stock",
)


def reset_mapping_state_on_file_change(state, current_file_id,
                                       id_key: str = "_mapping_file_id",
                                       keys=MAPPING_SCOPED_STATE_KEYS) -> bool:
    """Clear mapping-scoped session state when the uploaded file changes.

    A new file must start from clean auto-detection rather than inheriting a
    previous file's column mappings or the sticky manual-mode flag (E6). The
    file identity is stable across reruns of the same file, so within a single
    file nothing is cleared and the hide/un-hide behaviour is unaffected.

    `state` is any MutableMapping (st.session_state in the app, a plain dict in
    tests). Returns True if a reset was performed.
    """
    if state.get(id_key) == current_file_id:
        return False
    for k in keys:
        state.pop(k, None)
    state[id_key] = current_file_id
    return True


# ---- v34.50: collision-free defaults and header-row detection (audit C11) ----

def deconflict_defaults(
    required: dict[str, str | None],
    optional: dict[str, str | None],
) -> dict[str, str | None]:
    """Optional-field defaults with every already-claimed column removed.

    Synonym matching is deliberately substring-based (German compounds such as
    "Jahresverbrauch" must still read as consumption), so an optional field's
    auto-detected column can be one a required field already uses ("Year" on
    "Jahresverbrauch", "Standard/Special" on "Artikel" via "Art"). Such a
    default is dropped (None = unassigned), as is a column an earlier optional
    field in ``optional``'s order already took. Explicit picks are not the
    concern of this function. Never mutates its inputs.
    """
    claimed = {c for c in required.values() if c}
    out: dict[str, str | None] = {}
    for field, col in optional.items():
        if col and col not in claimed:
            out[field] = col
            claimed.add(col)
        else:
            out[field] = None
    return out


def suggest_header_row(raw: "pd.DataFrame", max_scan: int = 30) -> int:
    """1-based row most likely to hold the column names of ``raw``.

    ``raw`` is a sheet read with ``header=None``. The header row is the first
    row, among the first ``max_scan``, with the most non-empty text cells
    (banner rows carry one or two cells, data rows carry numbers). Returns 1
    when nothing better is found.
    """
    best_row, best_score = 1, -1
    for i in range(min(len(raw), max_scan)):
        row = raw.iloc[i]
        texts = [v for v in row if isinstance(v, str) and v.strip() and not _is_number_text(v)]
        score = len(texts)
        if score > best_score:
            best_row, best_score = i + 1, score
    return best_row


def _is_number_text(v: str) -> bool:
    try:
        float(v.strip().replace(",", "."))
        return True
    except ValueError:
        return False


def headers_look_misplaced(df: "pd.DataFrame") -> bool:
    """True when most columns that hold data have no header ("Unnamed: n").

    That is the signature of a sheet read with the wrong header row (banner
    rows above the real headers). Columns without any data are ignored, so
    empty formatted columns next to a proper table never trigger it.
    """
    data_cols = [c for c in df.columns if df[c].notna().any()]
    if not data_cols:
        return False
    unnamed = [c for c in data_cols if str(c).startswith("Unnamed:")]
    return len(unnamed) * 2 > len(data_cols)
