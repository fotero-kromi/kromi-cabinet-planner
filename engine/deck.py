"""kromi_app.engine.deck — pure content model for the KROMI presentation deck.

This holds the data and the small amount of logic that decides *what* goes on the
generated slides (the plan-summary stat cards). It is pure and testable: no
python-pptx, no I/O. The actual rendering into a branded .pptx lives in
`presentation.py`, which consumes the structures defined here.
"""

from __future__ import annotations

from dataclasses import dataclass

# KROMI house palette (from the corporate decks).
KROMI_GREEN_DARK = "006954"
KROMI_GREEN_BRIGHT = "49B848"
KROMI_GREEN_MINT = "AAE2CA"
KROMI_HEADER_FONT = "MetaOT-Bold"
KROMI_BODY_FONT = "MetaOT-Book"


@dataclass(frozen=True)
class DeckStats:
    """Headline figures for the plan-summary deck, gathered from a planner run."""

    customer: str = ""
    site: str = ""
    date_str: str = ""
    supply_points: int = 0
    total_cabinets: int = 0
    helix: int = 0
    carousel: int = 0
    lockers: int = 0
    ktc_items: int = 0
    kanban_items: int = 0
    total_items: int = 0


@dataclass(frozen=True)
class StatCard:
    value: str
    label: str


def summary_cards(stats: DeckStats) -> list[StatCard]:
    """Headline metric cards for the plan-summary slide, in display order.

    Cabinet-type cards (Helix/Carousel/Lockers) are included only when that type
    is actually used, so the slide isn't padded with zero-machine cards. Supply
    points, total cabinets, KTC items, and items managed are always shown.
    """
    cards: list[StatCard] = [
        StatCard(str(stats.supply_points), "Supply points"),
        StatCard(str(stats.total_cabinets), "Cabinets total"),
    ]
    if stats.helix:
        cards.append(StatCard(str(stats.helix), "Helix"))
    if stats.carousel:
        cards.append(StatCard(str(stats.carousel), "Carousel"))
    if stats.lockers:
        cards.append(StatCard(str(stats.lockers), "Lockers"))
    cards.append(StatCard(str(stats.ktc_items), "KTC items"))
    if stats.kanban_items:
        cards.append(StatCard(str(stats.kanban_items), "Kanban items"))
    cards.append(StatCard(str(stats.total_items), "Items managed"))
    return cards


def summary_pyramid(stats: DeckStats) -> list[list[StatCard]]:
    """The summary metric cards arranged as three stacked tiers, top to bottom,
    so the slide reads as a pyramid:

    1. scope — supply points and total cabinets;
    2. the cabinet-type breakdown — Helix / Carousel / Lockers, only the types
       in use;
    3. the item split — items managed, KTC items, and (when any) Kanban items.

    The renderer centres each tier, so a narrower top tier sits above the wider
    item tier. The middle (cabinet) tier is dropped only when the plan has no
    cabinets of any type, leaving a sensible two-tier stack.
    """
    tier_scope = [
        StatCard(str(stats.supply_points), "Supply points"),
        StatCard(str(stats.total_cabinets), "Cabinets total"),
    ]
    tier_cabinets: list[StatCard] = []
    if stats.helix:
        tier_cabinets.append(StatCard(str(stats.helix), "Helix"))
    if stats.carousel:
        tier_cabinets.append(StatCard(str(stats.carousel), "Carousel"))
    if stats.lockers:
        tier_cabinets.append(StatCard(str(stats.lockers), "Lockers"))
    tier_items = [
        StatCard(str(stats.total_items), "Items managed"),
        StatCard(str(stats.ktc_items), "KTC items"),
    ]
    if stats.kanban_items:
        tier_items.append(StatCard(str(stats.kanban_items), "Kanban items"))
    tiers = [tier_scope]
    if tier_cabinets:
        tiers.append(tier_cabinets)
    tiers.append(tier_items)
    return tiers


def summary_subtitle(stats: DeckStats) -> str:
    """The bright-green subtitle under 'SUMMARY' (e.g. 'ACME VENDING').

    Uses the customer name; if blank, falls back to the site, so a run with only
    a site filled in still gets a meaningful subtitle rather than the generic
    placeholder.
    """
    name = (stats.customer or "").strip().upper() or (stats.site or "").strip().upper()
    return f"{name} VENDING" if name else "VENDING PLAN"


def cover_lines(stats: DeckStats) -> tuple[str, str, str]:
    """(title, subtitle, footer-ish) for the cover slide."""
    title = "KROMI Logistik"
    bits = [b for b in (stats.customer.strip(), stats.site.strip()) if b]
    subtitle = " — ".join(bits) if bits else "Vending plan"
    return title, subtitle, stats.date_str


# Standard external cabinet widths (mm) for the scale line-up; height ~2000 mm.
LINEUP_WIDTH_MM = {"helix": 1010, "carousel": 1100, "locker": 500}


@dataclass(frozen=True)
class LineupUnit:
    """One group of identical cabinets in the proposed line-up."""

    label: str
    count: int
    width_mm: int
    kind: str  # "carousel" | "helix_master" | "helix_slave" | "locker"


def lineup_units(stats: DeckStats) -> list[LineupUnit]:
    """The proposed machine line-up as groups, in install order.

    Mirrors how KROMI lays a line out: Carousel(s), then one Helix Master (the
    cabinet with the panoramic monitor), then the Helix Slaves, then Lockers.
    Each present type is one group with its count, so the drawing scales to any
    plan size instead of drawing dozens of identical boxes.
    """
    units: list[LineupUnit] = []
    if stats.carousel:
        units.append(
            LineupUnit("Carousel", stats.carousel, LINEUP_WIDTH_MM["carousel"], "carousel")
        )
    if stats.helix:
        units.append(LineupUnit("Helix Master", 1, LINEUP_WIDTH_MM["helix"], "helix_master"))
        if stats.helix > 1:
            units.append(
                LineupUnit("Helix Slave", stats.helix - 1, LINEUP_WIDTH_MM["helix"], "helix_slave")
            )
    if stats.lockers:
        units.append(LineupUnit("Locker", stats.lockers, LINEUP_WIDTH_MM["locker"], "locker"))
    return units


def lineup_total_width_mm(stats: DeckStats) -> int:
    """Total floor width (mm) of the proposed line-up: every cabinet side by side."""
    return (
        stats.carousel * LINEUP_WIDTH_MM["carousel"]
        + stats.helix * LINEUP_WIDTH_MM["helix"]
        + stats.lockers * LINEUP_WIDTH_MM["locker"]
    )
