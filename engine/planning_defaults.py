"""Setting defaults and choice labels shared by every front end (v34.61).

The planner page used to spell each default inside its widget call, so a second
front end would have had to copy them. They live here once: the Streamlit page
reads them for its controls, and the new app reads them for its settings
object. Choices are stored as tokens; the labels are the texts the page shows
(and writes into Run_Metadata), kept in the page's option order.

Changing a value here changes the default of both apps; results for explicit
settings are unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

from .fixed_config import FIXED_MODE
from .sizing_factors import (
    CAROUSEL_RESERVE_FACTOR,
    HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR,
    SP_MODE_PARTITION,
    SP_MODE_REPLICATE,
)

#: Operation-mode tokens (``PlanParams.op_mode``); the numbering-only mode never
#: reaches the planner.
OP_STANDARD = ""
OP_HELIX = "Helix"
OP_CAROUSEL = "Carousel"
OP_CAPPED = "Capped"
OP_NUMBERING_ONLY = "NumberingOnly"

#: Tools + PPE handling.
CALC_COMBINED = "combined"
CALC_SEPARATED = "separated"


@dataclass(frozen=True)
class PlanningDefaults:
    """The value every setting starts from when nothing else is chosen."""

    # Source and planning base
    header_row: int = 1
    use_description_2: bool = True
    year_mode: str = "all_rows"
    dedup_mode: str = "code_supplier"
    # Routing and sizing
    ktc_threshold: float = 1.0
    insert_pack_units: int = 10
    helix_threshold: float = 6.0
    consumption_months: float = 12.0
    helix_overfill_factor: float = HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR
    min_carousel_allocation: int = 3
    coverage_days: int = 20
    coverage_days_special: int = 20
    special_ktc: bool = False
    carousel_reserve_factor: float = CAROUSEL_RESERVE_FACTOR
    carousel_fill_ceiling: float = 1.0
    enable_rebalancer: bool = True
    underuse_threshold_pct: float = 30.0
    capacity_buffer_pct: float = 15.0
    # Vend-mode controls
    pack_hint_extraction: bool = True
    bulk_routing: bool = False
    force_screws_kanban: bool = False
    # Supply points and listings
    n_supply_points: int = 1
    sp_mode: str = SP_MODE_REPLICATE
    calc_mode: str = CALC_COMBINED
    # Operation mode
    op_mode: str = OP_STANDARD
    max_carousels: int = 2
    fixed_headroom_pct: float = 10.0
    fixed_allow_spill: bool = True
    fixed_stock_promotion: bool = False
    fixed_stock_months: float = 3.0
    numbering_system: str = "Kanban"
    # Scope and exports
    ktc_id: str = "191"
    apply_overrides: bool = True
    include_planogram: bool = True
    include_technical: bool = False


DEFAULTS = PlanningDefaults()

#: Allowed range per numeric setting (inclusive; ``None`` = open), as the page's
#: controls enforce it.
LIMITS: Dict[str, Tuple[Optional[float], Optional[float]]] = {
    "header_row": (1, 50),
    "ktc_threshold": (0.0, None),
    "insert_pack_units": (1, None),
    "helix_threshold": (0.0, None),
    "consumption_months": (1.0, None),
    "helix_overfill_factor": (1.0, None),
    "min_carousel_allocation": (1, None),
    "coverage_days": (1, 90),
    "coverage_days_special": (1, 90),
    "carousel_reserve_factor": (0.05, 2.0),
    "carousel_fill_ceiling": (0.5, 1.0),
    "underuse_threshold_pct": (5.0, 80.0),
    "capacity_buffer_pct": (0.0, 200.0),
    "n_supply_points": (1, 10),
    "max_carousels": (1, 50),
    "fixed_headroom_pct": (0.0, 90.0),
    "fixed_stock_months": (0.5, 24.0),
}

#: Machines per supply point in the fixed configuration: (key, label, default).
FIXED_MACHINE_KINDS: Tuple[Tuple[str, str, int], ...] = (
    ("helix", "Helix", 1), ("carousel", "Carousel", 1),
    ("locker_a", "Locker A", 0), ("locker_b", "Locker B", 0),
    ("locker_c", "Locker C", 0),
)
FIXED_MAX_SUPPLY_POINTS = 10

# Labels (token -> text shown by the page), in the page's option order.
OP_MODE_LABELS: Dict[str, str] = {
    OP_STANDARD: "Standard (best fit per tool)",
    OP_HELIX: "Helix only",
    OP_CAROUSEL: "Carousel only",
    OP_CAPPED: "Helix + Carousel (capped)",
    FIXED_MODE: "Fixed configuration (existing machines)",
    OP_NUMBERING_ONLY: "Only article number assignment",
}
SP_MODE_LABELS: Dict[str, str] = {
    SP_MODE_REPLICATE: "Replicate \u2014 each item at every SP at 1/N consumption "
                       "(realistic default)",
    SP_MODE_PARTITION: "Partition \u2014 each item at ONE SP only, LPT balanced by "
                       "consumption",
}
CALC_MODE_LABELS: Dict[str, str] = {
    CALC_COMBINED: "Combined (one vending machine plan for both)",
    CALC_SEPARATED: "Separated (Tools and PPE each get their own plan)",
}
YEAR_MODE_LABELS: Dict[str, str] = {
    "all_rows": "Use all rows",
    "latest_year_only": "Keep latest year only",
}
DEDUP_MODE_LABELS: Dict[str, str] = {
    "none": "No deduplication",
    "code": "Deduplicate by Code",
    "code_supplier": "Deduplicate by Code + Supplier",
}
NUMBERING_SYSTEM_LABELS: Dict[str, str] = {
    "Kanban": "Kanban \u2014 one KROMI number per article",
    "KTC": "KTC \u2014 customer-property predecessor + KROMI successor pair",
}

_MISSING = object()


def label_index(labels: Mapping[str, str], token: str) -> int:
    """Position of ``token``'s label among the options (for a select control)."""
    return list(labels).index(token)


def token_for(labels: Mapping[str, str], label: str, default: object = _MISSING) -> str:
    """The token whose label is ``label``; ``default`` when unknown (else KeyError)."""
    for token, text in labels.items():
        if text == label:
            return token
    if default is _MISSING:
        raise KeyError(label)
    return str(default)
