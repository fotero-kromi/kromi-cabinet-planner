"""Tests for engine/demand.py (v33.84).

Demand arithmetic and the base KTC/Kanban routing, extracted from the planner
page. The arithmetic is the most correctness-sensitive part of the app, so it is
pinned here at three levels: scalar primitives, the DataFrame columns they feed,
and the routing decision with its strict-greater-than boundary.
"""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from engine.demand import (
    monthly_pcs, monthly_packs, target_packs,
    compute_demand, assign_system_category,
)
from engine.constants import DAYS_PER_MONTH


# ---- scalar primitives ----

@pytest.mark.parametrize("cons,months,exp", [
    (160, 16, 10.0), (320, 16, 20.0), (8, 16, 0.5), (0, 16, 0.0), (5, 1, 5.0), (1, 16, 0.0625),
])
def test_monthly_pcs(cons, months, exp):
    assert monthly_pcs(cons, months) == pytest.approx(exp)


@pytest.mark.parametrize("mp,pack,exp", [
    (10.0, 1, 10.0), (10.0, 10, 1.0), (10.0, 0, 10.0), (5.0, 4, 1.25), (0.0, 5, 0.0),
])
def test_monthly_packs_with_zero_guard(mp, pack, exp):
    assert monthly_packs(mp, pack) == pytest.approx(exp)


def test_monthly_packs_zero_pack_treated_as_one():
    assert monthly_packs(7.0, 0) == 7.0


@pytest.mark.parametrize("mpk,cov,exp", [
    (2.0, 18, 2.0 * 18 / DAYS_PER_MONTH),
    (1.0, 30, 30 / DAYS_PER_MONTH),
    (0.0, 18, 0.0),
])
def test_target_packs(mpk, cov, exp):
    assert target_packs(mpk, cov) == pytest.approx(exp)


def test_target_packs_custom_days_per_month():
    assert target_packs(2.0, 30, days_per_month=30.0) == pytest.approx(2.0)


# ---- compute_demand ----

def _base():
    return pd.DataFrame({
        "Consumption_pcs": [160.0, 320.0, 8.0, 0.0],
        "PackUnits": [1, 10, 0, 5],
    })


def test_compute_demand_monthly_columns():
    out = compute_demand(_base(), consumption_period_months=16.0, coverage_days=18, coverage_days_special=18)
    assert list(out["Monthly_pcs"]) == [10.0, 20.0, 0.5, 0.0]
    # third row has PackUnits 0, guarded to 1 -> Monthly_packs equals Monthly_pcs
    assert list(out["Monthly_packs"]) == [10.0, 2.0, 0.5, 0.0]


def test_compute_demand_target_packs():
    out = compute_demand(_base(), consumption_period_months=16.0, coverage_days=18, coverage_days_special=18)
    assert out["Target_packs"].iloc[0] == pytest.approx(10.0 * 18 / DAYS_PER_MONTH)


def test_compute_demand_no_stdspecial_uses_scalar_coverage():
    out = compute_demand(_base(), consumption_period_months=16.0, coverage_days=18, coverage_days_special=30)
    assert (out["Coverage_days"] == 18.0).all()
    assert "Coverage_class" not in out.columns


def test_compute_demand_splits_coverage_when_stdspecial_and_windows_differ():
    df = _base().assign(StdSpecial=["1", "2", "1", "2"])
    out = compute_demand(df, consumption_period_months=16.0, coverage_days=18, coverage_days_special=30)
    assert "Coverage_class" in out.columns
    cov = list(out["Coverage_days"])
    assert cov[0] == 18.0  # row 0 standard
    assert cov[1] == 30.0  # row 1 special


def test_compute_demand_no_split_when_windows_equal_even_with_stdspecial():
    df = _base().assign(StdSpecial=["1", "2", "1", "2"])
    out = compute_demand(df, consumption_period_months=16.0, coverage_days=18, coverage_days_special=18)
    assert "Coverage_class" not in out.columns
    assert (out["Coverage_days"] == 18.0).all()


def test_compute_demand_does_not_mutate_input():
    df = _base()
    before = df.copy()
    compute_demand(df, consumption_period_months=16.0, coverage_days=18, coverage_days_special=18)
    assert_frame_equal(df, before)


# ---- assign_system_category ----

def _demand_frame():
    df = pd.DataFrame({
        "Consumption_pcs": [160.0, 320.0, 8.0, 4.0],
        "PackUnits": [1, 10, 1, 1],
        "ProductCategory": ["drills", "inserts", "taps", "drills"],
        "ToolClass": ["drill", "insert", "tap", "drill"],
    })
    return compute_demand(df, consumption_period_months=16.0, coverage_days=18, coverage_days_special=18)


def test_assign_system_category_standard_threshold():
    out = assign_system_category(_demand_frame(), usage_threshold=1.0,
                                 per_class_thresholds={}, optional_thresholds_active=False)
    # Monthly_pcs = [10, 20, 0.5, 0.25] against threshold 1
    assert list(out["SystemCategory"]) == ["KTC", "KTC", "Kanban", "Kanban"]


def test_assign_system_category_boundary_is_strictly_greater():
    df = compute_demand(pd.DataFrame({"Consumption_pcs": [16.0], "PackUnits": [1]}),
                        consumption_period_months=16.0, coverage_days=18, coverage_days_special=18)
    df["ProductCategory"] = "drills"
    df["ToolClass"] = "drill"
    # Monthly_pcs is exactly 1.0; threshold is 1.0; equal is NOT above -> Kanban
    out = assign_system_category(df, usage_threshold=1.0, per_class_thresholds={}, optional_thresholds_active=False)
    assert out["SystemCategory"].iloc[0] == "Kanban"


def test_assign_system_category_per_class_threshold_active():
    out = assign_system_category(_demand_frame(), usage_threshold=1.0,
                                 per_class_thresholds={"inserts": 99.0}, optional_thresholds_active=True)
    # the insert row (Monthly_pcs 20) now sits under the 99 inserts threshold
    assert out["SystemCategory"].iloc[1] == "Kanban"


def test_assign_system_category_reason_string():
    out = assign_system_category(_demand_frame(), usage_threshold=1.0,
                                 per_class_thresholds={}, optional_thresholds_active=False)
    assert ">" in out["SystemCategory_Reason"].iloc[0]    # a KTC row
    assert "<=" in out["SystemCategory_Reason"].iloc[2]   # a Kanban row
    assert "threshold 1 pcs/mo" in out["SystemCategory_Reason"].iloc[0]


def test_assign_system_category_empty_frame():
    empty = pd.DataFrame({"Monthly_pcs": pd.Series(dtype=float),
                          "ProductCategory": pd.Series(dtype=object),
                          "ToolClass": pd.Series(dtype=object)})
    out = assign_system_category(empty, usage_threshold=1.0, per_class_thresholds={}, optional_thresholds_active=False)
    assert len(out) == 0
    assert "SystemCategory" in out.columns and "SystemCategory_Reason" in out.columns


def test_assign_system_category_does_not_mutate_input():
    df = _demand_frame()
    before = df.copy()
    assign_system_category(df, usage_threshold=1.0, per_class_thresholds={}, optional_thresholds_active=False)
    assert_frame_equal(df, before)


# ---- composition ----

def test_full_demand_and_routing_columns_present():
    df = pd.DataFrame({"Consumption_pcs": [160.0], "PackUnits": [1],
                       "ProductCategory": ["drills"], "ToolClass": ["drill"]})
    out = compute_demand(df, consumption_period_months=16.0, coverage_days=18, coverage_days_special=18)
    out = assign_system_category(out, usage_threshold=1.0, per_class_thresholds={}, optional_thresholds_active=False)
    for col in ["Monthly_pcs", "Monthly_packs", "Coverage_days", "Target_packs",
                "SystemCategory", "SystemCategory_Reason"]:
        assert col in out.columns


def test_primitives_agree_with_compute_demand_columns():
    df = _base()
    out = compute_demand(df, consumption_period_months=16.0, coverage_days=18, coverage_days_special=18)
    for i in range(len(df)):
        mp = monthly_pcs(df["Consumption_pcs"].iloc[i], 16.0)
        assert out["Monthly_pcs"].iloc[i] == pytest.approx(mp)
        assert out["Monthly_packs"].iloc[i] == pytest.approx(monthly_packs(mp, df["PackUnits"].iloc[i]))
        assert out["Target_packs"].iloc[i] == pytest.approx(target_packs(out["Monthly_packs"].iloc[i], 18.0))
