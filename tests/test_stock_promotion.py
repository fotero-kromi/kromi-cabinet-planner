"""Stock-based Helix promotion (v34.58, fixed configuration only).

Onboarding lists often lack consumption for articles the customer clearly
uses: a large stock on hand hints at a high use the Carousel minimum (a few
compartments) cannot serve. With the rule on, after the normal fit, the Helix
space still free (the headroom stays empty) takes the Carousel articles whose
stock implies the highest demand:

* implied monthly packs = stock / VPE / "stock covers (months)";
* a candidate is a KTC article placed in a Carousel, of a size a spiral takes
  (S or M, as for the overflow move), without a technician cabinet override,
  whose implied demand is above the Helix threshold and above its recorded
  demand;
* highest implied demand first; each gets the spirals the normal Helix sizing
  gives for that demand, or is skipped when they do not fit;
* the Carousel compartments it frees go to articles that found no space,
  most used first;
* only the cabinet type, the spirals and so the takeover maximum change; the
  rule is off by default and inert without a stock column.
"""
import pandas as pd
import pytest

from engine.cabinet_math import _force_helix_resources
from engine.fixed_config import (
    STATUS_NOT_PLACED, STATUS_PLACED, STATUS_PROMOTED, MachineSet, fit_fixed_configuration,
    run_meta_rows,
)
from engine.takeover import STOCK_COL, build_takeover_frames

_KW = dict(helix_overfill_factor=1.10, min_carousel_compartments=3,
           carousel_reserve_factor=0.85)


def _row(code, cab="Carousel", *, pcs=1.0, size="S", stock_pcs=0.0, vpe=1.0,
         spirals=0, slots=3, override_fields="", system="KTC"):
    packs = pcs / vpe
    return {
        "Code": code, "Description": f"Article {code}", "SystemCategory": system,
        "CabinetType": cab if system == "KTC" else "Kanban", "SizeCategory": size,
        "ProductCategory": "drills", "PackUnits": vpe,
        "Monthly_pcs": float(pcs), "Monthly_packs": float(packs),
        "Target_packs": float(packs) * 0.4, "Consumption_pcs": float(pcs) * 12,
        "Spiral_capacity": 28 if cab == "Helix" else pd.NA,
        "Spirals_needed": (spirals or 1) if cab == "Helix" else 0,
        "Carousel_stockpiles": slots if cab == "Carousel" else 0,
        "Regrind": False, "Override_Applied": bool(override_fields),
        "Override_Fields": override_fields, STOCK_COL: float(stock_pcs),
    }


def _frame(*rows):
    return pd.DataFrame(list(rows), index=[f"r{i}" for i in range(len(rows))])


def _fit(df, machines=MachineSet(helix=1, carousel=1), headroom=0.0, *, months=3.0,
         threshold=6.0, **kw):
    args = dict(_KW)
    args.update(kw)
    return fit_fixed_configuration(df, machines, headroom, stock_promotion_months=months,
                                   helix_threshold=threshold, **args)


def _at(out, code):
    return out[out["Code"] == code].iloc[0]


# ---- off / inert -----------------------------------------------------------------

def test_off_by_default_nothing_changes():
    df = _frame(_row("A", stock_pcs=300.0), _row("B", "Helix", pcs=50.0))
    base_out, base_rep = fit_fixed_configuration(df, MachineSet(helix=1, carousel=1), 0.0, **_KW)
    off_out, off_rep = _fit(df, months=0.0)
    pd.testing.assert_frame_equal(base_out, off_out)
    assert base_rep == off_rep
    assert _at(off_out, "A")["CabinetType"] == "Carousel"


def test_without_a_stock_column_the_rule_is_inert():
    df = _frame(_row("A", stock_pcs=300.0)).drop(columns=[STOCK_COL])
    out, rep = _fit(df)
    assert _at(out, "A")["CabinetType"] == "Carousel"
    assert rep["promoted"] == 0


# ---- the promotion ---------------------------------------------------------------------

def test_high_stock_carousel_article_moves_into_the_free_helix():
    df = _frame(_row("A", pcs=0.5, stock_pcs=90.0))
    out, rep = _fit(df)
    a = _at(out, "A")
    implied = 90.0 / 1.0 / 3.0
    cap, spirals = _force_helix_resources(implied, "S", "drills", 1.10)
    assert a["CabinetType"] == "Helix"
    assert a["Placement_Status"] == STATUS_PROMOTED
    assert int(a["Spirals_needed"]) == spirals and int(a["Spiral_capacity"]) == cap
    assert int(a["Carousel_stockpiles"]) == 0
    assert "90" in a["Placement_Note"] and "3 months" in a["Placement_Note"]
    assert rep["promoted"] == 1 and rep["placed"] == 1
    assert rep["used"]["Helix"] == spirals and rep["used"]["Carousel"] == 0


def test_the_packaging_unit_counts():
    """300 pieces in packs of 10 over 3 months are 10 packs a month: above 6."""
    df = _frame(_row("A", pcs=5.0, vpe=10.0, stock_pcs=300.0),
                _row("B", pcs=5.0, vpe=10.0, stock_pcs=150.0))
    out, _ = _fit(df)
    assert _at(out, "A")["Placement_Status"] == STATUS_PROMOTED
    assert _at(out, "B")["Placement_Status"] == STATUS_PLACED


def test_only_the_free_helix_space_is_used_and_the_headroom_stays():
    # 90 % headroom leaves 7 of 70 spirals; the Helix article takes 5.
    df = _frame(_row("H", "Helix", pcs=500.0, spirals=5),
                _row("A", pcs=0.1, stock_pcs=600.0),     # needs more spirals than left
                _row("B", pcs=0.1, stock_pcs=60.0))      # needs 1
    out, rep = _fit(df, headroom=90.0)
    assert _at(out, "A")["CabinetType"] == "Carousel"      # skipped, not stopped
    assert _at(out, "B")["Placement_Status"] == STATUS_PROMOTED
    assert rep["used"]["Helix"] <= rep["usable"]["Helix"] == 7


def test_highest_stock_demand_first():
    # 90 % headroom leaves 7 spirals; the Helix article takes 6, so only one
    # of the two candidates (one spiral each) fits.
    df = _frame(_row("LOW", pcs=0.1, stock_pcs=60.0), _row("HIGH", pcs=0.1, stock_pcs=80.0),
                _row("H", "Helix", pcs=500.0, spirals=6))
    out, _ = _fit(df, headroom=90.0)
    assert _at(out, "HIGH")["Placement_Status"] == STATUS_PROMOTED
    assert _at(out, "LOW")["CabinetType"] == "Carousel"


@pytest.mark.parametrize("row", [
    _row("A", pcs=0.1, stock_pcs=15.0),                # 5 packs/month: not above 6
    _row("A", pcs=40.0, stock_pcs=60.0),               # recorded use already higher
    _row("A", pcs=0.1, stock_pcs=300.0, size="L"),     # too large for a spiral
    _row("A", pcs=0.1, stock_pcs=300.0, override_fields="cabinet_type"),
])
def test_articles_that_stay_in_the_carousel(row):
    out, rep = _fit(_frame(row))
    assert _at(out, "A")["CabinetType"] == "Carousel"
    assert rep["promoted"] == 0


def test_articles_without_space_are_not_promoted():
    df = _frame(_row("A", pcs=0.1, stock_pcs=300.0))
    out, _ = _fit(df, machines=MachineSet(helix=1, carousel=0))
    # No Carousel: the S article moved into the Helix by the normal overflow rule.
    assert _at(out, "A")["Placement_Status"] != STATUS_PROMOTED


def test_freed_carousel_space_places_an_article_that_had_none():
    """The promoted article leaves its compartments; a not-placed Carousel
    article takes them (most used first) and the report counts it."""
    # 90 % headroom: 72 Carousel slots, 7 spirals.
    rows = [_row(f"C{i:02d}", pcs=10.0 - i * 0.1, slots=3) for i in range(23)]  # 69 slots
    rows.append(_row("PROMO", pcs=5.0, stock_pcs=90.0, slots=3))    # placed (72 used)
    rows.append(_row("BIG", pcs=0.005, size="L", slots=3))          # no room left
    out, rep = _fit(_frame(*rows), headroom=90.0)
    assert _at(out, "PROMO")["Placement_Status"] == STATUS_PROMOTED
    big = _at(out, "BIG")
    assert big["Placement_Status"] == STATUS_PLACED
    assert "freed" in big["Placement_Note"]
    assert rep["not_placed"] == 0 and rep["placed_in_freed"] == 1


def test_the_takeover_maximum_follows_the_promotion():
    df = _frame(_row("A", pcs=0.5, stock_pcs=90.0))
    df["Listing"], df["SupplyPoint"], df["Kromi_Art_No"] = "Tools", 1, "140100001000"
    before, _ = fit_fixed_configuration(df, MachineSet(helix=1, carousel=1), 0.0, **_KW)
    after, _ = _fit(df)
    t0 = dict(build_takeover_frames(before))[1].iloc[0]
    t1 = dict(build_takeover_frames(after))[1].iloc[0]
    assert (t0["im KTC"], t1["im KTC"]) == (3, 28)      # 3 compartments -> 1 spiral x 28
    assert t1["Schranktyp"] == "Helix"


def test_run_metadata_names_the_rule_only_when_on():
    df = _frame(_row("A", pcs=0.5, stock_pcs=90.0))
    _, rep_off = fit_fixed_configuration(df, MachineSet(helix=1, carousel=1), 0.0, **_KW)
    _, rep_on = _fit(df)
    plan = {"fixed_config": None}
    keys_off = [r["Key"] for r in run_meta_rows([("SP 1", {**plan, "fixed_config": rep_off})])]
    rows_on = run_meta_rows([("SP 1", {**plan, "fixed_config": rep_on})])
    assert not [k for k in keys_off if "promotion" in k.lower()]
    on = {r["Key"]: r["Value"] for r in rows_on}
    assert on["Stock-based Helix promotion"] == "on (stock covers 3 months)"
    assert on["Articles promoted to the Helix (stock)"] == 1


# ---- plan and settings -----------------------------------------------------------------

def test_plan_params_carry_the_rule():
    from engine.fixed_config import FIXED_MODE
    from engine.plan import run_plan
    from tests.test_run_plan_equivalence import _boundary_frame, _params
    df = _boundary_frame()
    df[STOCK_COL] = 0.0
    df.loc[df["Code"] == "T003", STOCK_COL] = 300.0      # drill, S, low recorded use
    common = dict(op_mode=FIXED_MODE, fixed_machines=((1, 1, 1, 0, 0, 0),),
                  fixed_headroom_pct=10.0)
    off = run_plan(df, pd.DataFrame(), _params(df, **common)).work
    on = run_plan(df, pd.DataFrame(), _params(
        df, fixed_stock_promotion_months=3.0, **common)).work
    assert off.loc[off["Code"] == "T003", "CabinetType"].iloc[0] == "Carousel"
    assert on.loc[on["Code"] == "T003", "Placement_Status"].iloc[0] == STATUS_PROMOTED


def test_the_settings_are_restorable():
    from engine.run_restore import CONTROL_KEYS
    assert {"ks_fixed_stock_promo", "ks_fixed_stock_months"} <= set(CONTROL_KEYS)


def test_page_applies_the_rule_and_it_moves_the_fingerprint_only_when_on(monkeypatch, tmp_path):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    import engine.plan as plan_mod
    from engine.run_restore import build_seed
    from tests._paths import PLANNER_PAGE
    from io import BytesIO
    from tests.test_takeover_wiring import _kds_like_bytes

    captured = {}
    orig = plan_mod.run_plan

    def spy(work, ov, params):
        res = orig(work, ov, params)
        captured["res"] = res
        return res
    monkeypatch.setattr(plan_mod, "run_plan", spy)
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "promo.db"))
    st.cache_data.clear()
    raw, cols = _kds_like_bytes()
    src = pd.read_excel(BytesIO(raw), sheet_name="Tabelle1")
    src.loc[src[cols[0]] == "60F0003", cols[5]] = 90     # M mill, 2 pcs/month recorded
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        src.to_excel(w, index=False, sheet_name="Tabelle1")
    raw = bio.getvalue()
    seed = build_seed({"cm_code": cols[0], "cm_desc1": cols[2], "cm_cons": cols[3],
                       "ks_sheet_tools": "Tabelle1",
                       "ks_op_mode": "Fixed configuration (existing machines)",
                       "ks_fixed_helix_1": 1, "ks_fixed_carousel_1": 1,
                       "ks_consumption_months": 12.0, "ks_helix_threshold": 6.0,
                       "ks_fixed_stock_promo": True, "ks_fixed_stock_months": 3.0}, cols)
    seed.update({"ks_hide_optional": False, "ks_ai_colmap": False,
                 "_std_special_mapped": False})
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 0, "bytes": raw, "filename": "kds.xlsx", "customer": "PrC",
        "site": "PrS", "classifications": {}, "override_mode": "none",
        "override_set_id": None}
    at.session_state["_pending_restore"] = seed
    at.run()
    at.selectbox(key="cm_prod").select(cols[1])
    at.selectbox(key="cm_pack").select(cols[4])
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception
    w = captured["res"].work.set_index("Code")
    assert w.loc["60F0003", "Placement_Status"] == STATUS_PROMOTED    # 90 pcs / 3 months
    assert w.loc["60F0003", "CabinetType"] == "Helix"
    assert w.loc["60B0002", "CabinetType"] == "Carousel"                # size L stays
    assert "Stock-based Helix promotion" in " ".join(str(c.value) for c in at.caption)
    fp_on = at.session_state["_run_fingerprint"]
    at.checkbox(key="ks_fixed_stock_promo").uncheck()
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["has_results"] is False     # the change invalidates results
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception
    fp_off = at.session_state["_run_fingerprint"]
    assert fp_off != fp_on
    assert (((1, 1, 1, 0, 0, 0),), 10.0, True) in fp_off     # the v34.57 fixed settings
    w = captured["res"].work.set_index("Code")
    assert w.loc["60F0003", "CabinetType"] == "Carousel"
