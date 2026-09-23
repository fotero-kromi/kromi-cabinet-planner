"""Tests for engine/sizing.py (v33.86) — cabinet-type assignment.

First slice of the sizing-orchestration extraction. Beyond reproducing the
per-branch routing, these tests pin the two properties that matter most for a
pipeline stage: no row is silently dropped (row count and index are preserved),
and nothing outside the two intended columns changes.
"""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from engine.sizing import assign_cabinet_types


def _frame():
    return pd.DataFrame([
        dict(SystemCategory="Kanban", SizeCategory="m",   Monthly_packs=0.5, ProductCategory="taps"),
        dict(SystemCategory="KTC",    SizeCategory="xxl", Monthly_packs=1.0, ProductCategory="drills"),
        dict(SystemCategory="KTC",    SizeCategory="xxls", Monthly_packs=1.0, ProductCategory="drills"),
        dict(SystemCategory="KTC",    SizeCategory="xls", Monthly_packs=1.0, ProductCategory="drills"),
        dict(SystemCategory="KTC",    SizeCategory="m",   Monthly_packs=99.0, ProductCategory="inserts"),
    ], index=[10, 20, 30, 40, 50])


def test_kanban_rows_get_kanban_cabinet_and_no_spiral():
    out = assign_cabinet_types(_frame(), helix_threshold=4.0)
    assert out.loc[10, "CabinetType"] == "Kanban"
    assert pd.isna(out.loc[10, "Spiral_capacity"])


def test_locker_sizes_route_to_lockers():
    out = assign_cabinet_types(_frame(), helix_threshold=4.0)
    assert out.loc[20, "CabinetType"] == "Locker A"   # xxl
    assert out.loc[30, "CabinetType"] == "Locker B"   # xxls
    assert out.loc[40, "CabinetType"] == "Locker C"   # xls


def test_high_volume_routes_to_helix_with_spiral_capacity():
    out = assign_cabinet_types(_frame(), helix_threshold=4.0)
    assert out.loc[50, "CabinetType"] == "Helix"
    assert out.loc[50, "Spiral_capacity"] == 22


def test_non_helix_rows_have_no_spiral_capacity():
    out = assign_cabinet_types(_frame(), helix_threshold=4.0)
    for idx in [10, 20, 30, 40]:
        assert pd.isna(out.loc[idx, "Spiral_capacity"])


# ---- the guards that matter most: no lost rows, no unintended changes ----

def test_row_count_is_preserved():
    df = _frame()
    out = assign_cabinet_types(df, helix_threshold=4.0)
    assert len(out) == len(df)


def test_index_is_preserved_exactly():
    df = _frame()
    out = assign_cabinet_types(df, helix_threshold=4.0)
    assert out.index.equals(df.index)
    assert set(out.index) == set(df.index)  # no row silently lost or duplicated


def test_only_two_columns_are_added():
    df = _frame()
    out = assign_cabinet_types(df, helix_threshold=4.0)
    assert set(out.columns) - set(df.columns) == {"CabinetType", "Spiral_capacity"}


def test_original_columns_are_unchanged():
    df = _frame()
    out = assign_cabinet_types(df, helix_threshold=4.0)
    for col in df.columns:
        assert out[col].equals(df[col])


def test_input_is_not_mutated():
    df = _frame()
    before = df.copy()
    assign_cabinet_types(df, helix_threshold=4.0)
    assert_frame_equal(df, before)


def test_empty_frame_yields_empty_columns():
    empty = pd.DataFrame({"SystemCategory": pd.Series(dtype=object),
                          "SizeCategory": pd.Series(dtype=object),
                          "Monthly_packs": pd.Series(dtype=float),
                          "ProductCategory": pd.Series(dtype=object)})
    out = assign_cabinet_types(empty, helix_threshold=4.0)
    assert len(out) == 0
    assert "CabinetType" in out.columns and "Spiral_capacity" in out.columns


def test_helix_threshold_changes_routing():
    df = pd.DataFrame([dict(SystemCategory="KTC", SizeCategory="m", Monthly_packs=5.0, ProductCategory="mills")])
    # the cabinet decision depends on the helix threshold; a different threshold can move it
    low = assign_cabinet_types(df, helix_threshold=1.0).loc[0, "CabinetType"]
    high = assign_cabinet_types(df, helix_threshold=100.0).loc[0, "CabinetType"]
    assert low != high


@pytest.mark.parametrize("size,expected", [
    ("xxl", "Locker A"),
    ("xxls", "Locker B"),
    ("xls", "Locker C"),
])
def test_locker_size_mapping(size, expected):
    df = pd.DataFrame([dict(SystemCategory="KTC", SizeCategory=size, Monthly_packs=1.0, ProductCategory="drills")])
    assert assign_cabinet_types(df, helix_threshold=4.0).loc[0, "CabinetType"] == expected


# ---------------------------------------------------------------------------
# assign_physical_sizing (v33.87) — Helix spirals + KTC carousel stockpiles.
# The reserve and overfill factors are user run-time settings, so the function
# takes them as parameters; these tests pin that the parameters are honoured,
# that no row is dropped, and that nothing outside the two columns changes.
# ---------------------------------------------------------------------------

from engine.sizing import assign_physical_sizing


def _sizing_frame():
    return pd.DataFrame([
        dict(CabinetType="Helix",    SystemCategory="KTC",    Target_packs=1.0,  Spiral_capacity=28,   Regrind=False),
        dict(CabinetType="Helix",    SystemCategory="KTC",    Target_packs=60.0, Spiral_capacity=28,   Regrind=False),
        dict(CabinetType="Helix",    SystemCategory="KTC",    Target_packs=1.0,  Spiral_capacity=28,   Regrind=True),
        dict(CabinetType="Helix",    SystemCategory="KTC",    Target_packs=99.0, Spiral_capacity=28,   Regrind=True),
        dict(CabinetType="Carousel", SystemCategory="KTC",    Target_packs=0.5,  Spiral_capacity=None, Regrind=False),
        dict(CabinetType="Carousel", SystemCategory="KTC",    Target_packs=20.0, Spiral_capacity=None, Regrind=False),
        dict(CabinetType="Locker A", SystemCategory="KTC",    Target_packs=5.0,  Spiral_capacity=None, Regrind=False),
        dict(CabinetType="Kanban",   SystemCategory="Kanban", Target_packs=2.0,  Spiral_capacity=None, Regrind=False),
    ], index=[10, 20, 30, 40, 50, 60, 70, 80])


def _size(df, *, mn=3, reserve=0.85, overfill=1.10):
    return assign_physical_sizing(df, minimum_carousel_allocation=mn,
                                  carousel_reserve_factor=reserve, helix_overfill_factor=overfill)


def test_helix_single_spiral():
    out = _size(_sizing_frame())
    assert out.loc[10, "Spirals_needed"] == 1


def test_helix_multi_spiral():
    out = _size(_sizing_frame())
    assert out.loc[20, "Spirals_needed"] == 3


def test_regrind_helix_floored_to_two():
    out = _size(_sizing_frame())
    assert out.loc[30, "Spirals_needed"] == 2  # 1 -> 2


def test_regrind_helix_already_above_floor_unchanged():
    out = _size(_sizing_frame())
    assert out.loc[40, "Spirals_needed"] == 4  # >=2 already, untouched


def test_carousel_stockpile_clipped_to_minimum():
    out = _size(_sizing_frame(), mn=3)
    assert out.loc[50, "Carousel_stockpiles"] == 3  # tiny demand floored to min


def test_carousel_stockpile_sized_from_reserve():
    out = _size(_sizing_frame())
    assert out.loc[60, "Carousel_stockpiles"] == 17  # ceil(20 * 0.85)


def test_locker_and_kanban_get_no_spirals_or_stockpiles():
    out = _size(_sizing_frame())
    for idx in [70, 80]:
        assert out.loc[idx, "Spirals_needed"] == 0
        assert out.loc[idx, "Carousel_stockpiles"] == 0


def test_reserve_factor_is_honoured():
    # lower reserve -> fewer stockpiles for the reserve-sized row
    high = _size(_sizing_frame(), reserve=0.85).loc[60, "Carousel_stockpiles"]
    low = _size(_sizing_frame(), reserve=0.70).loc[60, "Carousel_stockpiles"]
    assert low < high


def test_minimum_allocation_is_honoured():
    out3 = _size(_sizing_frame(), mn=3).loc[50, "Carousel_stockpiles"]
    out5 = _size(_sizing_frame(), mn=5).loc[50, "Carousel_stockpiles"]
    assert out3 == 3 and out5 == 5


def test_overfill_factor_is_honoured():
    # a higher overfill factor can only keep or raise the spiral count
    lo = _size(_sizing_frame(), overfill=1.10).loc[20, "Spirals_needed"]
    hi = _size(_sizing_frame(), overfill=2.00).loc[20, "Spirals_needed"]
    assert hi >= lo


def test_sizing_row_and_index_preserved():
    df = _sizing_frame()
    out = _size(df)
    assert len(out) == len(df)
    assert out.index.equals(df.index)
    assert set(out.index) == set(df.index)


def test_sizing_only_two_columns_added_and_int_typed():
    df = _sizing_frame()
    out = _size(df)
    assert set(out.columns) - set(df.columns) == {"Spirals_needed", "Carousel_stockpiles"}
    assert str(out["Spirals_needed"].dtype) == "int64"
    assert str(out["Carousel_stockpiles"].dtype) == "int64"


def test_sizing_original_columns_unchanged():
    df = _sizing_frame()
    out = _size(df)
    for col in df.columns:
        assert out[col].equals(df[col])


def test_sizing_input_not_mutated():
    df = _sizing_frame()
    before = df.copy()
    _size(df)
    assert_frame_equal(df, before)


def test_sizing_empty_frame():
    empty = pd.DataFrame({"CabinetType": pd.Series(dtype=object),
                          "SystemCategory": pd.Series(dtype=object),
                          "Target_packs": pd.Series(dtype=float),
                          "Spiral_capacity": pd.Series(dtype=object),
                          "Regrind": pd.Series(dtype=bool)})
    out = _size(empty)
    assert len(out) == 0
    assert "Spirals_needed" in out.columns and "Carousel_stockpiles" in out.columns


def test_non_ktc_carousel_gets_no_stockpiles():
    # a Carousel row that is not KTC must not receive stockpiles
    df = pd.DataFrame([dict(CabinetType="Carousel", SystemCategory="Kanban",
                            Target_packs=50.0, Spiral_capacity=None, Regrind=False)])
    out = _size(df)
    assert out.loc[0, "Carousel_stockpiles"] == 0
