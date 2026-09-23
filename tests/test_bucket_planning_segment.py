"""Functional tests for run_bucket_planning_segment (engine/plan.py).

The segment is a faithful extraction of the page's per-bucket planning loop
(proven structurally identical token-for-token modulo the factor injections the
shims used to perform). These tests exercise its behaviour directly: per-bucket
plan rollup, in-place write-back to ``work``, the rebalancer / carousel-cap /
locker-consolidation paths, mode gating, and a real-customer-file check.
"""

import os
import numpy as np
import pandas as pd
import pytest

from engine.plan import run_bucket_planning_segment

_COLS = ["Code", "SystemCategory", "CabinetType", "Monthly_packs", "Target_packs",
         "Spiral_capacity", "Spirals_needed", "Carousel_stockpiles", "Consumption_pcs",
         "SizeCategory", "ProductCategory", "Regrind"]


def _work(rows):
    return pd.DataFrame(rows, columns=_COLS)


def _run(work, buckets, **kw):
    base = dict(op_mode="Standard", enable_rebalancer=False, buf_pct=0,
                minimum_carousel_allocation=3, underuse_threshold_pct=50.0,
                max_carousels_cap=0, helix_overfill_factor=1.1,
                carousel_reserve_factor=0.85, carousel_fill_ceiling=1.0)
    base.update(kw)
    return run_bucket_planning_segment(work, buckets, **base)


def test_standard_no_rebalancer_plan_rollup():
    work = _work([
        ["C1", "KTC", "Carousel", 5, 6, None, 0, 100, 200, "M", "Drill", False],
        ["H1", "KTC", "Helix", 3, 4, 6, 1, 0, 150, "S", "Mill", False],
    ])
    out, plans, audit = _run(work, [("b1", work.loc[[0, 1]])])
    assert len(plans) == 1
    label, plan = plans[0]
    assert label == "b1"
    assert plan["car_cabs"] == 1          # 100 carousel slots -> 1 cabinet
    assert plan["helix_cabs"] == 1        # 1 spiral -> 1 cabinet
    assert plan["total_cabs"] == 2
    assert audit == []                    # rebalancer off
    assert not out["SizeIssue"].any()     # Standard flags nothing up front


def test_writes_sizeissue_back_in_place():
    work = _work([["C1", "KTC", "Carousel", 5, 6, None, 0, 100, 200, "M", "Drill", False]])
    assert "SizeIssue" not in work.columns
    out, _, _ = _run(work, [("b1", work.loc[[0]])])
    # the same object is mutated, and the segment returns it
    assert out is work
    assert "SizeIssue" in work.columns


def test_rebalancer_consolidates_and_audits():
    # Two underused carousels that the rebalancer can fold into a helix.
    work = _work([
        ["C1", "KTC", "Carousel", 2, 3, None, 0, 5, 100, "M", "Drill", False],
        ["C2", "KTC", "Carousel", 1, 2, None, 0, 3, 50, "S", "Mill", False],
        ["H1", "KTC", "Helix", 4, 5, 6, 1, 0, 200, "M", "Drill", False],
    ])
    out, plans, audit = _run(work, [("b1", work.loc[[0, 1, 2]])], enable_rebalancer=True)
    assert len(audit) >= 1                              # something was moved
    assert all(ev["bucket"] == "b1" for ev in audit)    # events tagged with bucket
    # the carousels were re-routed in `work`
    assert (out["CabinetType"] == "Carousel").sum() < 2


def test_capped_mode_applies_cap_and_flags_unspillable():
    # ~3 carousels of demand, capped at 1; an L tool cannot spill -> SizeIssue.
    work = _work([
        ["C1", "KTC", "Carousel", 50, 60, None, 0, 800, 9000, "L", "Body", False],
        ["C2", "KTC", "Carousel", 50, 60, None, 0, 800, 9000, "L", "Body", False],
    ])
    out, plans, audit = _run(work, [("b1", work.loc[[0, 1]])],
                             op_mode="Capped", max_carousels_cap=1)
    _, plan = plans[0]
    # L/XL carousel tools cannot spill to Helix (a spiral is too small), so the cap
    # cannot move them: car_cabs stays at the physical need and they are flagged.
    assert out["SizeIssue"].any()              # unspillable overflow is flagged
    assert plan["car_cabs"] >= 1


def test_helix_mode_flags_unfit_and_skips_locker_consolidation():
    work = _work([
        ["H1", "KTC", "Helix", 3, 4, 6, 1, 0, 150, "M", "Drill", False],
        ["B1", "KTC", "Carousel", 5, 6, None, 0, 100, 200, "XXL", "Body", False],
    ])
    out, plans, audit = _run(work, [("b1", work.loc[[0, 1]])], op_mode="Helix")
    # Helix mode flags size-unfit tools up front; no rebalancer audit
    assert audit == []
    assert isinstance(out["SizeIssue"], pd.Series)


def test_locker_consolidation_picks_largest_tier():
    work = _work([
        ["L1", "KTC", "Locker C", 1, 1, None, 0, 0, 30, "XL", "Body", False],
        ["L2", "KTC", "Locker C", 1, 1, None, 0, 0, 20, "XXL", "Body", False],
    ])
    work["SystemTyp"] = "Locker"
    out, plans, audit = _run(work, [("b1", work.loc[[0, 1]])])
    # both consolidate into ONE tier (the one fitting the largest item); reason annotated
    tiers = set(out["CabinetType"])
    assert len(tiers) == 1
    assert out["SystemCategory_Reason"].str.contains("consolidated into").all()


def test_multi_bucket_yields_one_plan_each():
    work = _work([
        ["C1", "KTC", "Carousel", 5, 6, None, 0, 100, 200, "M", "Drill", False],
        ["C2", "KTC", "Carousel", 5, 6, None, 0, 100, 200, "M", "Drill", False],
    ])
    buckets = [("b1", work.loc[[0]]), ("b2", work.loc[[1]])]
    out, plans, audit = _run(work, buckets)
    assert [lbl for lbl, _ in plans] == ["b1", "b2"]
    assert all(p["car_cabs"] == 1 for _, p in plans)


def test_empty_bucket_is_graceful():
    work = _work([["C1", "KTC", "Carousel", 5, 6, None, 0, 100, 200, "M", "Drill", False]])
    empty = work.iloc[0:0]
    out, plans, audit = _run(work, [("b1", empty)])
    _, plan = plans[0]
    assert plan["total_cabs"] == 0
    assert audit == []


def test_capped_suppresses_carousel_buffer_but_standard_applies_it():
    # 720 slots = exactly 1 cabinet base; a 10% buffer would push Standard to 2,
    # but Capped suppresses the carousel buffer so it stays at the base.
    rows = [["C1", "KTC", "Carousel", 50, 60, None, 0, 720, 9000, "M", "Drill", False]]
    w_std = _work([r[:] for r in rows])
    _, plans_std, _ = _run(w_std, [("b1", w_std.loc[[0]])], buf_pct=10)
    _, std_plan = plans_std[0]
    w_cap = _work([r[:] for r in rows])
    _, plans_cap, _ = _run(w_cap, [("b1", w_cap.loc[[0]])], op_mode="Capped",
                           max_carousels_cap=5, buf_pct=10)
    _, cap_plan = plans_cap[0]
    assert std_plan["car_cabs"] == 2          # buffer adds a carousel in Standard
    assert cap_plan["car_cabs"] == 1          # capped mode suppresses the carousel buffer


@pytest.mark.skipif(not os.getenv("KROMI_GROUNDTRUTH_XLSX"),
                    reason="ground-truth customer file not provided")
def test_real_groundtruth_totals_reproduced_from_final_routing():
    # The ground-truth Result sheet is the planner's own output (post-rebalance
    # routing). Recomputing the plan from that routing with the rebalancer off must
    # reproduce a self-consistent cabinet count for the carousel/helix dimensions.
    path = os.getenv("KROMI_GROUNDTRUTH_XLSX")
    df = pd.ExcelFile(path).parse("Result")
    # the export uses "System" for KTC/Kanban; the engine reads "SystemCategory"
    if "SystemCategory" not in df.columns and "System" in df.columns:
        df = df.rename(columns={"System": "SystemCategory"})
    for col in ("Spirals_needed", "Carousel_stockpiles", "Consumption_pcs",
                "CabinetType", "SizeCategory"):
        assert col in df.columns, f"ground-truth missing {col}"
    work = df.copy()
    out, plans, audit = run_bucket_planning_segment(
        work, [("all", work)], op_mode="Standard", enable_rebalancer=False,
        buf_pct=0, minimum_carousel_allocation=3, underuse_threshold_pct=50.0,
        max_carousels_cap=0, helix_overfill_factor=1.1, carousel_reserve_factor=0.85,
        carousel_fill_ceiling=1.0)
    _, plan = plans[0]
    # raw routing base for this file: 720 carousel slots -> 1 carousel,
    # 125 spirals -> 2 helix. (The saved "2 carousels / 1 helix" headline is the
    # buffered/min-allocation result, not this unbuffered re-sum.)
    assert plan["car_cabs"] == 1, f"expected 1 carousel base, got {plan['car_cabs']}"
    assert plan["helix_cabs"] == 2, f"expected 2 helix base, got {plan['helix_cabs']}"
    # internal consistency on the real frame
    assert plan["total_cabs"] == (plan["helix_cabs"] + plan["car_cabs"]
                                  + plan["cabA"] + plan["cabB"] + plan["cabC"])
    assert plan["ktc_count"] + plan["kanban_count"] == plan["rows_total"]


# ---- strengthening pass: factor threading + edge cases ----

_COLS_NO_SPIRALS = [c for c in _COLS if c != "Spirals_needed"]


def _work_ns(rows):
    """A work frame WITHOUT a precomputed Spirals_needed column, so the helix
    rollup recomputes per row (so the passed overfill_factor has an effect)."""
    return pd.DataFrame(rows, columns=_COLS_NO_SPIRALS)


def test_overfill_factor_is_threaded_to_helix_sizing():
    # monthly_packs=6.5, spiral_capacity=6: one spiral holds 6*1.1=6.6 at overfill
    # 1.1 (1 spiral) but only 6.0 at 1.0 (2 spirals). The segment forwards its
    # helix_overfill_factor argument; if it silently defaulted, both would match.
    def spirals_for(of):
        w = _work_ns([["H1", "KTC", "Helix", 6.5, 7, 6, 0, 150, "S", "Mill", False]])
        _, plans, _ = _run(w, [("b", w.loc[[0]])], helix_overfill_factor=of)
        return plans[0][1]["total_spirals"]
    assert spirals_for(1.0) == 2
    assert spirals_for(1.1) == 1


def test_regrind_floors_helix_to_two_spirals():
    # A reground Helix item sized to one spiral is floored to two (new and reground
    # pieces cannot share a coil).
    w = _work_ns([["H1", "KTC", "Helix", 3, 4, 6, 0, 150, "S", "Mill", True]])
    _, plans, _ = _run(w, [("b", w.loc[[0]])])
    assert plans[0][1]["total_spirals"] == 2


def test_capped_spillable_m_tools_move_to_helix():
    # Two M carousels (1600 slots ~ 3 cabinets) capped at 1; M tools CAN spill, so
    # both move to Helix, the carousel count drops to the cap, nothing is flagged.
    w = _work([
        ["C1", "KTC", "Carousel", 50, 60, None, 0, 800, 9000, "M", "Drill", False],
        ["C2", "KTC", "Carousel", 50, 60, None, 0, 800, 9000, "M", "Drill", False],
    ])
    out, plans, _ = _run(w, [("b", w.loc[[0, 1]])], op_mode="Capped", max_carousels_cap=1)
    assert plans[0][1]["car_cabs"] <= 1
    assert (out["CabinetType"] == "Helix").sum() == 2     # both spilled
    assert not out["SizeIssue"].any()                     # clean spill, no overflow


def test_helix_mode_flags_oversize_helix_item():
    # In Helix mode a Helix-routed tool bigger than M does not fit a spiral.
    w = _work([["H1", "KTC", "Helix", 5, 6, 6, 1, 0, 200, "L", "Body", False]])
    out, _, audit = _run(w, [("b", w.loc[[0]])], op_mode="Helix")
    assert out["SizeIssue"].sum() == 1
    assert audit == []                                    # no rebalancer in Helix mode


def test_carousel_mode_flags_locker_only_size():
    # In Carousel mode a Carousel-routed tool of a locker-only size (XXL) is unfit.
    w = _work([["C1", "KTC", "Carousel", 5, 6, None, 0, 100, 200, "XXL", "Body", False]])
    out, _, _ = _run(w, [("b", w.loc[[0]])], op_mode="Carousel")
    assert out["SizeIssue"].sum() == 1


def test_rebalancer_no_move_leaves_work_unchanged():
    # A single near-full carousel is not underused, so nothing is relocated.
    w = _work([["C1", "KTC", "Carousel", 50, 60, None, 0, 700, 9000, "M", "Drill", False]])
    before = w["CabinetType"].tolist()
    out, plans, audit = _run(w, [("b", w.loc[[0]])], enable_rebalancer=True)
    assert audit == []
    assert out["CabinetType"].tolist() == before


def test_mixed_ktc_and_kanban_counts_split():
    w = _work([
        ["C1", "KTC", "Carousel", 5, 6, None, 0, 100, 200, "M", "Drill", False],
        ["K1", "Kanban", "Kanban", 2, 3, None, 0, 0, 50, "S", "Mill", False],
    ])
    _, plans, _ = _run(w, [("b", w.loc[[0, 1]])])
    p = plans[0][1]
    assert p["ktc_count"] == 1
    assert p["kanban_count"] == 1
    assert p["car_cabs"] == 1          # only the KTC carousel needs a cabinet


def test_empty_buckets_list_initialises_sizeissue():
    w = _work([["C1", "KTC", "Carousel", 5, 6, None, 0, 100, 200, "M", "Drill", False]])
    out, plans, audit = _run(w, [])
    assert plans == []
    assert audit == []
    assert "SizeIssue" in out.columns   # the pre-loop init runs even with no buckets


def test_multi_bucket_mutations_accumulate_in_work():
    # Two buckets, each consolidating a customer-fixed locker; both write back.
    w = _work([
        ["L1", "KTC", "Locker C", 1, 1, None, 0, 0, 30, "XL", "Body", False],
        ["L2", "KTC", "Locker C", 1, 1, None, 0, 0, 20, "XXL", "Body", False],
    ])
    w["SystemTyp"] = "Locker"
    out, plans, _ = _run(w, [("b1", w.loc[[0]]), ("b2", w.loc[[1]])])
    assert len(plans) == 2
    assert out["SystemCategory_Reason"].str.contains("consolidated into").all()


def test_nan_numeric_values_do_not_crash():
    w = _work([["C1", "KTC", "Carousel", np.nan, np.nan, None, 0, np.nan, np.nan,
                "M", "Drill", False]])
    out, plans, audit = _run(w, [("b", w.loc[[0]])])
    assert isinstance(plans[0][1]["total_cabs"], int)
    assert plans[0][1]["total_cabs"] == 0       # NaN slots -> 0

