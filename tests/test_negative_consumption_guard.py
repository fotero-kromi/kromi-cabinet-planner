"""Contract for the negative consumption guard (found on a real ERP extract).

ERP period-quantity exports can carry credit and return artifacts as negative
consumption. Unguarded, a negative value flows into pack math and produces
invalid Target_packs (the plan-integrity invariant flags the plan and the
export verification fails), and under deduplication the aggregation SUM would
silently fold a negative into other rows of the same key, corrupting a total
that then looks plausible. The guard clamps negatives to zero at the entry of
prepare_planning_base, before the year filter and the dedup aggregation, and
surfaces the count in base_info; frames without negatives are untouched.
"""

import pandas as pd
from pandas.testing import assert_frame_equal

from engine.constants import DAYS_PER_MONTH
from engine.invariants import verify_plan
from engine.plan import run_plan
from engine.preprocessing import prepare_planning_base
from tests.test_run_plan_equivalence import _boundary_frame, _params


def test_negative_consumption_is_clamped_and_counted():
    df = _boundary_frame()
    df.loc[2, "Consumption_pcs"] = -48.0
    df.loc[7, "Consumption_pcs"] = -1.0
    base, info = prepare_planning_base(df, dedup_mode="none",
                                       year_mode="all_rows", has_year=False)
    assert info["negative_consumption_clamped"] == 2
    got = pd.to_numeric(base["Consumption_pcs"], errors="coerce")
    assert (got.fillna(0.0) >= 0).all()
    assert float(got[base["Code"] == "T003"].iloc[0]) == 0.0
    assert float(got[base["Code"] == "T008"].iloc[0]) == 0.0
    # untouched rows keep their values
    assert float(got[base["Code"] == "T001"].iloc[0]) == 960.0


def test_clean_frames_pass_through_untouched():
    df = _boundary_frame()
    base, info = prepare_planning_base(df, dedup_mode="none",
                                       year_mode="all_rows", has_year=False)
    assert info["negative_consumption_clamped"] == 0
    assert_frame_equal(base.reset_index(drop=True), df.reset_index(drop=True),
                       check_dtype=True)


def test_dedup_sum_cannot_swallow_a_negative():
    df = _boundary_frame()
    dup = df.iloc[[0]].copy()
    dup["Consumption_pcs"] = [-16.0]
    stacked = pd.concat([df, dup], ignore_index=True)
    base, info = prepare_planning_base(stacked, dedup_mode="code",
                                       year_mode="all_rows", has_year=False)
    assert info["negative_consumption_clamped"] == 1
    got = float(pd.to_numeric(
        base.loc[base["Code"] == "T001", "Consumption_pcs"]).iloc[0])
    assert got == 960.0, f"dedup summed a negative into the total: {got}"


def test_plan_invariants_hold_with_negative_input_rows():
    df = _boundary_frame()
    df.loc[2, "Consumption_pcs"] = -48.0
    base, info = prepare_planning_base(df, dedup_mode="none",
                                       year_mode="all_rows", has_year=False)
    result = run_plan(base, (), _params(base))
    integrity = verify_plan(result.work, info, days_per_month=DAYS_PER_MONTH,
                            consumption_period_months=16.0)
    assert integrity.n_passed == integrity.n_checks, (
        f"invariants failed with a negative input row: "
        f"{[p for p in integrity.problems]}")
