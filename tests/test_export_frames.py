"""engine/export_frames.py (v34.61): the Summary, Run_Metadata, audit, bucket
comparison and distribution tables of the result workbook, moved out of the
planner page and the exports panel so every front end builds them the same way.
"""
import dataclasses

import pandas as pd
import pytest

from engine import export_frames as ef
from engine.cabinet_math import SPECIAL_KTC_REASON
from engine.fixed_config import FIXED_MODE
from engine.plan_config import PlanConfig
from engine.sizing_factors import SP_MODE_PARTITION, SP_MODE_REPLICATE

_PLAN_KEYS = (
    "ktc_count", "kanban_count", "helix_refs", "total_spirals", "total_spirals_buf",
    "helix_cabs_base", "helix_cabs", "carousel_refs", "car_slots", "car_slots_buf",
    "car_cabs_base", "car_cabs", "locker_a_refs", "cabA_base", "cabA", "locker_b_refs",
    "cabB_base", "cabB", "locker_c_refs", "cabC_base", "cabC", "total_cabs_base",
    "total_cabs",
)


def _plan(offset: int) -> dict:
    return {k: offset + i for i, k in enumerate(_PLAN_KEYS)}


# ---- bucket tables --------------------------------------------------------------------

def test_summary_has_one_row_per_bucket_and_the_buffer_column():
    df = ef.summary_frame([("All", _plan(0))], _plan(100), buffer_pct=15.0)
    assert list(df["Bucket"]) == ["All"]
    assert list(df.columns) == [
        "Bucket", "KTC items", "Kanban items", "Helix refs", "Helix spirals (base)",
        "Helix spirals (buf)", "Helix cabs (base)", "Helix cabs (buf)", "Carousel refs",
        "Carousel slots (base)", "Carousel slots (buf)", "Carousel cabs (base)",
        "Carousel cabs (buf)", "Locker A refs", "Locker A cabs (base)", "Locker A cabs (buf)",
        "Locker B refs", "Locker B cabs (base)", "Locker B cabs (buf)", "Locker C refs",
        "Locker C cabs (base)", "Locker C cabs (buf)", "Total cabs (base)", "Total cabs (buf)",
        "Capacity buffer (%)",
    ]
    row = df.iloc[0]
    assert row["KTC items"] == 0 and row["Total cabs (buf)"] == 22
    assert row["Helix spirals (buf)"] == 4 and row["Carousel slots (base)"] == 8
    assert row["Capacity buffer (%)"] == 15.0


def test_summary_adds_a_grand_total_for_several_buckets():
    df = ef.summary_frame([("SP 1", _plan(0)), ("SP 2", _plan(50))], _plan(100), buffer_pct=0.0)
    assert list(df["Bucket"]) == ["SP 1", "SP 2", "Grand total"]
    assert df.iloc[2]["KTC items"] == 100


def test_bucket_compare_rows_and_grand_total():
    one = ef.bucket_compare_frame([("All", _plan(0))], _plan(100))
    assert list(one.columns) == ["Bucket", "KTC items", "Kanban items", "Helix cabs",
                                 "Carousel cabs", "Locker A cabs", "Locker B cabs",
                                 "Locker C cabs", "Total cabs"]
    assert list(one["Bucket"]) == ["All"]
    assert one.iloc[0]["Helix cabs"] == 6 and one.iloc[0]["Carousel cabs"] == 11
    two = ef.bucket_compare_frame([("SP 1", _plan(0)), ("SP 2", _plan(1))], _plan(100))
    assert list(two["Bucket"]) == ["SP 1", "SP 2", "Grand total"]
    assert two.iloc[2]["Total cabs"] == 122


# ---- audit and distributions -----------------------------------------------------------

def _work():
    return pd.DataFrame({
        "Listing": ["Tools", "Tools", "Tools", "PPE"],
        "ProductCategory": ["drill", "drill", "mill", "glove"],
        "SystemCategory": ["KTC", "KTC", "Kanban", "KTC"],
        "CabinetType": ["Helix", "Carousel", "", "Carousel"],
        "Monthly_packs": [1.0, 3.0, 4.0, 2.0],
        "ProductCategory_Source": ["Provided", "Heuristic", "Heuristic", None],
        "SizeCategory_Source": ["Heuristic", "Default", "AI", "Default"],
        "PackUnits_Source": ["Provided", "Provided", "Provided", "Provided"],
        "ProductCategory_AI_Consulted": [False, True, None, False],
        "SizeCategory_AI_Consulted": [False, False, False, False],
        "PackUnits_AI_Consulted": [True, True, True, True],
    })


def test_audit_counts_sources_per_field():
    df = ef.audit_frame(_work())
    assert list(df.columns) == ["Field", "Provided", "Heuristic", "AI", "Default",
                                "AI_Consulted (total)", "Total rows"]
    assert df.to_dict("records") == [
        {"Field": "ProductCategory", "Provided": 1, "Heuristic": 2, "AI": 0, "Default": 0,
         "AI_Consulted (total)": 1, "Total rows": 4},
        {"Field": "SizeCategory", "Provided": 0, "Heuristic": 1, "AI": 1, "Default": 2,
         "AI_Consulted (total)": 0, "Total rows": 4},
        {"Field": "PackUnits", "Provided": 4, "Heuristic": 0, "AI": 0, "Default": 0,
         "AI_Consulted (total)": 4, "Total rows": 4},
    ]


def test_distribution_counts_and_shares_within_each_listing():
    df = ef.distribution_counts(_work(), "ProductCategory")
    assert list(df.columns) == ["Listing", "ProductCategory", "Count", "Share"]
    rows = {(r.Listing, r.ProductCategory): (r.Count, r.Share) for r in df.itertuples()}
    assert rows[("Tools", "drill")] == (2, pytest.approx(2 / 3))
    assert rows[("Tools", "mill")] == (1, pytest.approx(1 / 3))
    assert rows[("PPE", "glove")] == (1, 1.0)


def test_distribution_by_volume_sums_monthly_packs():
    df = ef.distribution_volume(_work(), "ProductCategory")
    assert list(df.columns) == ["Listing", "ProductCategory", "MonthlyPacks", "Share"]
    rows = {(r.Listing, r.ProductCategory): (r.MonthlyPacks, r.Share) for r in df.itertuples()}
    assert rows[("Tools", "drill")] == (4.0, 0.5)


def test_empty_distributions_keep_their_columns():
    empty = _work().iloc[0:0]
    assert list(ef.distribution_counts(empty, "X").columns) == ["Listing", "X", "Count", "Share"]
    assert list(ef.distribution_volume(empty, "X").columns) == [
        "Listing", "X", "MonthlyPacks", "Share"]


def test_distribution_frames_uses_ktc_rows_for_the_cabinet_type():
    d = ef.distribution_frames(_work())
    assert set(d.cabinet_type["CabinetType"]) == {"Helix", "Carousel"}
    assert int(d.cabinet_type["Count"].sum()) == 3
    pd.testing.assert_frame_equal(d.category_rows, ef.distribution_counts(_work(), "ProductCategory"))
    pd.testing.assert_frame_equal(d.category_volume, ef.distribution_volume(_work(), "ProductCategory"))
    pd.testing.assert_frame_equal(d.system, ef.distribution_counts(_work(), "SystemCategory"))


def test_listings_in_data():
    assert ef.listings_in_data(_work()) == ["PPE", "Tools"]


def test_takeover_shares_stock_only_for_replicated_supply_points_without_programs():
    assert ef.takeover_shared_stock(SP_MODE_REPLICATE, 2, program_mapping_active=False)
    assert not ef.takeover_shared_stock(SP_MODE_REPLICATE, 1, program_mapping_active=False)
    assert not ef.takeover_shared_stock(SP_MODE_REPLICATE, 2, program_mapping_active=True)
    assert not ef.takeover_shared_stock(SP_MODE_PARTITION, 2, program_mapping_active=False)


# ---- run metadata ---------------------------------------------------------------------

_META_KEYS = [
    "Build", "Timestamp (UTC)", "Model", "Calc mode", "Operational mode",
    "Max carousels (capped mode)", "Supply points", "SP mode", "Capacity buffer (%)",
    "KTC threshold", "Helix threshold", "Consumption months", "Coverage window (days)",
    "Carousel reserve factor", "Carousel fill ceiling", "Min carousel alloc",
    "Helix overfill factor", "Pack-hint extraction", "Per-class thresholds",
    "Coverage special (days)", "Consolidate underused cabinets",
    "Empty-cabinet threshold (%)", "Force screws/accessories Kanban",
    "Regrind handling (Helix +1 spiral)", "System type override (Lagersystem)",
    "Use Description_2", "AI fallback", "Restocking column",
    "Restockable categories (rule)", "Restock buffer compartments", "Bulk routing enabled",
    "Bulk routed rows", "Bulk removed spirals", "Bulk removed slots",
    "Overrides blocked bulk", "Program→SP mapping", "Programmes mapped", "Customer", "Site",
    "Overrides applied", "Overrides rows touched", "Overrides stale", "Overrides invalid",
    "Listings loaded", "Tools sheet", "PPE sheet", "Rows before preproc",
    "Rows after year filter", "Rows after dedup", "AI batches run", "AI batches failed",
    "AI items processed", "AI missing responses", "Input tokens", "Output tokens",
    "Validation issues",
]


def _inputs(**kw):
    base = dict(
        build="v0", timestamp_utc="2026-01-01T00:00:00+00:00", model="m",
        calc_mode="Combined (one vending machine plan for both)",
        operational_mode="Standard (best fit per tool)", op_mode="", max_carousels_cap=2,
        n_sp=1, sp_mode=SP_MODE_REPLICATE, buf_pct=15.0, usage_threshold=1.0,
        helix_threshold=6.0, consumption_period_months=12.0, coverage_days=20,
        plan_cfg=PlanConfig(), minimum_carousel_allocation=3,
        enable_pack_hint_extraction=True, optional_thresholds_active=False,
        per_class_thresholds={}, split_coverage=False, coverage_days_special=20,
        enable_rebalancer=True, underuse_threshold_pct=30.0,
        force_screws_accessories_kanban=False, col_regrind=None, col_systemtyp=None,
        use_description_2=True, use_ai=False, col_restock=None, restock_categories=[],
        restock_slots_total=0, enable_bulk_routing=False, vend_stats={},
        program_mapping_active=False, program_to_sp_map={}, effective_customer="C",
        effective_site="S", override_store_unavailable=False, apply_overrides_ui=True,
        override_stats={"rows_touched": 0, "unmatched_overrides": [], "invalid_overrides": []},
        listings_in_data=["Tools"], sheet_tools="Catalog", sheet_ppe=None,
        base_info={"rows_before": 10, "rows_after_year_filter": 9, "rows_after_dedup": 8},
        ai_batches_run=0, ai_batches_failed=0, ai_items_run=0, ai_missing_responses=0,
        total_in_tokens=0, total_out_tokens=0, validation_issues=[], col_stdspecial=None,
        special_ktc=False,
    )
    base.update(kw)
    return ef.RunMetadataInputs(**base)


def _as_dict(rows):
    return {r["Key"]: r["Value"] for r in rows}


def test_run_metadata_keys_in_order_and_standard_values():
    rows = ef.run_metadata_rows(_inputs(), work=pd.DataFrame(), bucket_plans=[])
    assert [r["Key"] for r in rows] == _META_KEYS
    v = _as_dict(rows)
    assert v["Build"] == "v0" and v["Timestamp (UTC)"] == "2026-01-01T00:00:00+00:00"
    assert v["Max carousels (capped mode)"] == ""
    assert v["Carousel reserve factor"] == 0.85 and v["Helix overfill factor"] == 1.10
    assert v["Per-class thresholds"] == "off"
    assert v["Coverage special (days)"] == "n/a"
    assert v["Consolidate underused cabinets"] == "on"
    assert v["Empty-cabinet threshold (%)"] == 30.0
    assert v["Regrind handling (Helix +1 spiral)"] == "off"
    assert v["Use Description_2"] == "yes" and v["AI fallback"] == "off"
    assert v["Restocking column"] == "off" and v["Restockable categories (rule)"] == "off"
    assert v["Bulk routed rows"] == 0 and v["Overrides blocked bulk"] == 0
    assert v["Program→SP mapping"] == "off" and v["Programmes mapped"] == 0
    assert v["Overrides applied"] == "yes"
    assert v["Tools sheet"] == "Catalog" and v["PPE sheet"] == "\u2014"
    assert v["Rows after dedup"] == 8 and v["Validation issues"] == "none"


def test_run_metadata_reflects_the_optional_features():
    rows = ef.run_metadata_rows(_inputs(
        op_mode="Capped", max_carousels_cap=4.0, optional_thresholds_active=True,
        per_class_thresholds={"mill": 2.0, "drill": 1.5}, split_coverage=True,
        coverage_days_special=35.0, enable_rebalancer=False, col_regrind="RG",
        col_systemtyp="ST", use_description_2=False, use_ai=True, col_restock="R",
        restock_categories=["drill", "tap"], restock_slots_total=7.0,
        vend_stats={"routed_rows": 3, "removed_spirals": 2, "removed_carousel_slots": 5,
                    "overridden_bulk_candidates": 1},
        program_mapping_active=True, program_to_sp_map={"A": 1, "B": 2},
        override_stats={"rows_touched": 4, "unmatched_overrides": [1], "invalid_overrides": [1, 2]},
        listings_in_data=["PPE", "Tools"], sheet_ppe="PPE sheet",
        validation_issues=["x", "y"],
    ), work=pd.DataFrame(), bucket_plans=[])
    v = _as_dict(rows)
    assert v["Max carousels (capped mode)"] == 4
    assert v["Per-class thresholds"] == "drill=1.5, mill=2"
    assert v["Coverage special (days)"] == 35
    assert v["Consolidate underused cabinets"] == "off"
    assert v["Regrind handling (Helix +1 spiral)"] == "on"
    assert v["System type override (Lagersystem)"] == "on"
    assert v["Use Description_2"] == "no" and v["AI fallback"] == "on"
    assert v["Restocking column"] == "R"
    assert v["Restockable categories (rule)"] == "drill, tap"
    assert v["Restock buffer compartments"] == 7
    assert (v["Bulk routed rows"], v["Bulk removed spirals"], v["Bulk removed slots"],
            v["Overrides blocked bulk"]) == (3, 2, 5, 1)
    assert v["Program→SP mapping"] == "active" and v["Programmes mapped"] == 2
    assert (v["Overrides rows touched"], v["Overrides stale"], v["Overrides invalid"]) == (4, 1, 2)
    assert v["Listings loaded"] == "PPE, Tools"
    assert v["Validation issues"] == "x; y"


def test_run_metadata_override_states():
    assert _as_dict(ef.run_metadata_rows(_inputs(apply_overrides_ui=False),
                    work=pd.DataFrame(), bucket_plans=[]))["Overrides applied"] == "no"
    assert _as_dict(ef.run_metadata_rows(_inputs(override_store_unavailable=True),
                    work=pd.DataFrame(), bucket_plans=[]))["Overrides applied"] == \
        "NO - override database unreadable"


def test_run_metadata_adds_the_special_rows_when_mapped():
    work = pd.DataFrame({"StdSpecial": ["Special", "Standard", "Special"],
                         "SystemCategory_Reason": [SPECIAL_KTC_REASON, "", ""]})
    rows = ef.run_metadata_rows(_inputs(col_stdspecial="SS", special_ktc=True),
                                work=work, bucket_plans=[])
    assert rows[-3:] == [
        {"Key": "Set special tools as KTC", "Value": "on"},
        {"Key": "Special rows (marked Special)", "Value": 2},
        {"Key": "Special forced to KTC", "Value": 1},
    ]
    plain = ef.run_metadata_rows(_inputs(col_stdspecial=None), work=work, bucket_plans=[])
    assert [r["Key"] for r in plain] == _META_KEYS


def test_run_metadata_adds_the_fixed_rows_in_fixed_mode(monkeypatch):
    monkeypatch.setattr(ef, "fixed_run_meta_rows", lambda plans: [{"Key": "F", "Value": len(plans)}])
    rows = ef.run_metadata_rows(_inputs(op_mode=FIXED_MODE), work=pd.DataFrame(),
                                bucket_plans=[("All", {})])
    assert rows[-1] == {"Key": "F", "Value": 1}


def test_the_inputs_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _inputs().build = "x"  # type: ignore[misc]
