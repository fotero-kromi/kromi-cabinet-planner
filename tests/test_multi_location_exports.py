"""Stored runs, export columns and Run_Metadata for articles on several
machines (v34.63). Nothing new appears for files without multi-machine cells.
"""
import pandas as pd
import pytest

from engine import export_frames as ef
from engine import run_restore as rr
from engine.export_shaping import USER_FRIENDLY_COLS, user_view
from engine.multi_location import SHARED_COL, SOURCE_COL, multi_location_meta_rows
from engine.tool_list import apply_export_display_columns
from tests.test_export_frames import _as_dict, _inputs

# ---- stored runs -----------------------------------------------------------------------

def test_not_planned_here_is_captured_and_restored():
    snap = rr.capture_ui_state({"prog_sp::AB-100": 1, "prog_sp::AB-102": 0,
                                "prog_sp::AB-103": -1, "prog_sp::AB-104": None,
                                "ks_ml_full_consumption": True})
    assert snap["prog_sp::AB-100"] == 1 and snap["prog_sp::AB-102"] == 0
    assert "prog_sp::AB-103" not in snap and "prog_sp::AB-104" not in snap
    assert snap["ks_ml_full_consumption"] is True
    seed = rr.build_seed(snap, ["x"])
    assert seed["prog_sp::AB-102"] == 0
    assert seed["ks_ml_full_consumption"] is True


def test_keys_of_older_runs_are_translated_to_the_canonical_label():
    seed = rr.build_seed({"prog_sp::ab 101": 2, "prog_sp::Line A": 1, "prog_sp::": 1,
                          "prog_sp::  Line   B ": 2, "prog_sp::CD-7 +": 1}, ["x"])
    assert seed == {"prog_sp::AB-101": 2, "prog_sp::Line A": 1, "prog_sp::": 1,
                    "prog_sp::Line B": 2, "prog_sp::CD-7": 1}


def test_an_older_key_naming_several_machines_is_not_restored():
    ui = {"prog_sp::AB-100 + AB 101": 2, "prog_sp::AB-100": 1}
    seed = rr.build_seed(ui, ["x"])
    assert seed == {"prog_sp::AB-100": 1}
    summary = rr.restore_summary(ui, seed)
    assert summary == {"restored": 1, "total": 2, "dropped": ["prog_sp::AB-100 + AB 101"]}


def test_the_canonical_key_wins_over_a_translated_twin():
    for ui in ({"prog_sp::AB-101": 1, "prog_sp::ab 101": 2},
               {"prog_sp::ab 101": 2, "prog_sp::AB-101": 1}):
        assert rr.build_seed(ui, ["x"]) == {"prog_sp::AB-101": 1}


def test_translated_keys_count_as_restored():
    ui = {"prog_sp::ab 101": 2, "cm_code": "Art"}
    seed = rr.build_seed(ui, ["Art"])
    assert rr.restore_summary(ui, seed) == {"restored": 2, "total": 2, "dropped": []}


# ---- export columns ------------------------------------------------------------------------

def _plan_frame(with_source=True):
    df = pd.DataFrame({
        "Listing": ["Tools", "Tools", "Tools"], "Code": ["X", "X", "Y"],
        "SupplyPoint": [1, 2, 1], "SystemCategory": ["KTC"] * 3,
        "SystemCategory_Reason": [""] * 3,
    })
    if with_source:
        df[SOURCE_COL] = ["AB-100 + AB 101", "AB-100 + AB 101", "AB-100"]
        df[SHARED_COL] = [True, True, False]
    return df


def test_the_result_carries_the_machines_and_the_supply_points():
    df = _plan_frame()
    apply_export_display_columns(df)
    assert list(df["Machines (source)"]) == ["AB-100 + AB 101", "AB-100 + AB 101", "AB-100"]
    assert list(df["Supply points"]) == ["SP 1, SP 2", "SP 1, SP 2", "SP 1"]


def test_no_new_columns_without_multi_machine_cells():
    df = _plan_frame(with_source=False)
    before = list(df.columns)
    apply_export_display_columns(df)
    assert list(df.columns) == before


def test_the_user_view_shows_the_new_columns_after_the_supply_point():
    i = USER_FRIENDLY_COLS.index("SupplyPoint")
    assert USER_FRIENDLY_COLS[i + 1:i + 3] == ["Machines (source)", "Supply points"]
    df = _plan_frame()
    apply_export_display_columns(df)
    cols = list(user_view(df).columns)
    assert cols.index("Machines (source)") == cols.index("SupplyPoint") + 1


# ---- Run_Metadata -----------------------------------------------------------------------------

def _meta(**kw):
    return {"multi_rows": 12, "shared_articles": 7, "full_consumption": False,
            "not_planned_machines": ("AB-102",), **kw}


def test_the_metadata_rows():
    assert multi_location_meta_rows(_meta()) == [
        {"Key": "Rows naming several machines", "Value": 12},
        {"Key": "Articles in several supply points", "Value": 7},
        {"Key": "Consumption for shared articles", "Value": "equal share per machine"},
        {"Key": "Machines not planned", "Value": "AB-102"},
    ]
    rows = multi_location_meta_rows(_meta(full_consumption=True, not_planned_machines=()))
    assert rows[2]["Value"] == "full in every supply point"
    assert rows[3]["Value"] == "none"


def test_run_metadata_adds_the_rows_after_the_programme_count():
    rows = ef.run_metadata_rows(_inputs(multi_location=_meta()), work=pd.DataFrame(
        {"SystemCategory_Reason": []}), bucket_plans=[])
    keys = [r["Key"] for r in rows]
    i = keys.index("Programmes mapped")
    assert keys[i + 1:i + 5] == ["Rows naming several machines",
                                "Articles in several supply points",
                                "Consumption for shared articles", "Machines not planned"]
    assert _as_dict(rows)["Articles in several supply points"] == 7


def test_run_metadata_is_unchanged_without_multi_machine_cells():
    work = pd.DataFrame({"SystemCategory_Reason": []})
    plain = ef.run_metadata_rows(_inputs(), work=work, bucket_plans=[])
    assert "Rows naming several machines" not in [r["Key"] for r in plain]
    assert ef.run_metadata_rows(_inputs(multi_location=None), work=work,
                                bucket_plans=[]) == plain


@pytest.mark.parametrize("n,label", [(0, "0"), (3, "3")])
def test_counts_are_plain_numbers(n, label):
    assert str(multi_location_meta_rows(_meta(multi_rows=n))[0]["Value"]) == label
