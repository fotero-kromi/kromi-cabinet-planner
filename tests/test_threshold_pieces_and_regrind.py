"""Tests for the pieces-based KTC/Kanban threshold, per-tool-class optional
thresholds, regrind parsing, and the regrind Helix spiral floor.

Written before the implementation (TDD). Covers:
- routing_rules.threshold_for_row: standard vs per-class, optional on/off, inserts
- routing_rules.is_regrind: YES/NO parsing
- cabinet_math.regrind_spiral_floor: Helix 1 -> 2, >=2 untouched, 0 untouched
- cabinet_math.route_and_size_row: gate on monthly_pcs, regrind floor on Helix
"""
import pandas as pd
import pytest

from engine import routing_rules as rr
from engine import cabinet_math as cm


# ---------------------------------------------------------------------------
# threshold_for_row
# ---------------------------------------------------------------------------
class TestThresholdForRow:
    def test_optional_off_uses_standard_for_everything(self):
        # When optional thresholds are off, every category (including inserts)
        # uses the single standard threshold.
        for cat in ("drills", "mills", "inserts", "taps", ""):
            t = rr.threshold_for_row(
                product_category=cat, tool_class="",
                standard_threshold=1.0, per_class_thresholds={"inserts": 3.0, "drills": 5.0},
                optional_active=False,
            )
            assert t == 1.0

    def test_optional_on_uses_per_class_when_set(self):
        t = rr.threshold_for_row(
            product_category="drills", tool_class="",
            standard_threshold=1.0, per_class_thresholds={"drills": 5.0, "inserts": 3.0},
            optional_active=True,
        )
        assert t == 5.0

    def test_optional_on_falls_back_to_standard_when_class_absent(self):
        t = rr.threshold_for_row(
            product_category="mills", tool_class="",
            standard_threshold=1.0, per_class_thresholds={"drills": 5.0},
            optional_active=True,
        )
        assert t == 1.0

    def test_optional_on_inserts_use_insert_class_threshold(self):
        t = rr.threshold_for_row(
            product_category="inserts", tool_class="",
            standard_threshold=1.0, per_class_thresholds={"inserts": 3.0},
            optional_active=True,
        )
        assert t == 3.0

    def test_inserts_detected_via_toolclass_fallback(self):
        # ProductCategory blank but ToolClass says turning_insert -> insert class
        t = rr.threshold_for_row(
            product_category="", tool_class="turning_insert",
            standard_threshold=1.0, per_class_thresholds={"inserts": 3.0},
            optional_active=True,
        )
        assert t == 3.0

    def test_category_matching_is_case_insensitive(self):
        t = rr.threshold_for_row(
            product_category="DRILLS", tool_class="",
            standard_threshold=1.0, per_class_thresholds={"drills": 5.0},
            optional_active=True,
        )
        assert t == 5.0


# ---------------------------------------------------------------------------
# is_regrind
# ---------------------------------------------------------------------------
class TestIsRegrind:
    @pytest.mark.parametrize("val", ["YES", "yes", "Yes", " yes ", "Y", "true", "1"])
    def test_yes_values(self, val):
        assert rr.is_regrind(val) is True

    @pytest.mark.parametrize("val", ["NO", "no", "", "  ", "0", "false", "nein", None, "maybe"])
    def test_no_values(self, val):
        assert rr.is_regrind(val) is False


# ---------------------------------------------------------------------------
# regrind_spiral_floor
# ---------------------------------------------------------------------------
class TestRegrindSpiralFloor:
    def test_regrind_one_spiral_becomes_two(self):
        assert cm.regrind_spiral_floor(1, True) == 2

    def test_regrind_two_or_more_unchanged(self):
        assert cm.regrind_spiral_floor(2, True) == 2
        assert cm.regrind_spiral_floor(3, True) == 3
        assert cm.regrind_spiral_floor(5, True) == 5

    def test_no_regrind_unchanged(self):
        assert cm.regrind_spiral_floor(1, False) == 1
        assert cm.regrind_spiral_floor(3, False) == 3

    def test_zero_spirals_not_bumped(self):
        # A 0-spiral (non-Helix / phantom) item must not be bumped to 2.
        assert cm.regrind_spiral_floor(0, True) == 0


# ---------------------------------------------------------------------------
# route_and_size_row: gate on monthly_pcs, regrind floor
# ---------------------------------------------------------------------------
class TestRouteAndSizeRowPiecesAndRegrind:
    def _common(self):
        return dict(
            size_cat="S", product_category="drills", threshold=1.0,
            helix_threshold=5.0, min_carousel_compartments=3,
            carousel_reserve_factor=0.85, helix_overfill_factor=1.1,
        )

    def test_gate_uses_monthly_pcs_when_provided(self):
        # monthly_packs is low (0.4, below the 1.0 threshold) but monthly_pcs is
        # high (8, above) -> with pieces gating the row is KTC, not Kanban.
        res = cm.route_and_size_row(
            monthly_packs=0.4, monthly_pcs=8.0, target_packs=0.2, **self._common()
        )
        assert res["SystemCategory"] == "KTC"

    def test_gate_pieces_below_threshold_is_kanban(self):
        res = cm.route_and_size_row(
            monthly_packs=5.0, monthly_pcs=0.5, target_packs=2.0, **self._common()
        )
        assert res["SystemCategory"] == "Kanban"

    def test_backcompat_gate_falls_back_to_packs_when_pcs_none(self):
        # Existing callers that pass only monthly_packs keep the old behaviour.
        res = cm.route_and_size_row(
            monthly_packs=0.5, target_packs=0.3, **self._common()
        )
        assert res["SystemCategory"] == "Kanban"
        res2 = cm.route_and_size_row(
            monthly_packs=9.0, target_packs=5.0, **self._common()
        )
        assert res2["SystemCategory"] == "KTC"

    def test_regrind_helix_item_gets_at_least_two_spirals(self):
        # A Helix item (monthly_packs high) sized to 1 spiral, regrind -> 2.
        common = self._common()
        common["helix_threshold"] = 5.0
        res = cm.route_and_size_row(
            monthly_packs=6.0, monthly_pcs=60.0, target_packs=6.0, regrind=True, **common
        )
        assert res["CabinetType"] == "Helix"
        assert res["Spirals_needed"] >= 2

    def test_no_regrind_helix_item_keeps_one_spiral(self):
        common = self._common()
        res = cm.route_and_size_row(
            monthly_packs=6.0, monthly_pcs=60.0, target_packs=6.0, regrind=False, **common
        )
        assert res["CabinetType"] == "Helix"
        assert res["Spirals_needed"] == 1

    def test_regrind_does_not_affect_carousel(self):
        # Low-velocity KTC item -> Carousel; regrind must not change its sizing.
        common = self._common()
        common["helix_threshold"] = 100.0  # force Carousel
        res_no = cm.route_and_size_row(
            monthly_packs=2.0, monthly_pcs=20.0, target_packs=2.0, regrind=False, **common
        )
        res_yes = cm.route_and_size_row(
            monthly_packs=2.0, monthly_pcs=20.0, target_packs=2.0, regrind=True, **common
        )
        assert res_no["CabinetType"] == "Carousel"
        assert res_yes["CabinetType"] == "Carousel"
        assert res_yes["Carousel_stockpiles"] == res_no["Carousel_stockpiles"]
        assert res_yes["Spirals_needed"] == 0 == res_no["Spirals_needed"]
