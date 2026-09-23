"""kromi_app.engine.layout — cabinet planogram allocation (pure, Phase A).

Given the already-sized planning items (each knows its cabinet type and how many
compartments it needs), this module assigns every item to a concrete physical
position: cabinet number, row, column, and a zero-padded compartment label. The
result is a `LayoutPlan` that the Excel export (Phase B) renders as a coloured,
collapsible grid — one sheet/grid per cabinet.

Design rules (agreed with the domain owner):
* **Family/category contiguity** — items are ordered by category then identifier
  so same-family tools sit next to each other in the grid.
* **Multi-compartment items stay together** — an item needing N compartments
  occupies N consecutive cells sharing a `span_group`, and is never split across
  a cabinet boundary (if it doesn't fit in the current cabinet's remaining cells,
  the whole item moves to the next cabinet; the leftover cells stay empty).
* **Deterministic** — identical input always produces identical placement, so the
  planogram is auditable and unit-testable.

This module is pure: no Streamlit, no I/O, no global state. Colour choices and
rendering are intentionally left to Phase B; here we only carry each item's
`confidence` tag through onto its compartments.
"""

from __future__ import annotations

from dataclasses import dataclass

# Physical grid of each cabinet type as (rows, cols); capacity = rows * cols.
# Helix and Carousel are fixed by the hardware; locker grids are sensible
# factorisations of their compartment counts and can be adjusted if the physical
# door layout differs.
GRID_DIMS: dict[str, tuple[int, int]] = {
    "Helix": (7, 10),  # 70 spirals (7 drawers x 10 coils)
    "Carousel": (24, 30),  # 720 slots
    "Locker A": (6, 8),  # 48 compartments
    "Locker B": (8, 9),  # 72 compartments
    "Locker C": (8, 12),  # 96 compartments
}

# Order cabinets appear in a full plan.
CABINET_ORDER: list[str] = ["Helix", "Carousel", "Locker A", "Locker B", "Locker C"]


def grid_dims(cabinet_type: str) -> tuple[int, int]:
    """Return (rows, cols) for a cabinet type, or raise KeyError if unknown."""
    return GRID_DIMS[cabinet_type]


# Confidence -> Excel fill for the planogram (Phase B colour scale). Green is most
# confident, degrading through yellow to orange for least confident. 6-digit RGB hex.
_CONFIDENCE_FILL: dict[str, str] = {
    "high": "63BE7B",  # green
    "medium": "FFE066",  # yellow
    "low": "FFB84D",  # yellow-orange
    "unknown": "F4793B",  # orange
    "": "F4793B",  # blank treated as least confident
}
_CONFIDENCE_FILL_DEFAULT = "F4793B"


RESTOCK_FILL_HEX = "4A90D2"  # restock buffer cells (v34.26)


def fill_hex_for_cell(kind: str | None, confidence: str) -> str:
    """Fill colour for one planogram cell: the restock kind wins over the
    confidence channel, everything else keeps the confidence palette."""
    if (kind or "") == "restock":
        return RESTOCK_FILL_HEX
    return confidence_fill_hex(confidence)


def confidence_fill_hex(confidence: str) -> str:
    """Map a confidence tag to a 6-digit RGB hex fill for the planogram.

    Green = most confident, degrading through yellow to orange. Unknown or blank
    is treated as least confident. Case-insensitive; unrecognized values fall
    back to the least-confident colour.
    """
    return _CONFIDENCE_FILL.get((confidence or "").strip().lower(), _CONFIDENCE_FILL_DEFAULT)


def grid_capacity(cabinet_type: str) -> int:
    rows, cols = GRID_DIMS[cabinet_type]
    return rows * cols


@dataclass(frozen=True)
class LayoutItem:
    """One item to place. `compartments` is spirals (Helix) / stockpiles
    (Carousel) / 1 (Locker). `confidence` is carried through unchanged for
    Phase B colouring (e.g. the source tag: Provided/Heuristic/AI/Default)."""

    identifier: str
    cabinet_type: str
    compartments: int = 1
    category: str = ""
    confidence: str = ""
    # Cell kind (v34.26): "" for a regular item, "restock" for a reserved
    # buffer compartment. Buffers sort after every regular item of their
    # cabinet type and colour blue on the planogram.
    kind: str = ""


@dataclass
class Compartment:
    """One physical cell in a cabinet grid."""

    index: int  # 1-based, row-major within the cabinet
    row: int  # 0-based
    col: int  # 0-based
    label: str  # zero-padded position label, e.g. "01" or "007"
    item_id: str | None = None
    category: str | None = None
    confidence: str | None = None
    kind: str | None = None  # "restock" for a buffer cell (v34.26)
    is_item_start: bool = False  # first cell of a (possibly multi-cell) item
    span_group: int | None = None  # shared id across one item's cells


@dataclass
class CabinetLayout:
    cabinet_type: str
    cabinet_index: int  # 1-based within its type
    rows: int
    cols: int
    compartments: list[Compartment]

    @property
    def capacity(self) -> int:
        return self.rows * self.cols

    @property
    def used(self) -> int:
        return sum(1 for c in self.compartments if c.item_id is not None)

    @property
    def occupation(self) -> float:
        cap = self.capacity
        return (self.used / cap) if cap else 0.0


@dataclass
class LayoutPlan:
    cabinets: list[CabinetLayout]

    def for_type(self, cabinet_type: str) -> list[CabinetLayout]:
        return [c for c in self.cabinets if c.cabinet_type == cabinet_type]


def _blank_cabinet(cabinet_type: str, cabinet_index: int) -> CabinetLayout:
    rows, cols = GRID_DIMS[cabinet_type]
    cap = rows * cols
    width = len(str(cap))
    comps = [
        Compartment(
            index=i + 1,
            row=i // cols,
            col=i % cols,
            label=str(i + 1).zfill(width),
        )
        for i in range(cap)
    ]
    return CabinetLayout(cabinet_type, cabinet_index, rows, cols, comps)


def allocate_for_type(items: list[LayoutItem], cabinet_type: str) -> list[CabinetLayout]:
    """Place all items of a single cabinet type into one or more cabinet grids."""
    if cabinet_type not in GRID_DIMS:
        raise KeyError(f"Unknown cabinet type: {cabinet_type!r}")

    cap = grid_capacity(cabinet_type)
    # Family/category contiguity + deterministic ordering.
    queue = sorted(
        (it for it in items if it.cabinet_type == cabinet_type),
        key=lambda it: (it.kind == "restock", it.category, it.identifier),
    )

    cabinets: list[CabinetLayout] = []
    current: CabinetLayout | None = None
    cursor = 0  # next free 0-based slot in `current`
    span_counter = 0

    def open_cabinet() -> CabinetLayout:
        cab = _blank_cabinet(cabinet_type, len(cabinets) + 1)
        cabinets.append(cab)
        return cab

    for it in queue:
        need = max(1, int(it.compartments))
        if need > cap:
            # An item larger than a whole cabinet: clamp to a full cabinet so it
            # is still represented (shouldn't happen with real sizing).
            need = cap

        if current is None or cursor + need > cap:
            current = open_cabinet()
            cursor = 0

        span_counter += 1
        for k in range(need):
            comp = current.compartments[cursor + k]
            comp.item_id = it.identifier
            comp.category = it.category
            comp.confidence = it.confidence
            comp.kind = it.kind or None
            comp.span_group = span_counter
            comp.is_item_start = k == 0
        cursor += need

    return cabinets


def allocate_plan(items: list[LayoutItem]) -> LayoutPlan:
    """Allocate every cabinet type present in `items`, in CABINET_ORDER."""
    cabinets: list[CabinetLayout] = []
    present = {it.cabinet_type for it in items}
    ordered_types = [t for t in CABINET_ORDER if t in present]
    # Any unexpected types (defensive) appended after the known order.
    ordered_types += sorted(t for t in present if t not in CABINET_ORDER and t in GRID_DIMS)
    for ctype in ordered_types:
        cabinets.extend(allocate_for_type(items, ctype))
    return LayoutPlan(cabinets)


def restock_layout_items(df) -> list[LayoutItem]:
    """One synthetic LayoutItem per reserved buffer compartment (v34.26).

    Reads the restock columns the plan segment wrote: every row with a slot
    becomes a one-compartment item of the buffer's target cabinet, labelled
    ``CODE (R)`` and kinded ``restock`` so the allocator places it after the
    regular items and the planogram colours it blue. Frames without the
    columns yield an empty list, so the builder is safe on any frame.
    """
    items: list[LayoutItem] = []
    if df is None or getattr(df, "empty", True):
        return items
    if "Restock_slots" not in df.columns or "Restock_target" not in df.columns:
        return items
    for _, row in df.iterrows():
        try:
            slots = int(row.get("Restock_slots", 0) or 0)
        except (TypeError, ValueError):
            slots = 0
        target = str(row.get("Restock_target", "") or "").strip()
        if slots <= 0 or target not in GRID_DIMS:
            continue
        code = str(row.get("Code", "") or "").strip()
        items.append(LayoutItem(
            identifier=f"{code} (R)",
            cabinet_type=target,
            compartments=1,
            category=str(row.get("ProductCategory", "") or "").strip(),
            confidence="",
            kind="restock",
        ))
    return items
