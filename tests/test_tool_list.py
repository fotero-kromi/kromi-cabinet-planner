"""engine/tool_list.py (v34.61): building the tool list from the mapped sheets,
moved out of the planner page so every front end builds it the same way.
"""
import math

import pandas as pd
import pytest

from engine import tool_list as tl
from engine.cabinet_math import SPECIAL_KTC_REASON
from engine.takeover import CATEGORY_TEXT_COL, STOCK_COL


def _mapping(**kw):
    base = {"code": "Art", "description": "Text", "consumption": "Use"}
    base.update(kw)
    return tl.ColumnMapping(**base)


def _sheet(**extra):
    data = {"Art": ["A1", "B2"], "Text": ["Drill 5", "Mill 8"], "Use": ["12", "3,5"]}
    data.update(extra)
    return pd.DataFrame(data)


# ---- mapping ---------------------------------------------------------------------------

def test_rename_map_follows_the_page_order_and_skips_unmapped_fields():
    m = _mapping(stock="Qty", category="Cat", description_2="Text2", supplier_code="Sup")
    assert list(tl.rename_map(m).items()) == [
        ("Art", "Code"), ("Text", "Description"), ("Use", "Consumption_pcs"),
        ("Sup", "SupplierCode"), ("Text2", "Description_2"), ("Cat", "ProductCategory"),
        ("Qty", STOCK_COL),
    ]


def test_an_unmapped_consumption_stays_out_of_the_rename_map():
    assert tl.rename_map(_mapping(consumption=None)) == {"Art": "Code", "Text": "Description"}


def test_mapping_collisions_name_every_field_of_a_shared_column():
    m = _mapping(category="Text", stock="Use")
    assert tl.mapping_collisions(m) == {"Text": ["Description", "ProductCategory"],
                                        "Use": ["Consumption pcs", "Stock"]}
    assert tl.mapping_collisions(_mapping()) == {}


def test_description_2_is_dropped_when_switched_off():
    m = _mapping(description_2="Text2")
    assert tl.effective_mapping(m, use_description_2=True).description_2 == "Text2"
    assert tl.effective_mapping(m, use_description_2=False).description_2 is None


def test_the_mapping_is_frozen():
    with pytest.raises(AttributeError):
        _mapping().code = "X"  # type: ignore[misc]


# ---- building --------------------------------------------------------------------------

def test_build_tool_list_renames_tags_cleans_and_scaffolds():
    raw = _sheet(Cat=[" drill ", None])
    out = tl.build_tool_list(raw, None, _mapping(category="Cat"), use_description_2=True)
    w = out.work
    assert list(w["Code"]) == ["A1", "B2"]
    assert list(w["Listing"]) == ["Tools", "Tools"]
    assert list(w["ProductCategory"]) == ["drill", ""]
    assert list(w["Consumption_pcs"]) == [12.0, 3.5]
    assert all(math.isnan(v) for v in w["PackUnits"])
    for col, value in (("SupplierCode", ""), ("Description_2", ""), ("SizeCategory", ""),
                       ("SystemTyp", ""), ("Program", ""), ("Site", "")):
        assert list(w[col]) == [value, value], col
    assert list(w["Regrind"]) == [False, False]
    assert list(w["Routing_Pinned"]) == [False, False]
    assert w["Year"].isna().all()
    assert out.missing == () and out.blocking == ()
    assert out.dropped_empty_codes.empty
    assert STOCK_COL not in w.columns and CATEGORY_TEXT_COL not in w.columns


def test_integral_float_codes_keep_their_integer_text():
    raw = pd.DataFrame({"Art": [12345.0, float("nan"), 7.0], "Text": ["a", "b", "c"],
                        "Use": [1, 2, 3]})
    out = tl.build_tool_list(raw, None, _mapping(), use_description_2=True)
    assert list(out.work["Code"]) == ["12345", "7"]


def test_blank_codes_are_dropped_and_reported():
    raw = pd.DataFrame({"Art": ["A1", "  ", None], "Text": ["a", "b", "c"], "Use": [1, 2, 3]})
    out = tl.build_tool_list(raw, None, _mapping(), use_description_2=True)
    assert list(out.work["Code"]) == ["A1"]
    assert list(out.work.index) == [0]
    assert list(out.dropped_empty_codes["Description"]) == ["b", "c"]


def test_description_2_is_blank_when_switched_off():
    raw = _sheet(Text2=["x", "y"])
    m = tl.effective_mapping(_mapping(description_2="Text2"), use_description_2=False)
    out = tl.build_tool_list(raw, None, m, use_description_2=False)
    assert list(out.work["Description_2"]) == ["", ""]
    assert "Text2" in out.work.columns  # left unrenamed, as before


def test_regrind_and_system_type_columns():
    raw = _sheet(RG=["yes", "no"], ST=["KTC", None])
    out = tl.build_tool_list(raw, None, _mapping(regrind="RG", system_type="ST"),
                             use_description_2=True)
    assert list(out.work["Regrind"]) == [True, False]
    assert list(out.work["SystemTyp"]) == ["KTC", ""]


def test_stock_is_parsed_and_clipped_and_the_category_text_kept():
    raw = _sheet(Qty=["5", "-3"], Cat=["Bohrer", "Fraeser"])
    out = tl.build_tool_list(raw, None, _mapping(stock="Qty", category="Cat"),
                             use_description_2=True)
    assert list(out.work[STOCK_COL]) == [5.0, 0.0]
    assert list(out.work[CATEGORY_TEXT_COL]) == ["Bohrer", "Fraeser"]


def test_stock_without_a_category_has_no_category_text():
    out = tl.build_tool_list(_sheet(Qty=["5", "1"]), None, _mapping(stock="Qty"),
                             use_description_2=True)
    assert STOCK_COL in out.work.columns
    assert CATEGORY_TEXT_COL not in out.work.columns


def test_tools_and_ppe_are_concatenated_in_that_order():
    ppe = pd.DataFrame({"Art": ["P1"], "Text": ["Glove"], "Use": [100]})
    out = tl.build_tool_list(_sheet(), ppe, _mapping(), use_description_2=True)
    assert list(out.work["Listing"]) == ["Tools", "Tools", "PPE"]
    assert list(out.work["Code"]) == ["A1", "B2", "P1"]
    assert list(out.work.index) == [0, 1, 2]


def test_a_missing_optional_column_is_reported_not_blocking():
    ppe = pd.DataFrame({"Art": ["P1"], "Text": ["Glove"], "Use": [100]})
    out = tl.build_tool_list(_sheet(Cat=["a", "b"]), ppe, _mapping(category="Cat"),
                             use_description_2=True)
    assert out.missing == (tl.MissingColumns("PPE", (("Cat", "ProductCategory"),)),)
    assert out.missing[0].critical == ()
    assert out.blocking == ()
    assert list(out.work["ProductCategory"][:2]) == ["a", "b"]
    assert pd.isna(out.work["ProductCategory"].iloc[2])  # empty, as the page did


def test_a_missing_code_or_consumption_column_blocks():
    ppe = pd.DataFrame({"Art": ["P1"], "Text": ["Glove"]})
    out = tl.build_tool_list(_sheet(), ppe, _mapping(), use_description_2=True)
    assert out.missing == (tl.MissingColumns("PPE", (("Use", "Consumption_pcs"),)),)
    assert out.missing[0].critical == ("Consumption_pcs",)
    assert out.blocking == out.missing


def test_the_input_frames_are_not_changed():
    raw = _sheet()
    before = raw.copy()
    tl.build_tool_list(raw, None, _mapping(), use_description_2=True)
    pd.testing.assert_frame_equal(raw, before)


# ---- scope ----------------------------------------------------------------------------

def test_scope_defaults_and_a_single_site_column_value():
    w = pd.DataFrame({"Site": ["Plant 7", "Plant 7", ""]})
    assert tl.scope_value("  ") == "default"
    assert tl.scope_value(None) == "default"
    assert tl.scope_value(" Acme ") == "Acme"
    assert tl.resolve_override_scope("", "", w, site_mapped=False) == ("default", "default", [])
    assert tl.resolve_override_scope("C", "S", w, site_mapped=True) == ("C", "Plant 7", ["Plant 7"])


def test_several_sites_keep_the_entered_site():
    w = pd.DataFrame({"Site": ["A", "B", "nan", "None"]})
    assert tl.resolve_override_scope("C", "S", w, site_mapped=True) == ("C", "S", ["A", "B"])


# ---- programs -------------------------------------------------------------------------

def test_distinct_programs_are_sorted_with_blank_last():
    w = pd.DataFrame({"Program": ["Line B", "", "Line A", "Line B", " "]})
    assert tl.distinct_programs(w) == ["Line A", "Line B", ""]


def test_unassigned_programs():
    assert tl.unassigned_programs(["A", "B", ""], {"A": 1, "": 2}) == ["B"]


def test_assign_supply_points_maps_programs_and_defaults_to_sp_1():
    w = pd.DataFrame({"Program": ["A", "B", "C"]})
    n_default = tl.assign_supply_points(w, {"A": 2, "B": 1})
    assert list(w["SupplyPoint"]) == [2, 1, 1]
    assert w["SupplyPoint"].dtype == int
    assert n_default == 1


# ---- classification scaffold and export display ----------------------------------------

def test_the_classification_audit_columns_are_added_in_order():
    w = pd.DataFrame({"Code": ["A"]})
    tl.add_classification_audit_columns(w)
    assert list(w.columns) == ["Code"] + list(tl.CLASSIFICATION_AUDIT_COLUMNS)
    for col, default in tl.CLASSIFICATION_AUDIT_COLUMNS.items():
        assert w[col].iloc[0] == default, col
    assert tl.CLASSIFICATION_AUDIT_COLUMNS["ProductCategory_AI_Consulted"] is False
    assert tl.CLASSIFICATION_AUDIT_COLUMNS["ToolClass"] == ""


def test_export_display_columns_for_standard_special_and_restockable():
    w = pd.DataFrame({
        "StdSpecial": ["Special", "Standard", ""],
        "SystemCategory_Reason": [SPECIAL_KTC_REASON, "", ""],
        "Restockable": [True, False, True],
    })
    tl.apply_export_display_columns(w)
    assert list(w["Std_Special"]) == ["Special", "Standard", ""]
    assert list(w["Forced_to_KTC"]) == ["Yes", "", ""]
    assert list(w["Restockable"]) == ["Yes", "", "Yes"]
    tl.apply_export_display_columns(w)  # a second pass changes nothing
    assert list(w["Restockable"]) == ["Yes", "", "Yes"]


def test_export_display_columns_leave_a_plain_frame_alone():
    w = pd.DataFrame({"Code": ["A"]})
    tl.apply_export_display_columns(w)
    assert list(w.columns) == ["Code"]
