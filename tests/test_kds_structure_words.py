"""Contracts for the KDS structure-code vocabulary (v34.47).

KROMI's KDS onboarding template constrains Bezeichnung 1 to the official
structure-code list. Mapping that column as ProductCategory should resolve
EVERY structure-code word deterministically, but ~660 of the 963 words were
unknown to `normalize_product_category` and fell back to text heuristics,
which miscoded countersinks (13 instead of 17), holder adapters (11) and
extensions (20 vs 20008). The fix embeds the structure-code words as an
exact-match table checked before the keyword matcher, mapped by the list's
own L1 family. Collet entries ("... Spannzangen") are included as
tool_holders, aligning with the engine matrix's collet = 20008.
"""

from engine.classification import normalize_product_category
from engine.constants import PC_VALID, TOOLCLASS_FROM_PRODUCT_CATEGORY
from engine.kds_structure_words import KDS_STRUCTURE_CATEGORY
from engine.kromi_numbering import KROMI_RULESET


# ---- the words that were miscoded in the field ------------------------------

def test_senker_words_resolve_to_counterbores():
    for raw in ("Kegelsenker HSS", "Kegelsenker HSS-E/HSCO",
                "Rückwärtssenker VHM", "Flachsenker HSS", "Stufensenker VHM"):
        assert normalize_product_category(raw) == "counterbores", raw


def test_holder_adapter_words_resolve_to_tool_holders():
    for raw in ("ABS50 Verlängerung", "ABS80 Reduzierung", "SK50 ABS",
                "Capto Aufsteck-Fräsdorn", "MASBT50 ABS", "HSK63 Verlängerung",
                "SK50 Weldon"):
        assert normalize_product_category(raw) == "tool_holders", raw
    # A cell deviating from the official list (e.g. "Capto-Adapter") is not
    # in the table and falls back to today's behaviour.
    assert normalize_product_category("Capto-Adapter") == "other"


def test_collets_align_with_matrix_not_accessories():
    # The engine matrix says collet -> 20008; the structure list's L1 agrees.
    for raw in ("HSK63 Spannzangen", "SK50 Spannzangen", "ABS50 Spannzangen"):
        assert normalize_product_category(raw) == "tool_holders", raw


def test_special_families():
    assert normalize_product_category("feste Zentrierspitze Stahl") == "center_points"
    assert normalize_product_category("Wechselplatte Bohren VHM") == "inserts"


# ---- unchanged behaviour ----------------------------------------------------

def test_existing_words_unchanged():
    assert normalize_product_category("Schraube") == "screws"
    assert normalize_product_category("Spiralbohrer VHM") == "drills"
    assert normalize_product_category("Gewindebohrer HSS") == "taps"
    assert normalize_product_category("Halter Bohrstange") == "boring_bars"
    assert normalize_product_category("völlig unbekanntes Wort") == "other"
    assert normalize_product_category("") == ""


# ---- the resulting KROMI codes ----------------------------------------------

def test_categories_reach_the_right_code():
    for cat, code in (("counterbores", "17"), ("tool_holders", "20008"),
                      ("center_points", "13"), ("grinding_tools", "19")):
        tool_class = TOOLCLASS_FROM_PRODUCT_CATEGORY[cat]
        assert KROMI_RULESET.code_matrix[tool_class] == code, (cat, tool_class)


# ---- table hygiene ----------------------------------------------------------

def test_table_values_are_valid_categories():
    assert len(KDS_STRUCTURE_CATEGORY) > 500
    for k, v in KDS_STRUCTURE_CATEGORY.items():
        assert v in PC_VALID and v != "other", (k, v)
        # keys are stored pre-normalized so lookups are one dict hit
        from engine.text_utils import norm
        assert norm(k) == k, k
