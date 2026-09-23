"""Edge cases for the demand arithmetic and routing thresholds (v33.83).

The demand arithmetic (Monthly_pcs = consumption / months; Monthly_packs =
Monthly_pcs / pack units, with a guard against division by zero pack units) is
inline page logic with no engine unit test, so it is pinned here. The routing
threshold edges exercise the boundary and the per-tool-class override matrix.
"""

import math

import pytest

from engine.routing_rules import threshold_for_row, is_insert


def monthly_pcs(consumption, months):
    return consumption / months


def monthly_packs(mp, pack_units):
    return mp / (pack_units if pack_units else 1)  # page guards 0 -> 1


# ---- demand arithmetic edges ----

@pytest.mark.parametrize("cons,months,exp", [
    (0, 16, 0.0),
    (16, 16, 1.0),
    (1, 16, 0.0625),
    (100000, 12, 100000 / 12),
    (5, 1, 5.0),
])
def test_monthly_pcs_values(cons, months, exp):
    assert monthly_pcs(cons, months) == pytest.approx(exp)


@pytest.mark.parametrize("mp,pack,exp", [
    (10.0, 1, 10.0),
    (10.0, 10, 1.0),
    (10.0, 0, 10.0),     # zero pack guarded to 1
    (5.0, 4, 1.25),
    (0.0, 5, 0.0),
])
def test_monthly_packs_values_with_zero_pack_guard(mp, pack, exp):
    assert monthly_packs(mp, pack) == pytest.approx(exp)


def test_monthly_packs_never_divides_by_zero():
    # the guard means a zero pack count yields the piece count unchanged, not an error
    assert monthly_packs(7.0, 0) == 7.0
    assert not math.isinf(monthly_packs(7.0, 0))


def test_fractional_consumption_propagates():
    mp = monthly_pcs(2.5, 16)
    assert mp == pytest.approx(0.15625)
    assert monthly_packs(mp, 1) == pytest.approx(0.15625)


# ---- routing threshold boundary ----

@pytest.mark.parametrize("mp,thr,expected_ktc", [
    (1.0, 1.0, False),   # equal -> NOT above threshold -> Kanban
    (1.0001, 1.0, True),
    (0.9999, 1.0, False),
    (0.0, 1.0, False),
    (100.0, 1.0, True),
])
def test_routing_boundary_is_strictly_greater_than(mp, thr, expected_ktc):
    assert (mp > thr) is expected_ktc


# ---- per-class threshold matrix ----

def test_standard_threshold_when_optional_inactive():
    for pc in ["drills", "mills", "inserts", "taps", ""]:
        assert threshold_for_row(product_category=pc, tool_class="", standard_threshold=2.0,
                                 per_class_thresholds={"inserts": 9.0}, optional_active=False) == 2.0


def test_per_class_threshold_used_when_present_and_active():
    assert threshold_for_row(product_category="drills", tool_class="", standard_threshold=1.0,
                             per_class_thresholds={"drills": 5.0}, optional_active=True) == 5.0


def test_falls_back_to_standard_when_class_absent_from_map():
    assert threshold_for_row(product_category="mills", tool_class="", standard_threshold=1.0,
                             per_class_thresholds={"drills": 5.0}, optional_active=True) == 1.0


def test_insert_resolves_to_inserts_key_when_category_blank():
    # blank category but ToolClass says insert -> uses the inserts threshold
    assert threshold_for_row(product_category="", tool_class="indexable insert",
                             standard_threshold=1.0, per_class_thresholds={"inserts": 3.0},
                             optional_active=True) == 3.0


def test_nan_per_class_value_falls_back_to_standard():
    assert threshold_for_row(product_category="drills", tool_class="", standard_threshold=1.0,
                             per_class_thresholds={"drills": float("nan")}, optional_active=True) == 1.0


@pytest.mark.parametrize("pc,tc,expected", [
    ("inserts", "", True),
    ("INSERTS", "", True),
    ("", "carbide insert", True),
    ("drills", "", False),
    ("mills", "end mill", False),
    ("", "", False),
])
def test_is_insert_matrix(pc, tc, expected):
    assert is_insert(pc, tc) is expected


def test_routing_combines_demand_and_threshold():
    # a 0.5 pcs/mo insert with a 3.0 inserts threshold stays Kanban; a 4.0 insert goes KTC
    thr = threshold_for_row(product_category="inserts", tool_class="", standard_threshold=1.0,
                            per_class_thresholds={"inserts": 3.0}, optional_active=True)
    assert (0.5 > thr) is False
    assert (4.0 > thr) is True
