"""kromi_api/services/workbook.py and the planning service's error cases."""
from io import BytesIO

import pandas as pd
import pytest

from engine.column_suggest import suggest_columns
from kromi_api import settings as s
from kromi_api.services import planning, workbook
from kromi_api.services.errors import PlanningError
from tools import synthetic_golden as sg


def _xlsx(sheets: dict, header=True) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        for name, frame in sheets.items():
            frame.to_excel(w, index=False, header=header, sheet_name=name)
    return bio.getvalue()


def test_sheet_names_in_workbook_order(catalog_bytes):
    raw = _xlsx({"Info": pd.DataFrame({"a": [1]}), "Werkzeuge": pd.DataFrame({"b": [2]})})
    assert workbook.sheet_names(raw) == ["Info", "Werkzeuge"]
    assert workbook.sheet_names(catalog_bytes) == [sg.SHEET]


def test_inspect_sheet_gives_columns_preview_and_suggested_mapping(catalog_bytes):
    info = workbook.inspect_sheet(catalog_bytes, sg.SHEET, header_row=1)
    frame = sg.build_catalog()
    assert info.columns == list(frame.columns)
    assert info.row_count == len(frame)
    assert len(info.preview) == 20
    assert info.preview[0]["Article No"] == frame.iloc[0]["Article No"]
    assert info.suggested_mapping == suggest_columns(frame)
    assert info.headers_look_misplaced is False


def test_a_banner_template_suggests_the_real_header_row():
    rows = [["KROMI onboarding", None, None], [None, None, None], [None, None, None],
            ["Artikelnummer", "Bezeichnung", "Jahresverbrauch"],
            ["A1", "Bohrer D5", 12], ["A2", "Fraeser D8", 3]]
    raw = _xlsx({"Tools": pd.DataFrame(rows)}, header=False)
    info = workbook.inspect_sheet(raw, "Tools", header_row=1)
    assert info.headers_look_misplaced is True
    assert info.suggested_header_row == 4
    fixed = workbook.inspect_sheet(raw, "Tools", header_row=4)
    assert fixed.columns == ["Artikelnummer", "Bezeichnung", "Jahresverbrauch"]
    assert fixed.suggested_mapping["Code"] == "Artikelnummer"


def test_preview_values_are_plain_json():
    raw = _xlsx({"T": pd.DataFrame({"a": [1.5, float("nan")], "b": [None, "y"],
                                    "c": [3, 4]})})
    info = workbook.inspect_sheet(raw, "T", header_row=1)
    assert info.preview == [{"a": 1.5, "b": None, "c": 3}, {"a": None, "b": "y", "c": 4}]
    assert all(type(r["c"]) is int for r in info.preview)


def test_not_an_excel_file_is_refused():
    with pytest.raises(PlanningError) as e:
        workbook.sheet_names(b"not a workbook")
    assert e.value.code == "unreadable_workbook"


def test_an_unknown_sheet_is_refused(catalog_bytes):
    with pytest.raises(PlanningError) as e:
        workbook.inspect_sheet(catalog_bytes, "Nope", header_row=1)
    assert e.value.code == "unknown_sheet"


def _request(**mapping):
    base = {"code": "Article No", "description": "Description",
            "consumption": "Consumption 12 months"}
    base.update(mapping)
    return s.RunRequest(sheet=sg.SHEET, mapping=base)


def test_a_column_used_twice_stops_the_run(catalog_bytes):
    with pytest.raises(PlanningError) as e:
        planning.run(catalog_bytes, _request(category="Description"))
    assert e.value.code == "mapping_conflict"
    assert e.value.details == {"Description": ["Description", "ProductCategory"]}


def test_a_missing_required_column_stops_the_run(catalog_bytes):
    with pytest.raises(PlanningError) as e:
        planning.run(catalog_bytes, _request(consumption="No such column"))
    assert e.value.code == "missing_columns"


def test_an_empty_sheet_stops_the_run():
    raw = _xlsx({"T": pd.DataFrame({"Code": [None, " "], "Text": ["a", "b"], "Use": [1, 2]})})
    req = s.RunRequest(sheet="T", mapping={"code": "Code", "description": "Text",
                                           "consumption": "Use"})
    with pytest.raises(PlanningError) as e:
        planning.run(raw, req)
    assert e.value.code == "empty_planning_base"
