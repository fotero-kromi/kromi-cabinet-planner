"""Tests for the user-facing export column shaper (v33.81).

These pin the behaviour the Excel "clean" sheets rely on: column selection and
order, per-sheet dropping of entirely-empty columns, non-mutation of the input,
and the empty-frame header case. One test writes the shaped frame to an actual
xlsx and reads it back, so a regression in the exported sheet content is caught.
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import openpyxl

from engine.export_shaping import user_view, USER_FRIENDLY_COLS


def _row(**kw):
    r = {"Listing": "Tools", "Code": "X", "Description": "d",
         "ProductCategory": "inserts", "SizeCategory": "M",
         "System": "KTC", "SupplyPoint": "SP1", "CabinetType": "Helix"}
    for n in ["PackUnits", "Monthly_pcs", "Spirals_needed", "Carousel_stockpiles"]:
        r[n] = 0
    r.update(kw)
    return r


def test_preserves_user_friendly_order_regardless_of_input_order():
    # build a frame whose columns are in a scrambled order
    df = pd.DataFrame([_row(PackUnits=10, Monthly_pcs=5.0, Spirals_needed=1)])
    df = df[list(reversed(df.columns))]
    out = list(user_view(df).columns)
    # surviving columns must follow USER_FRIENDLY_COLS order
    assert out == [c for c in USER_FRIENDLY_COLS if c in out]


def test_drops_columns_not_in_the_list():
    df = pd.DataFrame([{"Listing": "Tools", "Code": "Z", "Monthly_pcs": 4.0,
                        "AI_reason": "audit", "Override_note": "x"}])
    out = user_view(df)
    assert "AI_reason" not in out.columns and "Override_note" not in out.columns


def test_drops_numeric_column_that_is_all_zero_or_nan():
    df = pd.DataFrame([_row(Monthly_pcs=5.0), _row(Monthly_pcs=np.nan)])
    # Carousel_stockpiles is all 0 -> dropped; Spirals_needed all 0 -> dropped
    assert "Carousel_stockpiles" not in user_view(df).columns
    assert "Spirals_needed" not in user_view(df).columns


def test_keeps_numeric_column_with_a_nonzero_value():
    df = pd.DataFrame([_row(Spirals_needed=2), _row(Spirals_needed=np.nan)])
    assert "Spirals_needed" in user_view(df).columns


def test_drops_all_blank_text_column_keeps_populated_one():
    df = pd.DataFrame([_row(SupplierCode="", Monthly_pcs=5.0),
                       _row(SupplierCode="   ", Monthly_pcs=5.0)])
    assert "SupplierCode" not in user_view(df).columns
    df2 = pd.DataFrame([_row(SupplierCode="Seco", Monthly_pcs=5.0)])
    assert "SupplierCode" in user_view(df2).columns


def test_skips_columns_absent_from_the_frame():
    df = pd.DataFrame([{"Listing": "Tools", "Code": "Z", "Monthly_pcs": 4.0}])
    # must not raise even though most USER_FRIENDLY_COLS are missing
    out = user_view(df)
    assert list(out.columns) == ["Listing", "Code", "Monthly_pcs"]


def test_empty_frame_with_columns_emits_header_only():
    df = pd.DataFrame(columns=USER_FRIENDLY_COLS + ["AuditCol"])
    out = user_view(df)
    assert len(out) == 0
    assert list(out.columns) == [c for c in USER_FRIENDLY_COLS if c in df.columns]
    assert "AuditCol" not in out.columns


def test_empty_frame_without_columns():
    out = user_view(pd.DataFrame())
    assert out.empty and list(out.columns) == []


def test_does_not_mutate_input_frame():
    df = pd.DataFrame([_row(PackUnits=10, Monthly_pcs=5.0, SupplierCode="Seco")])
    before = df.copy(deep=True)
    df["AuditCol"] = ["a"]
    before["AuditCol"] = ["a"]
    _ = user_view(df)
    pd.testing.assert_frame_equal(df, before)


def test_size_issue_kept_when_populated():
    df = pd.DataFrame([_row(SizeIssue="too big", Monthly_pcs=5.0)])
    assert "SizeIssue" in user_view(df).columns


def test_custom_columns_argument_overrides_default():
    df = pd.DataFrame([_row(PackUnits=10, Monthly_pcs=5.0)])
    out = user_view(df, columns=["Code", "Listing"])
    assert list(out.columns) == ["Code", "Listing"]


def test_xlsx_roundtrip_matches_shaped_frame():
    # concrete export check: the written sheet content equals the shaped frame
    df = pd.DataFrame([_row(PackUnits=10, Monthly_pcs=5.0, Spirals_needed=2, SupplierCode="Seco"),
                       _row(Code="B", PackUnits=1, Monthly_pcs=3.0, Spirals_needed=1, SupplierCode="Iscar")])
    shaped = user_view(df)
    path = Path(tempfile.mkdtemp()) / "clean.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        shaped.to_excel(w, index=False, sheet_name="Result")
    wb = openpyxl.load_workbook(path)["Result"]
    rows = [[c.value for c in r] for r in wb.iter_rows()]
    assert rows[0] == list(shaped.columns)               # header
    assert len(rows) == len(shaped) + 1                  # header + data rows
    # first data cell matches
    assert rows[1][0] == shaped.iloc[0, 0]
