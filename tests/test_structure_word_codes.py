"""KROMI code from the structure word (v34.56).

A KDS onboarding file carries the structure word in Bezeichnung 1, mapped as
the ProductCategory column. "Stufenbohrer ..." is a step drill (structure
801, KROMI code 14), but the category column only resolves to "drills", so
the successor number used code 13 whenever Bezeichnung 2 (the dimensions)
did not repeat the word. The structure word now sets the ToolClass.

Threading inserts ("WSP Gewinde ...") sit in structure family 806, the
insert family, so their code stays 12: pinned here.
"""
import pandas as pd

from engine.boundary import apply_pre_ai_heuristics
from engine.kromi_numbering import build_article_setup

KTC = "140"


def _scaffold(cats, descs):
    n = len(cats)
    return pd.DataFrame({
        "Code": [f"C{i}" for i in range(n)], "SupplierCode": [""] * n,
        "Listing": ["Tools"] * n, "Description": descs, "Description_2": [""] * n,
        "ProductCategory": cats, "ProductCategory_Source": [""] * n,
        "ProductCategory_Evidence": [""] * n, "ProductCategory_Confidence": [""] * n,
        "ToolClass": [""] * n, "ToolClass_Source": [""] * n,
        "SizeCategory": [""] * n, "SizeCategory_Source": [""] * n,
        "PackUnits": [pd.NA] * n, "PackUnits_Source": [""] * n,
    })


def _classified(cats, descs):
    return apply_pre_ai_heuristics(_scaffold(cats, descs), enable_pack_hint_extraction=True,
                                   insert_default_pack_units=10.0)


def test_structure_word_step_drill_sets_the_tool_class():
    out = _classified(["Stufenbohrer VHM", "Stufenbohrer HSS-E/HSCO"],
                      ["Drm. 4,80/ 8,00", "Drm. 9,18/12,0"])
    assert list(out["ProductCategory"]) == ["drills", "drills"]
    assert list(out["ToolClass"]) == ["step_drill", "step_drill"]
    assert list(out["ToolClass_Source"]) == ["Provided", "Provided"]


def test_other_drills_and_step_countersinks_are_untouched():
    out = _classified(["Spiralbohrer VHM", "Stufensenker VHM", "Schaftfräser VHM"],
                      ["Drm. 3,50", "D 8", "D 12"])
    assert out.loc[0, "ToolClass"] == "solid_carbide_drill"
    assert out.loc[1, "ToolClass"] != "step_drill"
    assert out.loc[2, "ToolClass"] != "step_drill"


def _successor_code(cat, desc, pc):
    out = _classified([cat], [desc])
    out["SystemCategory"] = "KTC"
    out["CabinetType"] = "Carousel"
    out["PackUnits"] = 1.0
    setup = build_article_setup(out, KTC)
    succ = setup.loc[setup["Property"] == "KROMI property", "Kromi_Art_No"].iloc[0]
    assert out.loc[0, "ProductCategory"] == pc
    return succ[3:5]


def test_step_drill_successor_gets_code_14():
    assert _successor_code("Stufenbohrer VHM", "Drm. 4,80/ 8,00", "drills") == "14"


def test_threading_insert_keeps_the_insert_code():
    assert _successor_code("WSP Gewinde VHM", "16 ER 0,8", "inserts") == "12"


def test_the_structure_word_survives_deduplication():
    """The planning base merges duplicate rows before the heuristics run; the
    merged row keeps the provided text, so the step-drill word is still seen."""
    from engine.preprocessing import prepare_planning_base
    df = _scaffold(["Stufenbohrer VHM", "Stufenbohrer VHM", "Spiralbohrer VHM"],
                   ["Drm. 4,80/ 8,00", "Drm. 4,80/ 8,00", "Drm. 3,50"])
    df["Code"] = ["S1", "S1", "S2"]
    df["Consumption_pcs"] = [5.0, 7.0, 3.0]
    base, _ = prepare_planning_base(
        df.drop(columns=["ProductCategory_Source", "ProductCategory_Evidence",
                         "ProductCategory_Confidence", "ToolClass", "ToolClass_Source",
                         "SizeCategory_Source", "PackUnits_Source"]),
        dedup_mode="code_supplier", year_mode="all", has_year=False)
    for c in ("ProductCategory_Source", "ProductCategory_Evidence", "ProductCategory_Confidence",
              "ToolClass", "ToolClass_Source", "SizeCategory_Source", "PackUnits_Source"):
        base[c] = ""
    out = apply_pre_ai_heuristics(base, enable_pack_hint_extraction=True,
                                  insert_default_pack_units=10.0).set_index("Code")
    assert out.loc["S1", "ToolClass"] == "step_drill"
    assert out.loc["S1", "ProductCategory"] == "drills"
    assert out.loc["S2", "ToolClass"] == "solid_carbide_drill"
