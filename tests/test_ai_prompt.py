"""Golden and structural tests for the AI classification prompt (v33.80).

The exact prompt wording drives the model's classification and is NOT part of the
batch cache key, so it must never drift unnoticed. It is pinned byte-for-byte
against tests/golden_classification_prompt.txt; if the prompt is changed on
purpose, regenerate that golden file in the same change.
"""

import json
from pathlib import Path

from engine.ai_classifier import build_classification_prompt

GOLDEN = (Path(__file__).parent / "golden_classification_prompt.txt").read_text(encoding="utf-8")

# The exact input the golden was captured from (includes non-ASCII to exercise
# ensure_ascii=False in the appended JSON).
FIXED_ITEMS = json.loads(r"""[
    {
        "row_id": "1",
        "listing": "Tools",
        "code": "CNMG 120408",
        "product_category_current": "inserts",
        "description": "turning insert",
        "description_2": "second line",
        "supplier_code": "seco",
        "pack_units_current": "10",
        "size_category_current": "M"
    },
    {
        "row_id": "2",
        "listing": "Tools",
        "code": "FORET Ø6.0",
        "product_category_current": "drills",
        "description": "carbide drill ä",
        "description_2": "",
        "supplier_code": "guhring",
        "pack_units_current": "1",
        "size_category_current": "S"
    },
    {
        "row_id": "42",
        "listing": "PPE",
        "code": "EARPLUG-X",
        "product_category_current": "ppe",
        "description": "ear protection",
        "description_2": "",
        "supplier_code": "3M",
        "pack_units_current": "1",
        "size_category_current": "S"
    }
]""")


def test_prompt_matches_golden_byte_for_byte():
    assert build_classification_prompt(FIXED_ITEMS) == GOLDEN


def test_prompt_is_stripped():
    p = build_classification_prompt(FIXED_ITEMS)
    assert p == p.strip()


def test_prompt_lists_every_product_category():
    p = build_classification_prompt(FIXED_ITEMS)
    for cat in ["inserts", "drills", "mills", "reamers", "holders",
                "screws", "accessories", "boring_bars", "ppe", "other"]:
        assert cat in p


def test_prompt_keeps_the_critical_rules():
    p = build_classification_prompt(FIXED_ITEMS)
    assert "Listing rule (CRITICAL)" in p
    assert "Insert rule (CRITICAL, Tools only)" in p
    assert "preserving the exact row_id" in p


def test_prompt_embeds_items_json_with_all_row_ids():
    p = build_classification_prompt(FIXED_ITEMS)
    start = p.index("[", p.index("Input items JSON:"))
    payload = json.loads(p[start:])
    assert [it["row_id"] for it in payload] == [it["row_id"] for it in FIXED_ITEMS]


def test_non_ascii_preserved_not_escaped():
    p = build_classification_prompt(FIXED_ITEMS)
    assert "\u00d8" in p and "\u00e4" in p          # the literal characters
    assert "\\u00d8" not in p                       # not the escaped form
