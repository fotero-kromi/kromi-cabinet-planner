"""Tests for the constant de-shadow (v33.91).

`CAROUSEL_RESERVE_FACTOR` and `HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR` used to be
imported as constants and then rebound from the UI inputs, so the same name meant
"default" in constants.py and "the user's value" in the page after the rebind.
Any code that read the constant instead of the rebound name would silently size
cabinets to the default and ignore the user. This is now structurally impossible:
the constants are imported under alias names used only to seed the widgets, and
the run-time values live in plainly-named lower-case variables.

These tests pin that structure so the shadow cannot return, and demonstrate why
it matters by showing the factors do drive sizing on data where they are not
masked by the minimum-allocation floor.

As of the PlanConfig migration the two run-time values are built once into a
frozen ``PlanConfig`` (engine/plan_config.py) from the UI inputs, and every reader
reads from that single immutable object rather than a mutable module global.
"""

import os
import re

import pandas as pd
import pytest

from engine.sizing import assign_physical_sizing
from engine.cabinet_math import compute_plan_for_subset

_PAGE = os.path.join(os.path.dirname(__file__), "..", "pages", "1_Kromi_Planner.py")


def _page_src() -> str:
    with open(_PAGE, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Static guards: the shadow cannot come back
# ---------------------------------------------------------------------------

def test_bare_reserve_constant_only_in_aliased_import():
    src = _page_src()
    hits = re.findall(r"\bCAROUSEL_RESERVE_FACTOR\b", src)
    assert len(hits) == 1, f"expected only the aliased import, found {len(hits)} references"


def test_bare_overfill_constant_only_in_aliased_import():
    src = _page_src()
    hits = re.findall(r"\bHELIX_SINGLE_SPIRAL_OVERFILL_FACTOR\b", src)
    assert len(hits) == 1, f"expected only the aliased import, found {len(hits)} references"


def test_reserve_constant_is_aliased():
    assert "CAROUSEL_RESERVE_FACTOR as _DEFAULT_RESERVE_FACTOR" in _page_src()


def test_overfill_constant_is_aliased():
    assert "HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR as _DEFAULT_OVERFILL_FACTOR" in _page_src()


def test_reserve_runvar_assigned_from_ui():
    # the run-time reserve factor is built into the frozen PlanConfig from the UI input
    assert re.search(r"carousel_reserve_factor=float\(carousel_reserve_factor_ui\)",
                     _page_src())


def test_overfill_runvar_assigned_from_ui():
    # the run-time overfill factor is built into the frozen PlanConfig from the UI input
    assert re.search(r"helix_overfill_factor=float\(helix_single_spiral_overfill_factor_ui\)",
                     _page_src())


def test_runtime_factors_read_through_the_frozen_config():
    # the factors are read as _plan_cfg.<name>, never rebound as bare module globals
    src = _page_src()
    assert "_plan_cfg = PlanConfig(" in src
    assert not re.search(r"^helix_overfill_factor = ", src, re.MULTILINE)
    assert not re.search(r"^carousel_reserve_factor = ", src, re.MULTILINE)


def test_widget_defaults_use_the_aliased_constants():
    src = _page_src()
    assert "value=_DEFAULT_RESERVE_FACTOR" in src
    assert "value=_DEFAULT_OVERFILL_FACTOR" in src


def test_no_redundant_overfill_redeclaration():
    # the old `HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR = 1.10` / its renamed form is gone
    assert not re.search(r"^helix_overfill_factor = 1\.10\s*$", _page_src(), re.MULTILINE)


def test_aliases_referenced_only_at_import_and_default():
    src = _page_src()
    assert len(re.findall(r"_DEFAULT_RESERVE_FACTOR", src)) == 2
    assert len(re.findall(r"_DEFAULT_OVERFILL_FACTOR", src)) == 2


# ---------------------------------------------------------------------------
# Why it matters: the factors do drive sizing (where the floor doesn't mask them)
# ---------------------------------------------------------------------------

def _carousel_frame(target_packs):
    return pd.DataFrame([dict(CabinetType="Carousel", SystemCategory="KTC",
                              Target_packs=target_packs, Spiral_capacity=None, Regrind=False)])


def test_reserve_factor_changes_stockpiles_above_the_floor():
    df = _carousel_frame(20.0)  # 20*0.85=17 vs 20*0.70=14, both well above min 3
    high = assign_physical_sizing(df, minimum_carousel_allocation=3,
                                  carousel_reserve_factor=0.85, helix_overfill_factor=1.10)
    low = assign_physical_sizing(df, minimum_carousel_allocation=3,
                                 carousel_reserve_factor=0.70, helix_overfill_factor=1.10)
    assert high.loc[0, "Carousel_stockpiles"] == 17
    assert low.loc[0, "Carousel_stockpiles"] == 14


def _helix_frame(target_packs, cap=28):
    return pd.DataFrame([dict(CabinetType="Helix", SystemCategory="KTC",
                              Target_packs=target_packs, Spiral_capacity=cap, Regrind=False)])


def test_overfill_factor_changes_spirals_at_the_boundary():
    # at 30 packs and capacity 28: overfill 1.0 needs 2 spirals, overfill 1.10 fits 1
    df = _helix_frame(30.0, cap=28)
    tight = assign_physical_sizing(df, minimum_carousel_allocation=3,
                                   carousel_reserve_factor=0.85, helix_overfill_factor=1.0)
    loose = assign_physical_sizing(df, minimum_carousel_allocation=3,
                                   carousel_reserve_factor=0.85, helix_overfill_factor=1.10)
    assert tight.loc[0, "Spirals_needed"] == 2
    assert loose.loc[0, "Spirals_needed"] == 1


def test_default_factor_values_match_engine_constants():
    # the aliases the widgets seed from are the engine defaults
    from engine.constants import CAROUSEL_RESERVE_FACTOR, HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR
    assert CAROUSEL_RESERVE_FACTOR == 0.85
    assert HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR == 1.10


def test_plan_counts_respond_to_reserve_on_a_loaded_carousel():
    # many mid-volume carousel items: a deeper reserve can push to a second cabinet
    rows = [dict(CabinetType="Carousel", SystemCategory="KTC", Target_packs=4.0,
                 Consumption_pcs=60.0, Spiral_capacity=None, Regrind=False) for _ in range(220)]
    df = pd.DataFrame(rows)
    shallow = assign_physical_sizing(df, minimum_carousel_allocation=3,
                                     carousel_reserve_factor=0.70, helix_overfill_factor=1.10)
    deep = assign_physical_sizing(df, minimum_carousel_allocation=3,
                                  carousel_reserve_factor=1.50, helix_overfill_factor=1.10)
    p_shallow = compute_plan_for_subset(shallow, 0.0)
    p_deep = compute_plan_for_subset(deep, 0.0)
    assert p_deep["car_slots"] > p_shallow["car_slots"]


# ---------------------------------------------------------------------------
# Real-data pipeline (runs when the customer ground-truth is present)
# ---------------------------------------------------------------------------

# Path to a planner "Result" workbook, supplied from outside the shipped code so
# no customer name lives in the test. Set KROMI_GROUNDTRUTH_XLSX to run this.
_GROUND_TRUTH = os.environ.get("KROMI_GROUNDTRUTH_XLSX", "")


@pytest.mark.skipif(not (_GROUND_TRUTH and os.path.exists(_GROUND_TRUTH)),
                    reason="set KROMI_GROUNDTRUTH_XLSX to a planner Result workbook to run")
def test_real_data_sizing_pipeline_runs_and_conserves_rows():
    from engine.demand import compute_demand, assign_system_category
    from engine.sizing import assign_cabinet_types
    from engine.constants import DAYS_PER_MONTH
    res = pd.ExcelFile(_GROUND_TRUTH).parse("Result")
    n = len(res)
    work = pd.DataFrame({
        "Consumption_pcs": pd.to_numeric(res.Consumption_pcs, errors="coerce"),
        "PackUnits": pd.to_numeric(res.PackUnits, errors="coerce"),
        "SizeCategory": res.SizeCategory.astype(str),
        "ProductCategory": res.ProductCategory.astype(str),
        "Regrind": False,
    }, index=res.index)
    work = compute_demand(work, consumption_period_months=16, coverage_days=18,
                          coverage_days_special=18, days_per_month=DAYS_PER_MONTH)
    work = assign_system_category(work, usage_threshold=1.0, per_class_thresholds={},
                                  optional_thresholds_active=False)
    work = assign_cabinet_types(work, helix_threshold=4.0)
    sized = assign_physical_sizing(work, minimum_carousel_allocation=3,
                                   carousel_reserve_factor=0.85, helix_overfill_factor=1.10)
    assert len(sized) == n  # every customer row survives the pipeline
    plan = compute_plan_for_subset(sized, 0.0)
    assert plan["total_cabs"] >= 1 and plan["car_slots"] > 0
