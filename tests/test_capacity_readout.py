"""Are the configured machines enough? (v34.63, fixed configuration)

``capacity_rows`` gains two columns per supply point and machine type:

* "Needed by not placed": the units (spirals, compartments or boxes) the
  articles that found no space would need in their own machine type, with the
  same footprint the fit uses;
* "Extra machines (estimate)": ceil(max(0, needed - free) / usable units per
  machine), usable after the headroom.

A machine type with no machine configured appears when not-placed articles
need it. ``capacity_verdicts`` gives one plain line per supply point.
"""
import pandas as pd

from engine.fixed_config import (
    MachineSet,
    capacity_rows,
    capacity_verdicts,
    fit_fixed_configuration,
    fixed_plan_for_subset,
)
from tests.test_fixed_config import _KW, _frame, _row


def _plans(df, machines, headroom=0.0, sp=1, **kw):
    args = dict(_KW)
    args.update(kw)
    out, rep = fit_fixed_configuration(df, machines, headroom, **args)
    rep["supply_point"] = sp
    return [(f"SP {sp}", fixed_plan_for_subset(out, rep, overfill_factor=1.10))]


def _by_machine(rows):
    return {r["Machine"]: r for r in rows}


def test_everything_placed_needs_nothing():
    df = _frame([_row("A", "Carousel", 5, stock=10), _row("B", "Helix", 9, spirals=2)])
    rows = _by_machine(capacity_rows(_plans(df, MachineSet(helix=1, carousel=1))))
    for t in ("Helix", "Carousel"):
        assert rows[t]["Needed by not placed"] == 0
        assert rows[t]["Extra machines (estimate)"] == 0
    assert capacity_verdicts(_plans(df, MachineSet(helix=1, carousel=1))) == [
        "SP 1: all articles placed."]


def test_an_overflow_of_1_2_machines_gives_2():
    # one Carousel (720 compartments) is filled by the first article; the L-size
    # rest (864 = 1.2 x 720) cannot move to a Helix and finds no space
    rows = [_row("TOP", "Carousel", 99, stock=720, size="L")]
    rows += [_row(f"R{i}", "Carousel", 1, stock=96, size="L") for i in range(9)]
    plans = _plans(_frame(rows), MachineSet(carousel=1))
    car = _by_machine(capacity_rows(plans))["Carousel"]
    assert car["Needed by not placed"] == 864
    assert car["Free (usable)"] == 0
    assert car["Extra machines (estimate)"] == 2
    assert capacity_verdicts(plans) == [
        "SP 1: 9 articles not placed; about 2 more Carousel machines needed (estimate)."]


def test_the_headroom_is_respected():
    rows = [_row("TOP", "Carousel", 99, stock=300, size="L"),
            _row("R1", "Carousel", 1, stock=700, size="L")]
    full = _by_machine(capacity_rows(_plans(_frame(rows), MachineSet(carousel=1))))
    half = _by_machine(capacity_rows(_plans(_frame(rows), MachineSet(carousel=1),
                                            headroom=50.0)))
    # 700 needed; 420 free of 720 per machine, or 60 free of 360 with 50 % headroom
    assert full["Carousel"]["Needed by not placed"] == half["Carousel"]["Needed by not placed"] == 700
    assert full["Carousel"]["Extra machines (estimate)"] == 1
    assert half["Carousel"]["Extra machines (estimate)"] == 2


def test_lockers_count_one_box_per_article():
    rows = [_row(f"L{i}", "Locker C", 1, size="XLS") for i in range(100)]
    plans = _plans(_frame(rows), MachineSet(locker_c=1))
    lc = _by_machine(capacity_rows(plans))["Locker C"]
    assert lc["Needed by not placed"] == 4
    assert lc["Extra machines (estimate)"] == 1
    assert capacity_verdicts(plans) == [
        "SP 1: 4 articles not placed; about 1 more Locker C needed (estimate)."]


def test_a_type_without_machines_appears_when_it_is_needed():
    rows = [_row("H", "Helix", 9, spirals=3), _row("C", "Carousel", 2, stock=50, size="L")]
    plans = _plans(_frame(rows), MachineSet(helix=1))
    got = _by_machine(capacity_rows(plans))
    assert got["Carousel"]["Machines"] == 0
    assert got["Carousel"]["Needed by not placed"] == 50
    assert got["Carousel"]["Extra machines (estimate)"] == 1
    assert "Locker A" not in got
    assert capacity_verdicts(plans) == [
        "SP 1: 1 article not placed; about 1 more Carousel needed (estimate)."]


def test_several_types_in_one_line():
    rows = [_row("H", "Helix", 9, spirals=3), _row("C", "Carousel", 2, stock=50, size="L"),
            _row("L", "Locker A", 1, size="XXL")]
    plans = _plans(_frame(rows), MachineSet(), allow_spill=False)
    assert capacity_verdicts(plans) == [
        "SP 1: 3 articles not placed; about 1 more Helix, 1 more Carousel and "
        "1 more Locker A needed (estimate)."]


def test_one_line_per_supply_point_in_order():
    df = _frame([_row("A", "Carousel", 5, stock=10)])
    plans = _plans(df, MachineSet(carousel=1), sp=1) + _plans(
        _frame([_row("B", "Carousel", 5, stock=10, size="L")]), MachineSet(), sp=2)
    assert capacity_verdicts(plans) == [
        "SP 1: all articles placed.",
        "SP 2: 1 article not placed; about 1 more Carousel needed (estimate)."]


def test_a_stored_report_without_the_new_figures_still_renders():
    df = _frame([_row("A", "Carousel", 5, stock=10)])
    plans = _plans(df, MachineSet(carousel=1))
    del plans[0][1]["fixed_config"]["needed_not_placed"]
    car = _by_machine(capacity_rows(plans))["Carousel"]
    assert car["Needed by not placed"] == 0 and car["Extra machines (estimate)"] == 0


def test_the_columns_follow_the_existing_ones():
    df = _frame([_row("A", "Carousel", 5, stock=10)])
    cols = list(pd.DataFrame(capacity_rows(_plans(df, MachineSet(carousel=1)))).columns)
    assert cols[-3:] == ["Fill % of capacity", "Needed by not placed",
                         "Extra machines (estimate)"]


def test_kanban_articles_need_nothing():
    df = _frame([_row("K", "Kanban", 0.1, system="Kanban")])
    assert capacity_verdicts(_plans(df, MachineSet(carousel=1))) == [
        "SP 1: all articles placed."]
