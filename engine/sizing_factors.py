"""kromi_app.engine.sizing_factors — split out of constants.py (v34.35).

Run-level sizing factors, time constants, and routing enums: the reserve
and overfill factors, days per month, listing names, and supply-point
modes.
"""

__all__ = ['CABINET_TYPES_VALID', 'CAROUSEL_RESERVE_FACTOR', 'DAYS_PER_MONTH', 'HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR', 'LISTING_PPE', 'LISTING_TOOLS', 'LISTING_VALID', 'PACK_MONTH_EPS', 'SP_MODE_PARTITION', 'SP_MODE_REPLICATE', 'SP_MODE_VALID']

# Carousel stockpile rule:
# reserve 85% of monthly packs
CAROUSEL_RESERVE_FACTOR = 0.85

# Helix rule:
# one spiral is enough up to 110% of its nominal capacity
HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR = 1.10

# Tolerance for "1 pack/month" logic
PACK_MONTH_EPS = 1e-9

# Days per month (Gregorian average). Used to convert a coverage-window in
DAYS_PER_MONTH = 30.4375

LISTING_TOOLS = "Tools"

LISTING_PPE = "PPE"

LISTING_VALID = {LISTING_TOOLS, LISTING_PPE}

SP_MODE_PARTITION = "partition"

SP_MODE_REPLICATE = "replicate"

SP_MODE_VALID = {SP_MODE_PARTITION, SP_MODE_REPLICATE}

CABINET_TYPES_VALID = {"Helix", "Carousel", "Locker A", "Locker B", "Locker C", "Kanban"}
