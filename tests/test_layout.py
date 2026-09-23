"""Tests for engine.layout — pure cabinet planogram allocation (Phase A)."""

from __future__ import annotations

from engine.layout import (
    CABINET_ORDER,
    GRID_DIMS,
    LayoutItem,
    allocate_for_type,
    allocate_plan,
    grid_capacity,
)


def _item(idn, ctype, comp=1, cat="", conf=""):
    return LayoutItem(
        identifier=idn, cabinet_type=ctype, compartments=comp, category=cat, confidence=conf
    )


class TestGrid:
    def test_capacities(self):
        assert grid_capacity("Helix") == 70
        assert grid_capacity("Carousel") == 720
        assert grid_capacity("Locker A") == 48
        assert grid_capacity("Locker B") == 72
        assert grid_capacity("Locker C") == 96

    def test_helix_shape(self):
        assert GRID_DIMS["Helix"] == (7, 10)

    def test_carousel_shape(self):
        assert GRID_DIMS["Carousel"] == (24, 30)


class TestSingleCabinet:
    def test_empty_input(self):
        assert allocate_for_type([], "Helix") == []

    def test_single_item_one_cabinet(self):
        cabs = allocate_for_type([_item("A1", "Helix")], "Helix")
        assert len(cabs) == 1
        cab = cabs[0]
        assert cab.cabinet_type == "Helix"
        assert cab.cabinet_index == 1
        assert cab.capacity == 70
        assert cab.used == 1
        first = cab.compartments[0]
        assert first.item_id == "A1"
        assert first.index == 1
        assert (first.row, first.col) == (0, 0)
        assert first.label == "01"
        assert first.is_item_start is True

    def test_label_width_per_type(self):
        helix = allocate_for_type([_item("x", "Helix")], "Helix")[0]
        assert helix.compartments[0].label == "01"
        assert helix.compartments[-1].label == "70"
        carousel = allocate_for_type([_item("x", "Carousel")], "Carousel")[0]
        assert carousel.compartments[0].label == "001"
        assert carousel.compartments[-1].label == "720"

    def test_row_col_mapping(self):
        cab = allocate_for_type([_item("x", "Helix")], "Helix")[0]
        # index 11 -> row 1, col 0 (10 cols per row)
        c11 = cab.compartments[10]
        assert c11.index == 11
        assert (c11.row, c11.col) == (1, 0)


class TestContiguity:
    def test_items_grouped_by_category_then_id(self):
        items = [
            _item("d2", "Helix", cat="drills"),
            _item("m1", "Helix", cat="mills"),
            _item("d1", "Helix", cat="drills"),
        ]
        cab = allocate_for_type(items, "Helix")[0]
        placed = [c.item_id for c in cab.compartments if c.item_id]
        # drills (d1, d2) contiguous and before mills (m1); ids sorted within category
        assert placed == ["d1", "d2", "m1"]


class TestMultiCell:
    def test_multi_compartment_consecutive_and_grouped(self):
        cab = allocate_for_type([_item("BIG", "Helix", comp=3)], "Helix")[0]
        occupied = [c for c in cab.compartments if c.item_id == "BIG"]
        assert len(occupied) == 3
        assert [c.index for c in occupied] == [1, 2, 3]
        # all share one span_group
        assert len({c.span_group for c in occupied}) == 1
        # only the first is the item start
        assert [c.is_item_start for c in occupied] == [True, False, False]

    def test_item_not_split_across_cabinets(self):
        # Helix cap 70. Fill 69 single-cell items, then a 3-cell item: it must
        # move wholly to cabinet 2, leaving the 70th cell of cabinet 1 empty.
        items = [_item(f"s{i:02d}", "Helix", cat="a") for i in range(69)]
        items.append(_item("zz_big", "Helix", comp=3, cat="z"))
        cabs = allocate_for_type(items, "Helix")
        assert len(cabs) == 2
        assert cabs[0].used == 69  # 70th left empty
        assert cabs[0].compartments[69].item_id is None
        big_cells = [c for c in cabs[1].compartments if c.item_id == "zz_big"]
        assert [c.index for c in big_cells] == [1, 2, 3]

    def test_exact_fill_starts_new_cabinet(self):
        items = [_item(f"s{i:03d}", "Helix", cat="a") for i in range(70)]
        items.append(_item("s071", "Helix", cat="a"))
        cabs = allocate_for_type(items, "Helix")
        assert len(cabs) == 2
        assert cabs[0].used == 70
        assert cabs[1].used == 1


class TestCarryThrough:
    def test_confidence_and_category_preserved(self):
        cab = allocate_for_type([_item("A", "Helix", cat="drills", conf="AI")], "Helix")[0]
        c = cab.compartments[0]
        assert c.category == "drills"
        assert c.confidence == "AI"


class TestDeterminism:
    def test_same_input_same_output(self):
        items = [_item(f"i{i}", "Helix", comp=(i % 3) + 1, cat=f"c{i % 4}") for i in range(50)]
        a = allocate_for_type(items, "Helix")
        b = allocate_for_type(list(reversed(items)), "Helix")
        # Order of input must not matter (sorted internally).
        sig_a = [(c.index, c.item_id) for cab in a for c in cab.compartments]
        sig_b = [(c.index, c.item_id) for cab in b for c in cab.compartments]
        assert sig_a == sig_b


class TestFullPlan:
    def test_only_present_types_allocated(self):
        items = [_item("h", "Helix"), _item("l", "Locker C")]
        plan = allocate_plan(items)
        types = [c.cabinet_type for c in plan.cabinets]
        assert types == ["Helix", "Locker C"]  # CABINET_ORDER, Carousel skipped

    def test_cabinet_order_respected(self):
        items = [_item("l", "Locker A"), _item("c", "Carousel"), _item("h", "Helix")]
        plan = allocate_plan(items)
        types = [c.cabinet_type for c in plan.cabinets]
        assert types == [t for t in CABINET_ORDER if t in {"Helix", "Carousel", "Locker A"}]
        assert types == ["Helix", "Carousel", "Locker A"]

    def test_for_type_filter(self):
        items = [_item(f"h{i}", "Helix") for i in range(80)]  # spills into 2 helix cabs
        plan = allocate_plan(items)
        assert len(plan.for_type("Helix")) == 2
        assert plan.for_type("Carousel") == []


class TestConfidenceColour:
    def test_scale_distinct_and_ordered(self):
        from engine.layout import confidence_fill_hex

        hi = confidence_fill_hex("high")
        med = confidence_fill_hex("medium")
        low = confidence_fill_hex("low")
        unk = confidence_fill_hex("unknown")
        assert len({hi, med, low, unk}) == 4  # four distinct bands
        assert hi == "63BE7B"  # green for most confident

    def test_case_insensitive(self):
        from engine.layout import confidence_fill_hex

        assert confidence_fill_hex("HIGH") == confidence_fill_hex("high")

    def test_blank_and_unknown_are_least_confident(self):
        from engine.layout import confidence_fill_hex

        assert confidence_fill_hex("") == confidence_fill_hex("unknown")

    def test_unrecognized_falls_back(self):
        from engine.layout import confidence_fill_hex

        assert confidence_fill_hex("banana") == confidence_fill_hex("unknown")

    def test_hex_is_six_digits(self):
        from engine.layout import confidence_fill_hex

        for tag in ["high", "medium", "low", "unknown", ""]:
            h = confidence_fill_hex(tag)
            assert len(h) == 6 and all(c in "0123456789ABCDEF" for c in h)
