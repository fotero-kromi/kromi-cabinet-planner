"""kromi_app.engine.overrides — technician overrides library.

Pure functions for validating, applying, and merging overrides. Since
v34.23 the application reads overrides from the database only; the file
loader and saver here remain as the tested foundation of
tools/migrate_override_files.py, which brings legacy per-customer files
into the database. The engine stays completely free of streamlit and
__file__ dependencies, so everything is trivially testable in isolation.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from .constants import (
    LISTING_TOOLS,
    OVERRIDE_COLUMNS,
    OVERRIDE_VALID_CABINETS,
    OVERRIDE_VALID_SIZES,
    OVERRIDE_VALID_VEND,
    PC_VALID,
)


def _safe_scope_component(s: str) -> str:
    """Sanitize a customer or site name for use as a folder path component."""
    s = re.sub(r"[^A-Za-z0-9_\-]", "_", (s or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    s = s[:40]
    return s if s else "default"


def overrides_folder(customer: str, site: str, base_dir: Path) -> Path:
    """Return the overrides folder for a given (customer, site) scope under
    base_dir. Does NOT create the folder — only computes the path."""
    return base_dir / f"{_safe_scope_component(customer)}__{_safe_scope_component(site)}"


def load_overrides(
    customer: str,
    site: str,
    base_dir: Path,
    on_error: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """Load the overrides CSV for this (customer, site).

    Returns an empty DataFrame (with the standard columns) if the file is
    missing or unreadable. If a read fails and on_error is provided, the
    callback is invoked with a human-readable message (the page binds this
    to st.error so the user sees it).
    """
    folder = overrides_folder(customer, site, base_dir)
    path = folder / "overrides.csv"
    if not path.exists():
        return pd.DataFrame(columns=OVERRIDE_COLUMNS)

    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as e:
        if on_error:
            on_error(f"Failed to read overrides file {path}: {type(e).__name__}: {e}")
        return pd.DataFrame(columns=OVERRIDE_COLUMNS)

    # Ensure all expected columns exist (forward compatibility for older files)
    for c in OVERRIDE_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df[OVERRIDE_COLUMNS]

    # Drop rows with no code (garbage) and entirely empty overrides
    df = df[df["code"].astype(str).str.strip() != ""].copy()
    override_value_cols = [
        "product_category_override",
        "pack_units_override",
        "size_category_override",
        "cabinet_type_override",
        "vend_mode_override",
    ]
    nonempty_mask = False
    for c in override_value_cols:
        nonempty_mask = nonempty_mask | (df[c].astype(str).str.strip() != "")
    df = df[nonempty_mask].copy() if isinstance(nonempty_mask, pd.Series) else df

    # Deduplicate: latest reviewed_at per (code, listing)
    if len(df) > 0:
        df["__order"] = range(len(df))  # tiebreak for missing timestamps
        df = df.sort_values(["reviewed_at", "__order"], ascending=[True, True])
        kept = df.drop_duplicates(subset=["code", "listing"], keep="last")
        dropped = df[~df.index.isin(kept.index)]
        if len(dropped) > 0:
            # Append dropped rows to history file (atomic-ish append)
            hist_path = folder / "overrides.history.csv"
            dropped_out = dropped.drop(columns=["__order"])
            try:
                if hist_path.exists():
                    dropped_out.to_csv(hist_path, mode="a", header=False, index=False)
                else:
                    dropped_out.to_csv(hist_path, index=False)
            except Exception:
                pass  # history is best-effort, don't fail the load
        df = kept.drop(columns=["__order"]).reset_index(drop=True)

    return df


def save_overrides(
    customer: str,
    site: str,
    df: pd.DataFrame,
    base_dir: Path,
) -> tuple[bool, str]:
    """Write the active overrides CSV atomically (write to .tmp, then rename)
    so a crash during save never leaves a half-written file. Returns
    (ok, path_or_error)."""
    try:
        folder = overrides_folder(customer, site, base_dir)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "overrides.csv"
        tmp = folder / "overrides.csv.tmp"

        # Ensure schema + drop empty rows
        df_out = df.copy()
        for c in OVERRIDE_COLUMNS:
            if c not in df_out.columns:
                df_out[c] = ""
        df_out = df_out[OVERRIDE_COLUMNS]
        df_out = df_out[df_out["code"].astype(str).str.strip() != ""]

        df_out.to_csv(tmp, index=False)
        tmp.replace(path)  # atomic on POSIX + modern Windows
        return True, str(path)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ---- Field validators ----


def _valid_category(cat: str) -> bool:
    return str(cat or "").strip().lower() in PC_VALID


def _valid_cabinet_type(ct: str) -> bool:
    return str(ct or "").strip() in OVERRIDE_VALID_CABINETS


def _valid_vend_mode(v: str) -> bool:
    return str(v or "").strip() in OVERRIDE_VALID_VEND


def _valid_size(sz: str) -> bool:
    return str(sz or "").strip().upper() in OVERRIDE_VALID_SIZES


def _parse_pack_override(pu: str) -> int | None:
    """Return a valid integer pack size in [1, 10000], or None if unparseable."""
    s = str(pu or "").strip()
    if not s:
        return None
    try:
        n = int(float(s))
        if 1 <= n <= 10000:
            return n
    except Exception:
        pass
    return None


def apply_overrides(
    work: pd.DataFrame,
    overrides_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply the overrides library to a work dataframe."""
    out = work.copy()

    def _put(col: str, mask_: Any, value: Any) -> None:
        # v34.49: a text value written into a column that arrived as numbers
        # (typically an all-empty float audit column) is a FutureWarning in
        # pandas 2 and a TypeError in pandas 3. Make the column text first;
        # the resulting values equal pandas 2's implicit upcast.
        if (isinstance(value, str) and col in out.columns
                and (pd.api.types.is_numeric_dtype(out[col])
                     or pd.api.types.is_bool_dtype(out[col]))):
            out[col] = out[col].astype(object)
        out.loc[mask_, col] = value

    # Initialize audit columns (always — so downstream code can rely)
    if "Override_Applied" not in out.columns:
        out["Override_Applied"] = False
    # True when an override explicitly set the row's routing (cabinet type or
    # vend mode). The page uses this to decide which overridden rows to re-route
    # from their new attributes (HMA-1) vs. leave at the explicitly forced type.
    if "Routing_Overridden" not in out.columns:
        out["Routing_Overridden"] = False
    if "Override_Fields" not in out.columns:
        out["Override_Fields"] = ""
    if "Override_Note" not in out.columns:
        out["Override_Note"] = ""
    if "Override_ReviewedBy" not in out.columns:
        out["Override_ReviewedBy"] = ""
    if "Override_ReviewedAt" not in out.columns:
        out["Override_ReviewedAt"] = ""

    stats: dict[str, Any] = {
        "rows_touched": 0,
        "fields_changed": {},  # field_name -> count
        "unmatched_overrides": [],  # (code, listing) pairs in CSV with no match
        "invalid_overrides": [],  # list of {code, listing, reason}
        "applied_overrides": [],  # list of {code, listing, fields_changed}
    }

    if overrides_df is None or len(overrides_df) == 0:
        return out, stats

    # Lowercased (code, listing) index on the work dataframe for lookup
    out["_code_lc"] = out["Code"].astype(str).str.strip().str.lower()
    out["_listing_lc"] = (
        out["Listing"].astype(str).str.strip().str.lower()
        if "Listing" in out.columns
        else LISTING_TOOLS.lower()
    )

    for _, o in overrides_df.iterrows():
        code = str(o.get("code", "")).strip()
        listing = str(o.get("listing", "")).strip() or LISTING_TOOLS

        if not code:
            continue

        code_lc = code.lower()
        listing_lc = listing.lower()

        mask = (out["_code_lc"] == code_lc) & (out["_listing_lc"] == listing_lc)
        if not mask.any():
            stats["unmatched_overrides"].append({"code": code, "listing": listing})
            continue

        fields_changed: list[str] = []
        invalid_reasons: list[str] = []

        pc_ov = str(o.get("product_category_override", "")).strip().lower()
        pu_ov_raw = str(o.get("pack_units_override", "")).strip()
        sz_ov = str(o.get("size_category_override", "")).strip().upper()
        ct_ov = str(o.get("cabinet_type_override", "")).strip()
        vm_ov = str(o.get("vend_mode_override", "")).strip()
        rs_ov = str(o.get("restocking_override", "")).strip().lower()

        if pc_ov:
            if _valid_category(pc_ov):
                _put("ProductCategory", mask, pc_ov)
                _put("ProductCategory_Source", mask, "Override")
                _put("ProductCategory_Evidence", mask, f"override:{pc_ov}")
                _put("ProductCategory_Confidence", mask, "high")
                fields_changed.append("category")
                stats["fields_changed"]["category"] = stats["fields_changed"].get(
                    "category", 0
                ) + int(mask.sum())
            else:
                invalid_reasons.append(f"invalid category '{pc_ov}'")

        if pu_ov_raw:
            pu_ov = _parse_pack_override(pu_ov_raw)
            if pu_ov is not None:
                out.loc[mask, "PackUnits"] = float(pu_ov)
                _put("PackUnits_Source", mask, "Override")
                _put("PackUnits_Evidence", mask, f"override:{pu_ov}")
                _put("PackUnits_Confidence", mask, "high")
                fields_changed.append("pack_units")
                stats["fields_changed"]["pack_units"] = stats["fields_changed"].get(
                    "pack_units", 0
                ) + int(mask.sum())
            else:
                invalid_reasons.append(f"unparseable pack_units '{pu_ov_raw}'")

        if sz_ov:
            if _valid_size(sz_ov):
                _put("SizeCategory", mask, sz_ov)
                _put("SizeCategory_Source", mask, "Override")
                fields_changed.append("size")
                stats["fields_changed"]["size"] = stats["fields_changed"].get("size", 0) + int(
                    mask.sum()
                )
            else:
                invalid_reasons.append(f"invalid size '{sz_ov}'")

        if ct_ov:
            if _valid_cabinet_type(ct_ov):
                _put("CabinetType", mask, ct_ov)
                out.loc[mask, "Routing_Overridden"] = True
                # Align SystemCategory when forcing to/from Kanban
                if ct_ov == "Kanban":
                    _put("SystemCategory", mask, "Kanban")
                else:
                    _put("SystemCategory", mask, "KTC")
                fields_changed.append("cabinet_type")
                stats["fields_changed"]["cabinet_type"] = stats["fields_changed"].get(
                    "cabinet_type", 0
                ) + int(mask.sum())
            else:
                invalid_reasons.append(f"invalid cabinet_type '{ct_ov}'")

        if vm_ov:
            if _valid_vend_mode(vm_ov):
                _put("VendMode", mask, vm_ov)
                out.loc[mask, "Routing_Overridden"] = True
                # VendMode=Bulk/Kanban implies SystemCategory=Kanban
                if vm_ov == "Bulk/Kanban":
                    _put("SystemCategory", mask, "Kanban")
                    _put("CabinetType", mask, "Kanban")
                    _put("VendBlockReason", mask, "override:bulk")
                elif vm_ov == "Vending":
                    _put("VendMode", mask, "Vending")
                    _put("VendBlockReason", mask, "")
                fields_changed.append("vend_mode")
                stats["fields_changed"]["vend_mode"] = stats["fields_changed"].get(
                    "vend_mode", 0
                ) + int(mask.sum())
            else:
                invalid_reasons.append(f"invalid vend_mode '{vm_ov}'")

        if rs_ov:
            from engine.preprocessing import normalize_restock_flag
            if normalize_restock_flag(rs_ov) is not None:
                # The raw yes/no travels on the frame; the restock segment
                # normalizes it and lets the override win over the mapped
                # column and the category rule (v34.28).
                _put("Restocking_Override", mask, rs_ov)
                fields_changed.append("restocking")
                stats["fields_changed"]["restocking"] = stats["fields_changed"].get(
                    "restocking", 0
                ) + int(mask.sum())
            else:
                invalid_reasons.append(f"invalid restocking '{rs_ov}'")

        if invalid_reasons:
            stats["invalid_overrides"].append(
                {
                    "code": code,
                    "listing": listing,
                    "reasons": "; ".join(invalid_reasons),
                }
            )

        if fields_changed:
            out.loc[mask, "Override_Applied"] = True
            _put("Override_Fields", mask, ", ".join(fields_changed))
            _put("Override_Note", mask, str(o.get("note", "")))
            _put("Override_ReviewedBy", mask, str(o.get("reviewed_by", "")))
            _put("Override_ReviewedAt", mask, str(o.get("reviewed_at", "")))
            stats["rows_touched"] += int(mask.sum())
            stats["applied_overrides"].append(
                {
                    "code": code,
                    "listing": listing,
                    "fields_changed": ", ".join(fields_changed),
                    "rows": int(mask.sum()),
                }
            )

    # Clean up helper columns
    out = out.drop(columns=["_code_lc", "_listing_lc"], errors="ignore")
    return out, stats


# Pending-overrides accumulator (used by the technician editor) ----------------
# The editor only ever shows one filtered/paged slice at a time. To let a
# technician correct items across several filters and pages and have every edit
# survive, the page keeps a running map of pending overrides keyed by tool code
# and folds each slice's edits into it. These two pure helpers do the folding and
# the conversion to the wide OVERRIDE_COLUMNS frame the engine and the database
# both consume.

_PENDING_OVERRIDE_FIELDS = (
    "product_category_override",
    "pack_units_override",
    "size_category_override",
    "cabinet_type_override",
    "vend_mode_override",
    "restocking_override",
    "note",
)


def merge_pending_overrides(pending, diffs):
    """Fold one view's edits into a running pending-overrides map.

    ``pending`` maps a tool code to its accumulated override fields; ``diffs`` is
    the list of per-row edits the editor produced for the current filter/page
    (each a dict with at least ``code`` plus changed override fields). Returns a
    new map with this view's edits merged in, keyed by code, so an edit made
    under one filter is not lost when the technician switches filters or pages.
    A later edit to the same code and field overwrites the earlier value; the
    code's other fields are preserved. The input map is not mutated.
    """
    out = {code: dict(fields) for code, fields in (pending or {}).items()}
    for d in diffs or []:
        code = str(d.get("code", "")).strip()
        if not code:
            continue
        entry = dict(out.get(code, {}))
        listing = d.get("listing")
        if listing:
            entry["listing"] = str(listing)
        for f in _PENDING_OVERRIDE_FIELDS:
            if f in d and str(d.get(f, "")).strip() != "":
                entry[f] = d[f]
        if entry:
            out[code] = entry
    return out


def pending_overrides_to_df(pending):
    """A wide override frame (OVERRIDE_COLUMNS shape) from a pending map, ready
    for ``apply_overrides`` and for saving as a database set. Codes keep
    insertion order; a code with no recorded listing defaults to the Tools
    listing."""
    rows = []
    for code, fields in (pending or {}).items():
        row = {c: "" for c in OVERRIDE_COLUMNS}
        row["code"] = code
        row["listing"] = fields.get("listing", LISTING_TOOLS)
        for f in _PENDING_OVERRIDE_FIELDS:
            if f in fields:
                row[f] = fields[f]
        rows.append(row)
    return pd.DataFrame(rows, columns=OVERRIDE_COLUMNS)
