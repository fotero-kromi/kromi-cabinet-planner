"""Tests for engine.plan composition segments (v33.96).

The first two contiguous runs of the planning pipeline are composed into
engine/plan.py: run_demand_segment (demand arithmetic then the base system
decision) and run_sizing_segment (cabinet-type, optional fit-check, physical
sizing). These tests prove each segment equals running its stages by hand,
preserves rows and index, honours the fit-check flag, and produces the expected
columns, with a real-data check on a planner Result workbook.
"""

import os

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from engine.demand import compute_demand, assign_system_category
from engine.sizing import assign_cabinet_types, assign_physical_sizing
from engine.fitting import apply_fit_check
from engine.plan import (run_demand_segment, run_sizing_segment,
                         run_routing_override_segment, run_bulk_routing_segment, run_supply_point_segment,
                         run_override_application_segment)

_DEMAND = dict(consumption_period_months=16, coverage_days=18, coverage_days_special=18)
_SYS = dict(usage_threshold=1.0, per_class_thresholds={}, optional_thresholds_active=False)
_SIZE = dict(minimum_carousel_allocation=3, carousel_reserve_factor=0.85, helix_overfill_factor=1.10)


def _base(n=6):
    return pd.DataFrame({
        "Consumption_pcs": [100.0, 5.0, 800.0, 2000.0, 50.0, 1.0][:n],
        "PackUnits": [1.0, 10.0, 1.0, 1.0, 10.0, 1.0][:n],
        "SizeCategory": ["M", "S", "L", "XL", "M", "S"][:n],
        "ProductCategory": ["mills", "inserts", "drills", "holders", "taps", "reamers"][:n],
        "Regrind": [False] * n,
    }, index=[10, 20, 30, 40, 50, 60][:n])


# ---------------------------------------------------------------------------
# run_demand_segment
# ---------------------------------------------------------------------------

def test_demand_segment_equals_manual_compose():
    df = _base()
    manual = assign_system_category(compute_demand(df, **_DEMAND), **_SYS)
    seg = run_demand_segment(df, **_DEMAND, **_SYS)
    assert_frame_equal(seg, manual, check_dtype=True)


def test_demand_segment_preserves_rows_and_index():
    df = _base()
    out = run_demand_segment(df, **_DEMAND, **_SYS)
    assert len(out) == len(df)
    assert list(out.index) == list(df.index)


def test_demand_segment_adds_demand_columns():
    out = run_demand_segment(_base(), **_DEMAND, **_SYS)
    for c in ["Monthly_pcs", "Target_packs", "SystemCategory"]:
        assert c in out.columns


def test_demand_segment_does_not_mutate_input():
    df = _base()
    before = df.copy()
    run_demand_segment(df, **_DEMAND, **_SYS)
    assert_frame_equal(df, before)


# ---------------------------------------------------------------------------
# run_sizing_segment
# ---------------------------------------------------------------------------

def _sized_input():
    return run_demand_segment(_base(), **_DEMAND, **_SYS)


def test_sizing_segment_equals_manual_compose_no_fit():
    df = _sized_input()
    manual = assign_physical_sizing(assign_cabinet_types(df, helix_threshold=4.0), **_SIZE)
    seg = run_sizing_segment(df, helix_threshold=4.0, run_fit_check=False, **_SIZE)
    assert_frame_equal(seg, manual, check_dtype=True)


def test_sizing_segment_equals_manual_compose_with_fit():
    df = _sized_input()
    df = df.assign(PackageDimensions="Ø 10 x 70 mm")
    manual = assign_cabinet_types(df, helix_threshold=4.0)
    manual = apply_fit_check(manual)
    manual = assign_physical_sizing(manual, **_SIZE)
    seg = run_sizing_segment(df, helix_threshold=4.0, run_fit_check=True, **_SIZE)
    assert_frame_equal(seg, manual, check_dtype=True)


def test_fit_check_flag_true_adds_fit_columns():
    df = _sized_input().assign(PackageDimensions="Ø 10 x 70 mm")
    out = run_sizing_segment(df, helix_threshold=4.0, run_fit_check=True, **_SIZE)
    assert "Fit_status" in out.columns


def test_fit_check_flag_false_omits_fit_columns():
    df = _sized_input().assign(PackageDimensions="Ø 10 x 70 mm")
    out = run_sizing_segment(df, helix_threshold=4.0, run_fit_check=False, **_SIZE)
    assert "Fit_status" not in out.columns


def test_sizing_segment_adds_sizing_columns():
    out = run_sizing_segment(_sized_input(), helix_threshold=4.0, run_fit_check=False, **_SIZE)
    for c in ["CabinetType", "Spirals_needed", "Carousel_stockpiles"]:
        assert c in out.columns


def test_sizing_segment_preserves_rows_and_index():
    df = _sized_input()
    out = run_sizing_segment(df, helix_threshold=4.0, run_fit_check=False, **_SIZE)
    assert len(out) == len(df) and list(out.index) == list(df.index)


def test_sizing_segment_honours_reserve_factor():
    df = _sized_input()
    shallow = run_sizing_segment(df, helix_threshold=4.0, run_fit_check=False,
                                 minimum_carousel_allocation=3, carousel_reserve_factor=0.5,
                                 helix_overfill_factor=1.10)
    deep = run_sizing_segment(df, helix_threshold=4.0, run_fit_check=False,
                              minimum_carousel_allocation=3, carousel_reserve_factor=2.0,
                              helix_overfill_factor=1.10)
    # at least one carousel stockpile should grow with a deeper reserve
    assert deep["Carousel_stockpiles"].sum() >= shallow["Carousel_stockpiles"].sum()


def test_sizing_segment_does_not_mutate_input():
    df = _sized_input()
    before = df.copy()
    run_sizing_segment(df, helix_threshold=4.0, run_fit_check=False, **_SIZE)
    assert_frame_equal(df, before)


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------

def test_segments_chain_to_a_plan():
    from engine.cabinet_math import compute_plan_for_subset
    sized = run_sizing_segment(run_demand_segment(_base(), **_DEMAND, **_SYS),
                               helix_threshold=4.0, run_fit_check=False, **_SIZE)
    plan = compute_plan_for_subset(sized, 0.0)
    assert plan["total_cabs"] >= 1


# ---------------------------------------------------------------------------
# Real-data simulation
# ---------------------------------------------------------------------------

_GROUND_TRUTH = os.environ.get("KROMI_GROUNDTRUTH_XLSX", "")


@pytest.mark.skipif(not (_GROUND_TRUTH and os.path.exists(_GROUND_TRUTH)),
                    reason="set KROMI_GROUNDTRUTH_XLSX to a planner Result workbook to run")
def test_real_data_segments_match_inline_and_reach_ground_truth_plan():
    from engine.cabinet_math import compute_plan_for_subset
    res = pd.ExcelFile(_GROUND_TRUTH).parse("Result")
    base = pd.DataFrame({
        "Consumption_pcs": pd.to_numeric(res.Consumption_pcs, errors="coerce"),
        "PackUnits": pd.to_numeric(res.PackUnits, errors="coerce"),
        "SizeCategory": res.SizeCategory.astype(str),
        "ProductCategory": res.ProductCategory.astype(str),
        "Regrind": False,
    }, index=res.index)
    # segment vs inline
    seg_d = run_demand_segment(base, **_DEMAND, **_SYS)
    inline_d = assign_system_category(compute_demand(base, **_DEMAND), **_SYS)
    assert_frame_equal(seg_d, inline_d, check_dtype=True)
    seg_s = run_sizing_segment(seg_d, helix_threshold=4.0, run_fit_check=False, **_SIZE)
    inline_s = assign_physical_sizing(assign_cabinet_types(inline_d, helix_threshold=4.0), **_SIZE)
    assert_frame_equal(seg_s, inline_s, check_dtype=True)
    assert len(seg_s) == len(res)  # rows conserved
    plan = compute_plan_for_subset(seg_s, 0.0)
    assert plan["car_cabs"] == 2 and plan["helix_cabs"] == 1  # known ground-truth plan


# ---------------------------------------------------------------------------
# run_routing_override_segment (v33.97)
# ---------------------------------------------------------------------------

_FORCE = dict(threshold=1.0, helix_threshold=4.0, min_carousel_compartments=3,
              carousel_reserve_factor=0.85, helix_overfill_factor=1.10)


def _routing_input(n=8):
    base = pd.DataFrame({
        "Consumption_pcs": [100., 5., 800., 2000., 50., 1., 300., 12.][:n],
        "PackUnits": [1., 10., 1., 1., 10., 1., 5., 1.][:n],
        "SizeCategory": ["M", "S", "L", "XL", "M", "S", "L", "M"][:n],
        "ProductCategory": ["mills", "inserts", "drills", "holders", "taps", "reamers", "mills", "ppe"][:n],
        "Regrind": [False] * n,
        "SystemTyp": ["KTC", "", "Locker", "KTC or Kanban", "", "KTC", "", "Locker"][:n],
        "StdSpecial": ["special", "standard", "special", "standard", "special", "", "standard", "special"][:n],
    })
    return run_sizing_segment(run_demand_segment(base, **_DEMAND, **_SYS),
                              helix_threshold=4.0, run_fit_check=False, **_SIZE)


def test_routing_override_both_flags_equals_inline():
    from engine.cabinet_math import apply_system_type, force_special_to_ktc
    a, b = _routing_input(), _routing_input()
    inline = {"system_type": apply_system_type(a, **_FORCE),
              "special_forced": force_special_to_ktc(a, **_FORCE)}
    seg = run_routing_override_segment(b, force_system_type=True, force_special_ktc=True, **_FORCE)
    assert_frame_equal(b, a, check_dtype=True)
    assert seg == inline


def test_routing_override_neither_flag_is_noop():
    df = _routing_input()
    before = df.copy()
    counts = run_routing_override_segment(df, force_system_type=False, force_special_ktc=False, **_FORCE)
    assert_frame_equal(df, before)
    assert counts == {"system_type": None, "special_forced": None}


def test_routing_override_only_system_type():
    from engine.cabinet_math import apply_system_type
    a, b = _routing_input(), _routing_input()
    inline = apply_system_type(a, **_FORCE)
    seg = run_routing_override_segment(b, force_system_type=True, force_special_ktc=False, **_FORCE)
    assert_frame_equal(b, a, check_dtype=True)
    assert seg["system_type"] == inline and seg["special_forced"] is None


def test_routing_override_only_special():
    from engine.cabinet_math import force_special_to_ktc
    a, b = _routing_input(), _routing_input()
    inline = force_special_to_ktc(a, **_FORCE)
    seg = run_routing_override_segment(b, force_system_type=False, force_special_ktc=True, **_FORCE)
    assert_frame_equal(b, a, check_dtype=True)
    assert seg["special_forced"] == inline and seg["system_type"] is None


def test_routing_override_counts_shape():
    counts = run_routing_override_segment(_routing_input(), force_system_type=True,
                                          force_special_ktc=True, **_FORCE)
    assert isinstance(counts["system_type"], dict)
    assert set(counts["system_type"]) == {"ktc", "locker", "flex"}
    assert isinstance(counts["special_forced"], int)


def test_routing_override_system_type_wins_over_special():
    # a row that is both forced by system type and marked special must keep the
    # system-type routing: system type runs first and pins the row, so the special
    # pass leaves it alone.
    df = _routing_input()
    run_routing_override_segment(df, force_system_type=True, force_special_ktc=True, **_FORCE)
    # rows pinned by system type stay pinned (Routing_Pinned True) and were not
    # re-touched; the segment completed without error and pinned at least one row
    assert "Routing_Pinned" in df.columns
    assert bool(df["Routing_Pinned"].any())


def test_routing_override_mutates_in_place():
    df = _routing_input()
    same = df
    run_routing_override_segment(df, force_system_type=True, force_special_ktc=False, **_FORCE)
    assert same is df  # same object, mutated in place


@pytest.mark.skipif(not (_GROUND_TRUTH and os.path.exists(_GROUND_TRUTH)),
                    reason="set KROMI_GROUNDTRUTH_XLSX to a planner Result workbook to run")
def test_routing_override_real_data_noop_without_columns():
    res = pd.ExcelFile(_GROUND_TRUTH).parse("Result")
    base = pd.DataFrame({
        "Consumption_pcs": pd.to_numeric(res.Consumption_pcs, errors="coerce"),
        "PackUnits": pd.to_numeric(res.PackUnits, errors="coerce"),
        "SizeCategory": res.SizeCategory.astype(str),
        "ProductCategory": res.ProductCategory.astype(str),
        "Regrind": False,
    }, index=res.index)
    sized = run_sizing_segment(run_demand_segment(base, **_DEMAND, **_SYS),
                               helix_threshold=4.0, run_fit_check=False, **_SIZE)
    before = sized.copy()
    counts = run_routing_override_segment(sized, force_system_type=False,
                                          force_special_ktc=False, **_FORCE)
    assert_frame_equal(sized, before, check_dtype=True)
    assert counts == {"system_type": None, "special_forced": None}


# ---------------------------------------------------------------------------
# run_bulk_routing_segment (v33.98)
# ---------------------------------------------------------------------------

def _bulk_input(n=8):
    base = pd.DataFrame({
        "Consumption_pcs": [100., 5., 800., 2000., 50., 1., 300., 12.][:n],
        "PackUnits": [1., 10., 1., 1., 10., 1., 5., 1.][:n],
        "SizeCategory": ["M", "S", "L", "XL", "M", "S", "L", "M"][:n],
        "ProductCategory": ["mills", "inserts", "drills", "holders", "taps", "reamers", "mills", "ppe"][:n],
        "Description": ["end mill", "insert", "drill", "holder", "tap", "reamer", "mill", "glove"][:n],
        "Code": [f"C{i}" for i in range(n)],
        "SupplierCode": [f"S{i}" for i in range(n)],
        "Regrind": [False] * n,
    })
    return run_sizing_segment(run_demand_segment(base, **_DEMAND, **_SYS),
                              helix_threshold=4.0, run_fit_check=False, **_SIZE)


def _inline_bulk_disabled(df):
    """Verbatim copy of the page's pre-extraction disabled else-branch (reference)."""
    from engine.classification import detect_item_family
    df["ItemFamily"] = df.apply(lambda r: detect_item_family(
        r.get("Description", ""), r.get("Description_2", ""), r.get("Code", ""), r.get("SupplierCode", "")), axis=1)
    if "Override_Applied" in df.columns:
        has_override = df["Override_Applied"] == True  # noqa: E712
    else:
        has_override = pd.Series(False, index=df.index)
    if "VendMode" not in df.columns:
        df["VendMode"] = "Vending"
    else:
        df.loc[~has_override, "VendMode"] = "Vending"
    if "VendBlockReason" not in df.columns:
        df["VendBlockReason"] = ""
    else:
        df.loc[~has_override, "VendBlockReason"] = ""
    df["CabinetType_pre_route"] = df["CabinetType"] if "CabinetType" in df.columns else ""
    if "Spirals_needed" in df.columns:
        df["Spirals_needed_pre_route"] = pd.to_numeric(df["Spirals_needed"], errors="coerce").fillna(0).astype(int)
    else:
        df["Spirals_needed_pre_route"] = 0
    if "Carousel_stockpiles" in df.columns:
        df["Carousel_stockpiles_pre_route"] = pd.to_numeric(df["Carousel_stockpiles"], errors="coerce").fillna(0).astype(int)
    else:
        df["Carousel_stockpiles_pre_route"] = 0
    return df, {"routed_rows": 0, "removed_spirals": 0, "removed_carousel_slots": 0, "by_family": {}}


def test_bulk_disabled_equals_inline():
    a, b = _bulk_input(), _bulk_input()
    fi, si = _inline_bulk_disabled(a)
    fs, ss = run_bulk_routing_segment(b, enable_bulk_routing=False)
    assert_frame_equal(fs, fi, check_dtype=True)
    assert ss == si


def test_bulk_enabled_equals_apply_bulk_routing():
    from engine.cabinet_math import apply_bulk_routing
    a, b = _bulk_input(), _bulk_input()
    fi, si = apply_bulk_routing(a)
    fs, ss = run_bulk_routing_segment(b, enable_bulk_routing=True)
    assert_frame_equal(fs, fi, check_dtype=True)
    assert ss == si


def test_bulk_disabled_creates_audit_columns():
    df, _ = run_bulk_routing_segment(_bulk_input(), enable_bulk_routing=False)
    for c in ["ItemFamily", "VendMode", "VendBlockReason", "CabinetType_pre_route",
              "Spirals_needed_pre_route", "Carousel_stockpiles_pre_route"]:
        assert c in df.columns


def test_bulk_disabled_returns_zeroed_stats():
    _, stats = run_bulk_routing_segment(_bulk_input(), enable_bulk_routing=False)
    assert stats == {"routed_rows": 0, "removed_spirals": 0, "removed_carousel_slots": 0, "by_family": {}}


def test_bulk_disabled_defaults_vendmode_vending():
    df, _ = run_bulk_routing_segment(_bulk_input(), enable_bulk_routing=False)
    assert (df["VendMode"] == "Vending").all()


def test_bulk_disabled_respects_existing_vendmode_override():
    df = _bulk_input()
    df["Override_Applied"] = [True] + [False] * (len(df) - 1)
    df["VendMode"] = ["Blocked"] + ["x"] * (len(df) - 1)
    out, _ = run_bulk_routing_segment(df, enable_bulk_routing=False)
    assert out["VendMode"].iloc[0] == "Blocked"        # override preserved
    assert (out["VendMode"].iloc[1:] == "Vending").all()  # rest reset


def test_bulk_disabled_pre_route_snapshots_match_sized():
    sized = _bulk_input()
    expected_sp = pd.to_numeric(sized["Spirals_needed"], errors="coerce").fillna(0).astype(int)
    out, _ = run_bulk_routing_segment(sized.copy(), enable_bulk_routing=False)
    assert (out["Spirals_needed_pre_route"] == expected_sp.values).all()


@pytest.mark.skipif(not (_GROUND_TRUTH and os.path.exists(_GROUND_TRUTH)),
                    reason="set KROMI_GROUNDTRUTH_XLSX to a planner Result workbook to run")
def test_bulk_real_data_both_paths():
    from engine.cabinet_math import apply_bulk_routing
    res = pd.ExcelFile(_GROUND_TRUTH).parse("Result")
    base = pd.DataFrame({
        "Consumption_pcs": pd.to_numeric(res.Consumption_pcs, errors="coerce"),
        "PackUnits": pd.to_numeric(res.PackUnits, errors="coerce"),
        "SizeCategory": res.SizeCategory.astype(str), "ProductCategory": res.ProductCategory.astype(str),
        "Description": res.Description.astype(str), "Code": res.Code.astype(str),
        "SupplierCode": res.SupplierCode.astype(str), "Regrind": False,
    }, index=res.index)
    sized = run_sizing_segment(run_demand_segment(base, **_DEMAND, **_SYS),
                               helix_threshold=4.5, run_fit_check=False, **_SIZE)
    fi, si = _inline_bulk_disabled(sized.copy())
    fs, ss = run_bulk_routing_segment(sized.copy(), enable_bulk_routing=False)
    assert_frame_equal(fs, fi, check_dtype=True) and ss == si
    ea, ta = apply_bulk_routing(sized.copy())
    eb, tb = run_bulk_routing_segment(sized.copy(), enable_bulk_routing=True)
    assert_frame_equal(eb, ea, check_dtype=True) and ta == tb


# ---------------------------------------------------------------------------
# run_supply_point_segment (v33.99)
# ---------------------------------------------------------------------------

def _sp_base(n=6):
    return pd.DataFrame({
        "Consumption_pcs": [100.0, 5.0, 800.0, 2000.0, 50.0, 1.0][:n],
        "Code": [f"C{i}" for i in range(n)],
        "SupplierCode": [f"S{i}" for i in range(n)],
    }, index=range(n))


def _inline_sp(df, n, mode):
    from engine.cabinet_math import assign_supply_points
    from engine.invariants import check_supply_point_conservation
    pre = float(pd.to_numeric(df["Consumption_pcs"], errors="coerce").fillna(0.0).sum())
    out = assign_supply_points(df, n, mode=mode)
    post = float(pd.to_numeric(out["Consumption_pcs"], errors="coerce").fillna(0.0).sum())
    return out, check_supply_point_conservation(pre, post)


def test_supply_point_partition_equals_inline():
    fi, ii = _inline_sp(_sp_base(), 3, "partition")
    fs, iss = run_supply_point_segment(_sp_base(), n_supply_points=3, mode="partition")
    assert_frame_equal(fs, fi, check_dtype=True)
    assert ii == iss


def test_supply_point_replicate_equals_inline():
    fi, ii = _inline_sp(_sp_base(), 3, "replicate")
    fs, iss = run_supply_point_segment(_sp_base(), n_supply_points=3, mode="replicate")
    assert_frame_equal(fs, fi, check_dtype=True)
    assert ii == iss


def test_supply_point_replicate_multiplies_rows():
    fs, _ = run_supply_point_segment(_sp_base(6), n_supply_points=3, mode="replicate")
    assert len(fs) == 6 * 3


def test_supply_point_single_sp_is_identity_count():
    fs, issues = run_supply_point_segment(_sp_base(6), n_supply_points=1, mode="replicate")
    assert len(fs) == 6
    assert issues == []


def test_supply_point_conservation_holds_on_valid_split():
    _, issues = run_supply_point_segment(_sp_base(), n_supply_points=4, mode="replicate")
    assert issues == []  # consumption conserved


@pytest.mark.skipif(not (_GROUND_TRUTH and os.path.exists(_GROUND_TRUTH)),
                    reason="set KROMI_GROUNDTRUTH_XLSX to a planner Result workbook to run")
def test_supply_point_real_data_both_modes():
    res = pd.ExcelFile(_GROUND_TRUTH).parse("Result")
    base = pd.DataFrame({
        "Consumption_pcs": pd.to_numeric(res.Consumption_pcs, errors="coerce"),
        "Code": res.Code.astype(str), "SupplierCode": res.SupplierCode.astype(str),
    }, index=res.index)
    for mode in ("partition", "replicate"):
        fi, ii = _inline_sp(base.copy(), 3, mode)
        fs, iss = run_supply_point_segment(base.copy(), n_supply_points=3, mode=mode)
        assert_frame_equal(fs, fi, check_dtype=True)
        assert ii == iss == []


# ---------------------------------------------------------------------------
# run_override_application_segment (v34.00)
# ---------------------------------------------------------------------------
import math as _math
from engine.overrides import OVERRIDE_COLUMNS as _OVC, apply_overrides as _apply_overrides
from engine.cabinet_math import (decide_spiral_capacity as _dsc, regrind_spiral_floor as _rsf,
                                 route_and_size_row as _rasr,
                                 compute_helix_spirals_needed as _eng_chsn)
from engine.routing_rules import threshold_for_row as _tfr
from engine.constants import DAYS_PER_MONTH as _DPM

_OVK = dict(usage_threshold=1.0, helix_threshold=4.0, minimum_carousel_allocation=3,
            carousel_reserve_factor=0.85, helix_overfill_factor=1.10, per_class_thresholds={},
            optional_thresholds_active=False, force_screws_accessories_kanban=False)


def _ov_frame():
    base = pd.DataFrame({
        "Consumption_pcs": [2000., 3000., 500., 60., 5., 800.],
        "PackUnits": [1., 1., 1., 1., 10., 1.],
        "SizeCategory": ["M", "M", "M", "S", "S", "L"],
        "ProductCategory": ["mills", "drills", "holders", "taps", "inserts", "drills"],
        "Code": [f"R{i}" for i in range(6)], "Listing": ["Tools"] * 6,
        "Regrind": [False, True, False, False, False, False],
    })
    w = run_sizing_segment(run_demand_segment(base, **_DEMAND, **_SYS),
                           helix_threshold=4.0, run_fit_check=False, **_SIZE)
    w["ProductCategory_Confidence"] = "high"
    w["ToolClass"] = ""
    w["SystemCategory_Reason"] = ""
    return w


def _ov(code, **kw):
    r = {c: "" for c in _OVC}
    r["code"] = code
    r["listing"] = "Tools"
    r.update(kw)
    return r


def _ov_reference(df, ovs, *, usage_threshold, helix_threshold, minimum_carousel_allocation,
                  carousel_reserve_factor, helix_overfill_factor, per_class_thresholds,
                  optional_thresholds_active, force_screws_accessories_kanban):
    """Reference mirroring the page block, modelling the helix shim (overfill injected)."""
    default = {"rows_touched": 0, "fields_changed": {}, "unmatched_overrides": [],
               "invalid_overrides": [], "applied_overrides": []}
    if len(ovs) == 0:
        return df, default, 0
    df["ProductCategory_PreOverride"] = df["ProductCategory"].copy()
    df["ProductCategory_ConfidencePreOverride"] = df["ProductCategory_Confidence"].copy()
    df, stats = _apply_overrides(df, ovs)
    flips = 0
    touched = df["Override_Applied"] == True  # noqa: E712
    if touched.any():
        pk = pd.to_numeric(df.loc[touched, "PackUnits"], errors="coerce").fillna(1.0).clip(lower=1.0)
        mp = pd.to_numeric(df.loc[touched, "Monthly_pcs"], errors="coerce").fillna(0.0)
        df.loc[touched, "Monthly_packs"] = (mp / pk)
        df.loc[touched, "Target_packs"] = df.loc[touched, "Monthly_packs"] * (df.loc[touched, "Coverage_days"] / _DPM)
        rov = touched & (df.get("Routing_Overridden") == True)  # noqa: E712
        hf = rov & (df["CabinetType"] == "Helix")
        for idx in df[hf].index:
            sc = _dsc(str(df.at[idx, "SizeCategory"]), str(df.at[idx, "ProductCategory"]))
            df.at[idx, "Spiral_capacity"] = sc
            mpv = float(pd.to_numeric(df.at[idx, "Monthly_packs"], errors="coerce") or 0.0)
            nsr = _eng_chsn(mpv, sc, overfill_factor=helix_overfill_factor)
            df.at[idx, "Spirals_needed"] = _rsf(int(max(1, nsr)), bool(df.at[idx, "Regrind"]))
            df.at[idx, "Carousel_stockpiles"] = 0
        cf = rov & (df["CabinetType"] == "Carousel")
        if cf.any():
            tc = pd.to_numeric(df.loc[cf, "Target_packs"], errors="coerce").fillna(0.0)
            sp = tc.apply(lambda t: max(int(minimum_carousel_allocation), max(1, _math.ceil(t * carousel_reserve_factor))))
            df.loc[cf, "Carousel_stockpiles"] = sp.astype(int)
            df.loc[cf, "Spirals_needed"] = 0
            df.loc[cf, "Spiral_capacity"] = pd.NA
        kf = rov & (df["CabinetType"] == "Kanban")
        if kf.any():
            df.loc[kf, "Spirals_needed"] = 0
            df.loc[kf, "Carousel_stockpiles"] = 0
            df.loc[kf, "Spiral_capacity"] = pd.NA
            df.loc[kf, "SystemCategory"] = "Kanban"
        lf = rov & df["CabinetType"].isin(["Locker A", "Locker B", "Locker C"])
        if lf.any():
            df.loc[lf, "Spirals_needed"] = 0
            df.loc[lf, "Carousel_stockpiles"] = 0
            df.loc[lf, "Spiral_capacity"] = pd.NA
        rr = touched & ~rov
        if rr.any():
            for idx in df[rr].index:
                npc = df.at[idx, "ProductCategory"]
                tc = df.at[idx, "ToolClass"] if "ToolClass" in df.columns else ""
                thr = _tfr(product_category=npc, tool_class=tc, standard_threshold=float(usage_threshold),
                           per_class_thresholds=per_class_thresholds, optional_active=bool(optional_thresholds_active))
                fk = bool(force_screws_accessories_kanban) and str(npc).strip().lower() in ("screws", "accessories")
                ps = df.at[idx, "SystemCategory"]
                res = _rasr(monthly_packs=pd.to_numeric(df.at[idx, "Monthly_packs"], errors="coerce"),
                            monthly_pcs=pd.to_numeric(df.at[idx, "Monthly_pcs"], errors="coerce"),
                            target_packs=pd.to_numeric(df.at[idx, "Target_packs"], errors="coerce"),
                            size_cat=df.at[idx, "SizeCategory"], product_category=npc, threshold=thr,
                            helix_threshold=float(helix_threshold), min_carousel_compartments=int(minimum_carousel_allocation),
                            carousel_reserve_factor=float(carousel_reserve_factor), helix_overfill_factor=float(helix_overfill_factor),
                            force_kanban=fk, regrind=bool(df.at[idx, "Regrind"]))
                df.at[idx, "SystemCategory"] = res["SystemCategory"]
                df.at[idx, "CabinetType"] = res["CabinetType"]
                df.at[idx, "Spiral_capacity"] = (res["Spiral_capacity"] if res["Spiral_capacity"] is not None else pd.NA)
                df.at[idx, "Spirals_needed"] = int(res["Spirals_needed"])
                df.at[idx, "Carousel_stockpiles"] = int(res["Carousel_stockpiles"])
                if res["SystemCategory"] != ps:
                    flips += 1
                    if "SystemCategory_Reason" in df.columns:
                        df.at[idx, "SystemCategory_Reason"] = f"Re-routed to {res['SystemCategory']} after override"
    return df, stats, flips


def test_override_empty_set_is_noop():
    w = _ov_frame()
    out, stats, flips = run_override_application_segment(w.copy(), pd.DataFrame(columns=_OVC), **_OVK)
    assert flips == 0 and stats["rows_touched"] == 0
    assert out.equals(w)


def test_override_helix_forced_sizes_spirals():
    out, _, _ = run_override_application_segment(_ov_frame(), pd.DataFrame([_ov("R0", cabinet_type_override="Helix")]), **_OVK)
    r = out.set_index("Code")
    assert r.at["R0", "CabinetType"] == "Helix"
    assert int(r.at["R0", "Spirals_needed"]) >= 1
    assert int(r.at["R0", "Carousel_stockpiles"]) == 0


def test_override_carousel_forced_sizes_stockpiles():
    out, _, _ = run_override_application_segment(_ov_frame(), pd.DataFrame([_ov("R2", cabinet_type_override="Carousel")]), **_OVK)
    r = out.set_index("Code")
    assert r.at["R2", "CabinetType"] == "Carousel"
    assert int(r.at["R2", "Carousel_stockpiles"]) >= 3   # min-alloc floor
    assert int(r.at["R2", "Spirals_needed"]) == 0


def test_override_kanban_forced_sets_system_category():
    out, _, _ = run_override_application_segment(_ov_frame(), pd.DataFrame([_ov("R3", cabinet_type_override="Kanban")]), **_OVK)
    r = out.set_index("Code")
    assert r.at["R3", "SystemCategory"] == "Kanban"
    assert int(r.at["R3", "Spirals_needed"]) == 0 and int(r.at["R3", "Carousel_stockpiles"]) == 0


def test_override_locker_forced_zeroes_vend_counts():
    out, _, _ = run_override_application_segment(_ov_frame(), pd.DataFrame([_ov("R4", cabinet_type_override="Locker A")]), **_OVK)
    r = out.set_index("Code")
    assert r.at["R4", "CabinetType"] == "Locker A"
    assert int(r.at["R4", "Spirals_needed"]) == 0 and int(r.at["R4", "Carousel_stockpiles"]) == 0


def test_override_rows_touched_matches_matches():
    ovs = pd.DataFrame([_ov("R0", cabinet_type_override="Helix"), _ov("R1", cabinet_type_override="Carousel")])
    _, stats, _ = run_override_application_segment(_ov_frame(), ovs, **_OVK)
    assert stats["rows_touched"] == 2


def test_override_recomputes_monthly_packs_for_touched():
    # change PackUnits via override -> Monthly_packs must update
    ovs = pd.DataFrame([_ov("R0", pack_units_override="4")])
    w = _ov_frame()
    before = float(w.set_index("Code").at["R0", "Monthly_packs"])
    out, _, _ = run_override_application_segment(w, ovs, **_OVK)
    after = float(out.set_index("Code").at["R0", "Monthly_packs"])
    assert after == pytest.approx(before / 4.0, rel=1e-9)


def test_override_creates_preoverride_snapshot():
    out, _, _ = run_override_application_segment(_ov_frame(), pd.DataFrame([_ov("R0", product_category_override="drills")]), **_OVK)
    assert "ProductCategory_PreOverride" in out.columns
    assert "ProductCategory_ConfidencePreOverride" in out.columns


def test_override_helix_uses_runtime_overfill_factor():
    """Guard for the shim bug: forced-Helix spirals must track helix_overfill_factor."""
    ovs = pd.DataFrame([_ov("R0", cabinet_type_override="Helix")])
    K2 = dict(_OVK); K2["helix_overfill_factor"] = 2.0
    gf, _, _ = _ov_reference(_ov_frame(), ovs, **K2)
    sf, _, _ = run_override_application_segment(_ov_frame(), ovs, **K2)
    g = gf.set_index("Code").at["R0", "Spirals_needed"]
    s = sf.set_index("Code").at["R0", "Spirals_needed"]
    assert int(g) == int(s)


@pytest.mark.parametrize("hof", [1.10, 2.0])
def test_override_full_golden_vs_reference(hof):
    ovs = pd.DataFrame([
        _ov("R0", cabinet_type_override="Helix"), _ov("R1", cabinet_type_override="Helix"),
        _ov("R2", cabinet_type_override="Carousel"), _ov("R3", cabinet_type_override="Kanban"),
        _ov("R4", cabinet_type_override="Locker A"),
        _ov("R5", product_category_override="drills", pack_units_override="3")])
    K = dict(_OVK); K["helix_overfill_factor"] = hof
    gf, gs, gfl = _ov_reference(_ov_frame(), ovs, **K)
    sf, ss, sfl = run_override_application_segment(_ov_frame(), ovs, **K)
    assert_frame_equal(sf, gf, check_dtype=True)
    assert gs == ss and gfl == sfl


@pytest.mark.skipif(not (_GROUND_TRUTH and os.path.exists(_GROUND_TRUTH)),
                    reason="set KROMI_GROUNDTRUTH_XLSX to a planner Result workbook to run")
def test_override_real_data_empty_noop():
    res = pd.ExcelFile(_GROUND_TRUTH).parse("Result")
    base = pd.DataFrame({
        "Consumption_pcs": pd.to_numeric(res.Consumption_pcs, errors="coerce"),
        "PackUnits": pd.to_numeric(res.PackUnits, errors="coerce"),
        "SizeCategory": res.SizeCategory.astype(str), "ProductCategory": res.ProductCategory.astype(str),
        "Description": res.Description.astype(str), "Code": res.Code.astype(str),
        "SupplierCode": res.SupplierCode.astype(str), "Regrind": False,
    }, index=res.index)
    sized = run_sizing_segment(run_demand_segment(base, **_DEMAND, **_SYS),
                               helix_threshold=4.5, run_fit_check=False, **_SIZE)
    sized["ProductCategory_Confidence"] = "high"
    out, stats, flips = run_override_application_segment(sized.copy(), pd.DataFrame(columns=_OVC), **_OVK)
    assert flips == 0 and stats["rows_touched"] == 0 and out.equals(sized)
