"""Fixed-configuration operating mode (v34.52).

The machines already exist: per supply point the user states how many Helix,
Carousel and Locker cabinets stand there and how much headroom to keep free.
The planner fits the article list into that space instead of sizing cabinets.

Owner decisions pinned here:
* demand per article follows the existing routing and sizing rules;
* the most used articles are placed first (monthly pieces, then packs, then
  code), and the ones that do not fit are flagged "Not placed", never dropped;
* the headroom is left empty (usable = floor(physical x (100 - headroom) %));
* overflow may move to another machine type the article physically fits
  (S/M Carousel -> Helix, Helix -> Carousel, a locker to larger compartments),
  switchable; technician cabinet overrides never move.
"""

import math

import pandas as pd
import pytest

from engine.fixed_config import (
    FIXED_MODE, STATUS_MOVED, STATUS_NOT_PLACED, STATUS_PLACED, MachineSet,
    fit_fixed_configuration, fixed_plan_for_subset, machines_by_sp,
    physical_capacity, usable_capacity,
)
from engine.cabinet_math import _force_carousel_resources, _force_helix_resources

_KW = dict(helix_overfill_factor=1.10, min_carousel_compartments=3,
           carousel_reserve_factor=0.85)


def _row(code, cab, pcs, *, size="M", spirals=0, stock=0, system="KTC",
         packs=None, pcat="drills", restock=0, override_fields=""):
    packs = pcs if packs is None else packs
    if cab == "Helix" and not spirals:
        spirals = 1
    if cab == "Carousel" and not stock:
        stock = 3
    return {
        "Code": code, "Description": f"Article {code}", "SystemCategory": system,
        "CabinetType": cab if system == "KTC" else "Kanban",
        "SizeCategory": size, "ProductCategory": pcat,
        "Monthly_pcs": float(pcs), "Monthly_packs": float(packs),
        "Target_packs": float(packs) * 0.66, "Consumption_pcs": float(pcs) * 12,
        "Spiral_capacity": 22 if cab == "Helix" else pd.NA,
        "Spirals_needed": int(spirals) if system == "KTC" else 0,
        "Carousel_stockpiles": int(stock) if system == "KTC" else 0,
        "Regrind": False,
        "Restockable": bool(restock), "Restock_slots": int(restock),
        "Restock_target": ("Carousel" if cab in ("Helix", "Carousel") else cab) if restock else "",
        "Override_Applied": bool(override_fields),
        "Override_Fields": override_fields,
    }


def _frame(rows):
    return pd.DataFrame(rows, index=[f"r{i}" for i in range(len(rows))])


def _fit(df, machines, headroom=0.0, **kw):
    args = dict(_KW)
    args.update(kw)
    return fit_fixed_configuration(df, machines, headroom, **args)


# ---- capacity ---------------------------------------------------------------

def test_mode_token():
    assert FIXED_MODE == "Fixed"


def test_physical_and_usable_capacity():
    m = MachineSet(helix=2, carousel=1, locker_a=1)
    assert physical_capacity(m) == {"Helix": 140, "Carousel": 720, "Locker A": 48,
                                    "Locker B": 0, "Locker C": 0}
    assert usable_capacity(m, 10) == {"Helix": 126, "Carousel": 648, "Locker A": 43,
                                      "Locker B": 0, "Locker C": 0}
    assert usable_capacity(m, 0) == physical_capacity(m)


def test_headroom_is_clamped():
    m = MachineSet(helix=1)
    assert usable_capacity(m, -5)["Helix"] == 70
    assert usable_capacity(m, 500)["Helix"] == math.floor(70 * 0.10 + 1e-9)


def test_machines_by_sp_parses_tuples():
    got = machines_by_sp([(1, 2, 1, 0, 0, 0), (2, 1, 1, 0, 0, 0)])
    assert got[1] == MachineSet(helix=2, carousel=1)
    assert got[2] == MachineSet(helix=1, carousel=1)


# ---- priority and flagging --------------------------------------------------

def test_most_used_first_and_the_rest_flagged():
    df = _frame([
        _row("LOW", "Carousel", 1, stock=300),
        _row("TOP", "Carousel", 50, stock=300),
        _row("MID", "Carousel", 10, stock=300),
    ])
    out, rep = _fit(df, MachineSet(carousel=1), headroom=10)   # 648 usable
    st = out.set_index("Code")["Placement_Status"]
    assert st["TOP"] == STATUS_PLACED and st["MID"] == STATUS_PLACED
    assert st["LOW"] == STATUS_NOT_PLACED
    rank = out.set_index("Code")["Placement_Rank"]
    assert (rank["TOP"], rank["MID"], rank["LOW"]) == (1, 2, 3)
    assert rep["used"]["Carousel"] == 600 and rep["not_placed"] == 1
    note = out.set_index("Code").loc["LOW", "Placement_Note"]
    assert "Carousel" in note and "48" in note        # needs 300, 48 free


def test_ties_break_by_packs_then_code():
    df = _frame([
        _row("B", "Helix", 5, packs=5),
        _row("A", "Helix", 5, packs=5),
        _row("C", "Helix", 5, packs=9),
    ])
    out, _ = _fit(df, MachineSet(helix=1))
    rank = out.set_index("Code")["Placement_Rank"]
    assert (rank["C"], rank["A"], rank["B"]) == (1, 2, 3)


def test_kanban_rows_are_not_placed_and_not_flagged():
    df = _frame([_row("K", "Kanban", 0.2, system="Kanban"), _row("H", "Helix", 9)])
    out, rep = _fit(df, MachineSet(helix=1))
    k = out.set_index("Code").loc["K"]
    assert k["Placement_Status"] == "" and pd.isna(k["Placement_Rank"])
    assert rep["placed"] == 1 and rep["not_placed"] == 0


def test_input_is_not_mutated():
    df = _frame([_row("A", "Carousel", 5, stock=900)])
    before = df.copy()
    _fit(df, MachineSet(carousel=1))
    pd.testing.assert_frame_equal(df, before)


# ---- moving overflow to another machine type -------------------------------------

def test_small_carousel_article_moves_to_helix_when_carousel_is_full():
    df = _frame([
        _row("BIG", "Carousel", 50, stock=720),
        _row("SMALL", "Carousel", 5, size="S", stock=3),
    ])
    out, rep = _fit(df, MachineSet(helix=1, carousel=1))
    s = out.set_index("Code").loc["SMALL"]
    assert s["Placement_Status"] == STATUS_MOVED
    assert s["CabinetType"] == "Helix" and s["Carousel_stockpiles"] == 0
    cap, spirals = _force_helix_resources(5.0, "S", "drills", 1.10, False)
    assert s["Spirals_needed"] == spirals and s["Spiral_capacity"] == cap
    assert rep["moved"] == 1 and rep["used"]["Helix"] == spirals


def test_large_carousel_article_cannot_move_to_helix_and_is_flagged_size_issue():
    df = _frame([
        _row("BIG", "Carousel", 50, stock=720),
        _row("LARGE", "Carousel", 5, size="L", stock=3),
    ])
    out, _ = _fit(df, MachineSet(helix=1, carousel=1))
    r = out.set_index("Code").loc["LARGE"]
    assert r["Placement_Status"] == STATUS_NOT_PLACED
    assert r["CabinetType"] == "Carousel"                  # routing kept
    assert bool(r["SizeIssue"]) is True                    # a Helix-fit would place it
    assert "size L" in r["Placement_Note"]


def test_size_hint_only_for_articles_the_leftover_helix_space_can_take():
    df = _frame([
        _row("BIG", "Carousel", 50, stock=720),
        _row("H", "Helix", 40, spirals=68),
        _row("L1", "Carousel", 9, size="L", stock=3, packs=9),
        _row("L2", "Carousel", 5, size="L", stock=3, packs=5),
    ])
    out, rep = _fit(df, MachineSet(helix=1, carousel=1))
    assert rep["free"]["Helix"] == 2
    flags = out.set_index("Code")["SizeIssue"]
    # Each needs 1 spiral as a Helix-fit M; two spirals are left, so both fit.
    assert bool(flags["L1"]) and bool(flags["L2"])
    out2, _ = _fit(df.assign(Spirals_needed=df["Spirals_needed"].where(df["Code"] != "H", 69)),
                   MachineSet(helix=1, carousel=1))
    flags2 = out2.set_index("Code")["SizeIssue"]
    assert bool(flags2["L1"]) and not bool(flags2["L2"])   # one spiral left: most used


def test_helix_article_moves_to_carousel_when_helix_is_full():
    df = _frame([
        _row("H1", "Helix", 90, spirals=70),
        _row("H2", "Helix", 40, spirals=2),
    ])
    out, rep = _fit(df, MachineSet(helix=1, carousel=1))
    r = out.set_index("Code").loc["H2"]
    assert r["Placement_Status"] == STATUS_MOVED and r["CabinetType"] == "Carousel"
    stock = _force_carousel_resources(r["Target_packs"], 3, 0.85)
    assert r["Carousel_stockpiles"] == stock and r["Spirals_needed"] == 0
    assert pd.isna(r["Spiral_capacity"])
    assert rep["used"]["Carousel"] == stock


def test_moving_can_be_switched_off():
    df = _frame([
        _row("H1", "Helix", 90, spirals=70),
        _row("H2", "Helix", 40, spirals=2),
    ])
    out, _ = _fit(df, MachineSet(helix=1, carousel=1), allow_spill=False)
    r = out.set_index("Code").loc["H2"]
    assert r["Placement_Status"] == STATUS_NOT_PLACED and r["CabinetType"] == "Helix"
    assert "switched off" in r["Placement_Note"]


def test_technician_cabinet_override_never_moves():
    df = _frame([
        _row("H1", "Helix", 90, spirals=70),
        _row("H2", "Helix", 40, spirals=2, override_fields="cabinet_type"),
    ])
    out, _ = _fit(df, MachineSet(helix=1, carousel=1))
    r = out.set_index("Code").loc["H2"]
    assert r["Placement_Status"] == STATUS_NOT_PLACED and r["CabinetType"] == "Helix"
    assert "override" in r["Placement_Note"].lower()


def test_locker_article_moves_only_to_larger_compartments():
    df = _frame([
        _row("C1", "Locker C", 5, size="XLS"),
        _row("A1", "Locker A", 5, size="XXL"),
    ])
    out, _ = _fit(df, MachineSet(locker_b=1))
    st = out.set_index("Code")
    assert st.loc["C1", "Placement_Status"] == STATUS_MOVED
    assert st.loc["C1", "CabinetType"] == "Locker B"
    assert st.loc["A1", "Placement_Status"] == STATUS_NOT_PLACED
    assert "no Locker A" in st.loc["A1", "Placement_Note"]


# ---- restock buffers -----------------------------------------------------------

def test_restock_buffer_takes_a_carousel_slot():
    df = _frame([_row("H", "Helix", 9, restock=1)])
    out, rep = _fit(df, MachineSet(helix=1, carousel=1))
    r = out.set_index("Code").loc["H"]
    assert r["Restock_slots"] == 1 and r["Restock_target"] == "Carousel"
    assert rep["used"]["Carousel"] == 1 and rep["buffers_dropped"] == 0


def test_restock_buffer_dropped_when_no_space_article_still_placed():
    df = _frame([_row("H", "Helix", 9, restock=1)])
    out, rep = _fit(df, MachineSet(helix=1))                  # no Carousel at all
    r = out.set_index("Code").loc["H"]
    assert r["Placement_Status"] == STATUS_PLACED
    assert r["Restock_slots"] == 0 and r["Restock_target"] == ""
    assert "buffer" in r["Placement_Note"].lower()
    assert rep["buffers_dropped"] == 1


def test_not_placed_rows_reserve_no_buffer():
    df = _frame([_row("C", "Carousel", 9, stock=800, restock=1)])
    out, _ = _fit(df, MachineSet(carousel=1))
    r = out.set_index("Code").loc["C"]
    assert r["Placement_Status"] == STATUS_NOT_PLACED
    assert r["Restock_slots"] == 0 and r["Restock_target"] == ""


# ---- the bucket plan --------------------------------------------------------------

def test_plan_reports_configured_machines_and_placed_use():
    df = _frame([
        _row("TOP", "Carousel", 50, stock=600),
        _row("H", "Helix", 20, spirals=3, restock=1),
        _row("LOW", "Carousel", 1, stock=300, size="L"),
        _row("K", "Kanban", 0.1, system="Kanban"),
    ])
    out, rep = _fit(df, MachineSet(helix=2, carousel=1), headroom=10)
    plan = fixed_plan_for_subset(out, rep, overfill_factor=1.10)
    assert plan["helix_cabs"] == plan["helix_cabs_base"] == 2
    assert plan["car_cabs"] == plan["car_cabs_base"] == 1
    assert plan["total_cabs"] == plan["total_cabs_base"] == 3
    assert plan["total_spirals"] == plan["total_spirals_buf"] == rep["used"]["Helix"] == 3
    assert plan["car_slots"] == plan["car_slots_buf"] == rep["used"]["Carousel"] == 601
    assert plan["restock_car_slots"] == 1
    assert plan["ktc_count"] == 3 and plan["kanban_count"] == 1 and plan["rows_total"] == 4
    assert plan["carousel_refs"] == 1                       # LOW is not in a machine
    assert plan["fixed_config"]["not_placed"] == 1
    assert plan["carousel_cap_exceeded_by_restock"] is False
    for t, used in rep["used"].items():
        assert used <= rep["usable"][t]


# ---- run_plan in fixed mode ------------------------------------------------------

from engine.plan import run_plan  # noqa: E402
from tests.test_run_plan_equivalence import _boundary_frame, _params  # noqa: E402

_EMPTY_OV = pd.DataFrame()


def _fixed_params(df, **kw):
    base = dict(op_mode=FIXED_MODE, fixed_machines=((1, 1, 1, 0, 0, 0),),
                fixed_headroom_pct=10.0, fixed_allow_spill=True)
    base.update(kw)
    return _params(df, **base)


def test_run_plan_places_per_supply_point():
    df = _boundary_frame()
    df["SupplyPoint"] = [1] * 7 + [2] * 7
    p = _fixed_params(df, n_supply_points=2,
                      fixed_machines=((1, 1, 1, 0, 0, 0), (2, 0, 1, 0, 0, 1)))
    res = run_plan(df, _EMPTY_OV, p)
    labels = [lbl for lbl, _ in res.bucket_plans]
    assert labels == ["SP 1", "SP 2"]
    sp1, sp2 = (plan for _, plan in res.bucket_plans)
    assert (sp1["helix_cabs"], sp1["car_cabs"], sp1["cabC"]) == (1, 1, 0)
    assert (sp2["helix_cabs"], sp2["car_cabs"], sp2["cabC"]) == (0, 1, 1)
    assert res.grand["total_cabs"] == 4
    assert res.rebalance_audit == []
    assert res.integrity.ok, res.integrity.violations
    ktc = res.work[res.work["SystemCategory"] == "KTC"]
    assert set(ktc["Placement_Status"]) <= {STATUS_PLACED, STATUS_MOVED, STATUS_NOT_PLACED}
    assert (res.work.loc[res.work["SystemCategory"] == "Kanban", "Placement_Status"] == "").all()


def test_run_plan_fixed_mode_plans_listings_together():
    df = _boundary_frame(with_ppe=True)
    res = run_plan(df, _EMPTY_OV, _fixed_params(df, calc_mode_separated=True))
    assert res.listings == ()
    assert [lbl for lbl, _ in res.bucket_plans] == ["All"]


def test_buffer_and_consolidation_do_not_apply_in_fixed_mode():
    df = _boundary_frame()
    a = run_plan(df, _EMPTY_OV, _fixed_params(df, capacity_buffer_pct=0.0,
                                              enable_rebalancer=False))
    b = run_plan(df, _EMPTY_OV, _fixed_params(df, capacity_buffer_pct=80.0,
                                              enable_rebalancer=True))
    assert a.bucket_plans == b.bucket_plans
    pd.testing.assert_frame_equal(a.work, b.work)


def test_zero_machines_flags_every_vending_article():
    df = _boundary_frame()
    res = run_plan(df, _EMPTY_OV, _fixed_params(df, fixed_machines=()))
    ktc = res.work[res.work["SystemCategory"] == "KTC"]
    assert len(ktc) > 0
    assert (ktc["Placement_Status"] == STATUS_NOT_PLACED).all()
    assert res.grand["total_cabs"] == 0
    assert res.integrity.ok, res.integrity.violations


def test_other_modes_carry_no_placement_columns():
    df = _boundary_frame()
    for mode in ("", "Helix", "Carousel", "Capped"):
        res = run_plan(df, _EMPTY_OV, _params(df, op_mode=mode))
        assert "Placement_Status" not in res.work.columns, mode
        assert all("fixed_config" not in plan for _, plan in res.bucket_plans), mode


def test_fixed_run_is_deterministic_and_picklable():
    import pickle
    df = _boundary_frame()
    p = _fixed_params(df)
    a = run_plan(df, _EMPTY_OV, p)
    b = run_plan(df, _EMPTY_OV, p)
    pd.testing.assert_frame_equal(a.work, b.work)
    assert a.bucket_plans == b.bucket_plans
    pickle.loads(pickle.dumps(a))
