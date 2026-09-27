"""engine/multi_location.py (v34.63): the per-machine Program mapping.

``expand_locations`` replaces the plain Program -> supply point map: every
article is planned in each supply point its machines map to, with an equal
share of its consumption per machine (D1). Files without multi-machine cells
must come out exactly as before. Machine labels are invented.
"""
import math

import pandas as pd
import pytest

from engine import multi_location as ml
from engine import tool_list as tl
from engine.preprocessing import prepare_planning_base
from tools import synthetic_golden as sg


def _work(programs, cons=None, stock=None, codes=None, listing=None, year=None):
    n = len(programs)
    data = {
        "Art": codes or [f"A{i}" for i in range(n)],
        "Text": [f"Bohrer D{i + 3}" for i in range(n)],
        "Use": cons or [120.0] * n,
        "Loc": programs,
    }
    kw = {"program": "Loc"}
    if stock is not None:
        data["Qty"] = stock
        kw["stock"] = "Qty"
    if year is not None:
        data["Jahr"] = year
        kw["year"] = "Jahr"
    frame = pd.DataFrame(data)
    mapping = tl.ColumnMapping(code="Art", description="Text", consumption="Use", **kw)
    work = tl.build_tool_list(frame, None, mapping, use_description_2=False).work
    if listing is not None:
        work["Listing"] = listing
    return work


def _today(work, program_to_sp):
    """The v34.62 step: the plain Program -> supply point map."""
    out = work.copy()
    tl.assign_supply_points(out, program_to_sp)
    return out


# ---- machines ---------------------------------------------------------------------------

def test_distinct_machines_are_split_sorted_and_blank_last():
    w = _work(["AB-101 + AB 100", "Line A", "", "ab-100"])
    assert ml.distinct_machines(w) == ["AB-100", "AB-101", "Line A", ""]


def test_distinct_machines_equal_the_programmes_of_a_single_machine_file():
    w = _work(["Line B", "Line A", "", "Line A", "KTC-B"])
    assert ml.distinct_machines(w) == tl.distinct_programs(w)


def test_multi_machine_rows_are_counted():
    w = _work(["AB-100 + AB-101", "AB-100", "AB-100 +101 + 102", ""])
    assert ml.multi_machine_rows(w) == 2
    assert ml.has_multi_machine_cells(w)
    assert not ml.has_multi_machine_cells(_work(["AB-100", "Line A"]))


def test_unassigned_machines():
    assert ml.unassigned_machines(["AB-100", "AB-101", ""], {"AB-100": 1, "": 0}) == ["AB-101"]


def test_machine_stats_share_the_consumption_per_machine():
    w = _work(["AB-100 + AB-101", "AB-100"], cons=[100.0, 30.0])
    stats = ml.machine_stats(w)
    assert stats["AB-100"] == {"rows": 2, "consumption": pytest.approx(80.0)}
    assert stats["AB-101"] == {"rows": 1, "consumption": pytest.approx(50.0)}


# ---- identity for files without multi-machine cells ---------------------------------------

@pytest.mark.parametrize("with_stock", [False, True])
def test_a_file_without_multi_machine_cells_is_unchanged(with_stock):
    progs = ["Line A", "Line B", "", "Line A", "AB-100", "Line B"]
    w = _work(progs, cons=[5.0, 7.5, 0.0, 12.0, 3.0, 1.0],
              stock=[1, 2, 3, 4, 5, 6] if with_stock else None)
    mapping = {"Line A": 1, "Line B": 2, "": 1, "AB-100": 2}
    got, info = ml.expand_locations(w, mapping)
    pd.testing.assert_frame_equal(got, _today(w, mapping))
    assert info.multi_rows == 0 and info.shared_articles == 0
    assert not info.unplanned_articles and not info.not_planned_machines


def test_the_synthetic_catalog_is_unchanged():
    frame = sg.build_catalog()
    mapping = tl.ColumnMapping(code="Article No", description="Description",
                               consumption="Consumption 12 months", category="Category",
                               pack_units="Pack unit", program="Location", stock="Stock",
                               system_type="System")
    work = tl.build_tool_list(frame, None, mapping, use_description_2=False).work
    sp = {"Line A": 1, "Line B": 2}
    got, _info = ml.expand_locations(work, sp)
    pd.testing.assert_frame_equal(got, _today(work, sp))
    got_full, _ = ml.expand_locations(work, sp, full_consumption=True)
    pd.testing.assert_frame_equal(got_full, _today(work, sp))


def test_identity_holds_after_the_planning_base():
    w = _work(["Line A", "Line B", "Line A"], codes=["X", "X", "X"], stock=[4, 5, 6])
    sp = {"Line A": 1, "Line B": 2}
    a, _ = prepare_planning_base(ml.expand_locations(w, sp)[0], "code", "all_rows", False)
    b, _ = prepare_planning_base(_today(w, sp), "code", "all_rows", False)
    pd.testing.assert_frame_equal(a, b)


# ---- expansion ------------------------------------------------------------------------------

def test_an_article_on_two_machines_is_planned_in_both_supply_points():
    w = _work(["AB-100 + AB 101"], cons=[120.0], stock=[50])
    got, info = ml.expand_locations(w, {"AB-100": 1, "AB-101": 2})
    assert list(got["SupplyPoint"]) == [1, 2]
    assert list(got["Consumption_pcs"]) == [60.0, 60.0]
    assert list(got["Stock_pcs"]) == [25.0, 25.0]
    assert list(got[ml.ARTICLE_STOCK_COL]) == [50.0, 50.0]
    assert list(got[ml.SOURCE_COL]) == ["AB-100 + AB 101"] * 2
    assert list(got[ml.SHARED_COL]) == [True, True]
    assert info.multi_rows == 1 and info.shared_articles == 1


def test_two_of_three_machines_on_one_supply_point_give_two_thirds():
    w = _work(["AB-100 +101 + 102"], cons=[90.0])
    got, _ = ml.expand_locations(w, {"AB-100": 1, "AB-101": 2, "AB-102": 1})
    by_sp = dict(zip(got["SupplyPoint"], got["Consumption_pcs"]))
    assert by_sp[1] == pytest.approx(60.0) and by_sp[2] == pytest.approx(30.0)


def test_shares_restore_the_total_within_1e_9():
    w = _work(["AB-100 + 101 + 102", "AB-100 + 101 + 102 + 103 + 104 + 105 + 106"],
              cons=[1234.567, 1000.0 / 3.0])
    got, _ = ml.expand_locations(w, {f"AB-{n}": 1 + n % 3 for n in range(100, 107)})
    assert math.isclose(got["Consumption_pcs"].sum(), w["Consumption_pcs"].sum(),
                        rel_tol=0, abs_tol=1e-9)


def test_full_consumption_counts_the_whole_use_in_every_supply_point():
    w = _work(["AB-100 + AB-101 + AB-102"], cons=[90.0], stock=[30])
    got, _ = ml.expand_locations(w, {"AB-100": 1, "AB-101": 2, "AB-102": 2},
                                 full_consumption=True)
    assert list(got["Consumption_pcs"]) == [90.0, 90.0]
    # the stock share stays the machine share (the pool is the takeover's)
    assert list(got["Stock_pcs"]) == [10.0, 20.0]
    assert list(got[ml.ARTICLE_STOCK_COL]) == [30.0, 30.0]


def test_a_machine_not_planned_here_keeps_its_share_out():
    w = _work(["AB-100 + AB-102", "AB-100"], cons=[100.0, 10.0], stock=[40, 2],
              codes=["X", "Y"])
    got, info = ml.expand_locations(w, {"AB-100": 1, "AB-102": ml.NOT_PLANNED})
    assert list(got["Code"]) == ["X", "Y"]
    assert list(got["Consumption_pcs"]) == [50.0, 10.0]
    assert info.not_planned_machines == ("AB-102",)
    assert not info.unplanned_articles
    # the row reaches the plan, so its whole stock is the article's pool
    assert list(got[ml.ARTICLE_STOCK_COL]) == [40.0, 2.0]
    assert list(got[ml.SHARED_COL]) == [False, False]


def test_an_article_without_a_planned_machine_is_reported():
    w = _work(["AB-102", "AB-100", "AB-102 + AB-103", "AB-102"], codes=["P", "Q", "R", "Q"])
    got, info = ml.expand_locations(
        w, {"AB-100": 1, "AB-102": ml.NOT_PLANNED, "AB-103": ml.NOT_PLANNED})
    assert info.unplanned_articles == (("Tools", "P"), ("Tools", "R"))
    # Q still has a planned row; its row on the unplanned machine drops out
    assert list(got["Code"]) == ["Q"]
    assert info.dropped_rows == 3


def test_a_row_outside_the_plan_adds_no_stock_to_the_pool():
    w = _work(["AB-100 + AB-101", "AB-102"], codes=["X", "X"], stock=[10, 5], cons=[20.0, 8.0])
    got, _ = ml.expand_locations(w, {"AB-100": 1, "AB-101": 2, "AB-102": ml.NOT_PLANNED})
    assert list(got[ml.ARTICLE_STOCK_COL]) == [10.0, 10.0]


def test_the_pool_counts_each_source_row_once():
    w = _work(["AB-100 + AB-101", "AB-100"], codes=["X", "X"], stock=[10, 4])
    got, _ = ml.expand_locations(w, {"AB-100": 1, "AB-101": 2})
    assert list(got[ml.ARTICLE_STOCK_COL]) == [14.0, 14.0, 14.0]
    assert list(got[ml.SHARED_COL]) == [True, True, True]


def test_no_pool_without_a_stock_column_or_without_a_shared_article():
    got, _ = ml.expand_locations(_work(["AB-100 + AB-101"]), {"AB-100": 1, "AB-101": 2})
    assert ml.ARTICLE_STOCK_COL not in got.columns
    got, _ = ml.expand_locations(_work(["AB-100 + AB-101"], stock=[3]),
                                 {"AB-100": 1, "AB-101": 1})
    assert ml.ARTICLE_STOCK_COL not in got.columns
    assert list(got["Consumption_pcs"]) == [120.0]
    assert list(got[ml.SHARED_COL]) == [False]


def test_articles_are_listing_and_code():
    w = _work(["AB-100 + AB-101", "AB-100"], codes=["X", "X"], listing=["Tools", "PPE"])
    got, info = ml.expand_locations(w, {"AB-100": 1, "AB-101": 2})
    shared = dict(zip(zip(got["Listing"], got["SupplyPoint"]), got[ml.SHARED_COL]))
    assert shared == {("Tools", 1): True, ("Tools", 2): True, ("PPE", 1): False}
    assert info.shared_articles == 1


def test_an_unassigned_machine_is_an_error_never_a_silent_default():
    with pytest.raises(ValueError, match="AB-101"):
        ml.expand_locations(_work(["AB-100 + AB-101"]), {"AB-100": 1})


def test_expansion_does_not_mutate_its_input():
    w = _work(["AB-100 + AB-101"], stock=[4])
    before = w.copy()
    ml.expand_locations(w, {"AB-100": 1, "AB-101": 2})
    pd.testing.assert_frame_equal(w, before)


# ---- through the planning-base dedup ---------------------------------------------------------

def test_the_dedup_sums_the_shares_and_carries_the_new_columns():
    w = _work(["AB-100 + AB-101", "AB-100"], codes=["X", "X"], cons=[100.0, 10.0],
              stock=[10, 4])
    exp, _ = ml.expand_locations(w, {"AB-100": 1, "AB-101": 2})
    base, info = prepare_planning_base(exp, "code", "all_rows", False)
    assert list(base["SupplyPoint"]) == [1, 2]
    assert list(base["Consumption_pcs"]) == [60.0, 50.0]
    assert list(base["Stock_pcs"]) == [9.0, 5.0]
    assert list(base[ml.ARTICLE_STOCK_COL]) == [14.0, 14.0]
    assert list(base[ml.SHARED_COL]) == [True, True]
    assert list(base[ml.SOURCE_COL]) == ["AB-100, AB-100 + AB-101", "AB-100 + AB-101"]
    assert not [c for c in base.columns if c.startswith("_Location")]
    assert info["consumption_after_dedup"] == pytest.approx(110.0)


def test_without_dedup_the_helper_columns_are_dropped_too():
    exp, _ = ml.expand_locations(_work(["AB-100 + AB-101"], stock=[2]),
                                 {"AB-100": 1, "AB-101": 2})
    base, _ = prepare_planning_base(exp, "none", "all_rows", False)
    assert not [c for c in base.columns if c.startswith("_Location")]
    assert list(base[ml.ARTICLE_STOCK_COL]) == [2.0, 2.0]


def test_the_year_filter_decides_the_pool_and_the_shared_flag():
    # X is listed for two machines in the old year only; the latest-year row
    # names one machine. After the filter X is in one supply point only.
    w = _work(["AB-100 + AB-101", "AB-100", "AB-100 + AB-101"], codes=["X", "X", "Y"],
              stock=[10, 4, 6], year=[2024, 2025, 2025])
    exp, _ = ml.expand_locations(w, {"AB-100": 1, "AB-101": 2})
    base, _ = prepare_planning_base(exp, "code", "latest_year_only", True)
    x = base[base["Code"] == "X"]
    assert list(x["SupplyPoint"]) == [1] and list(x[ml.SHARED_COL]) == [False]
    assert list(x[ml.ARTICLE_STOCK_COL]) == [4.0]
    y = base[base["Code"] == "Y"]
    assert list(y[ml.SHARED_COL]) == [True, True]
    assert list(y[ml.ARTICLE_STOCK_COL]) == [6.0, 6.0]


# ---- the mapping summary -------------------------------------------------------------------

def test_the_mapping_summary_shows_rows_and_consumption_after_the_shares():
    w = _work(["AB-100 + AB-101", "AB-100", "AB-102 + AB-100"], cons=[100.0, 10.0, 40.0])
    rows = ml.mapping_summary(w, {"AB-100": 1, "AB-101": 2, "AB-102": ml.NOT_PLANNED},
                              n_supply_points=2)
    assert [r["Supply Point"] for r in rows] == ["SP 1", "SP 2", ml.NOT_PLANNED_LABEL]
    assert [r["Rows"] for r in rows] == [3, 1, 1]
    assert [r["Annual consumption"] for r in rows] == [80, 50, 20]
    assert [r["Machines (first 5)"] for r in rows] == ["AB-100", "AB-101", "AB-102"]


def test_the_mapping_summary_follows_the_full_consumption_option():
    w = _work(["AB-100 + AB-101"], cons=[100.0])
    rows = ml.mapping_summary(w, {"AB-100": 1, "AB-101": 2}, n_supply_points=2,
                              full_consumption=True)
    assert [r["Annual consumption"] for r in rows] == [100, 100]


def test_the_mapping_summary_ignores_machines_not_yet_chosen():
    w = _work(["AB-100 + AB-101"], cons=[100.0])
    rows = ml.mapping_summary(w, {"AB-100": 1}, n_supply_points=2)
    assert [(r["Rows"], r["Annual consumption"]) for r in rows] == [(1, 50), (0, 0)]
