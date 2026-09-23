"""Tests for engine.deck — pure presentation content model."""

from __future__ import annotations

from engine.deck import (
    DeckStats,
    LineupUnit,
    cover_lines,
    lineup_total_width_mm,
    lineup_units,
    summary_cards,
    summary_pyramid,
    summary_subtitle,
)


def _stats(**kw):
    return DeckStats(**kw)


class TestSummaryCards:
    def test_always_present_cards(self):
        cards = summary_cards(
            _stats(supply_points=2, total_cabinets=18, ktc_items=555, total_items=1036)
        )
        labels = [c.label for c in cards]
        assert "Supply points" in labels
        assert "Cabinets total" in labels
        assert "KTC items" in labels
        assert "Items managed" in labels

    def test_cabinet_type_cards_only_when_nonzero(self):
        cards = summary_cards(_stats(helix=16, carousel=0, lockers=0))
        labels = [c.label for c in cards]
        assert "Helix" in labels
        assert "Carousel" not in labels
        assert "Lockers" not in labels

    def test_all_cabinet_types_when_present(self):
        cards = summary_cards(_stats(helix=16, carousel=2, lockers=1))
        labels = [c.label for c in cards]
        assert {"Helix", "Carousel", "Lockers"} <= set(labels)

    def test_kanban_card_shown_when_nonzero(self):
        cards = summary_cards(_stats(ktc_items=456, kanban_items=993, total_items=1449))
        by_label = {c.label: c.value for c in cards}
        assert by_label.get("Kanban items") == "993"
        # KTC + Kanban should reconcile to items managed.
        assert by_label["KTC items"] == "456" and by_label["Items managed"] == "1449"

    def test_kanban_card_hidden_when_zero(self):
        cards = summary_cards(_stats(ktc_items=10, kanban_items=0, total_items=10))
        assert "Kanban items" not in [c.label for c in cards]

    def test_values_are_strings_of_numbers(self):
        cards = summary_cards(_stats(supply_points=3, total_cabinets=20))
        by_label = {c.label: c.value for c in cards}
        assert by_label["Supply points"] == "3"
        assert by_label["Cabinets total"] == "20"

    def test_order_supply_then_cabinets_first(self):
        cards = summary_cards(_stats(supply_points=1, total_cabinets=5, helix=5))
        assert cards[0].label == "Supply points"
        assert cards[1].label == "Cabinets total"


class TestSubtitle:
    def test_customer_uppercased(self):
        assert summary_subtitle(_stats(customer="Acme")) == "ACME VENDING"

    def test_blank_customer_fallback(self):
        assert summary_subtitle(_stats(customer="")) == "VENDING PLAN"

    def test_falls_back_to_site_when_no_customer(self):
        assert summary_subtitle(_stats(customer="", site="Riverside")) == "RIVERSIDE VENDING"

    def test_customer_wins_over_site(self):
        assert summary_subtitle(_stats(customer="Acme", site="Plant 1")) == "ACME VENDING"


class TestLineup:
    def test_order_carousel_then_helix_then_locker(self):
        units = lineup_units(_stats(helix=12, carousel=3, lockers=2))
        kinds = [u.kind for u in units]
        assert kinds == ["carousel", "helix_master", "helix_slave", "locker"]

    def test_helix_master_slave_split(self):
        units = {u.kind: u for u in lineup_units(_stats(helix=12))}
        assert units["helix_master"].count == 1
        assert units["helix_slave"].count == 11

    def test_single_helix_has_no_slave(self):
        kinds = [u.kind for u in lineup_units(_stats(helix=1))]
        assert kinds == ["helix_master"]

    def test_only_present_types(self):
        units = lineup_units(_stats(helix=0, carousel=3, lockers=0))
        assert [u.kind for u in units] == ["carousel"]

    def test_total_width_sums_all_cabinets(self):
        # 12 helix * 1010 + 3 carousel * 1100 + 0 lockers
        assert lineup_total_width_mm(_stats(helix=12, carousel=3)) == 12 * 1010 + 3 * 1100

    def test_unit_carries_count_and_width(self):
        units = lineup_units(_stats(carousel=3))
        assert isinstance(units[0], LineupUnit)
        assert units[0].count == 3 and units[0].width_mm == 1100


class TestCover:
    def test_title_is_kromi(self):
        title, _, _ = cover_lines(_stats(customer="Acme", site="Plant 1"))
        assert title == "KROMI Logistik"

    def test_subtitle_joins_customer_and_site(self):
        _, subtitle, _ = cover_lines(_stats(customer="Acme", site="Plant 1"))
        assert "Acme" in subtitle and "Plant 1" in subtitle

    def test_subtitle_fallback_when_empty(self):
        _, subtitle, _ = cover_lines(_stats())
        assert subtitle == "Vending plan"

    def test_date_passthrough(self):
        _, _, footer = cover_lines(_stats(date_str="21 May 2026"))
        assert footer == "21 May 2026"


class TestSummaryPyramid:
    def test_three_tiers_when_cabinets_present(self):
        tiers = summary_pyramid(_stats(supply_points=1, total_cabinets=5,
                                       helix=1, carousel=3, lockers=1,
                                       ktc_items=669, kanban_items=474, total_items=1143))
        assert len(tiers) == 3
        assert [c.label for c in tiers[0]] == ["Supply points", "Cabinets total"]
        assert [c.label for c in tiers[1]] == ["Helix", "Carousel", "Lockers"]
        assert [c.label for c in tiers[2]] == ["Items managed", "KTC items", "Kanban items"]

    def test_top_tier_values(self):
        tiers = summary_pyramid(_stats(supply_points=2, total_cabinets=7))
        assert tiers[0][0].value == "2" and tiers[0][1].value == "7"

    def test_cabinet_tier_only_present_types(self):
        tiers = summary_pyramid(_stats(helix=4, carousel=0, lockers=2))
        assert [c.label for c in tiers[1]] == ["Helix", "Lockers"]

    def test_cabinet_tier_dropped_when_no_cabinets(self):
        # No cabinets of any type -> two-tier stack (scope, items)
        tiers = summary_pyramid(_stats(helix=0, carousel=0, lockers=0))
        assert len(tiers) == 2
        assert [c.label for c in tiers[0]] == ["Supply points", "Cabinets total"]
        assert tiers[1][0].label == "Items managed"

    def test_kanban_card_hidden_when_zero(self):
        tiers = summary_pyramid(_stats(ktc_items=10, kanban_items=0, total_items=10))
        assert [c.label for c in tiers[-1]] == ["Items managed", "KTC items"]

    def test_bottom_tier_order_items_ktc_kanban(self):
        tiers = summary_pyramid(_stats(ktc_items=300, kanban_items=200, total_items=500))
        bottom = tiers[-1]
        assert [c.label for c in bottom] == ["Items managed", "KTC items", "Kanban items"]
        assert [c.value for c in bottom] == ["500", "300", "200"]
