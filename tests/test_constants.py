"""Tests for engine.constants — taxonomy integrity.

These verify the constants haven't drifted (no typos, no missing entries,
no accidentally removed mappings). They lock the domain taxonomies that
the rest of the engine depends on."""

import pytest

from engine import constants as c

# ---- Product category taxonomy ----

def test_pc_valid_is_kromi_aligned():
    """PC_VALID has been aligned to the Kromi L1 taxonomy.
    Expected size: 24 (10 original + 14 new Kromi-aligned categories)."""
    assert isinstance(c.PC_VALID, (set, list, tuple, frozenset))
    assert len(c.PC_VALID) == 24


def test_pc_valid_contains_kromi_categories():
    """All 19 Kromi L1 categories must have a matching PC, plus 4 engine-only PCs."""
    expected = {
        # Original engine PCs that map directly to Kromi L1
        "inserts",        # Wendeschneidplatten
        "drills",         # Bohrer
        "mills",          # Fräser
        "reamers",        # Reibahlen
        "holders",        # Halter
        "accessories",    # Zubehör
        "other",          # Weitere
        # Engine-specific (not in Kromi L1 taxonomy)
        "screws", "ppe", "boring_bars",
        # Kromi-aligned categories
        "taps", "thread_mills", "thread_dies",  # split out of Gewindewerkzeuge
        "counterbores",   # Senker
        "tool_holders",   # Werkzeugaufnahme
        "grinding_tools", # Schleifkörper
        "brushes",        # Bürste
        "broaches",       # Räumwerkzeug
        "honing_tools",   # Honahlen
        "gear_cutting",   # Verzahnungswerkzeug
        "center_points",  # Zentrierspitzen
        "welding",        # Schweißen
        "punching",       # Stanzwerkzeug
        "form_steel",     # Formstahl
    }
    assert set(c.PC_VALID) == expected


def test_tool_class_valid_is_expanded():
    """ToolClass taxonomy expanded for L2 detail across new categories.
    Should be a substantially larger set than the original 24."""
    assert len(c.TOOL_CLASS_VALID) >= 70  # 81 currently; allow growth


def test_tool_class_valid_includes_canonical():
    """A few canonical tool classes that must be present."""
    must_have = {
        "turning_insert", "milling_insert", "drilling_insert",
        "solid_carbide_drill", "solid_end_mill", "reamer",
        "grinding_wheel", "other",
    }
    assert must_have.issubset(set(c.TOOL_CLASS_VALID))


def test_toolclass_from_product_category_is_dict():
    assert isinstance(c.TOOLCLASS_FROM_PRODUCT_CATEGORY, dict)
    # All PCs that map should be in PC_VALID
    for pc in c.TOOLCLASS_FROM_PRODUCT_CATEGORY.keys():
        assert pc in c.PC_VALID
    # All target tool classes must be in TOOL_CLASS_VALID
    for tc in c.TOOLCLASS_FROM_PRODUCT_CATEGORY.values():
        assert tc in c.TOOL_CLASS_VALID


# ---- Size taxonomy ----

def test_slide_bucket_order_is_list_of_strings():
    assert isinstance(c.SLIDE_BUCKET_ORDER, list)
    assert all(isinstance(x, str) for x in c.SLIDE_BUCKET_ORDER)
    assert len(c.SLIDE_BUCKET_ORDER) > 0


# ---- Cabinet specs ----

def test_helix_spirals_per_cab_is_70():
    """Helix machines have exactly 70 spirals per cabinet."""
    assert c.HELIX_SPIRALS_PER_CAB == 70


def test_carousel_slots_per_cab_is_720():
    """Carousel machines have exactly 720 slots per cabinet."""
    assert c.CAROUSEL_SLOTS_PER_CAB == 720


def test_locker_capacities():
    """Lockers A=48, B=72, C=96."""
    assert c.LOCKER_A_CAP == 48
    assert c.LOCKER_B_CAP == 72
    assert c.LOCKER_C_CAP == 96


def test_factor_defaults():
    """The runtime-mutable factors have known starting defaults."""
    assert c.CAROUSEL_RESERVE_FACTOR == pytest.approx(0.85)
    assert c.HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR == pytest.approx(1.10)


# ---- Listing tags ----

def test_listing_constants_are_strings():
    assert isinstance(c.LISTING_TOOLS, str) and len(c.LISTING_TOOLS) > 0
    assert isinstance(c.LISTING_PPE, str) and len(c.LISTING_PPE) > 0


# ---- Keyword lists ----

def test_keyword_lists_nonempty():
    """All keyword lists should have at least one entry."""
    for name in ["INSERT_KEYWORDS", "DRILL_KEYWORDS", "MILL_KEYWORDS",
                 "REAMER_KEYWORDS", "HOLDER_KEYWORDS", "SCREW_KEYWORDS",
                 "ACCESSORY_KEYWORDS", "PPE_KEYWORDS", "BORING_BAR_KEYWORDS"]:
        kws = getattr(c, name)
        assert len(kws) > 0, f"{name} is empty"
        assert all(isinstance(k, str) for k in kws), f"{name} has non-string"


def test_french_shorthand_lists_nonempty():
    for name in ["DRILL_SHORTHAND_FR", "MILL_SHORTHAND_FR",
                 "REAMER_SHORTHAND_FR", "GRINDING_SHORTHAND_FR"]:
        kws = getattr(c, name)
        assert len(kws) > 0, f"{name} is empty"


# ---- Supplier patterns ----

def test_supplier_code_patterns_has_entries():
    """SUPPLIER_CODE_PATTERNS is a list of 5-tuples."""
    assert isinstance(c.SUPPLIER_CODE_PATTERNS, list)
    assert len(c.SUPPLIER_CODE_PATTERNS) >= 15
    for entry in c.SUPPLIER_CODE_PATTERNS:
        assert len(entry) == 5, f"bad tuple shape: {entry}"
        brand, pattern, cat, tool_class, evidence = entry
        assert isinstance(brand, str) and brand
        assert isinstance(pattern, str) and pattern
        assert cat in c.PC_VALID, f"unknown PC in supplier pattern: {cat}"
        assert tool_class in c.TOOL_CLASS_VALID, f"unknown TC: {tool_class}"
        assert isinstance(evidence, str) and evidence


def test_supplier_specialty_has_entries():
    """SUPPLIER_SPECIALTY is a dict of brand → (cat, tc, evidence)."""
    assert isinstance(c.SUPPLIER_SPECIALTY, dict)
    assert len(c.SUPPLIER_SPECIALTY) > 0
    for brand, payload in c.SUPPLIER_SPECIALTY.items():
        assert isinstance(brand, str) and brand
        assert len(payload) == 3
        cat, tc, evidence = payload
        assert cat in c.PC_VALID
        assert tc in c.TOOL_CLASS_VALID
        assert isinstance(evidence, str)


# ---- Bulk family sets ----

def test_bulk_families_are_sets():
    assert isinstance(c.BULK_ALWAYS_FAMILIES, (set, frozenset))
    assert isinstance(c.DISPOSABLE_PPE_FAMILIES, (set, frozenset))
    # All values are strings
    for f in c.BULK_ALWAYS_FAMILIES | c.DISPOSABLE_PPE_FAMILIES:
        assert isinstance(f, str)


# ---- Pack hint patterns ----

def test_pack_hint_patterns_is_list_of_tuples():
    assert isinstance(c.PACK_HINT_PATTERNS, list)
    assert len(c.PACK_HINT_PATTERNS) > 0
    for entry in c.PACK_HINT_PATTERNS:
        assert len(entry) == 2
        pattern, label = entry
        assert isinstance(pattern, str)
        assert isinstance(label, str)


# ---- SP mode constants ----

def test_sp_mode_constants():
    assert c.SP_MODE_PARTITION == "partition"
    assert c.SP_MODE_REPLICATE == "replicate"
    assert c.SP_MODE_PARTITION in c.SP_MODE_VALID
    assert c.SP_MODE_REPLICATE in c.SP_MODE_VALID
