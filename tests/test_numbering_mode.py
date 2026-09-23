"""Contracts for the numbering-only operational mode (v34.44).

"Only article number assignment": the page maps just what the numbering
needs (consumption optional), classification still resolves ToolClass, no
cabinet is planned, nothing is persisted, and the only output is the
Article setup sheet as its own workbook. Because no plan exists to decide
KTC vs Kanban, a mode control sets the default property system per run and
a mapped System type column overrides it per row (KTC / Locker markers
force KTC; everything else keeps the default).
"""

from io import BytesIO

import pandas as pd

from engine.kromi_numbering import (
    ARTICLE_SETUP_COLUMNS,
    build_article_setup,
    resolve_article_system,
)
from engine.workbook import build_article_setup_workbook
from tests._paths import PLANNER_PAGE

KTC = "191"


def _frame(rows):
    base = {
        "Code": "", "Listing": "Tools", "Description": "",
        "ToolClass": "solid_carbide_drill", "PackUnits": 1.0,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


# ---- resolve_article_system ------------------------------------------------

def test_default_kanban_all_rows():
    df = _frame([{"Code": "A"}, {"Code": "B"}])
    out = resolve_article_system(df, "Kanban")
    assert list(out["SystemCategory"]) == ["Kanban", "Kanban"]


def test_default_ktc_all_rows():
    df = _frame([{"Code": "A"}])
    out = resolve_article_system(df, "KTC")
    assert list(out["SystemCategory"]) == ["KTC"]


def test_system_typ_overrides_default():
    df = _frame([
        {"Code": "A", "SystemTyp": "KTC"},
        {"Code": "B", "SystemTyp": "Locker"},
        {"Code": "C", "SystemTyp": "KTC oder Kanban"},
        {"Code": "D", "SystemTyp": ""},
        {"Code": "E", "SystemTyp": "whatever"},
    ])
    out = resolve_article_system(df, "Kanban")
    assert list(out["SystemCategory"]) == ["KTC", "KTC", "Kanban", "Kanban", "Kanban"]


def test_kanban_cell_overrides_ktc_default():
    """v34.45: the mapped column is authoritative in BOTH directions. A cell
    naming Kanban alone forces Kanban even against a KTC default; a flexible
    or empty cell falls back to the default."""
    df = _frame([
        {"Code": "A", "SystemTyp": "Kanban"},
        {"Code": "B", "SystemTyp": "KANBAN"},
        {"Code": "C", "SystemTyp": "KTC"},
        {"Code": "D", "SystemTyp": "KTC oder Kanban"},
        {"Code": "E", "SystemTyp": ""},
        {"Code": "F", "SystemTyp": "whatever"},
    ])
    out = resolve_article_system(df, "KTC")
    assert list(out["SystemCategory"]) == [
        "Kanban", "Kanban", "KTC", "KTC", "KTC", "KTC"]


def test_kanban_cell_with_locker_still_forces_ktc():
    """Locker markers win over a Kanban word in the same cell, matching the
    planner's parse precedence."""
    df = _frame([{"Code": "A", "SystemTyp": "Kanban Locker"}])
    out = resolve_article_system(df, "KTC")
    assert list(out["SystemCategory"]) == ["KTC"]


def test_nan_cell_keeps_default():
    import numpy as np
    df = _frame([{"Code": "A", "SystemTyp": np.nan}])
    assert list(resolve_article_system(df, "KTC")["SystemCategory"]) == ["KTC"]
    assert list(resolve_article_system(df, "Kanban")["SystemCategory"]) == ["Kanban"]


def test_never_mutates_input():
    df = _frame([{"Code": "A"}])
    resolve_article_system(df, "KTC")
    assert "SystemCategory" not in df.columns


def test_resolved_frame_feeds_builder():
    df = _frame([
        {"Code": "A1", "Description": "Bohrer D8,5"},
        {"Code": "B1", "Description": "Schraube M6", "ToolClass": "screw"},
    ])
    out = build_article_setup(resolve_article_system(df, "Kanban"), KTC)
    assert len(out) == 2  # all Kanban: one number each
    out2 = build_article_setup(resolve_article_system(df, "KTC"), KTC)
    assert len(out2) == 4  # all KTC: predecessor + successor each


# ---- master-file ordering (v34.46) -----------------------------------------

def test_order_kanban_only_follows_source_order():
    from engine.kromi_numbering import order_article_setup

    df = _frame([
        {"Code": "C3", "Description": "Bohrer D9", "SystemTyp": ""},
        {"Code": "C1", "Description": "Bohrer D8", "SystemTyp": ""},
        {"Code": "C2", "Description": "Bohrer D7", "SystemTyp": ""},
    ])
    setup = build_article_setup(resolve_article_system(df, "Kanban"), KTC)
    # The planning-base dedup sorts articles, so simulate its output order:
    setup = setup.sort_values("Customer article No").reset_index(drop=True)
    out = order_article_setup(setup, ["C3", "C1", "C2"])
    assert list(out["Customer article No"]) == ["C3", "C1", "C2"]


def test_order_ktc_successors_append_after_last_unique_row():
    from engine.kromi_numbering import order_article_setup

    df = _frame([
        {"Code": "C3", "Description": "Bohrer D9", "SystemTyp": "KTC"},
        {"Code": "C1", "Description": "Bohrer D8", "SystemTyp": ""},
        {"Code": "C2", "Description": "Bohrer D7", "SystemTyp": "KTC"},
    ])
    setup = build_article_setup(resolve_article_system(df, "Kanban"), KTC)
    out = order_article_setup(setup, ["C3", "C1", "C2"])
    # Block 1: one row per article in master-file order (KTC predecessor or
    # the Kanban number). Block 2: the duplicate numbers (KTC successors)
    # after the last non-duplicate row, in the same master-file order.
    assert list(out["Customer article No"]) == ["C3", "C1", "C2", "C3", "C2"]
    assert list(out["Property"]) == [
        "Customer property", "Customer property", "Customer property",
        "KROMI property", "KROMI property",
    ]
    # Linkage survives the reorder.
    pred_c3 = out.iloc[0]; succ_c3 = out.iloc[3]
    assert pred_c3["Replaced by"] == succ_c3["Kromi_Art_No"]
    assert succ_c3["Replaces"] == pred_c3["Kromi_Art_No"]


def test_order_unknown_codes_go_last_stable():
    from engine.kromi_numbering import order_article_setup

    df = _frame([
        {"Code": "A", "Description": "Bohrer D8", "SystemTyp": ""},
        {"Code": "B", "Description": "Bohrer D9", "SystemTyp": ""},
    ])
    setup = build_article_setup(resolve_article_system(df, "Kanban"), KTC)
    out = order_article_setup(setup, ["B"])  # A not in the order list
    assert list(out["Customer article No"]) == ["B", "A"]


def test_order_without_list_keeps_current_order():
    from engine.kromi_numbering import order_article_setup

    df = _frame([
        {"Code": "B", "Description": "Bohrer D9", "SystemTyp": ""},
        {"Code": "A", "Description": "Bohrer D8", "SystemTyp": ""},
    ])
    setup = build_article_setup(resolve_article_system(df, "Kanban"), KTC)
    for empty in (None, []):
        out = order_article_setup(setup, empty)
        assert list(out["Customer article No"]) == ["B", "A"]


def test_page_numbering_branch_orders_by_source():
    """Wiring contract: the numbering branch must capture the pre-dedup code
    order and pass it through order_article_setup, so the download follows
    the master file instead of the planning-base sort."""
    from pathlib import Path

    src = Path(PLANNER_PAGE).read_text(encoding="utf-8")
    assert "_nb_code_order" in src
    assert "order_article_setup(" in src


# ---- minimal workbook ------------------------------------------------------

def test_article_setup_workbook_single_sheet():
    from openpyxl import load_workbook

    df = _frame([{"Code": "A1", "Description": "Bohrer D8,5"}])
    setup = build_article_setup(resolve_article_system(df, "KTC"), KTC)
    xbytes = build_article_setup_workbook(setup)
    wb = load_workbook(BytesIO(xbytes))
    assert wb.sheetnames == ["Article setup"]
    ws = wb["Article setup"]
    assert [c.value for c in ws[1]] == list(ARTICLE_SETUP_COLUMNS)
    assert ws.max_row == 1 + 2


# ---- page drive: numbering mode end to end ---------------------------------

def _template_xlsx_bytes() -> bytes:
    """A KDS-style workbook: one banner row, headers on row 2, three articles."""
    data = pd.DataFrame({
        "Artikel": ["C1", "C2", "C3"],
        "Bezeichnung": ["Bohrer D8,5", "Schraube M6x20", "Fraeser D12"],
        "Lieferant": ["ACME", "ACME", "ACME"],
    })
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        pd.DataFrame([["banner"]]).to_excel(
            writer, index=False, header=False, sheet_name="Import")
        data.to_excel(writer, index=False, sheet_name="Import", startrow=1)
    bio.seek(0)
    return bio.getvalue()


def test_page_numbering_mode_drive(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "nb.db"))
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": _template_xlsx_bytes(), "filename": "input.xlsx",
        "customer": "TestCustomer", "site": "TestSite",
        "classifications": {}, "override_mode": "none", "override_set_id": None,
    }
    at.session_state["_pending_restore"] = {
        "ks_sheet_tools": "Import",
        "ks_op_mode": "Only article number assignment",
        "ks_header_row": 2,
        "cm_code": "Artikel",
        "cm_desc1": "Bezeichnung",
        # The lean path this mode is for: optional fields hidden, so only the
        # numbering-relevant mappings are made (consumption is optional here).
        "ks_hide_optional": True,
        "ks_ai_colmap": False,
    }
    at.run()
    assert not at.exception, at.exception
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception

    subheaders = [str(s.value) for s in at.subheader]
    assert "Article setup" in subheaders
    # No cabinet planning happened.
    assert "Required cabinets (KTC only)" not in subheaders
    assert at.session_state["has_results"] is True
    # The three Kanban articles got one number each, all well-formed.
    successes = " ".join(str(s.value) for s in at.success)
    assert "3 number(s) assigned" in successes
