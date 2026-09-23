"""Contract for restocking handling, stage 1 (v34.24).

A per-item boolean Restockable, sourced from a mapped yes/no column
(Provided) or from a configurable set of product categories (Rule), reserves
one buffer compartment for the item: coil cabinets cannot restock, so a Helix
item buffers in a Carousel, while Carousel and Locker items buffer in their
own cabinet class. Restocking is a vending concept: only KTC rows in a
cabinet participate, so a Kanban-routed row never carries a buffer, and an
override that moves a flagged item to Kanban drops the allocation. Buffers
ride the frame as a separate slot column, so the spill and rebalance logic
never sees them as movable material, and one buffer slot alone forces the
first Carousel through the ordinary ceiling math. The Helix operational mode
is incompatible with restocking and makes the whole segment inert.
"""

from pathlib import Path

import pandas as pd
import pytest

from engine.cabinet_math import (
    CAROUSEL_SLOTS_PER_CAB,
    compute_carousel_needs,
    compute_locker_needs,
    compute_plan_for_subset,
)
from engine.plan import run_plan, run_restock_segment
from engine.preprocessing import normalize_restock_flag
from tests.test_run_plan_equivalence import _boundary_frame, _params
from tests._paths import PLANNER_PAGE


# ---- value normalization -------------------------------------------------

@pytest.mark.parametrize("raw", ["yes", "Y", "JA", "j", "1", "x", "true", "WAHR", " Ja "])
def test_normalize_truthy(raw):
    assert normalize_restock_flag(raw) is True


@pytest.mark.parametrize("raw", ["no", "N", "nein", "0", "false", "falsch", "", "  ", None])
def test_normalize_falsy(raw):
    assert normalize_restock_flag(raw) is False


def test_normalize_unknown_is_none():
    assert normalize_restock_flag("maybe") is None
    assert normalize_restock_flag("2") is None


# ---- the segment ----------------------------------------------------------

def _row(system="KTC", cabinet="Helix", category="inserts", provided=None):
    r = {"SystemCategory": system, "CabinetType": cabinet, "ProductCategory": category}
    if provided is not None:
        r["Restocking"] = provided
    return r


def _seg(rows, categories=(), op_mode=""):
    df = pd.DataFrame(rows)
    return run_restock_segment(df, restock_categories=tuple(categories), op_mode=op_mode)


def test_provided_beats_rule_and_default():
    out, info = _seg([_row(provided="no", category="inserts"),
                      _row(provided="yes", category="mills"),
                      _row(category="mills")], categories=("inserts",))
    assert list(out["Restockable"]) == [False, True, False]
    assert list(out["Restockable_Source"]) == ["Provided", "Provided", ""]
    assert info["provided_true"] == 1 and info["rule_true"] == 0


def test_rule_by_category_when_no_column():
    out, info = _seg([_row(category="inserts"), _row(category="taps")],
                     categories=("inserts",))
    assert list(out["Restockable"]) == [True, False]
    assert out.loc[0, "Restockable_Source"] == "Rule"
    assert info["rule_true"] == 1


def test_targets_follow_the_cabinet_family():
    out, _ = _seg([_row(cabinet="Helix", provided="yes"),
                   _row(cabinet="Carousel", provided="yes"),
                   _row(cabinet="Locker B", provided="yes")])
    assert list(out["Restock_target"]) == ["Carousel", "Carousel", "Locker B"]
    assert list(out["Restock_slots"]) == [1, 1, 1]


def test_kanban_rows_never_carry_a_buffer():
    out, info = _seg([_row(system="Kanban", cabinet="Kanban", provided="yes")])
    assert int(out["Restock_slots"].sum()) == 0
    assert out.loc[0, "Restockable"] is True or bool(out.loc[0, "Restockable"])
    assert info["flagged_kanban"] == 1


def test_unknown_values_are_counted_and_false():
    out, info = _seg([_row(provided="maybe")])
    assert int(out["Restock_slots"].sum()) == 0
    assert info["unknown_values"] == 1


def test_helix_mode_makes_the_segment_inert():
    out, info = _seg([_row(provided="yes")], categories=("inserts",), op_mode="Helix")
    assert int(out["Restock_slots"].sum()) == 0
    assert info["inert_mode"] is True


# ---- buffer math ----------------------------------------------------------

def test_one_buffer_slot_forces_the_first_carousel():
    assert compute_carousel_needs(pd.DataFrame(), extra_slots=1)[1] == 1


def test_extra_slots_cross_the_capacity_boundary():
    df = pd.DataFrame({"Carousel_stockpiles": [CAROUSEL_SLOTS_PER_CAB - 1]})
    slots, cabs = compute_carousel_needs(df, extra_slots=2)
    assert slots == CAROUSEL_SLOTS_PER_CAB + 1 and cabs == 2


def test_locker_extras_per_class():
    df = pd.DataFrame({"CabinetType": ["Locker A", "Locker C"]})
    (cA, cabA), (cB, cabB), (cC, cabC) = compute_locker_needs(df, extras=(1, 0, 2))
    assert (cA, cB, cC) == (2, 0, 3)
    assert cabA >= 1 and cabB == 0 and cabC >= 1


def test_subset_plan_reads_the_buffer_columns():
    df = pd.DataFrame({
        "SystemCategory": ["KTC", "KTC"],
        "CabinetType": ["Helix", "Locker B"],
        "Spirals_needed": [3, 0],
        "Carousel_stockpiles": [0, 0],
        "Monthly_packs": [10.0, 1.0],
        "Consumption_pcs": [100.0, 10.0],
        "Restock_target": ["Carousel", "Locker B"],
        "Restock_slots": [1, 1],
    })
    plan = compute_plan_for_subset(df, 0.0)
    assert plan["car_slots"] == 1 and plan["car_cabs"] == 1, (
        "a lone Helix buffer must open the first Carousel"
    )
    assert plan["countB"] == 2, "the locker buffer joins its own class count"


# ---- run_plan integration -------------------------------------------------

def test_run_plan_applies_the_rule_end_to_end():
    import dataclasses
    df = _boundary_frame()
    base = _params(df)
    baseline = run_plan(df, (), base)
    ktc = baseline.work[
        (baseline.work["SystemCategory"] == "KTC")
        & (baseline.work["CabinetType"].isin(["Helix", "Carousel"]))
    ]
    assert len(ktc) > 0, "the equivalence frame must contain vending rows"
    cat = str(ktc.iloc[0]["ProductCategory"])

    params = dataclasses.replace(base, restock_categories=(cat,))
    result = run_plan(df, (), params)
    assert int(result.work["Restock_slots"].sum()) >= 1
    assert result.restock_info["rule_true"] >= 1
    base_car = sum(p.get("car_cabs", 0) for _, p in baseline.bucket_plans)
    got_car = sum(p.get("car_cabs", 0) for _, p in result.bucket_plans)
    assert got_car >= max(base_car, 1)


def test_vend_override_to_kanban_drops_the_allocation():
    import dataclasses
    from engine.constants import OVERRIDE_COLUMNS
    df = _boundary_frame()
    base = _params(df)
    probe = run_plan(df, (), base)
    ktc = probe.work[(probe.work["SystemCategory"] == "KTC")
                     & (probe.work["CabinetType"].isin(["Helix", "Carousel"]))]
    code = str(ktc.iloc[0]["Code"])
    cat = str(ktc.iloc[0]["ProductCategory"])

    ov = {c: "" for c in OVERRIDE_COLUMNS}
    ov.update({"code": code, "listing": "TOOLS", "vend_mode_override": "Bulk/Kanban"})
    params = dataclasses.replace(base, restock_categories=(cat,))
    result = run_plan(df, pd.DataFrame([ov], columns=OVERRIDE_COLUMNS), params)
    moved = result.work[result.work["Code"].astype(str) == code]
    assert int(moved["Restock_slots"].sum()) == 0, (
        "an override that routes the item to Kanban must drop its buffer"
    )


# ---- page-level drive -------------------------------------------------------

def test_page_drive_announces_reserved_buffers(monkeypatch, tmp_path):
    """A mapped restocking column drives the whole path: mapping restore,
    rename, segment, carousel forcing, and the results banner."""
    from io import BytesIO
    from engine.run_restore import build_seed

    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "rk.db"))
    rows = 6
    df = pd.DataFrame({
        "ItemCode": [f"S{i:03d}" for i in range(rows)],
        "ItemName": [f"Spiral tool {i}" for i in range(rows)],
        "Cons16": [(i + 1) * 8000.0 for i in range(rows)],
        "Restock": ["yes", "no", "yes", "", "ja", "nein"],
    })
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    raw_bytes = bio.getvalue()

    ui = {"cm_code": "ItemCode", "cm_desc1": "ItemName", "cm_cons": "Cons16",
          "cm_restock": "Restock", "ks_sheet_tools": "Sheet1"}
    restore = build_seed(ui, list(df.columns))
    restore["ks_hide_optional"] = False
    restore["ks_ai_colmap"] = False
    restore["_std_special_mapped"] = False

    import streamlit as st
    st.cache_data.clear()
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": raw_bytes, "filename": "input.xlsx",
        "customer": "TestCustomer", "site": "TestSite",
        "classifications": {}, "override_mode": "none", "override_set_id": None,
    }
    at.session_state["_pending_restore"] = restore
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    infos = " | ".join(str(i.value) for i in at.info)
    assert "Restocking:" in infos and "buffer compartment" in infos


# ---- stage 2: planogram and workbook visualization (v34.26) ----------------

def test_layout_item_kind_reaches_cells_and_sorts_last():
    from engine.layout import LayoutItem, allocate_for_type
    items = [
        LayoutItem(identifier="B1", cabinet_type="Carousel", compartments=2,
                   category="mills"),
        LayoutItem(identifier="A1 (R)", cabinet_type="Carousel", compartments=1,
                   category="inserts", kind="restock"),
        LayoutItem(identifier="A1", cabinet_type="Carousel", compartments=1,
                   category="inserts"),
    ]
    cabs = allocate_for_type(items, "Carousel")
    filled = [c for cab in cabs for c in cab.compartments if c.item_id]
    assert [c.item_id for c in filled] == ["A1", "B1", "B1", "A1 (R)"], (
        "buffers must sort after every regular item"
    )
    assert filled[-1].kind == "restock"
    assert all(c.kind is None for c in filled[:-1])


def test_restock_layout_items_builder():
    from engine.layout import restock_layout_items
    df = pd.DataFrame({
        "Code": ["T1", "T2", "T3"],
        "ProductCategory": ["inserts", "mills", "drills"],
        "Restock_target": ["Carousel", "Locker B", ""],
        "Restock_slots": [1, 1, 0],
    })
    items = restock_layout_items(df)
    assert [(i.identifier, i.cabinet_type, i.compartments, i.kind) for i in items] == [
        ("T1 (R)", "Carousel", 1, "restock"),
        ("T2 (R)", "Locker B", 1, "restock"),
    ]
    assert items[0].category == "inserts"


def test_restock_fill_is_blue_and_wins_over_confidence():
    from engine.layout import RESTOCK_FILL_HEX, fill_hex_for_cell, confidence_fill_hex
    assert RESTOCK_FILL_HEX == "4A90D2"
    assert fill_hex_for_cell("restock", "high") == RESTOCK_FILL_HEX
    assert fill_hex_for_cell(None, "high") == confidence_fill_hex("high")
    assert fill_hex_for_cell("", "low") == confidence_fill_hex("low")


def test_user_friendly_columns_carry_restocking():
    from engine.export_shaping import USER_FRIENDLY_COLS
    assert "Restockable" in USER_FRIENDLY_COLS
    assert "Restock_target" in USER_FRIENDLY_COLS


# ---- stage 3: hardening (v34.27) --------------------------------------------

def test_restock_frame_check_passes_and_fires():
    from engine.invariants import check_restock_frame
    good = pd.DataFrame({
        "SystemCategory": ["KTC", "KTC", "Kanban"],
        "CabinetType": ["Helix", "Locker B", "Kanban"],
        "Restockable": [True, True, True],
        "Restock_target": ["Carousel", "Locker B", ""],
        "Restock_slots": [1, 1, 0],
    })
    assert check_restock_frame(good) == []
    assert check_restock_frame(pd.DataFrame({"Code": ["x"]})) == [], (
        "frames without the feature columns are silently fine"
    )
    bad = pd.DataFrame({
        "SystemCategory": ["KTC", "KTC", "Kanban", "KTC"],
        "CabinetType": ["Helix", "Helix", "Kanban", "Carousel"],
        "Restockable": [False, True, True, True],
        "Restock_target": ["Carousel", "", "Kanban", "Carousel"],
        "Restock_slots": [1, 2, 1, -1],
    })
    issues = check_restock_frame(bad)
    assert len(issues) >= 4, issues


def test_restock_bucket_check_floors_and_conservation():
    from engine.invariants import check_restock_bucket_consistency
    df = pd.DataFrame({
        "SystemCategory": ["KTC", "KTC"],
        "CabinetType": ["Helix", "Locker B"],
        "Restock_target": ["Carousel", "Locker B"],
        "Restock_slots": [1, 1],
    })
    ok_plans = [("SP 1", {"restock_car_slots": 1, "car_cabs": 1,
                          "restock_lockerA": 0, "restock_lockerB": 1, "restock_lockerC": 0,
                          "cabA": 0, "cabB": 1, "cabC": 0})]
    assert check_restock_bucket_consistency(df, ok_plans) == []

    floor_broken = [("SP 1", {"restock_car_slots": 1, "car_cabs": 0,
                              "restock_lockerA": 0, "restock_lockerB": 1, "restock_lockerC": 0,
                              "cabA": 0, "cabB": 0, "cabC": 0})]
    issues = check_restock_bucket_consistency(df, floor_broken)
    assert any("Carousel" in i for i in issues) and any("Locker B" in i for i in issues)

    drops = [("SP 1", {"restock_car_slots": 0, "car_cabs": 1,
                       "restock_lockerA": 0, "restock_lockerB": 1, "restock_lockerC": 0,
                       "cabA": 0, "cabB": 1, "cabC": 0})]
    issues = check_restock_bucket_consistency(df, drops)
    assert any("conservation" in i.lower() for i in issues), issues


def test_run_plan_integrity_includes_restock_checks():
    import dataclasses
    df = _boundary_frame()
    base = _params(df)
    probe = run_plan(df, (), base)
    ktc = probe.work[(probe.work["SystemCategory"] == "KTC")
                     & (probe.work["CabinetType"].isin(["Helix", "Carousel"]))]
    cat = str(ktc.iloc[0]["ProductCategory"])
    result = run_plan(df, (), dataclasses.replace(base, restock_categories=(cat,)))
    assert "restock_frame" in result.integrity.checks
    assert "restock_buckets" in result.integrity.checks
    assert result.integrity.checks["restock_frame"] == []
    assert result.integrity.checks["restock_buckets"] == []


def test_carousel_cap_never_touches_buffer_columns():
    from engine.cabinet_math import CAROUSEL_SLOTS_PER_CAB, apply_carousel_cap
    n = CAROUSEL_SLOTS_PER_CAB * 2
    df = pd.DataFrame({
        "SystemCategory": ["KTC"] * n,
        "CabinetType": ["Carousel"] * n,
        "SizeCategory": ["S"] * n,
        "Carousel_stockpiles": [1] * n,
        "Spirals_needed": [0] * n,
        "Monthly_packs": [float(i + 1) for i in range(n)],
        "Restockable": [True] * n,
        "Restock_target": ["Carousel"] * n,
        "Restock_slots": [1] * n,
    })
    out, overflow = apply_carousel_cap(df, 1, helix_overfill_factor=1.3)
    assert (out["CabinetType"] == "Helix").any(), "the cap must have spilled stockpiles"
    pd.testing.assert_series_equal(out["Restock_slots"], df["Restock_slots"])
    pd.testing.assert_series_equal(out["Restock_target"], df["Restock_target"])
    pd.testing.assert_series_equal(out["Restockable"], df["Restockable"])


def test_rebalance_never_touches_buffer_columns():
    from engine.cabinet_math import rebalance_cabinets
    df = pd.DataFrame({
        "SystemCategory": ["KTC"] * 4,
        "CabinetType": ["Carousel", "Carousel", "Helix", "Helix"],
        "SizeCategory": ["S", "S", "S", "S"],
        "Carousel_stockpiles": [1, 1, 0, 0],
        "Spirals_needed": [0, 0, 2, 2],
        "Spiral_capacity": [20, 20, 20, 20],
        "Monthly_packs": [1.0, 2.0, 3.0, 4.0],
        "Consumption_pcs": [10.0, 20.0, 30.0, 40.0],
        "Restockable": [True, False, True, False],
        "Restock_target": ["Carousel", "", "Carousel", ""],
        "Restock_slots": [1, 0, 1, 0],
    })
    out, _audit = rebalance_cabinets(df, 0.0, 1, 50.0)
    pd.testing.assert_series_equal(out["Restock_slots"], df["Restock_slots"])
    pd.testing.assert_series_equal(out["Restock_target"], df["Restock_target"])


def test_capped_run_flags_exceedance_and_keeps_buffers():
    import dataclasses
    import math
    from engine.cabinet_math import CAROUSEL_SLOTS_PER_CAB
    base_df = _boundary_frame()
    probe = run_plan(base_df, (), _params(base_df))
    vend = probe.work[(probe.work["SystemCategory"] == "KTC")
                      & (probe.work["CabinetType"].isin(["Helix", "Carousel"]))]
    per_copy = len(vend)
    assert per_copy > 0
    copies = math.ceil((CAROUSEL_SLOTS_PER_CAB + 1) / per_copy) + 1
    frames = []
    for i in range(copies):
        f = base_df.copy()
        f["Code"] = f["Code"].astype(str) + f"_{i}"
        frames.append(f)
    big = pd.concat(frames, ignore_index=True)
    cats = tuple(sorted(set(str(c) for c in vend["ProductCategory"])))
    params = dataclasses.replace(
        _params(big), restock_categories=cats,
        op_mode="Capped", max_carousels_cap=1,
    )
    result = run_plan(big, (), params)
    flagged = [(lbl, p) for lbl, p in result.bucket_plans
               if p.get("carousel_cap_exceeded_by_restock")]
    assert flagged, "buffers above the cap must raise the flag"
    for _lbl, p in flagged:
        assert p["car_cabs"] > 1 and p["restock_car_slots"] > 0


def test_persistence_columns_roundtrip(tmp_path):
    import os
    import db.store as store
    from db.persist_run import (persist_run, tools_from_dataframe,
                                summary_rows_from_plans, rebalance_events_from_audit)
    from tests.test_persist_run import (_work_df, _bucket_plans, _grand,
                                        _audit, _file, _run, _execution)
    conn = store.init_db(os.path.join(str(tmp_path), "s3.db"))
    df = _work_df()
    df["Restockable"] = [True] + [False] * (len(df) - 1)
    df["Restock_slots"] = [1] + [0] * (len(df) - 1)
    cfg = store.get_active_machine_config(conn)
    run_id = persist_run(
        conn, file=_file("sha-s3"), run=_run(cfg["config_id"]),
        tools=tools_from_dataframe(df),
        plan_rows=summary_rows_from_plans(_bucket_plans(), _grand()),
        rebalance_events=rebalance_events_from_audit(_audit()),
        execution=_execution(),
    )
    rows = conn.execute(
        "SELECT restockable, restock_slots FROM cabinet_calculations "
        "WHERE run_id = ? ORDER BY calc_id", (run_id,)
    ).fetchall()
    assert [tuple(r) for r in rows][0] == (1, 1)
    assert all(tuple(r) == (0, 0) for r in rows[1:])
    conn.close()


def test_buffers_are_exactly_additive_per_bucket():
    """With the rebalancer off, buffers are exactly additive on the Carousel
    slots; with it on, the consolidation legitimately reshapes the base
    component, and the conservation and floor invariants carry the guarantee
    instead."""
    import dataclasses
    df = _boundary_frame()
    base = dataclasses.replace(_params(df), enable_rebalancer=False)
    baseline = run_plan(df, (), base)
    vend = baseline.work[(baseline.work["SystemCategory"] == "KTC")
                         & (baseline.work["CabinetType"].isin(["Helix", "Carousel"]))]
    cats = tuple(sorted(set(str(c) for c in vend["ProductCategory"])))
    result = run_plan(df, (), dataclasses.replace(base, restock_categories=cats))
    base_by = dict(baseline.bucket_plans)
    for lbl, p in result.bucket_plans:
        assert p["car_slots"] == base_by[lbl]["car_slots"] + p["restock_car_slots"], (
            f"{lbl}: buffers must be exactly additive on the Carousel slots"
        )


# ---- stage 4: technician override (v34.28) ----------------------------------

def test_override_column_registered():
    from engine.constants import OVERRIDE_COLUMNS
    from engine.overrides import _PENDING_OVERRIDE_FIELDS
    assert "restocking_override" in OVERRIDE_COLUMNS
    assert "restocking_override" in _PENDING_OVERRIDE_FIELDS


def _ov_row(code, **fields):
    from engine.constants import OVERRIDE_COLUMNS
    row = {c: "" for c in OVERRIDE_COLUMNS}
    row.update({"code": code, "listing": "Tools"})
    row.update(fields)
    return row


def test_apply_overrides_writes_and_validates_restocking():
    from engine.overrides import apply_overrides
    work = pd.DataFrame({
        "Code": ["T1", "T2"], "Listing": ["Tools", "Tools"],
        "ProductCategory": ["inserts", "mills"],
    })
    ov = pd.DataFrame([_ov_row("T1", restocking_override="yes"),
                       _ov_row("T2", restocking_override="maybe")])
    out, stats = apply_overrides(work, ov)
    assert str(out.loc[out["Code"] == "T1", "Restocking_Override"].iloc[0]) == "yes"
    assert stats["fields_changed"].get("restocking", 0) == 1
    t2 = out.loc[out["Code"] == "T2"]
    val = t2["Restocking_Override"].iloc[0] if "Restocking_Override" in out.columns else ""
    assert pd.isna(val) or str(val).strip() == "", "an invalid value must not be applied"
    assert len(stats["invalid_overrides"]) >= 1


def test_segment_override_beats_provided_and_rule():
    rows = [
        {"SystemCategory": "KTC", "CabinetType": "Helix", "ProductCategory": "inserts",
         "Restocking": "no", "Restocking_Override": "yes"},
        {"SystemCategory": "KTC", "CabinetType": "Helix", "ProductCategory": "inserts",
         "Restocking": "yes", "Restocking_Override": "no"},
        {"SystemCategory": "KTC", "CabinetType": "Helix", "ProductCategory": "inserts",
         "Restocking": "yes", "Restocking_Override": ""},
    ]
    out, info = _seg(rows, categories=("inserts",))
    assert list(out["Restockable"]) == [True, False, True]
    assert list(out["Restockable_Source"]) == ["Override", "Override", "Provided"]
    assert list(out["Restock_slots"]) == [1, 0, 1]
    assert info["override_true"] == 1


def test_run_plan_override_reserves_a_buffer_end_to_end():
    df = _boundary_frame()
    base = _params(df)
    probe = run_plan(df, (), base)
    ktc = probe.work[(probe.work["SystemCategory"] == "KTC")
                     & (probe.work["CabinetType"].isin(["Helix", "Carousel"]))]
    code = str(ktc.iloc[0]["Code"])
    listing = str(ktc.iloc[0]["Listing"])
    ov = pd.DataFrame([_ov_row(code, listing=listing, restocking_override="yes")])
    result = run_plan(df, ov, base)
    row = result.work[result.work["Code"].astype(str) == code]
    assert int(row["Restock_slots"].sum()) == 1
    assert row["Restockable_Source"].iloc[0] == "Override"
    assert result.integrity.checks["restock_frame"] == []
    assert result.integrity.checks["restock_buckets"] == []


def test_editor_grid_carries_the_restocking_column():
    src = (Path(__file__).resolve().parents[1] / "ui" / "technician_panel.py").read_text(encoding="utf-8")
    assert '"Restocking": st.column_config.SelectboxColumn' in src
    assert 'changes["restocking_override"]' in src
