"""Equivalence contract for engine.plan.run_plan (the I1 capstone).

The expected side of every regime test replicates the page's deterministic
pipeline sequence literally -- the same segment calls with the same glue code, in
the page's exact order -- so the composed ``run_plan`` is proven equal to the
sequence it replaces. The order itself becomes an executable contract: reordering
a stage inside ``run_plan`` breaks these tests even while the unit suite stays
green.

The four regimes reach every branch: supply-point replication and partition,
forced screws/accessories, manual size fixes, stored-classification reuse,
technician overrides (forced routing and the HMA-1 re-route), system-type and
special-to-KTC forcing, bulk routing, the fit-check, separated listings, the
Helix operational mode, the rebalancer, and the carousel cap.

Three further tests pin the properties the Streamlit cache wiring relies on:
``run_plan`` never mutates its inputs, is deterministic across calls, and returns
a picklable ``PlanResult``. A final test proves the stored-classification applier
was moved, not duplicated: the db module delegates to the engine function.
"""

import math
import pickle

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from engine.classification import apply_stored_classifications
from engine.cabinet_math import apply_operational_mode
from engine.constants import (DAYS_PER_MONTH, LISTING_PPE, LISTING_TOOLS,
                              OVERRIDE_COLUMNS, SIZE_VALID)
from engine.invariants import check_restock_bucket_consistency, verify_plan
from engine.plan import (BaseCounts, PlanParams, PlanResult, PREVIEW_COLUMNS,
                         run_plan, run_bucket_planning_segment, run_bulk_routing_segment,
                         run_demand_segment, run_override_application_segment,
                         run_restock_segment, run_routing_override_segment, run_sizing_segment,
                         run_supply_point_segment)
from engine.plan_config import PlanConfig
from engine.routing_rules import classify_standard_special

# ---------------------------------------------------------------------------
# Boundary frame builder: the shape `work` has when the page reaches the
# deterministic pipeline (post-preprocessing, post-AI merge, post safety pass).
# ---------------------------------------------------------------------------

def _boundary_frame(*, with_stdspecial=False, with_systemtyp=False,
                    with_dims=False, with_ppe=False) -> pd.DataFrame:
    n = 14
    df = pd.DataFrame({
        "Code": [f"T{i:03d}" for i in range(1, n + 1)],
        "SupplierCode": [f"S{i:03d}" for i in range(1, n + 1)],
        "Description": [
            "End mill 10mm", "Insert CNMG", "Drill 5mm", "Holder ER32",
            "Tap M8", "Reamer 6H7", "Screw M4x10", "Accessory wrench",
            "Abrasive disc 125mm", "End mill 12mm", "Insert WNMG",
            "Drill 8mm", "End mill 6mm", "Boring bar",
        ],
        "Description_2": [""] * n,
        "Listing": ([LISTING_PPE] * 3 + [LISTING_TOOLS] * (n - 3)) if with_ppe
                   else [LISTING_TOOLS] * n,
        "Consumption_pcs": [960.0, 3200.0, 48.0, 8.0, 240.0, 4.0, 5000.0,
                            120.0, 2400.0, 640.0, 1600.0, 16.0, 320.0, 2.0],
        "PackUnits": [1.0, 10.0, 1.0, 1.0, 1.0, 1.0, 100.0, 1.0, 1.0, 1.0,
                      10.0, 1.0, 1.0, 1.0],
        "PackUnits_Source": ["Mapped", "Mapped", "Default", "Default", "Mapped",
                             "Default", "Mapped", "Default", "Default", "Default",
                             "Mapped", "Default", "Default", "Default"],
        "SizeCategory": ["M", "S", "S", "L", "M", "S", "S", "M", "L", "M",
                         "S", "S", "M", "XL"],
        "SizeCategory_Source": ["Heuristic"] * n,
        "ProductCategory": ["mills", "inserts", "drills", "holders", "taps",
                            "reamers", "screws", "accessories", "abrasives",
                            "mills", "inserts", "drills", "mills", "holders"],
        "ProductCategory_Source": ["Heuristic"] * n,
        "ProductCategory_Confidence": [0.8] * n,
        "Regrind": [True, False, False, False, True, False, False, False,
                    False, True, False, False, False, False],
    })
    if with_stdspecial:
        df["StdSpecial"] = ["standard", "special", "standard", "special",
                            "standard", "standard", "standard", "standard",
                            "standard", "special", "standard", "standard",
                            "standard", "unclear"]
    if with_systemtyp:
        df["SystemTyp"] = ["", "KTC", "", "Locker", "", "", "", "",
                           "", "KTC or Kanban", "", "", "", "Locker"]
    if with_dims:
        df["PackageDimensions"] = ["Ø 10 x 70 mm"] * n
    return df


def _base_counts(df: pd.DataFrame) -> BaseCounts:
    total = float(pd.to_numeric(df["Consumption_pcs"], errors="coerce").fillna(0.0).sum())
    return BaseCounts(
        rows_before=len(df), rows_after_year_filter=len(df),
        rows_after_dedup=len(df), consumption_before=total,
        consumption_after_year=total, consumption_after_dedup=total,
    )


def _params(df: pd.DataFrame, **kw) -> PlanParams:
    defaults = dict(
        n_supply_points=1, sp_mode="replicate",
        consumption_period_months=16.0, coverage_days=18, coverage_days_special=18,
        usage_threshold=1.0, per_class_thresholds=(), optional_thresholds_active=False,
        force_screws_accessories_kanban=False,
        manual_size_fixes=(), stored_classifications=(), restock_categories=(),
        helix_threshold=4.0, dims_mapped=False,
        minimum_carousel_allocation=3, plan_cfg=PlanConfig(),
        system_type_mapped=False, special_ktc=False, stdspecial_mapped=False,
        enable_bulk_routing=False,
        op_mode="", calc_mode_separated=False, capacity_buffer_pct=15.0,
        enable_rebalancer=True, underuse_threshold_pct=30.0, max_carousels_cap=1,
        base_counts=_base_counts(df),
    )
    defaults.update(kw)
    return PlanParams(**defaults)


# ---------------------------------------------------------------------------
# The expected side: the page's pipeline sequence, transcribed literally.
# ---------------------------------------------------------------------------

_PAGE_PREVIEW_COLS = [
    "Listing", "SupplyPoint", "Program", "Code", "SupplierCode", "Year",
    "ProductCategory", "ProductCategory_Source", "ProductCategory_Evidence",
    "ProductCategory_Confidence", "ProductCategory_AI_Consulted",
    "ProductCategory_AI_Model", "ProductCategory_AI_TimestampUTC",
    "Description", "Description_2", "Consumption_pcs",
    "PackUnits", "PackUnits_Source", "PackUnits_Evidence", "PackUnits_Confidence",
    "PackUnits_AI_Consulted", "PackUnits_AI_Model", "PackUnits_AI_TimestampUTC",
    "Monthly_pcs", "Monthly_packs", "Target_packs",
    "SizeCategory", "SizeCategory_Source", "SizeCategory_AI_Consulted",
    "SizeCategory_AI_Model", "SizeCategory_AI_TimestampUTC",
    "SystemCategory", "SystemCategory_Reason", "ItemFamily", "VendMode",
    "VendBlockReason", "CabinetType_pre_route", "CabinetType", "Spiral_capacity",
    "Spirals_needed_pre_route", "Spirals_needed",
    "Carousel_stockpiles_pre_route", "Carousel_stockpiles",
]


def _page_sequence(work: pd.DataFrame, overrides_df: pd.DataFrame, p: PlanParams) -> dict:
    """The page's deterministic pipeline, stage by stage, in the page's order."""
    if not work.index.is_unique:
        raise ValueError(
            "run_plan requires a unique row index; the frame carries "
            "duplicate labels"
        )
    work = work.copy()
    per_class = dict(p.per_class_thresholds)
    out: dict = {}

    # Supply point assignment (Partition OR Replicate)
    work, out["sp_conservation"] = run_supply_point_segment(
        work, n_supply_points=int(p.n_supply_points), mode=p.sp_mode)

    # Demand arithmetic and the base KTC/Kanban decision
    work = run_demand_segment(
        work,
        consumption_period_months=p.consumption_period_months,
        coverage_days=p.coverage_days,
        coverage_days_special=p.coverage_days_special,
        usage_threshold=p.usage_threshold,
        per_class_thresholds=per_class,
        optional_thresholds_active=p.optional_thresholds_active,
    )
    out["split_coverage"] = ("StdSpecial" in work.columns) and (
        p.coverage_days_special != p.coverage_days)

    if p.force_screws_accessories_kanban:
        mask = work["ProductCategory"].astype(str).str.lower().isin(["screws", "accessories"])
        work.loc[mask, "SystemCategory"] = "Kanban"
        work.loc[mask, "SystemCategory_Reason"] = "Forced Kanban: screws/accessories"

    out["n_pack_default"] = (
        int((work["PackUnits_Source"].astype(str) == "Default").sum())
        if "PackUnits_Source" in work.columns else 0)

    out["stdspecial_missing"] = False
    out["stdspecial_counts"] = None
    if p.stdspecial_mapped:
        if "StdSpecial" not in work.columns:
            out["stdspecial_missing"] = True
        else:
            cls = work["StdSpecial"].apply(classify_standard_special)
            out["stdspecial_counts"] = (int((cls == "standard").sum()),
                                        int((cls == "special").sum()),
                                        int((cls == "").sum()))

    # Stored-classification reuse (recompute path)
    out["reuse_hits_n"], out["reuse_misses_n"] = 0, 0
    if p.stored_classifications:
        lookup = {code: {"size_category": size, "product_category": prod}
                  for code, size, prod in p.stored_classifications}
        work, hits, misses = apply_stored_classifications(work, lookup)
        if "SizeCategory_Source" in work.columns:
            work.loc[work["Code"].astype(str).isin(hits), "SizeCategory_Source"] = (
                "Reused from stored run")
        out["reuse_hits_n"], out["reuse_misses_n"] = len(hits), len(misses)

    # Manual size fixes (after the reuse since v34.57: the fix wins)
    fixes = dict(p.manual_size_fixes)
    if fixes and "Code" in work.columns:
        codes = work["Code"].astype(str)
        for fix_code, fix_size in fixes.items():
            fm = codes == str(fix_code)
            if fm.any():
                work.loc[fm, "SizeCategory"] = str(fix_size).upper()
                work.loc[fm, "SizeCategory_Source"] = "Manual (Helix-fit)"

    # Cabinet type, optional fit-check, physical sizing
    work = run_sizing_segment(
        work,
        helix_threshold=p.helix_threshold,
        run_fit_check=bool(p.dims_mapped and "PackageDimensions" in work.columns),
        minimum_carousel_allocation=int(p.minimum_carousel_allocation),
        carousel_reserve_factor=float(p.plan_cfg.carousel_reserve_factor),
        helix_overfill_factor=float(p.plan_cfg.helix_overfill_factor),
    )

    # Technician overrides
    out["override_stats"] = {
        "rows_touched": 0, "fields_changed": {}, "unmatched_overrides": [],
        "invalid_overrides": [], "applied_overrides": [],
    }
    out["rerouted_flips"] = 0
    if len(overrides_df) > 0:
        work, out["override_stats"], out["rerouted_flips"] = run_override_application_segment(
            work, overrides_df,
            usage_threshold=p.usage_threshold,
            helix_threshold=p.helix_threshold,
            minimum_carousel_allocation=p.minimum_carousel_allocation,
            carousel_reserve_factor=p.plan_cfg.carousel_reserve_factor,
            helix_overfill_factor=p.plan_cfg.helix_overfill_factor,
            per_class_thresholds=per_class,
            optional_thresholds_active=p.optional_thresholds_active,
            force_screws_accessories_kanban=p.force_screws_accessories_kanban,
        )
    for c, default in [("Override_Applied", False), ("Override_Fields", ""),
                       ("Override_Note", ""), ("Override_ReviewedBy", ""),
                       ("Override_ReviewedAt", "")]:
        if c not in work.columns:
            work[c] = default

    # Forcing overrides: system type, then special-to-KTC
    force_system_type = bool(p.system_type_mapped and "SystemTyp" in work.columns)
    force_special_ktc = bool(p.special_ktc and p.stdspecial_mapped
                             and "StdSpecial" in work.columns)
    out["force_system_type"] = force_system_type
    out["force_special_ktc"] = force_special_ktc
    out["routing_override_counts"] = run_routing_override_segment(
        work,
        force_system_type=force_system_type,
        force_special_ktc=force_special_ktc,
        threshold=float(p.usage_threshold),
        helix_threshold=float(p.helix_threshold),
        min_carousel_compartments=int(p.minimum_carousel_allocation),
        carousel_reserve_factor=float(p.plan_cfg.carousel_reserve_factor),
        helix_overfill_factor=float(p.plan_cfg.helix_overfill_factor),
    )

    # Optional bulk routing
    work, out["vend_stats"] = run_bulk_routing_segment(
        work, enable_bulk_routing=p.enable_bulk_routing)

    # Pre-rollup data integrity validation
    validation_issues = []
    ktc_rows = work[work["SystemCategory"] == "KTC"]
    bad_cabtype = ktc_rows[~ktc_rows["CabinetType"].isin(
        ["Helix", "Carousel", "Locker A", "Locker B", "Locker C"])]
    if not bad_cabtype.empty:
        validation_issues.append(f"{len(bad_cabtype)} KTC row(s) have an unexpected CabinetType.")
    helix_rows = ktc_rows[ktc_rows["CabinetType"] == "Helix"]
    bad_helix = helix_rows[pd.to_numeric(helix_rows["Spiral_capacity"], errors="coerce").fillna(0) <= 0]
    if not bad_helix.empty:
        validation_issues.append(f"{len(bad_helix)} Helix row(s) missing Spiral_capacity.")
    carousel_rows = ktc_rows[ktc_rows["CabinetType"] == "Carousel"]
    bad_carousel = carousel_rows[
        (carousel_rows["Monthly_packs"] > 0)
        & (pd.to_numeric(carousel_rows["Carousel_stockpiles"], errors="coerce").fillna(0) <= 0)]
    if not bad_carousel.empty:
        validation_issues.append(
            f"{len(bad_carousel)} Carousel row(s) have 0 stockpiles despite positive consumption.")
    bad_pack = work[pd.to_numeric(work["PackUnits"], errors="coerce").fillna(0) <= 0]
    if not bad_pack.empty:
        validation_issues.append(f"{len(bad_pack)} row(s) have PackUnits <= 0.")
    bad_size = work[~work["SizeCategory"].astype(str).str.upper().isin(SIZE_VALID)]
    if not bad_size.empty:
        validation_issues.append(f"{len(bad_size)} row(s) have invalid SizeCategory.")
    nan_monthly = work[work["Monthly_packs"].isna()]
    if not nan_monthly.empty:
        validation_issues.append(f"{len(nan_monthly)} row(s) have NaN Monthly_packs.")
    out["validation_issues"] = validation_issues

    # Plan integrity (invariant layer)
    base_info = None
    if p.base_counts is not None:
        b = p.base_counts
        base_info = {
            "rows_before": b.rows_before,
            "rows_after_year_filter": b.rows_after_year_filter,
            "rows_after_dedup": b.rows_after_dedup,
            "consumption_before": b.consumption_before,
            "consumption_after_year": b.consumption_after_year,
            "consumption_after_dedup": b.consumption_after_dedup,
        }
    out["integrity"] = verify_plan(work, base_info, days_per_month=DAYS_PER_MONTH,
                                   consumption_period_months=float(p.consumption_period_months))

    # Pack-size audit snapshot (pre-bucket values, as the page renders them)
    hog_threshold = 10.0
    hogs = work[
        (work["PackUnits_Source"].astype(str) == "Default")
        & (pd.to_numeric(work["Monthly_packs"], errors="coerce").fillna(0) > hog_threshold)
    ].copy()
    if not hogs.empty:
        hogs = hogs.sort_values("Monthly_packs", ascending=False)
    out["hogs"] = hogs

    # Classification preview snapshot (pre-bucket values, as the page renders them)
    preview_cols = [c for c in _PAGE_PREVIEW_COLS if c in work.columns]
    out["preview"] = work[preview_cols].head(300).copy()

    # Operational mode, bucket construction, per-bucket planning, grand total
    buf_pct = float(p.capacity_buffer_pct)
    n_sp = int(p.n_supply_points)
    if p.op_mode in ("Helix", "Carousel"):
        work = apply_operational_mode(
            work, p.op_mode,
            min_carousel_compartments=int(p.minimum_carousel_allocation),
            carousel_reserve_factor=p.plan_cfg.carousel_reserve_factor,
            helix_overfill_factor=p.plan_cfg.helix_overfill_factor,
        )

    # Restocking (v34.24): mirrored at the same position as run_plan, after
    # the operational mode and before bucket planning.
    work, _restock_info = run_restock_segment(
        work,
        restock_categories=p.restock_categories,
        op_mode=str(p.op_mode or ""),
    )

    def _bucket_label(listing, sp):
        parts = []
        if listing is not None:
            parts.append(str(listing))
        if sp is not None:
            parts.append(f"SP {sp}")
        return " @ ".join(parts) if parts else "All"

    buckets = []
    if p.calc_mode_separated:
        listings_iter = [l for l in [LISTING_TOOLS, LISTING_PPE]
                         if l in set(work["Listing"].astype(str).unique())]
    else:
        listings_iter = ["__ALL__"]
    out["listings"] = tuple(l for l in listings_iter if l != "__ALL__")
    for listing_val in listings_iter:
        if listing_val == "__ALL__":
            listing_subset = work
            listing_display = None
        else:
            listing_subset = work[work["Listing"] == listing_val]
            listing_display = listing_val
        if n_sp > 1:
            for sp in range(1, n_sp + 1):
                sp_subset = listing_subset[listing_subset["SupplyPoint"] == sp]
                buckets.append((_bucket_label(listing_display, sp), sp_subset))
        else:
            buckets.append((_bucket_label(listing_display, None), listing_subset))

    work, bucket_plans, rebalance_audit = run_bucket_planning_segment(
        work, buckets,
        op_mode=p.op_mode,
        enable_rebalancer=p.enable_rebalancer,
        buf_pct=buf_pct,
        minimum_carousel_allocation=int(p.minimum_carousel_allocation),
        underuse_threshold_pct=float(p.underuse_threshold_pct),
        max_carousels_cap=p.max_carousels_cap,
        helix_overfill_factor=p.plan_cfg.helix_overfill_factor,
        carousel_reserve_factor=p.plan_cfg.carousel_reserve_factor,
        carousel_fill_ceiling=p.plan_cfg.carousel_fill_ceiling,
    )

    # Restocking bucket invariants (v34.27): mirrored at the same position.
    out["integrity"].checks["restock_buckets"] = check_restock_bucket_consistency(
        work, bucket_plans
    )
    out["bucket_plans"] = bucket_plans
    out["rebalance_audit"] = rebalance_audit

    keys_to_sum = [
        "rows_total", "ktc_count", "kanban_count", "helix_refs", "carousel_refs",
        "locker_a_refs", "locker_b_refs", "locker_c_refs",
        "total_spirals", "total_spirals_buf", "car_slots", "car_slots_buf",
        "countA", "countA_buf", "countB", "countB_buf", "countC", "countC_buf",
        "helix_cabs_base", "helix_cabs", "car_cabs_base", "car_cabs",
        "cabA_base", "cabA", "cabB_base", "cabB", "cabC_base", "cabC",
        "total_cabs_base", "total_cabs", "total_consumption",
    ]
    grand = {k: 0 for k in keys_to_sum}
    for _, plan in bucket_plans:
        for k in keys_to_sum:
            grand[k] = grand[k] + plan.get(k, 0)
    out["grand"] = grand
    out["work"] = work
    return out


# ---------------------------------------------------------------------------
# The four regimes
# ---------------------------------------------------------------------------

def _regime_default():
    df = _boundary_frame()
    return df, pd.DataFrame(columns=OVERRIDE_COLUMNS), _params(df)


def _regime_loaded():
    df = _boundary_frame(with_stdspecial=True)
    p = _params(
        df,
        n_supply_points=2, sp_mode="replicate",
        op_mode="Capped", max_carousels_cap=1,
        helix_threshold=2.0,
        enable_bulk_routing=True,
        force_screws_accessories_kanban=True,
        capacity_buffer_pct=30.0,
        coverage_days_special=25,
        special_ktc=True, stdspecial_mapped=True,
    )
    return df, pd.DataFrame(columns=OVERRIDE_COLUMNS), p


def _regime_overrides():
    df = _boundary_frame(with_stdspecial=True, with_systemtyp=True, with_dims=True)
    overrides = pd.DataFrame([
        {"code": "T003", "listing": LISTING_TOOLS, "pack_units_override": "25",
         "note": "carton of 25", "reviewed_by": "tech", "reviewed_at": "2026-01-01"},
        {"code": "T005", "listing": LISTING_TOOLS, "cabinet_type_override": "Carousel",
         "note": "forced", "reviewed_by": "tech", "reviewed_at": "2026-01-01"},
        {"code": "T001", "listing": LISTING_TOOLS, "cabinet_type_override": "Kanban",
         "note": "customer keeps on shelf", "reviewed_by": "tech", "reviewed_at": "2026-01-01"},
        {"code": "T012", "listing": LISTING_TOOLS, "product_category_override": "inserts",
         "note": "misclassified", "reviewed_by": "tech", "reviewed_at": "2026-01-01"},
    ]).reindex(columns=OVERRIDE_COLUMNS, fill_value="")
    p = _params(
        df,
        manual_size_fixes=(("T014", "M"),),
        stored_classifications=(("T004", "M", "holders"), ("T999", "S", "mills")),
        dims_mapped=True,
        system_type_mapped=True,
        special_ktc=True, stdspecial_mapped=True,
        per_class_thresholds=(("drills", 2.0),), optional_thresholds_active=True,
    )
    return df, overrides, p


def _regime_helix_separated():
    df = _boundary_frame(with_ppe=True)
    p = _params(
        df,
        op_mode="Helix",
        calc_mode_separated=True,
        n_supply_points=2, sp_mode="partition",
        capacity_buffer_pct=0.0,
    )
    return df, pd.DataFrame(columns=OVERRIDE_COLUMNS), p


_REGIMES = {
    "default": _regime_default,
    "loaded": _regime_loaded,
    "overrides": _regime_overrides,
    "helix_separated": _regime_helix_separated,
}


def _assert_result_equals_sequence(result: PlanResult, expected: dict):
    assert_frame_equal(result.work, expected["work"], check_dtype=True)
    assert result.sp_conservation == expected["sp_conservation"]
    assert result.split_coverage == expected["split_coverage"]
    assert result.n_pack_default == expected["n_pack_default"]
    assert result.stdspecial_missing == expected["stdspecial_missing"]
    assert result.stdspecial_counts == expected["stdspecial_counts"]
    assert result.reuse_hits_n == expected["reuse_hits_n"]
    assert result.reuse_misses_n == expected["reuse_misses_n"]
    assert result.override_stats == expected["override_stats"]
    assert result.rerouted_flips == expected["rerouted_flips"]
    assert result.force_system_type == expected["force_system_type"]
    assert result.force_special_ktc == expected["force_special_ktc"]
    assert result.routing_override_counts == expected["routing_override_counts"]
    assert result.vend_stats == expected["vend_stats"]
    assert result.validation_issues == expected["validation_issues"]
    assert result.integrity.checks == expected["integrity"].checks
    assert_frame_equal(result.hogs, expected["hogs"], check_dtype=True)
    assert_frame_equal(result.preview, expected["preview"], check_dtype=True)
    assert result.listings == expected["listings"]
    assert result.bucket_plans == expected["bucket_plans"]
    assert result.rebalance_audit == expected["rebalance_audit"]
    assert result.grand == expected["grand"]


@pytest.mark.parametrize("regime", sorted(_REGIMES))
def test_run_plan_equals_page_sequence(regime):
    df, overrides, p = _REGIMES[regime]()
    expected = _page_sequence(df, overrides, p)
    result = run_plan(df, overrides, p)
    _assert_result_equals_sequence(result, expected)


@pytest.mark.parametrize("regime", sorted(_REGIMES))
def test_run_plan_does_not_mutate_inputs(regime):
    df, overrides, p = _REGIMES[regime]()
    df_before = df.copy(deep=True)
    ov_before = overrides.copy(deep=True)
    run_plan(df, overrides, p)
    assert_frame_equal(df, df_before, check_dtype=True)
    assert_frame_equal(overrides, ov_before, check_dtype=True)


@pytest.mark.parametrize("regime", sorted(_REGIMES))
def test_run_plan_is_deterministic(regime):
    df, overrides, p = _REGIMES[regime]()
    r1 = run_plan(df, overrides, p)
    r2 = run_plan(df, overrides, p)
    assert_frame_equal(r1.work, r2.work, check_dtype=True)
    assert r1.grand == r2.grand
    assert r1.bucket_plans == r2.bucket_plans


@pytest.mark.parametrize("regime", sorted(_REGIMES))
def test_plan_result_is_picklable(regime):
    df, overrides, p = _REGIMES[regime]()
    result = run_plan(df, overrides, p)
    clone = pickle.loads(pickle.dumps(result))
    assert_frame_equal(clone.work, result.work, check_dtype=True)
    assert clone.grand == result.grand
    assert clone.integrity.checks == result.integrity.checks


def test_plan_params_is_hashable_and_content_keyed():
    df = _boundary_frame()
    p1 = _params(df)
    p2 = _params(df)
    assert hash(p1) == hash(p2) and p1 == p2
    p3 = _params(df, helix_threshold=2.0)
    assert p1 != p3


def test_db_applier_delegates_to_engine():
    from db.classification_reuse import apply_stored_classifications as db_apply
    assert db_apply is apply_stored_classifications


def test_preview_columns_match_page_list():
    assert list(PREVIEW_COLUMNS) == _PAGE_PREVIEW_COLS
