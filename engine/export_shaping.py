"""Column shaping for the user-facing export sheets.

The Result sheet keeps the full audit dump (every column). The segregated views
(KTC_only, Kanban_only, Helix_only, Carousel_only, Bulk_Routed, and the listing
sheet) are trimmed to the columns a user wants to read: identity,
classification, demand, and plan output. Audit, AI, and override fields stay in
Result only. Columns that are entirely empty (all NaN, blank, or zero) are dropped
per sheet, so each sheet shows only data that is present.

Pure pandas; no Streamlit and no I/O. The PDF and PPTX exports use separate data
paths and do not depend on this module.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

USER_FRIENDLY_COLS = [
    # identity
    "Listing", "Code", "Kromi_Art_No", "Description", "Description_2", "SupplierCode",
    # classification
    "ProductCategory", "ToolClass", "SizeCategory", "PackUnits",
    # takeover stock (v34.56): present only when a stock column was mapped
    "Stock_pcs",
    "Regrind", "SystemTyp",
    "Std_Special",
    # demand
    "Consumption_pcs", "Monthly_pcs", "Monthly_packs",
    # plan output
    "System", "Forced_to_KTC", "SupplyPoint", "CabinetType", "Spirals_needed", "Carousel_stockpiles",
    # fixed configuration (v34.52): present only in that mode
    "Placement_Rank", "Placement_Status", "Placement_Note",
    # restocking (v34.26): display flag and buffer target; user_view drops both
    # when the feature is off, so a plan without restocking keeps its sheets
    "Restockable", "Restock_target",
    # optional dimensional fit-check (present only when the package-dimensions
    # column was mapped; user_view drops them when empty)
    "Fit_status", "Fit_recommended", "Fit_package_mm",
    # problematic-size flag (present only when at least one item was flagged;
    # user_view drops it when empty). Carries the colour in the sheet.
    "SizeIssue",
]


def user_view(df: pd.DataFrame, columns: Optional[List[str]] = None) -> pd.DataFrame:
    """Return a copy of ``df`` trimmed to ``columns`` (default USER_FRIENDLY_COLS),
    with columns that are entirely empty (all NaN/blank/zero) removed.

    Preserves the given column order so the sheet always reads the same way
    regardless of which columns survived. An empty input still yields the trimmed
    columns, so the sheet exists with a header row but no data.
    """
    cols = USER_FRIENDLY_COLS if columns is None else columns
    if df.empty:
        # Empty DataFrame: still emit the trimmed columns so the sheet exists
        # with a header row but no data.
        return pd.DataFrame(columns=[c for c in cols if c in df.columns])
    kept_cols = []
    for col in cols:
        if col not in df.columns:
            continue
        s = df[col]
        if pd.api.types.is_numeric_dtype(s):
            # Numeric: drop if every value is NaN or 0
            if (s.fillna(0) == 0).all():
                continue
        else:
            # Text/object: drop if every value is empty after stripping
            if s.fillna("").astype(str).str.strip().eq("").all():
                continue
        kept_cols.append(col)
    return df[kept_cols].copy()


# ---- PDF absorption builders (v34.25) ---------------------------------------
# The per-supply-point PDF was retired; these three pure builders shape the
# pieces it carried so the workbook holds them instead: the five-metric KPI
# row, the pie series in slide bucket order, and the per-SP subclass table.

def build_sp_kpi_frame(plan: dict) -> pd.DataFrame:
    """One row with the five per-supply-point headline metrics.

    Spirals and compartments use the buffered totals, matching what the
    retired PDF's KPI strip showed: compartments sum the buffered Carousel
    slots and the three buffered locker counts.
    """
    compartments = (
        int(plan.get("car_slots_buf", 0) or 0)
        + int(plan.get("countA_buf", 0) or 0)
        + int(plan.get("countB_buf", 0) or 0)
        + int(plan.get("countC_buf", 0) or 0)
    )
    return pd.DataFrame([{
        "KTC items": int(plan.get("ktc_count", 0) or 0),
        "Kanban items": int(plan.get("kanban_count", 0) or 0),
        "Spirals (total)": int(plan.get("total_spirals_buf", 0) or 0),
        "Compartments (total)": compartments,
        "Cabinets": int(plan.get("total_cabs", 0) or 0),
    }])


def build_pie_series(dist: dict) -> tuple[list, list]:
    """Labels and values for one distribution pie, slide bucket order,
    zero buckets filtered, labels carrying the count like the retired PDF."""
    from engine.constants import SLIDE_BUCKET_ORDER

    labels: list = []
    values: list = []
    for bucket in SLIDE_BUCKET_ORDER:
        n = int(dist.get(bucket, 0) or 0)
        if n > 0:
            labels.append(f"{bucket} ({n})")
            values.append(n)
    return labels, values


def build_sp_subclass_frame(buckets: dict) -> pd.DataFrame:
    """Per-SP subclass table: one row per (bucket, subclass), buckets in
    slide order, subclasses by descending count, share within the bucket."""
    from engine.constants import SLIDE_BUCKET_ORDER

    rows: list = []
    for bucket in SLIDE_BUCKET_ORDER:
        sub = buckets.get(bucket, {}) or {}
        total = sum(int(v) for v in sub.values())
        for name, count in sorted(sub.items(), key=lambda kv: -int(kv[1])):
            share = (int(count) / total * 100.0) if total > 0 else 0.0
            rows.append({
                "Bucket": bucket,
                "Subclass": name,
                "Items": int(count),
                "Share of bucket %": round(share, 1),
            })
    return pd.DataFrame(rows, columns=["Bucket", "Subclass", "Items", "Share of bucket %"])


def frame_token(df: pd.DataFrame) -> str:
    """Cheap, content-exact digest of a dataframe (v34.29).

    Vectorized row hashing plus the column names and dtypes, so two frames
    share a token exactly when they carry the same columns, types, and
    values in the same order. Used as a cache key in place of streamlit's
    generic serialization, which walks every cell and grows expensive on
    large customer files.
    """
    import hashlib

    h = hashlib.sha256()
    h.update(repr(list(df.columns)).encode())
    h.update(repr([str(t) for t in df.dtypes]).encode())
    if len(df):
        h.update(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    return h.hexdigest()
