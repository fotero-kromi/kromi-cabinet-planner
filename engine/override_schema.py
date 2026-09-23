"""kromi_app.engine.override_schema — split out of constants.py (v34.35).

The technician override schema: the column list, its version, and the
valid value sets the editor and the apply layer share.
"""

__all__ = ['OVERRIDE_COLUMNS', 'OVERRIDE_SCHEMA_VERSION', 'OVERRIDE_VALID_CABINETS', 'OVERRIDE_VALID_SIZES', 'OVERRIDE_VALID_VEND']

OVERRIDE_SCHEMA_VERSION = "v28"

OVERRIDE_COLUMNS = [
    "code",
    "listing",
    "product_category_override",
    "pack_units_override",
    "size_category_override",
    "cabinet_type_override",
    "vend_mode_override",
    "restocking_override",
    "note",
    "reviewed_by",
    "reviewed_at",
]

OVERRIDE_VALID_CABINETS = {"Helix", "Carousel", "Locker A", "Locker B", "Locker C", "Kanban"}

OVERRIDE_VALID_VEND = {"Vending", "Bulk/Kanban"}

OVERRIDE_VALID_SIZES = {"S", "M", "L", "XL", "XXL"}
