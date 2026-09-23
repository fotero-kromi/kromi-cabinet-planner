"""Facade contract for the constants split (v34.35).

engine/constants.py becomes a facade over four topical modules; the public
surface, the values, and the object identities must be exactly what the
single-file module exposed, so no import anywhere in the tree can notice
the reorganization.
"""

import importlib


FROZEN_SURFACE = ['ACCESSORY_KEYWORDS', 'BORING_BAR_KEYWORDS', 'BROACH_KEYWORDS', 'BRUSH_KEYWORDS', 'BULK_ALWAYS_FAMILIES', 'CABINET_TYPES_VALID', 'CAROUSEL_RESERVE_FACTOR', 'CAROUSEL_SLOTS', 'CAROUSEL_SLOTS_PER_CAB', 'CENTER_POINT_KEYWORDS', 'COUNTERBORE_KEYWORDS', 'DAYS_PER_MONTH', 'DISPOSABLE_PPE_FAMILIES', 'DRILL_KEYWORDS', 'DRILL_SHORTHAND_FR', 'FORM_STEEL_KEYWORDS', 'GEAR_CUTTING_KEYWORDS', 'GRINDING_SHORTHAND_FR', 'GRINDING_TOOL_KEYWORDS', 'HELIX_COILS_PER_DRAWER', 'HELIX_COIL_CLEAR_DIAMETER_MM', 'HELIX_COIL_RING_DIAMETER_MM', 'HELIX_COIL_USABLE_LENGTH_MM', 'HELIX_COIL_WIRE_MM', 'HELIX_DRAWERS', 'HELIX_DRAWER_PITCH_MM', 'HELIX_MAX_PITCH_MM', 'HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR', 'HELIX_SPIRALS_PER_CAB', 'HELIX_SPIRAL_PITCHES_MM', 'HOLDER_KEYWORDS', 'HONING_TOOL_KEYWORDS', 'INSERT_KEYWORDS', 'KEYWORD_TO_TOOLCLASS', 'LISTING_PPE', 'LISTING_TOOLS', 'LISTING_VALID', 'LOCKER_A_CAP', 'LOCKER_BOXES', 'LOCKER_BOX_DEPTH_MM', 'LOCKER_BOX_WIDTH_MM', 'LOCKER_B_CAP', 'LOCKER_C_CAP', 'LOCKER_GRID_OFFSET_MM', 'LOCKER_GRID_UNIT_MM', 'MILL_KEYWORDS', 'MILL_SHORTHAND_FR', 'OVERRIDE_COLUMNS', 'OVERRIDE_SCHEMA_VERSION', 'OVERRIDE_VALID_CABINETS', 'OVERRIDE_VALID_SIZES', 'OVERRIDE_VALID_VEND', 'PACK_HINT_PATTERNS', 'PACK_MONTH_EPS', 'PC_VALID', 'PPE_KEYWORDS', 'PUNCHING_KEYWORDS', 'REAMER_KEYWORDS', 'REAMER_SHORTHAND_FR', 'SCREW_KEYWORDS', 'SIZE_VALID', 'SLIDE_BUCKET_ORDER', 'SLIDE_DISTRIBUTION_BUCKETS', 'SP_MODE_PARTITION', 'SP_MODE_REPLICATE', 'SP_MODE_VALID', 'SUPPLIER_CODE_PATTERNS', 'SUPPLIER_SPECIALTY', 'TAP_KEYWORDS', 'THREAD_DIE_KEYWORDS', 'THREAD_MILL_KEYWORDS', 'THRESHOLD_CATEGORIES', 'TOOLCLASS_FROM_PRODUCT_CATEGORY', 'TOOLCLASS_TO_BUCKET', 'TOOLCLASS_TO_PRODUCT_CATEGORY', 'TOOL_CLASS_VALID', 'TOOL_HOLDER_KEYWORDS', 'WELDING_KEYWORDS']


def test_public_surface_is_frozen():
    import engine.constants as c
    names = sorted(set(n for n in dir(c) if not n.startswith("_")))
    assert names == FROZEN_SURFACE, (
        "the facade must expose exactly the pre-split public surface"
    )


def test_the_four_topical_modules_exist():
    for mod in ("engine.cabinet_geometry", "engine.sizing_factors",
                "engine.override_schema", "engine.classification_tables"):
        importlib.import_module(mod)


def test_spot_values_and_identity():
    import engine.constants as c
    from engine import override_schema, cabinet_geometry, sizing_factors

    assert c.HELIX_SPIRALS_PER_CAB == 70
    assert c.CAROUSEL_SLOTS_PER_CAB == 720
    assert c.DAYS_PER_MONTH == 30.4375
    assert "restocking_override" in c.OVERRIDE_COLUMNS
    assert c.OVERRIDE_COLUMNS is override_schema.OVERRIDE_COLUMNS
    assert c.HELIX_SPIRALS_PER_CAB is cabinet_geometry.HELIX_SPIRALS_PER_CAB
    assert c.DAYS_PER_MONTH is sizing_factors.DAYS_PER_MONTH


def test_no_name_collisions_across_the_topical_modules():
    """Star re-exports resolve last-wins on collisions while preserving the
    frozen surface; forbid collisions outright so that failure mode cannot
    exist."""
    from engine import (cabinet_geometry, classification_tables,
                        override_schema, sizing_factors)
    mods = (cabinet_geometry, sizing_factors, override_schema, classification_tables)
    seen = {}
    for m in mods:
        for name in m.__all__:
            assert name not in seen, (
                f"{name} exported by both {seen[name]} and {m.__name__}"
            )
            seen[name] = m.__name__
