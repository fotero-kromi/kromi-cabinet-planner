"""Pipeline integration tests (v33.83).

These run a small synthetic tool list through the stages the page chains together
-- preprocessing, classification, the demand arithmetic, routing, and export
shaping -- and check the stages connect and produce the expected numbers. The
demand and routing arithmetic mirrors the page (Monthly_pcs = consumption /
months; Monthly_packs = Monthly_pcs / pack units; KTC when Monthly_pcs exceeds the
threshold). Data is synthetic; no customer content is used.
"""

import pandas as pd
import pytest

from engine.preprocessing import prepare_planning_base
from engine.classification import normalize_product_category, heuristic_product_category
from engine.routing_rules import threshold_for_row, is_insert
from engine.export_shaping import user_view

DAYS_PER_MONTH = 30.4375  # mirrors engine.constants


def _raw():
    return pd.DataFrame([
        dict(Code="D1", Description="HSS twist drill 5mm", Consumption_pcs=160, PackUnits=1),
        dict(Code="D2", Description="carbide drill 8mm", Consumption_pcs=32, PackUnits=1),
        dict(Code="M1", Description="solid carbide end mill 10mm", Consumption_pcs=96, PackUnits=1),
        dict(Code="I1", Description="indexable turning insert CNMG", Consumption_pcs=320, PackUnits=10),
        dict(Code="T1", Description="machine tap M6", Consumption_pcs=8, PackUnits=1),
        dict(Code="R1", Description="hand reamer 6mm", Consumption_pcs=4, PackUnits=1),
    ])


def _classify(desc, code=""):
    pc = normalize_product_category(desc)
    if not str(pc).strip():
        pc = heuristic_product_category(str(desc), "", str(code), "") or ""
    return pc


# ---- preprocessing ----

def test_preprocessing_preserves_rows_when_no_filter():
    base, info = prepare_planning_base(_raw(), dedup_mode="none", year_mode="all_years", has_year=False)
    assert len(base) == 6
    assert info["rows_before"] == 6


def test_preprocessing_reports_consumption_total():
    base, info = prepare_planning_base(_raw(), dedup_mode="none", year_mode="all_years", has_year=False)
    assert info["consumption_before"] == pytest.approx(160 + 32 + 96 + 320 + 8 + 4)


def test_preprocessing_handles_empty_frame():
    empty = pd.DataFrame(columns=["Code", "Description", "Consumption_pcs", "PackUnits"])
    base, info = prepare_planning_base(empty, dedup_mode="none", year_mode="all_years", has_year=False)
    assert len(base) == 0 and info["rows_before"] == 0


# ---- classification ----

@pytest.mark.parametrize("desc,expected", [
    ("HSS twist drill 5mm", "drills"),
    ("carbide drill 8mm", "drills"),
    ("solid carbide end mill 10mm", "mills"),
    ("indexable turning insert CNMG", "inserts"),
    ("machine tap M6", "taps"),
])
def test_classification_recognises_common_tools(desc, expected):
    assert _classify(desc) == expected


def test_classification_returns_a_string_for_every_row():
    cats = _raw()["Description"].map(_classify)
    assert all(isinstance(c, str) for c in cats)


# ---- demand arithmetic (mirrors the page) ----

@pytest.mark.parametrize("cons,months,pack,exp_mp,exp_mpk", [
    (160, 16, 1, 10.0, 10.0),
    (320, 16, 10, 20.0, 2.0),
    (8, 16, 1, 0.5, 0.5),
    (96, 12, 1, 8.0, 8.0),
])
def test_demand_arithmetic(cons, months, pack, exp_mp, exp_mpk):
    monthly_pcs = cons / months
    monthly_packs = monthly_pcs / (pack or 1)
    assert monthly_pcs == pytest.approx(exp_mp)
    assert monthly_packs == pytest.approx(exp_mpk)


def test_target_packs_uses_coverage_window():
    monthly_packs = 2.0
    coverage_days = 18
    target = monthly_packs * (coverage_days / DAYS_PER_MONTH)
    assert target == pytest.approx(2.0 * 18 / 30.4375)


# ---- routing ----

def test_routing_splits_on_threshold():
    cons_months = 16.0
    base = _raw()
    mp = base["Consumption_pcs"] / cons_months
    system = ["KTC" if v > 1.0 else "Kanban" for v in mp]
    # D1 (10), M1 (6), I1 (20) exceed 1 -> KTC; D2 (2) -> KTC; T1 (0.5), R1 (0.25) -> Kanban
    assert system == ["KTC", "KTC", "KTC", "KTC", "Kanban", "Kanban"]


def test_insert_threshold_override_changes_routing():
    # with the override active and an inserts threshold of 3, a 2.0 pcs/mo insert is Kanban
    thr = threshold_for_row(product_category="inserts", tool_class="insert",
                            standard_threshold=1.0, per_class_thresholds={"inserts": 3.0},
                            optional_active=True)
    assert thr == 3.0
    assert (2.0 > thr) is False  # would be Kanban


def test_is_insert_detection():
    assert is_insert("inserts") is True
    assert is_insert("", "indexable insert") is True
    assert is_insert("drills") is False


def test_standard_threshold_applies_when_override_inactive():
    thr = threshold_for_row(product_category="inserts", tool_class="insert",
                            standard_threshold=1.0, per_class_thresholds={"inserts": 9.0},
                            optional_active=False)
    assert thr == 1.0


# ---- stage hand-off: routed result through export shaping ----

def _routed_result():
    base = _raw().copy()
    base["ProductCategory"] = base["Description"].map(_classify)
    base["Monthly_pcs"] = base["Consumption_pcs"] / 16.0
    base["Monthly_packs"] = base["Monthly_pcs"] / base["PackUnits"].replace(0, 1)
    base["System"] = ["KTC" if v > 1.0 else "Kanban" for v in base["Monthly_pcs"]]
    base["CabinetType"] = ["Carousel" if pc == "inserts" else ("Helix" if s == "KTC" else "")
                           for pc, s in zip(base["ProductCategory"], base["System"])]
    base["Spirals_needed"] = [2 if ct == "Helix" else 0 for ct in base["CabinetType"]]
    base["Carousel_stockpiles"] = [3 if ct == "Carousel" else 0 for ct in base["CabinetType"]]
    base["SupplyPoint"] = 1
    return base


def test_routed_result_shapes_into_ktc_and_kanban_views():
    res = _routed_result()
    ktc = user_view(res[res["System"] == "KTC"])
    kanban = user_view(res[res["System"] == "Kanban"])
    assert len(ktc) == 4 and len(kanban) == 2
    # cabinet columns survive in KTC, drop in Kanban
    assert "Spirals_needed" in ktc.columns
    assert "Spirals_needed" not in kanban.columns


def test_high_consumption_drill_routes_ktc_and_appears_in_helix_view():
    res = _routed_result()
    helix = user_view(res[res["CabinetType"] == "Helix"])
    assert "D1" in set(helix["Code"])           # the 10 pcs/mo drill
    assert "Carousel_stockpiles" not in helix.columns


def test_insert_routes_to_carousel_view():
    res = _routed_result()
    car = user_view(res[res["CabinetType"] == "Carousel"])
    assert "I1" in set(car["Code"])
    assert "Spirals_needed" not in car.columns


def test_every_routed_row_lands_in_exactly_one_system():
    res = _routed_result()
    assert set(res["System"]) <= {"KTC", "Kanban"}
    assert len(res[res["System"] == "KTC"]) + len(res[res["System"] == "Kanban"]) == len(res)
