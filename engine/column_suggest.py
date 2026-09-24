"""The column each planning field starts from (v34.62).

Moved out of the planner page so every front end suggests the same mapping
for an uploaded sheet. A field takes the AI proposal when there is one, else
the first header matching its synonyms (exact first, then as a substring, so
German compounds such as "Jahresverbrauch" still read as consumption). The
stock column has its own rule (``takeover.guess_stock_column``). Optional
fields never take a column a required field or an earlier optional field
already uses (``colmap.deconflict_defaults``). The user confirms every field.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional

import pandas as pd

from .colmap import (
    CODE_SYNONYMS,
    CONSUMPTION_SYNONYMS,
    DESCRIPTION_SYNONYMS,
    deconflict_defaults,
)
from .takeover import STOCK_COL, guess_stock_column
from .text_utils import guess_column

REQUIRED_FIELDS = ("Code", "Description", "Consumption_pcs")
#: Optional fields in deconflict order: an earlier field wins a shared column.
OPTIONAL_FIELDS = (
    "ProductCategory", "Year", "Description_2", "Program", "Restocking",
    "SupplierCode", "SizeCategory", "Site", "StdSpecial", "PackUnits",
    "PackageDimensions", "Regrind", "SystemTyp", STOCK_COL,
)

SYNONYMS: Dict[str, List[str]] = {
    "Code": CODE_SYNONYMS,
    "Description": DESCRIPTION_SYNONYMS,
    "Consumption_pcs": CONSUMPTION_SYNONYMS,
    "ProductCategory": ["ProductCategory", "Produktkategorie", "Warengruppe", "Category"],
    "Description_2": ["Description_2", "Description2", "Langtext", "Zusatztext"],
    "SupplierCode": ["SupplierCode", "Lieferant", "Hersteller", "Manufacturer", "Supplier"],
    "PackUnits": ["PackUnits", "VPE", "VE", "Pack", "Packsize", "Packaging"],
    "SizeCategory": ["SizeCategory", "Size", "Größe", "Groesse", "KTC Size"],
    "Year": ["Year", "Jahr", "FiscalYear", "PeriodYear"],
    "Program": ["Program", "Programme", "Programma", "Programa", "Project", "Projekt", "Area",
                "Bereich", "Section"],
    "Restocking": ["Restocking", "Restock", "Restockable", "Nachfüllen", "Nachfuellen",
                   "Nachschub", "Refill", "Auffüllen", "Auffuellen"],
    "Site": ["Site", "Sites", "Standort", "Plant", "Factory", "Usine", "Werk"],
    "StdSpecial": [
        "Standard/Special", "Standard / Special", "StandardSpecial", "Std/Special",
        "Standard/Sonder", "Standard / Sonder", "Art", "Tooltype", "Tool type",
        "Typ", "Type", "Klasse", "Class", "Kategorie",
    ],
    "PackageDimensions": [
        "PackageDimensions", "Package dimensions", "Packagedimensions", "Package_Dimensions",
        "Abmessungen", "Abmessung", "Maße", "Masse", "Dimensions", "Dimension",
        "Verpackungsmaße", "Verpackungsmasse", "Größe LxBxH", "LxBxH", "L x B x H",
        "Package Size", "Packmaß", "Packmasse",
    ],
    "Regrind": [
        "Regrind", "Re-grind", "Regrindable", "Regrinding", "Reground",
        "Nachschleifbar", "Nachschleifen", "Nachschliff", "Schleifbar",
        "Wiederaufbereitbar", "Aufbereitbar",
    ],
    "SystemTyp": [
        "SystemTyp", "System type", "Systemtyp", "System Typ", "Lagersystem",
        "Lagersystem (KTC, usw)", "Storage system", "Vending system", "System",
    ],
}


def raw_guesses(df: pd.DataFrame,
                ai_guess: Optional[Mapping[str, Optional[str]]] = None) -> Dict[str, Optional[str]]:
    """Every field's first guess, before any column conflict is resolved."""
    ai = dict(ai_guess or {})
    out: Dict[str, Optional[str]] = {}
    for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
        if field == STOCK_COL:
            # Stock has its own rule; the AI proposal does not cover it.
            out[field] = guess_stock_column(df)
        else:
            out[field] = ai.get(field) or guess_column(df, SYNONYMS[field])
    return out


def suggest_columns(df: pd.DataFrame,
                    ai_guess: Optional[Mapping[str, Optional[str]]] = None,
                    required: Optional[Mapping[str, Optional[str]]] = None,
                    ) -> Dict[str, Optional[str]]:
    """The suggested source column per field (``None`` = leave unmapped).

    ``required`` holds explicit picks for the required fields; they replace
    the guesses and claim their columns before the optional fields choose.
    """
    guesses = raw_guesses(df, ai_guess)
    picked = dict(required or {})
    req = {f: (picked[f] if f in picked else guesses[f]) for f in REQUIRED_FIELDS}
    optional = deconflict_defaults(req, {f: guesses[f] for f in OPTIONAL_FIELDS})
    return {**req, **optional}
