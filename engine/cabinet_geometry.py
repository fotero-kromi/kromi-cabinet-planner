"""kromi_app.engine.cabinet_geometry — split out of constants.py (v34.35).

Physical machine geometry and capacities: Helix coils and drawers,
Carousel slot geometries, Locker grids and boxes. Values marked spec come
from the manufacturer drawings; derived values state their formula.
"""

__all__ = ['CAROUSEL_SLOTS', 'CAROUSEL_SLOTS_PER_CAB', 'HELIX_COILS_PER_DRAWER', 'HELIX_COIL_CLEAR_DIAMETER_MM', 'HELIX_COIL_RING_DIAMETER_MM', 'HELIX_COIL_USABLE_LENGTH_MM', 'HELIX_COIL_WIRE_MM', 'HELIX_DRAWERS', 'HELIX_DRAWER_PITCH_MM', 'HELIX_MAX_PITCH_MM', 'HELIX_SPIRALS_PER_CAB', 'HELIX_SPIRAL_PITCHES_MM', 'LOCKER_A_CAP', 'LOCKER_BOXES', 'LOCKER_BOX_DEPTH_MM', 'LOCKER_BOX_WIDTH_MM', 'LOCKER_B_CAP', 'LOCKER_C_CAP', 'LOCKER_GRID_OFFSET_MM', 'LOCKER_GRID_UNIT_MM']

# CABINET CONFIG (capacity is fixed; thresholds are configurable via UI)
HELIX_SPIRALS_PER_CAB = 70

CAROUSEL_SLOTS_PER_CAB = 720

LOCKER_A_CAP = 48

LOCKER_B_CAP = 72

LOCKER_C_CAP = 96


# ---------------------------------------------------------------------------
# PHYSICAL COMPARTMENT DIMENSIONS (millimetres)
# ---------------------------------------------------------------------------
# Source: KROMI / Storetec manufacturer spec sheets and engineering drawings.
# Where flyer and drawing disagree, the engineering drawing wins (flyers are
# marketing documents and contain transcription errors).
#
# These feed the OPTIONAL dimensional fit-check. They are NOT used by the
# default count/velocity-based planning path, so adding them changes no
# existing behaviour.
#
# Each dimension carries a "confidence" tag:
#   "spec"      — read directly from a drawing or manufacturer table
#   "derived"   — computed from a manufacturer formula
#   "estimated" — best estimate; flagged for confirmation (TBC)
#
# All measurements are USABLE internal envelope in mm.

# --- HELIX: spiral coils across 7 drawers ----------------------------------
# Source: ACD spiral drawings 1064/S01, 1065/S01, 1066/S01 (engineering,
# authoritative) + Häwa body drawing for the drawer layout.
#
# A tool rides on a spiral coil. A plastic end-cap on each coil stops it
# falling off the front; when the coil rotates the tool drops into a foam-
# padded catch box at the bottom (that foam is drop-cushioning, NOT a tool
# pocket, so it does not bound tool size). The coil geometry is what bounds
# the tool:
#   - DIAMETER  : the Ø68 mm coil ring is the cross-section envelope
#                 (Ø4 mm wire, ~64 mm clear inside the ring)
#   - THICKNESS : a tool occupies the gap between turns, so its thickness in
#                 the feed direction must be <= the spiral pitch (Steigung)
#   - LENGTH    : tools ride along the coil (~520-540 mm usable) and can
#                 extend into the inter-drawer gap, so length is rarely binding
HELIX_DRAWERS = 7  # spec — Häwa drawing, 7 drawers
HELIX_COILS_PER_DRAWER = 10  # spec — 10 coils per drawer (7*10 = 70)
HELIX_DRAWER_PITCH_MM = 184.0  # spec — vertical gap between drawer bases
HELIX_COIL_RING_DIAMETER_MM = 68.0  # spec — Ø68 coil ring (ACD drawings)
HELIX_COIL_WIRE_MM = 4.0  # spec — Ø4 wire
HELIX_COIL_CLEAR_DIAMETER_MM = 64.0  # derived — 68 minus wire; usable tool Ø
HELIX_COIL_USABLE_LENGTH_MM = 520.0  # spec — shortest usable coil run (52 mm pitch)

# Spiral types: pitch (Steigung) = max tool thickness in the feed direction.
HELIX_SPIRAL_PITCHES_MM = {
    # spiral_type: (pitch_mm, turns, confidence)
    "P52": (52.0, 12.5, "spec"),  # drawing 1066/S01
    "P30": (30.0, 20.5, "spec"),  # drawing 1065/S01
    "P24": (24.5, 24.5, "spec"),  # drawing 1064/S01
    "P18": (18.0, 28.0, "spec"),  # HELIX flyer (no ACD drawing on hand)
    "P15": (15.0, 29.0, "estimated"),  # 5th/narrowest — flyer "up to 29 turns"; TBC
}
# Widest pitch = the most a single tool can occupy in the feed direction.
HELIX_MAX_PITCH_MM = 52.0  # spec — Größe P52

# --- CAROUSEL: two slot geometries (radial drum segments) -----------------
# Source: KROMI engineering drawing K00002535 + customer confirmation.
#   "rect" : rectangular slot, 87 x 68 mm (outer)
#   "pie"  : triangular slot, 87 mm at outer, tapering to 6 mm at the inner part
# Both share a 195 mm radial depth.
CAROUSEL_SLOTS = {
    # slot_type: usable envelope, mm
    "rect": {
        "outer_width_mm": 87.0,  # spec — rectangle width
        "inner_width_mm": 87.0,  # spec — rectangular (no taper)
        "height_mm": 68.0,  # spec — 87 x 68
        "depth_mm": 195.0,  # spec — radial depth
        "confidence": "spec",
    },
    "pie": {
        "outer_width_mm": 87.0,  # spec — wide (outer) end
        "inner_width_mm": 6.0,  # spec — narrow end at hub
        "height_mm": 50.0,  # spec — side view
        "depth_mm": 195.0,  # spec — radial depth
        "confidence": "spec",
    },
}

# --- LOCKER: grid-based boxes ---------------------------------------------
# Source: Storetec "Sonderkonfiguration" sheets (authoritative; the Locker
# flyer's per-box height column is inverted and not used).
# Every box is 180 mm wide x 500 mm deep. Height follows the manufacturer
# formula from a fixed 24-unit column:
#       usable_height_mm = 77.5 * grid_units - 15      (minimum 2 grid units)
# Model -> cabinet layout (customer-confirmed):
#   Locker A (48): one 48-type column, boxes of 2 grid units  -> 140 mm
#   Locker C (96): one 96-type column, boxes of 1 grid unit   -> 62.5 mm
#   Locker B (72): a SPLIT cabinet — one column of 48-type boxes (140 mm) and
#                  one column of 24-type boxes (4 grid units -> 295 mm).
LOCKER_BOX_WIDTH_MM = 180.0  # spec — constant across all models
LOCKER_BOX_DEPTH_MM = 500.0  # spec — constant across all models
LOCKER_GRID_UNIT_MM = 77.5  # spec — Storetec formula coefficient
LOCKER_GRID_OFFSET_MM = 15.0  # spec — Storetec formula offset


def _locker_box_height_mm(grid_units: float) -> float:
    """Usable box height from the Storetec grid formula."""
    return LOCKER_GRID_UNIT_MM * grid_units - LOCKER_GRID_OFFSET_MM


# Per-model usable box envelope(s). A model may offer more than one box size;
# the fit-checker tries the smallest box that fits (then larger).
LOCKER_BOXES = {
    "Locker A": {  # 48-box model — uniform 2-grid-unit boxes
        "boxes_per_cabinet": 48,
        "box_sizes_mm": [
            {
                "width_mm": LOCKER_BOX_WIDTH_MM,
                "depth_mm": LOCKER_BOX_DEPTH_MM,
                "height_mm": _locker_box_height_mm(2),
                "confidence": "derived",
            },  # 140.0
        ],
    },
    "Locker B": {  # 72-box model — split: 48-type column + 24-type column
        "boxes_per_cabinet": 72,
        "box_sizes_mm": [
            {
                "width_mm": LOCKER_BOX_WIDTH_MM,
                "depth_mm": LOCKER_BOX_DEPTH_MM,
                "height_mm": _locker_box_height_mm(2),
                "confidence": "spec",
            },  # 140.0 (48-type)
            {
                "width_mm": LOCKER_BOX_WIDTH_MM,
                "depth_mm": LOCKER_BOX_DEPTH_MM,
                "height_mm": _locker_box_height_mm(4),
                "confidence": "spec",
            },  # 295.0 (24-type)
        ],
    },
    "Locker C": {  # 96-box model — uniform 1-grid-unit boxes
        "boxes_per_cabinet": 96,
        "box_sizes_mm": [
            {
                "width_mm": LOCKER_BOX_WIDTH_MM,
                "depth_mm": LOCKER_BOX_DEPTH_MM,
                "height_mm": _locker_box_height_mm(1),
                "confidence": "derived",
            },  # 62.5
        ],
    },
}
