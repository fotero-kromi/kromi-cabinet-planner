"""A shared article is KTC in every supply point when it is KTC in one (v34.63).

Owner decision (2026-09-27): an article cannot be KTC and Kanban at the same
time. With the equal consumption shares of D1, one supply point's share can
pass the KTC threshold while another's does not; the article is then KTC in
every supply point, each copy sized by its own share. Also pinned here: the
plan invariant that checks it, the run fingerprint and the per-supply-point
machine list.
"""
import pandas as pd
import pytest

from engine import multi_location as ml
from engine.distribution import build_per_sp_summary
from engine.invariants import check_shared_article_system, verify_plan
from engine.plan import run_plan
from engine.run_fingerprint import FingerprintInputs, compute_run_fingerprint
from tests.test_run_fingerprint import _BASE, GOLDEN
from tests.test_run_plan_equivalence import _boundary_frame, _params

_EMPTY_OV = pd.DataFrame()
_SIZING = dict(helix_threshold=4.0, min_carousel_compartments=3,
               carousel_reserve_factor=0.85, helix_overfill_factor=1.10)


def _shared_frame(cons_sp1=40.0, cons_sp2=8.0, flag=True):
    """The boundary frame at SP 1, plus a second copy of T003 at SP 2."""
    df = _boundary_frame()
    df["SupplyPoint"] = 1
    extra = df[df["Code"] == "T003"].copy()
    extra["SupplyPoint"] = 2
    df = pd.concat([df, extra], ignore_index=True)
    t003 = df["Code"] == "T003"
    df.loc[t003 & (df["SupplyPoint"] == 1), "Consumption_pcs"] = cons_sp1
    df.loc[t003 & (df["SupplyPoint"] == 2), "Consumption_pcs"] = cons_sp2
    if flag:
        df[ml.SOURCE_COL] = "AB-100 + AB-101"
        df[ml.SHARED_COL] = t003.to_numpy()
    return df


def _t003(work):
    return work[work["Code"] == "T003"].sort_values("SupplyPoint")


# ---- the rule -----------------------------------------------------------------------------

def test_a_shared_article_that_is_ktc_in_one_supply_point_is_ktc_in_all():
    df = _shared_frame()             # 40 pcs / 16 months = 2.5 > 1; 8 pcs = 0.5 <= 1
    res = run_plan(df, _EMPTY_OV, _params(df, n_supply_points=2))
    t = _t003(res.work)
    assert list(t["SystemCategory"]) == ["KTC", "KTC"]
    sp2 = t.iloc[1]
    assert sp2["CabinetType"] == "Carousel"
    assert int(sp2["Carousel_stockpiles"]) >= 3               # its own share, min allocation
    assert "another supply point" in sp2["SystemCategory_Reason"]
    assert res.shared_ktc_copies == 1
    assert res.integrity.ok, res.integrity.violations


def test_a_shared_article_below_the_threshold_everywhere_stays_kanban():
    df = _shared_frame(cons_sp1=8.0, cons_sp2=8.0)
    res = run_plan(df, _EMPTY_OV, _params(df, n_supply_points=2))
    assert list(_t003(res.work)["SystemCategory"]) == ["Kanban", "Kanban"]
    assert res.shared_ktc_copies == 0


def test_without_the_flag_nothing_changes():
    df = _shared_frame(flag=False)
    res = run_plan(df, _EMPTY_OV, _params(df, n_supply_points=2))
    assert list(_t003(res.work)["SystemCategory"]) == ["KTC", "Kanban"]
    assert res.shared_ktc_copies == 0


def test_the_rule_also_holds_in_the_fixed_configuration():
    df = _shared_frame()
    res = run_plan(df, _EMPTY_OV, _params(
        df, n_supply_points=2, op_mode="Fixed",
        fixed_machines=((1, 1, 1, 0, 0, 0), (2, 0, 1, 0, 0, 0))))
    t = _t003(res.work)
    assert list(t["SystemCategory"]) == ["KTC", "KTC"]
    assert set(t["Placement_Status"]) <= {"Placed", "Moved"}


def test_a_bulk_routed_copy_follows_its_ktc_sibling():
    df = _shared_frame()
    work = df.assign(SystemCategory="Kanban", CabinetType="Kanban", Spirals_needed=0,
                     Carousel_stockpiles=0, Spiral_capacity=pd.NA, VendMode="Vending",
                     VendBlockReason="", SystemCategory_Reason="",
                     Monthly_packs=0.5, Monthly_pcs=0.5, Target_packs=0.3)
    first = work.index[work["Code"] == "T003"][0]
    work.loc[first, ["SystemCategory", "CabinetType"]] = ["KTC", "Helix"]
    second = work.index[work["Code"] == "T003"][1]
    work.loc[second, ["VendMode", "VendBlockReason"]] = ["Bulk/Kanban", "bulk-family:x"]
    n = ml.harmonize_shared_system(work, **_SIZING)
    assert n == 1
    assert work.loc[second, "SystemCategory"] == "KTC"
    assert work.loc[second, "VendMode"] == "Vending"
    assert work.loc[second, "VendBlockReason"] == ""
    # rows that are not shared keep their routing
    assert (work.loc[work["Code"] != "T003", "SystemCategory"] == "Kanban").all()


def test_harmonize_without_the_column_does_nothing():
    df = _shared_frame(flag=False)
    before = df.copy()
    assert ml.harmonize_shared_system(df, **_SIZING) == 0
    pd.testing.assert_frame_equal(df, before)


# ---- the invariant -----------------------------------------------------------------------------

def test_the_invariant_flags_an_article_that_is_ktc_and_kanban():
    df = pd.DataFrame({"Listing": ["Tools"] * 3, "Code": ["X", "X", "Y"],
                       "SupplyPoint": [1, 2, 1], "SystemCategory": ["KTC", "Kanban", "KTC"],
                       ml.SHARED_COL: [True, True, False]})
    assert check_shared_article_system(df)
    df.loc[1, "SystemCategory"] = "KTC"
    assert check_shared_article_system(df) == []
    assert check_shared_article_system(df.drop(columns=[ml.SHARED_COL])) == []


def test_verify_plan_runs_the_check_only_with_the_column():
    df = pd.DataFrame({"Listing": ["Tools"] * 2, "Code": ["X", "X"],
                       "SupplyPoint": [1, 2], "SystemCategory": ["KTC", "Kanban"],
                       ml.SHARED_COL: [True, True]})
    assert "shared_article_system" in verify_plan(df).checks
    assert "shared_article_system" not in verify_plan(df.drop(columns=[ml.SHARED_COL])).checks


# ---- the run fingerprint ------------------------------------------------------------------------

def _fp(**kw):
    d = dict(_BASE)
    d.update(kw)
    return compute_run_fingerprint(FingerprintInputs(**d))


def test_the_fingerprint_is_unchanged_without_the_option():
    assert _fp() == GOLDEN
    assert _fp(full_consumption_shared=False) == GOLDEN


def test_the_full_consumption_option_moves_the_fingerprint():
    assert _fp(full_consumption_shared=True) != GOLDEN


def test_the_option_counts_only_with_the_programme_mapping():
    off = dict(program_mapping_active=False)
    assert _fp(full_consumption_shared=True, **off) == _fp(**off)


def test_a_machine_set_to_not_planned_moves_the_fingerprint():
    assert _fp(program_to_sp_map={"P1": 1, "P2": 0}) != GOLDEN


# ---- the per-supply-point summary lists machines ---------------------------------------------

def test_the_per_sp_summary_lists_machines_and_skips_not_planned():
    work = pd.DataFrame({"SupplyPoint": [1, 2], "Code": ["X", "X"],
                         "Consumption_pcs": [5.0, 5.0], "Monthly_pcs": [1.0, 1.0]})
    plans = [("SP 1", {}), ("SP 2", {}), ("Grand total", {"total_cabs": 0})]
    compact, _detail = build_per_sp_summary(
        work, plans, {"AB-100": 1, "AB-101": 2, "AB-102": 0}, 0.0)
    assert list(compact["Programmes (first 5)"])[:2] == ["AB-100", "AB-101"]
    assert list(compact["# programmes"]) == [1, 1, 2]


@pytest.mark.parametrize("value", [1, 2, 0])
def test_the_summary_accepts_every_mapping_value(value):
    work = pd.DataFrame({"SupplyPoint": [1], "Code": ["X"], "Consumption_pcs": [1.0],
                         "Monthly_pcs": [1.0]})
    build_per_sp_summary(work, [("All", {})], {"AB-100": value}, 0.0)


# ---- through the workbook --------------------------------------------------------------------

def test_every_sheet_shows_one_number_per_shared_article():
    from tests.test_takeover_wiring import _sheet, _workbook

    df = _shared_frame()
    df["ToolClass"] = "solid_carbide_drill"
    df["Stock_pcs"] = 4.0
    df[ml.ARTICLE_STOCK_COL] = df["Stock_pcs"]
    df.loc[df["Code"] == "T003", ml.ARTICLE_STOCK_COL] = 8.0
    res = run_plan(df, _EMPTY_OV, _params(df, n_supply_points=2, helix_threshold=30.0,
                                          enable_rebalancer=False))
    assert {"Helix", "Carousel"} <= set(res.work["CabinetType"])
    raw = _workbook(res)                     # asserts the export verification passed
    result = _sheet(raw, "Result")
    want = dict(zip(zip(result["Code"].astype(str), result["SupplyPoint"]),
                    result["Kromi_Art_No"].astype(str)))
    assert len({want[k] for k in want if k[0] == "T003"}) == 1
    # every sheet shows the Result sheet's number (cut from the whole plan)
    for sheet in ("KTC_only", "Kanban_only", "Helix_only", "Carousel_only"):
        frame = _sheet(raw, sheet)
        for code, sp, number in zip(frame["Code"].astype(str), frame["SupplyPoint"],
                                    frame["Kromi_Art_No"].astype(str)):
            assert number == want[(code, sp)], (sheet, code, sp)
    setup = _sheet(raw, "Article setup")
    assert (setup["Customer article No"].astype(str) == "T003").sum() == 2   # KTC pair
    sheets = [_sheet(raw, f"Takeover sheet SP {sp}") for sp in (1, 2)]
    lines = [s[s["Kunden Art. Nr."].astype(str) == "T003"] for s in sheets]
    assert all(len(line) == 1 for line in lines)
    assert sum(float(line["Total"].iloc[0]) for line in lines) == 8.0
