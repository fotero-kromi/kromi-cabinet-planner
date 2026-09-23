"""Header row in every mode, with detection (v34.50, audit C11).

The header-row control existed only in the numbering mode, so a file with
banner rows above its headers mapped "Unnamed" columns in planning mode and
planned zero consumption while Run stayed enabled. The control is now shown
in every mode, and a sheet whose data columns are mostly unnamed stops with a
message that names the row that most likely holds the headers.
"""
from io import BytesIO

import pandas as pd

from engine.colmap import headers_look_misplaced, suggest_header_row
from tests._paths import PLANNER_PAGE


def _banner_frame():
    # As read with header=None: two banner rows, a blank row, headers on row 4.
    return pd.DataFrame([
        ["KDS Import template", None, None, None],
        ["Customer 10265", None, None, None],
        [None, None, None, None],
        ["Artikel", "Bezeichnung", "Verbrauch", "Lieferant"],
        ["A1", "Bohrer D8,5", 120, "X"],
        ["A2", "Fraeser D12", 60, "Y"],
    ])


def test_suggest_header_row_finds_the_label_row():
    assert suggest_header_row(_banner_frame()) == 4


def test_suggest_header_row_defaults_to_first_row():
    plain = pd.DataFrame([["Code", "Desc"], ["A", "x"], ["B", "y"]])
    assert suggest_header_row(plain) == 1


def test_misplaced_headers_are_detected_only_for_data_columns():
    wrong = pd.DataFrame({"KDS Import template": ["x", "Artikel", "A1"],
                          "Unnamed: 1": [None, "Bezeichnung", "Bohrer"],
                          "Unnamed: 2": [None, "Verbrauch", 5]})
    assert headers_look_misplaced(wrong)
    # Empty formatted columns named "Unnamed" do not count.
    ok = pd.DataFrame({"Code": ["A"], "Desc": ["x"], "Qty": [1],
                       "Unnamed: 3": [None], "Unnamed: 4": [None],
                       "Unnamed: 5": [None], "Unnamed: 6": [None]})
    assert not headers_look_misplaced(ok)


def _banner_xlsx():
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        _banner_frame().to_excel(w, index=False, header=False, sheet_name="Import")
    return bio.getvalue()


def _drive(extra_restore=None):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    st.cache_data.clear()
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": _banner_xlsx(), "filename": "banner.xlsx",
        "customer": "C", "site": "S", "classifications": {},
        "override_mode": "none", "override_set_id": None}
    restore = {"ks_sheet_tools": "Import", "ks_hide_optional": False,
               "ks_ai_colmap": False}
    restore.update(extra_restore or {})
    at.session_state["_pending_restore"] = restore
    at.run()
    return at


def test_planning_mode_offers_the_header_row_and_stops_on_banner_headers():
    at = _drive()
    assert not at.exception, at.exception
    assert any(n.key == "ks_header_row" for n in at.number_input)
    errors = " ".join(str(e.value) for e in at.error)
    assert "header" in errors.lower() and "row 4" in errors


def test_planning_mode_reads_the_sheet_with_the_chosen_header_row():
    at = _drive({"ks_header_row": 4})
    assert not at.exception, at.exception
    errors = " ".join(str(e.value) for e in at.error)
    assert "row 4" not in errors
    picks = {sb.key: sb.value for sb in at.selectbox if sb.key}
    assert picks["cm_code"] == "Artikel"
