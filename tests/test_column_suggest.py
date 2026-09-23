"""engine/column_suggest.py (v34.62): the column each planning field starts
from, moved out of the planner page so every front end suggests the same
mapping.
"""
import pandas as pd

from engine import column_suggest as cs
from engine.colmap import CODE_SYNONYMS, CONSUMPTION_SYNONYMS, DESCRIPTION_SYNONYMS


def _frame(*cols):
    return pd.DataFrame({c: [] for c in cols})


def test_the_field_order_is_the_page_order():
    assert cs.REQUIRED_FIELDS == ("Code", "Description", "Consumption_pcs")
    assert cs.OPTIONAL_FIELDS == (
        "ProductCategory", "Year", "Description_2", "Program", "Restocking",
        "SupplierCode", "SizeCategory", "Site", "StdSpecial", "PackUnits",
        "PackageDimensions", "Regrind", "SystemTyp", "Stock_pcs",
    )


def test_required_fields_use_the_shared_synonyms():
    assert cs.SYNONYMS["Code"] is CODE_SYNONYMS
    assert cs.SYNONYMS["Description"] is DESCRIPTION_SYNONYMS
    assert cs.SYNONYMS["Consumption_pcs"] is CONSUMPTION_SYNONYMS
    assert "Stock_pcs" not in cs.SYNONYMS  # found by its own rule


def test_optional_synonyms_keep_the_validated_words():
    assert cs.SYNONYMS["PackUnits"] == ["PackUnits", "VPE", "VE", "Pack", "Packsize", "Packaging"]
    assert cs.SYNONYMS["Year"] == ["Year", "Jahr", "FiscalYear", "PeriodYear"]
    assert cs.SYNONYMS["SupplierCode"][:2] == ["SupplierCode", "Lieferant"]
    assert "Lagersystem (KTC, usw)" in cs.SYNONYMS["SystemTyp"]
    assert "Nachschleifbar" in cs.SYNONYMS["Regrind"]


def test_a_german_template_is_mapped():
    df = _frame("Artikelnummer", "Bezeichnung", "Jahresverbrauch", "VPE", "Warengruppe",
                "Lieferant", "Standort", "Aktueller Bestand")
    got = cs.suggest_columns(df)
    assert got["Code"] == "Artikelnummer"
    assert got["Description"] == "Bezeichnung"
    assert got["Consumption_pcs"] == "Jahresverbrauch"
    assert got["PackUnits"] == "VPE"
    assert got["ProductCategory"] == "Warengruppe"
    assert got["SupplierCode"] == "Lieferant"
    assert got["Site"] == "Standort"
    # "Year" would match "Jahresverbrauch" by substring, but consumption owns it
    assert got["Year"] is None
    assert got["Stock_pcs"] == "Aktueller Bestand"
    assert set(got) == set(cs.REQUIRED_FIELDS) | set(cs.OPTIONAL_FIELDS)


def test_an_optional_field_never_takes_a_required_column():
    # "Standard/Special" synonyms include "Art", a substring of "Artikel"
    df = _frame("Artikel", "Text", "Verbrauch")
    got = cs.suggest_columns(df)
    assert got["Code"] == "Artikel"
    assert got["StdSpecial"] is None


def test_an_earlier_optional_field_wins_a_shared_column():
    df = _frame("Code", "Description", "Consumption", "Size")
    got = cs.suggest_columns(df)
    assert got["SizeCategory"] == "Size"


def test_the_ai_proposal_comes_first():
    df = _frame("Code", "Description", "Consumption", "VPE", "Gebinde")
    got = cs.suggest_columns(df, ai_guess={"PackUnits": "Gebinde"})
    assert got["PackUnits"] == "Gebinde"


def test_a_substring_match_of_an_earlier_field_wins():
    # "Size" (SizeCategory) is a substring of "Packsize" and comes first
    df = _frame("Code", "Description", "Consumption", "Packsize")
    got = cs.suggest_columns(df, ai_guess={"PackUnits": "Packsize"})
    assert got["SizeCategory"] == "Packsize" and got["PackUnits"] is None


def test_explicit_required_picks_are_honoured_and_claimed():
    df = _frame("Code", "Description", "Consumption", "Jahr")
    got = cs.suggest_columns(df, required={"Consumption_pcs": "Jahr"})
    assert got["Consumption_pcs"] == "Jahr"
    assert got["Year"] is None


def test_nothing_found_stays_unmapped():
    got = cs.suggest_columns(_frame("A", "B"))
    assert all(v is None for k, v in got.items() if k not in cs.REQUIRED_FIELDS)
