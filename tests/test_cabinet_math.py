"""Tests for engine.cabinet_math — 13 functions including the rebalancer.

This is the second-largest test file (after classification). The rebalancer
is the most behavior-sensitive function in the codebase, so its tests are
extensive."""

import math

import pandas as pd
import pytest

from engine import cabinet_math as cm
from engine.constants import (
    CAROUSEL_SLOTS_PER_CAB,
    HELIX_SPIRALS_PER_CAB,
    LOCKER_A_CAP,
    LOCKER_B_CAP,
    LOCKER_C_CAP,
)

# ---- apply_capacity_buffer ----

class TestApplyCapacityBuffer:
    def test_zero_buffer(self):
        assert cm.apply_capacity_buffer(100, 0) == 100

    def test_15_pct(self):
        assert cm.apply_capacity_buffer(100, 15) == 115

    def test_30_pct(self):
        assert cm.apply_capacity_buffer(100, 30) == 130

    def test_100_pct(self):
        assert cm.apply_capacity_buffer(100, 100) == 200

    def test_negative_buffer_no_op(self):
        assert cm.apply_capacity_buffer(100, -5) == 100

    def test_zero_value(self):
        assert cm.apply_capacity_buffer(0, 30) == 0

    def test_negative_value(self):
        assert cm.apply_capacity_buffer(-1, 30) == -1

    def test_rounds_up(self):
        """33 * 1.15 = 37.95 → 38 (not 37)."""
        assert cm.apply_capacity_buffer(33, 15) == 38

    def test_rounds_up_2(self):
        """67 * 1.30 = 87.1 → 88."""
        assert cm.apply_capacity_buffer(67, 30) == 88

    def test_float_buffer(self):
        assert cm.apply_capacity_buffer(100, 12.5) == 113


# ---- decide_cabinet_type ----

class TestDecideCabinetType:
    def test_xxl_to_locker_a(self):
        assert cm.decide_cabinet_type("XXL", 100, 6) == "Locker A"

    def test_xxl_lowercase(self):
        assert cm.decide_cabinet_type("xxl", 100, 6) == "Locker A"

    def test_xxls_to_locker_b(self):
        assert cm.decide_cabinet_type("XXLS", 100, 6) == "Locker B"

    def test_xls_to_locker_c(self):
        assert cm.decide_cabinet_type("XLS", 100, 6) == "Locker C"

    def test_high_velocity_helix(self):
        assert cm.decide_cabinet_type("S", 10, 6) == "Helix"

    def test_low_velocity_carousel(self):
        assert cm.decide_cabinet_type("S", 3, 6) == "Carousel"

    def test_threshold_at_value_carousel(self):
        """Exact threshold goes to Carousel (not above)."""
        assert cm.decide_cabinet_type("S", 6, 6) == "Carousel"

    def test_threshold_just_over_helix(self):
        assert cm.decide_cabinet_type("S", 6.01, 6) == "Helix"

    def test_empty_size_with_low_velocity(self):
        assert cm.decide_cabinet_type("", 1, 6) == "Carousel"


# ---- decide_spiral_capacity ----

class TestDecideSpiralCapacity:
    def test_s_28(self):
        assert cm.decide_spiral_capacity("S", "drills") == 28

    def test_m_22(self):
        assert cm.decide_spiral_capacity("M", "drills") == 22

    def test_l_18(self):
        assert cm.decide_spiral_capacity("L", "drills") == 18

    def test_xl_12(self):
        assert cm.decide_spiral_capacity("XL", "drills") == 12

    def test_size_overrides_pc(self):
        """If size is given, it wins over pc-based fallback."""
        assert cm.decide_spiral_capacity("S", "mills") == 28

    def test_fallback_inserts_28(self):
        assert cm.decide_spiral_capacity("", "inserts") == 28

    def test_fallback_drills_22(self):
        assert cm.decide_spiral_capacity("", "drills") == 22

    def test_fallback_other_18(self):
        assert cm.decide_spiral_capacity("", "other") == 18

    def test_fallback_mills_18(self):
        assert cm.decide_spiral_capacity("", "mills") == 18


# ---- compute_helix_spirals_needed ----

class TestComputeHelixSpiralsNeeded:
    def test_zero_monthly(self):
        assert cm.compute_helix_spirals_needed(0, 22) == 0

    def test_nan_monthly(self):
        assert cm.compute_helix_spirals_needed(float("nan"), 22) == 0

    def test_zero_capacity(self):
        assert cm.compute_helix_spirals_needed(10, 0) == 0

    def test_negative_capacity(self):
        assert cm.compute_helix_spirals_needed(10, -5) == 0

    def test_within_capacity(self):
        assert cm.compute_helix_spirals_needed(20, 22) == 1

    def test_within_overfill_factor_110(self):
        """With default overfill 1.10, 24 packs at cap 22 → 1 spiral (24 ≤ 22*1.10 = 24.2)."""
        assert cm.compute_helix_spirals_needed(24, 22) == 1

    def test_just_over_overfill(self):
        """25 packs at cap 22 → 2 spirals (25 > 24.2)."""
        assert cm.compute_helix_spirals_needed(25, 22) == 2

    def test_44_packs_at_22cap(self):
        assert cm.compute_helix_spirals_needed(44, 22) == 2

    def test_45_packs_at_22cap(self):
        assert cm.compute_helix_spirals_needed(45, 22) == 3

    def test_parametrized_factor_2(self):
        """With factor 2.0, 40 packs at cap 22 → 1 spiral."""
        assert cm.compute_helix_spirals_needed(40, 22, overfill_factor=2.0) == 1

    def test_parametrized_factor_1(self):
        """With factor 1.0, 23 packs at cap 22 → 2 spirals."""
        assert cm.compute_helix_spirals_needed(23, 22, overfill_factor=1.0) == 2


# ---- compute_helix_needs ----

class TestComputeHelixNeeds:
    def test_empty_df(self):
        assert cm.compute_helix_needs(pd.DataFrame()) == (0, 0)

    def test_with_spirals_needed_column(self):
        df = pd.DataFrame({"Spirals_needed": [1, 2, 3, 4]})
        total, cabs = cm.compute_helix_needs(df)
        assert total == 10
        assert cabs == 1

    def test_70_spirals_boundary(self):
        """70 spirals = 1 cabinet exactly."""
        df = pd.DataFrame({"Spirals_needed": [70]})
        assert cm.compute_helix_needs(df) == (70, 1)

    def test_71_spirals_2_cabs(self):
        df = pd.DataFrame({"Spirals_needed": [71]})
        assert cm.compute_helix_needs(df) == (71, 2)

    def test_140_spirals_2_cabs(self):
        df = pd.DataFrame({"Spirals_needed": [140]})
        assert cm.compute_helix_needs(df) == (140, 2)

    def test_without_spirals_needed_computes(self):
        df = pd.DataFrame({
            "Monthly_packs": [10, 50, 30],
            "Spiral_capacity": [22, 22, 22],
        })
        total, cabs = cm.compute_helix_needs(df)
        # 10 → 1, 50 → 3, 30 → 2 = 6 spirals total
        assert total == 6


# ---- compute_carousel_needs ----

class TestComputeCarouselNeeds:
    def test_empty(self):
        assert cm.compute_carousel_needs(pd.DataFrame()) == (0, 0)

    def test_basic(self):
        df = pd.DataFrame({"Carousel_stockpiles": [3, 5, 4]})
        assert cm.compute_carousel_needs(df) == (12, 1)

    def test_720_boundary(self):
        """720 slots = 1 cabinet exactly."""
        df = pd.DataFrame({"Carousel_stockpiles": [720]})
        assert cm.compute_carousel_needs(df) == (720, 1)

    def test_721_two_cabs(self):
        df = pd.DataFrame({"Carousel_stockpiles": [721]})
        assert cm.compute_carousel_needs(df) == (721, 2)

    def test_negative_clipped(self):
        df = pd.DataFrame({"Carousel_stockpiles": [5, -3, 2]})
        # -3 clipped to 0; total = 5+0+2 = 7
        assert cm.compute_carousel_needs(df) == (7, 1)


# ---- compute_locker_needs ----

class TestComputeLockerNeeds:
    def test_locker_a_50_items(self):
        df = pd.DataFrame({"CabinetType": ["Locker A"] * 50})
        a, b, c = cm.compute_locker_needs(df)
        # 50 items, cap=48 → 2 cabinets
        assert a == (50, 2)

    def test_locker_b_72_items(self):
        df = pd.DataFrame({"CabinetType": ["Locker B"] * 72})
        a, b, c = cm.compute_locker_needs(df)
        # 72 items = 1 cabinet (cap=72)
        assert b == (72, 1)

    def test_locker_c_100_items(self):
        df = pd.DataFrame({"CabinetType": ["Locker C"] * 100})
        a, b, c = cm.compute_locker_needs(df)
        # 100 items, cap=96 → 2 cabinets
        assert c == (100, 2)

    def test_no_lockers(self):
        df = pd.DataFrame({"CabinetType": ["Helix", "Carousel"]})
        a, b, c = cm.compute_locker_needs(df)
        assert a == (0, 0)
        assert b == (0, 0)
        assert c == (0, 0)


# ---- assign_supply_points ----

class TestAssignSupplyPoints:
    def test_n_sp_1(self):
        df = pd.DataFrame({
            "Code": ["A", "B"], "Listing": ["Tools"] * 2,
            "Consumption_pcs": [10.0, 20.0],
        })
        out = cm.assign_supply_points(df, 1)
        assert (out["SupplyPoint"] == 1).all()

    def test_existing_sp_preserved(self):
        df = pd.DataFrame({"Code": ["A", "B"], "SupplyPoint": [2, 3]})
        out = cm.assign_supply_points(df, 4)
        assert list(out["SupplyPoint"]) == [2, 3]

    def test_partition_default(self):
        df = pd.DataFrame({
            "Code": ["A", "B"], "Listing": ["Tools"] * 2,
            "Consumption_pcs": [10.0, 20.0],
        })
        out = cm.assign_supply_points(df, 2)
        # Both SPs should be used
        assert set(out["SupplyPoint"]) == {1, 2}

    def test_invalid_mode_falls_to_partition(self):
        df = pd.DataFrame({
            "Code": ["A"], "Listing": ["Tools"],
            "Consumption_pcs": [10.0],
        })
        out = cm.assign_supply_points(df, 2, mode="garbage_mode")
        # Should not crash; mode falls back to partition
        assert "SupplyPoint" in out.columns


# ---- _partition_supply_points_lpt ----

class TestPartitionSupplyPointsLpt:
    def test_lpt_balances_load(self):
        df = pd.DataFrame({
            "Code": list("ABCDE"),
            "Listing": ["Tools"] * 5,
            "Consumption_pcs": [100, 80, 60, 40, 20],
        })
        out = cm._partition_supply_points_lpt(df, 2)
        # SP loads should be within 30% of each other
        sp_loads = {}
        for _, row in out.iterrows():
            sp_loads.setdefault(row["SupplyPoint"], 0)
            sp_loads[row["SupplyPoint"]] += row["Consumption_pcs"]
        max_load = max(sp_loads.values())
        min_load = min(sp_loads.values())
        assert (max_load - min_load) / max_load <= 0.3

    def test_per_listing_balanced(self):
        df = pd.DataFrame({
            "Code": list("ABCD"),
            "Listing": ["Tools", "Tools", "PPE", "PPE"],
            "Consumption_pcs": [100, 50, 100, 50],
        })
        out = cm._partition_supply_points_lpt(df, 2)
        # Tools and PPE balanced separately
        assert set(out["SupplyPoint"]) == {1, 2}


# ---- _replicate_across_supply_points ----

class TestReplicateAcrossSupplyPoints:
    def test_row_count_multiplied(self):
        df = pd.DataFrame({"Code": ["A", "B"], "Consumption_pcs": [100.0, 80.0]})
        out = cm._replicate_across_supply_points(df, 3)
        assert len(out) == 6

    def test_each_sp_present(self):
        df = pd.DataFrame({"Code": ["A"], "Consumption_pcs": [100.0]})
        out = cm._replicate_across_supply_points(df, 3)
        assert set(out["SupplyPoint"]) == {1, 2, 3}

    def test_consumption_divided(self):
        df = pd.DataFrame({"Code": ["A"], "Consumption_pcs": [100.0]})
        out = cm._replicate_across_supply_points(df, 4)
        # Each copy gets 100/4 = 25
        assert all(out["Consumption_pcs"] == 25.0)

    def test_n_sp_1_no_replication(self):
        df = pd.DataFrame({"Code": ["A"], "Consumption_pcs": [100.0]})
        out = cm._replicate_across_supply_points(df, 1)
        assert len(out) == 1
        assert out["SupplyPoint"].iloc[0] == 1


# ---- apply_bulk_routing ----

class TestApplyBulkRouting:
    def test_disque_routed(self):
        df = pd.DataFrame({
            "Description": ["DISQUE VELCRO"],
            "Description_2": [""], "Code": ["A"], "SupplierCode": [""],
            "CabinetType": ["Helix"], "SystemCategory": ["KTC"],
            "Spirals_needed": [1], "Carousel_stockpiles": [0],
            "Override_Applied": [False],
        })
        out, stats = cm.apply_bulk_routing(df)
        assert out.loc[0, "VendMode"] == "Bulk/Kanban"
        assert stats["routed_rows"] == 1

    def test_foret_not_routed(self):
        df = pd.DataFrame({
            "Description": ["foret D5"],
            "Description_2": [""], "Code": ["A"], "SupplierCode": [""],
            "CabinetType": ["Helix"], "SystemCategory": ["KTC"],
            "Spirals_needed": [1], "Carousel_stockpiles": [0],
            "Override_Applied": [False],
        })
        out, stats = cm.apply_bulk_routing(df)
        assert out.loc[0, "VendMode"] == "Vending"
        assert stats["routed_rows"] == 0

    def test_routed_items_become_kanban(self):
        df = pd.DataFrame({
            "Description": ["chiffon coton"],
            "Description_2": [""], "Code": ["A"], "SupplierCode": [""],
            "CabinetType": ["Helix"], "SystemCategory": ["KTC"],
            "Spirals_needed": [1], "Carousel_stockpiles": [0],
            "Override_Applied": [False],
        })
        out, stats = cm.apply_bulk_routing(df)
        assert out.loc[0, "SystemCategory"] == "Kanban"
        assert out.loc[0, "CabinetType"] == "Kanban"
        assert out.loc[0, "Spirals_needed"] == 0
        assert pd.isna(out.loc[0, "Spiral_capacity"])

    def test_override_protected(self):
        df = pd.DataFrame({
            "Description": ["DISQUE VELCRO"],
            "Description_2": [""], "Code": ["A"], "SupplierCode": [""],
            "CabinetType": ["Helix"], "SystemCategory": ["KTC"],
            "Spirals_needed": [1], "Carousel_stockpiles": [0],
            "Override_Applied": [True],
        })
        out, stats = cm.apply_bulk_routing(df)
        # Overridden — not routed
        assert out.loc[0, "VendMode"] != "Bulk/Kanban"
        assert stats["overridden_bulk_candidates"] == 1

    def test_stats_include_removed_spirals(self):
        df = pd.DataFrame({
            "Description": ["DISQUE VELCRO", "Mastic", "foret"],
            "Description_2": [""] * 3, "Code": ["A"] * 3, "SupplierCode": [""] * 3,
            "CabinetType": ["Helix"] * 3, "SystemCategory": ["KTC"] * 3,
            "Spirals_needed": [2, 1, 1], "Carousel_stockpiles": [0] * 3,
            "Override_Applied": [False] * 3,
        })
        out, stats = cm.apply_bulk_routing(df)
        assert stats["routed_rows"] == 2
        assert stats["removed_spirals"] == 3  # 2 + 1 from routed rows


# ---- compute_plan_for_subset ----

class TestComputePlanForSubset:
    def test_complex_plan(self):
        df = pd.DataFrame({
            "Code": [f"X{i}" for i in range(20)],
            "Listing": ["Tools"] * 20,
            "SystemCategory": ["KTC"] * 15 + ["Kanban"] * 5,
            "CabinetType": ["Helix"] * 8 + ["Carousel"] * 4 + ["Locker A"] * 2 + ["Locker B"] * 1 + ["Kanban"] * 5,
            "Spirals_needed": [1] * 8 + [0] * 12,
            "Carousel_stockpiles": [0] * 8 + [5] * 4 + [0] * 8,
            "Monthly_packs": [10.0] * 20,
            "Spiral_capacity": [22] * 20,
            "Consumption_pcs": [100.0] * 20,
        })
        plan = cm.compute_plan_for_subset(df, 15.0)
        assert plan["ktc_count"] == 15
        assert plan["kanban_count"] == 5
        assert plan["helix_refs"] == 8
        assert plan["carousel_refs"] == 4
        assert plan["total_spirals"] == 8
        assert plan["car_slots"] == 20
        assert plan["countA"] == 2
        assert plan["countB"] == 1
        # Buffered: 8 * 1.15 = 9.2 → ceil 10
        assert plan["total_spirals_buf"] == 10
        assert plan["helix_cabs"] == 1
        assert plan["total_consumption"] == 2000.0


# ---- rebalance_cabinets ----

class TestRebalanceCabinets:
    def test_consolidation_reduces_cabinets(self, work_consolidatable):
        out, audit = cm.rebalance_cabinets(
            work_consolidatable, buf_pct=15.0,
            minimum_carousel_allocation=3, underuse_threshold_pct=30.0,
        )
        plan = cm.compute_plan_for_subset(out, buf_pct=15.0)
        # 2 cabs → 1
        assert plan["total_cabs"] == 1

    def test_audit_captures_moves(self, work_consolidatable):
        out, audit = cm.rebalance_cabinets(
            work_consolidatable, buf_pct=15.0,
            minimum_carousel_allocation=3, underuse_threshold_pct=30.0,
        )
        total_moves = sum(len(e["items_moved"]) for e in audit)
        assert total_moves == 5  # 5 carousel items moved to helix

    def test_no_carousels_post_rebalance(self, work_consolidatable):
        out, audit = cm.rebalance_cabinets(
            work_consolidatable, buf_pct=15.0,
            minimum_carousel_allocation=3, underuse_threshold_pct=30.0,
        )
        plan = cm.compute_plan_for_subset(out, buf_pct=15.0)
        assert plan["car_cabs"] == 0

    def test_xl_item_can_relocate_to_carousel(self):
        """An XL vending item must be relocatable into a Carousel so it can't
        pin its cabinet. Helix holds only the XL item; the Carousel has an L
        item (which can't move to a Helix), so the only path to one cabinet is
        moving the XL into the Carousel."""
        rows = [{
            "Code": "XL1", "Description": "big bar", "Description_2": "", "SupplierCode": "",
            "Listing": "Tools", "SystemCategory": "KTC", "CabinetType": "Helix",
            "Spirals_needed": 1, "Carousel_stockpiles": 0, "Spiral_capacity": 10,
            "Target_packs": 5.0, "Monthly_packs": 5.0, "Consumption_pcs": 80.0,
            "ProductCategory": "boring_bars", "SizeCategory": "XL", "SupplyPoint": 1,
        }, {
            "Code": "L1", "Description": "groove", "Description_2": "", "SupplierCode": "",
            "Listing": "Tools", "SystemCategory": "KTC", "CabinetType": "Carousel",
            "Spirals_needed": 0, "Carousel_stockpiles": 3, "Spiral_capacity": pd.NA,
            "Target_packs": 1.0, "Monthly_packs": 1.0, "Consumption_pcs": 16.0,
            "ProductCategory": "holders", "SizeCategory": "L", "SupplyPoint": 1,
        }]
        for i in range(3):
            rows.append({
                "Code": f"S{i}", "Description": "small", "Description_2": "", "SupplierCode": "",
                "Listing": "Tools", "SystemCategory": "KTC", "CabinetType": "Carousel",
                "Spirals_needed": 0, "Carousel_stockpiles": 3, "Spiral_capacity": pd.NA,
                "Target_packs": 1.0, "Monthly_packs": 1.0, "Consumption_pcs": 16.0,
                "ProductCategory": "drills", "SizeCategory": "S", "SupplyPoint": 1,
            })
        df = pd.DataFrame(rows)
        out, _ = cm.rebalance_cabinets(
            df, buf_pct=0.0, minimum_carousel_allocation=3, underuse_threshold_pct=30.0)
        plan = cm.compute_plan_for_subset(out, buf_pct=0.0)
        assert plan["total_cabs"] == 1
        assert out[out["Code"] == "XL1"].iloc[0]["CabinetType"] == "Carousel"

    def test_protected_items_not_moved(self):
        """Items with Override_Applied=True and Override_Fields containing
        'cabinet_type' are PROTECTED."""
        rows = []
        for i in range(30):
            rows.append({
                "Code": f"H{i}", "Description": "x", "Listing": "Tools",
                "SystemCategory": "KTC", "CabinetType": "Helix",
                "Monthly_packs": 12.0, "Target_packs": 12.0,
                "SizeCategory": "S", "Spiral_capacity": 22,
                "Spirals_needed": 1, "Carousel_stockpiles": 0,
                "Consumption_pcs": 144, "ProductCategory": "drills",
                "Override_Applied": False, "Override_Fields": "",
            })
        for i in range(5):
            rows.append({
                "Code": f"C{i}", "Description": "x", "Listing": "Tools",
                "SystemCategory": "KTC", "CabinetType": "Carousel",
                "Monthly_packs": 2.0, "Target_packs": 2.0,
                "SizeCategory": "S", "Spiral_capacity": None,
                "Spirals_needed": 0, "Carousel_stockpiles": 3,
                "Consumption_pcs": 24, "ProductCategory": "drills",
                "Override_Applied": True, "Override_Fields": "cabinet_type",
            })
        work = pd.DataFrame(rows)
        out, audit = cm.rebalance_cabinets(
            work, buf_pct=15.0,
            minimum_carousel_allocation=3, underuse_threshold_pct=30.0,
        )
        plan = cm.compute_plan_for_subset(out, buf_pct=15.0)
        # Still 2 cabinets because the carousel items can't be moved
        assert plan["total_cabs"] == 2
        # No moves in audit
        assert sum(len(e["items_moved"]) for e in audit) == 0

    def test_with_custom_factors(self, work_consolidatable):
        """The function accepts overfill_factor and carousel_reserve_factor."""
        out, audit = cm.rebalance_cabinets(
            work_consolidatable, buf_pct=15.0,
            minimum_carousel_allocation=3, underuse_threshold_pct=30.0,
            carousel_reserve_factor=0.5, overfill_factor=2.0,
        )
        # Just check it runs without error and returns something
        assert isinstance(out, pd.DataFrame)

    def test_carousel_to_helix_move_has_nonzero_destination_cost(self):
        """v33 regression: a Carousel item carries no Spiral_capacity, so the
        rebalancer's cost-in-Helix used to compute 0 spirals — reporting
        cost_at_destination=0 and approving a phantom consolidation that would
        overfill the Helix. The cost must reflect real spirals (>= 1)."""
        rows = []
        # A Helix with room (20 of 70 spirals used).
        for i in range(20):
            rows.append({
                "Code": f"H{i}", "Description": "drill", "Listing": "Tools",
                "SystemCategory": "KTC", "CabinetType": "Helix",
                "Monthly_packs": 10.0, "Target_packs": 10.0,
                "SizeCategory": "S", "Spiral_capacity": 28,
                "Spirals_needed": 1, "Carousel_stockpiles": 0,
                "Consumption_pcs": 120, "ProductCategory": "drills",
                "Override_Applied": False, "Override_Fields": "",
            })
        # One underused Carousel holding a single FAST mover with NO stored
        # Spiral_capacity (as every carousel row has).
        rows.append({
            "Code": "2007", "Description": "Frae. WSP insert", "Listing": "Tools",
            "SystemCategory": "KTC", "CabinetType": "Carousel",
            "Monthly_packs": 44.5, "Target_packs": 44.5,
            "SizeCategory": "S", "Spiral_capacity": None,
            "Spirals_needed": 0, "Carousel_stockpiles": 25,
            "Consumption_pcs": 534, "ProductCategory": "inserts",
            "Override_Applied": False, "Override_Fields": "",
        })
        work = pd.DataFrame(rows)
        out, audit = cm.rebalance_cabinets(
            work, buf_pct=15.0,
            minimum_carousel_allocation=3, underuse_threshold_pct=30.0,
        )
        moves = [m for e in audit for m in e["items_moved"]]
        helix_moves = [m for m in moves if m["to_cabinet"] == "Helix"]
        assert helix_moves, "expected the fast carousel item to be promoted to Helix"
        for m in helix_moves:
            assert m["cost_at_destination"] >= 1, (
                f"Helix move must cost >= 1 spiral, got {m['cost_at_destination']}"
            )
        assert isinstance(audit, list)


# ---- HMA-1: route_and_size_row (override -> routing propagation) ----

class TestRouteAndSizeRow:
    COMMON = dict(helix_threshold=6.0, min_carousel_compartments=3,
                  carousel_reserve_factor=0.85, helix_overfill_factor=1.10)

    def test_below_threshold_is_kanban(self):
        r = cm.route_and_size_row(monthly_packs=0.5, target_packs=0.3, size_cat="S",
                                  product_category="drills", threshold=0.7, **self.COMMON)
        assert r["SystemCategory"] == "Kanban"
        assert r["CabinetType"] == "Kanban"
        assert r["Spirals_needed"] == 0 and r["Carousel_stockpiles"] == 0

    def test_insert_threshold_routes_to_kanban(self):
        # An insert at 3 packs/mo with an insert threshold of 10 -> Kanban,
        # even though it would be KTC under the 0.7 standard threshold.
        r = cm.route_and_size_row(monthly_packs=3.0, target_packs=2.0, size_cat="S",
                                  product_category="inserts", threshold=10.0, **self.COMMON)
        assert r["SystemCategory"] == "Kanban"

    def test_high_demand_is_helix(self):
        r = cm.route_and_size_row(monthly_packs=50.0, target_packs=30.0, size_cat="S",
                                  product_category="drills", threshold=0.7, **self.COMMON)
        assert r["SystemCategory"] == "KTC"
        assert r["CabinetType"] == "Helix"
        assert r["Spirals_needed"] >= 1
        assert r["Carousel_stockpiles"] == 0

    def test_low_but_above_threshold_is_carousel(self):
        r = cm.route_and_size_row(monthly_packs=3.0, target_packs=2.0, size_cat="S",
                                  product_category="drills", threshold=0.7, **self.COMMON)
        assert r["SystemCategory"] == "KTC"
        assert r["CabinetType"] == "Carousel"
        assert r["Carousel_stockpiles"] >= 3   # min compartment floor
        assert r["Spirals_needed"] == 0

    def test_force_kanban_overrides_routing(self):
        r = cm.route_and_size_row(monthly_packs=50.0, target_packs=30.0, size_cat="S",
                                  product_category="screws", threshold=0.7,
                                  force_kanban=True, **self.COMMON)
        assert r["SystemCategory"] == "Kanban"

    def test_oversize_is_locker(self):
        r = cm.route_and_size_row(monthly_packs=5.0, target_packs=3.0, size_cat="XXL",
                                  product_category="drills", threshold=0.7, **self.COMMON)
        assert r["SystemCategory"] == "KTC"
        assert r["CabinetType"] == "Locker A"
        assert r["Spirals_needed"] == 0 and r["Carousel_stockpiles"] == 0

    def test_nan_monthly_packs_is_kanban(self):
        r = cm.route_and_size_row(monthly_packs=float("nan"), target_packs=float("nan"),
                                  size_cat="S", product_category="drills", threshold=0.7, **self.COMMON)
        assert r["SystemCategory"] == "Kanban"


class TestDetectSizeLockedItems:
    """detect_size_locked_items flags Carousel items whose size keeps them out
    of a Helix (L/XL) and which, if resized to M, would let the rebalancer drop
    a cabinet. It must never mutate the input and never flag a Carousel that is
    genuinely needed for volume."""

    def _helix_row(self, code, size="S"):
        return {
            "Code": code, "Description": "drill", "Description_2": "", "SupplierCode": "",
            "Listing": "Tools", "SystemCategory": "KTC", "CabinetType": "Helix",
            "Spirals_needed": 1, "Carousel_stockpiles": 0, "Spiral_capacity": 10,
            "Target_packs": 8.0, "Monthly_packs": 8.0, "Consumption_pcs": 128.0,
            "ProductCategory": "drills", "SizeCategory": size, "SupplyPoint": 1,
        }

    def _car_row(self, code, size="L", stock=3, mp=1.0):
        return {
            "Code": code, "Description": "groove", "Description_2": "", "SupplierCode": "",
            "Listing": "Tools", "SystemCategory": "KTC", "CabinetType": "Carousel",
            "Spirals_needed": 0, "Carousel_stockpiles": stock, "Spiral_capacity": pd.NA,
            "Target_packs": mp, "Monthly_packs": mp, "Consumption_pcs": mp * 16.0,
            "ProductCategory": "holders", "SizeCategory": size, "SupplyPoint": 1,
        }

    def test_flags_lone_L_forcing_underused_carousel(self):
        rows = [self._helix_row(f"H{i}") for i in range(50)]
        rows.append(self._car_row("L_lonely", size="L"))
        df = pd.DataFrame(rows)
        flagged = cm.detect_size_locked_items(
            df, buf_pct=0.0, minimum_carousel_allocation=3, underuse_threshold_pct=30.0)
        assert df[df["Code"] == "L_lonely"].index[0] in flagged
        assert len(flagged) == 1

    def test_flags_lone_XL_forcing_underused_carousel(self):
        rows = [self._helix_row(f"H{i}") for i in range(50)]
        rows.append(self._car_row("XL_lonely", size="XL"))
        df = pd.DataFrame(rows)
        flagged = cm.detect_size_locked_items(
            df, buf_pct=0.0, minimum_carousel_allocation=3, underuse_threshold_pct=30.0)
        assert df[df["Code"] == "XL_lonely"].index[0] in flagged

    def test_no_flag_when_carousel_is_well_used(self):
        # A Carousel that is healthily full is genuinely needed; resizing its L
        # items would not drop a cabinet, so nothing is flagged.
        rows = [self._helix_row(f"H{i}") for i in range(50)]
        # ~400 carousel slots of S items + one L -> Carousel well above threshold
        for i in range(130):
            rows.append(self._car_row(f"C{i}", size="S", stock=3, mp=2.0))
        rows.append(self._car_row("L_in_full", size="L"))
        df = pd.DataFrame(rows)
        flagged = cm.detect_size_locked_items(
            df, buf_pct=0.0, minimum_carousel_allocation=3, underuse_threshold_pct=30.0)
        assert flagged == []

    def test_no_candidates_returns_empty(self):
        rows = [self._helix_row(f"H{i}") for i in range(10)]
        rows.append(self._car_row("C_small", size="S"))
        df = pd.DataFrame(rows)
        flagged = cm.detect_size_locked_items(
            df, buf_pct=0.0, minimum_carousel_allocation=3, underuse_threshold_pct=30.0)
        assert flagged == []

    def test_no_flag_when_single_cabinet(self):
        # One lone L item is its own (only) cabinet -- nothing to consolidate into.
        df = pd.DataFrame([self._car_row("L_alone", size="L")])
        flagged = cm.detect_size_locked_items(
            df, buf_pct=0.0, minimum_carousel_allocation=3, underuse_threshold_pct=30.0)
        assert flagged == []

    def test_does_not_mutate_input(self):
        rows = [self._helix_row(f"H{i}") for i in range(50)]
        rows.append(self._car_row("L_lonely", size="L"))
        df = pd.DataFrame(rows)
        before = df["SizeCategory"].tolist()
        cm.detect_size_locked_items(
            df, buf_pct=0.0, minimum_carousel_allocation=3, underuse_threshold_pct=30.0)
        assert df["SizeCategory"].tolist() == before


class TestOperationalMode:
    """Operational Mode A/B/C overrides the per-tool cabinet composition.
    apply_operational_mode forces every KTC vending row to one cabinet type
    (Helix or Carousel) and recomputes its resources; flag_unfit_for_mode marks
    rows whose size does not physically fit the forced type; apply_carousel_cap
    spills Helix-eligible Carousel overflow to Helix under a max-Carousel limit."""

    def _row(self, code, cab, size="S", mp=5.0, stock=0, spirals=0):
        return {
            "Code": code, "Description": "tool", "Description_2": "", "SupplierCode": "",
            "Listing": "Tools", "SystemCategory": ("Kanban" if cab == "Kanban" else "KTC"),
            "CabinetType": cab, "Spirals_needed": spirals, "Carousel_stockpiles": stock,
            "Spiral_capacity": (10 if cab == "Helix" else pd.NA),
            "Target_packs": mp, "Monthly_packs": mp, "Consumption_pcs": mp * 16.0,
            "ProductCategory": "drills", "SizeCategory": size, "Regrind": False, "SupplyPoint": 1,
        }

    # --- mode A: Helix ---
    def test_mode_helix_forces_all_vending_to_helix(self):
        df = pd.DataFrame([
            self._row("a", "Helix", "S"),
            self._row("b", "Carousel", "M", stock=5),
            self._row("c", "Locker A", "XXL"),
            self._row("k", "Kanban", "S"),
        ])
        out = cm.apply_operational_mode(
            df, "Helix", min_carousel_compartments=3,
            carousel_reserve_factor=1.0, helix_overfill_factor=1.1)
        ktc = out[out["SystemCategory"] == "KTC"]
        assert (ktc["CabinetType"] == "Helix").all()
        assert (ktc["Carousel_stockpiles"] == 0).all()
        assert (pd.to_numeric(ktc["Spirals_needed"]) >= 1).all()
        # Kanban row untouched
        assert out[out["Code"] == "k"].iloc[0]["CabinetType"] == "Kanban"

    def test_mode_carousel_forces_all_vending_to_carousel(self):
        df = pd.DataFrame([
            self._row("a", "Helix", "S", spirals=2),
            self._row("b", "Carousel", "M", stock=5),
            self._row("c", "Locker A", "XXL"),
            self._row("k", "Kanban", "S"),
        ])
        out = cm.apply_operational_mode(
            df, "Carousel", min_carousel_compartments=3,
            carousel_reserve_factor=1.0, helix_overfill_factor=1.1)
        ktc = out[out["SystemCategory"] == "KTC"]
        assert (ktc["CabinetType"] == "Carousel").all()
        assert (pd.to_numeric(ktc["Spirals_needed"]) == 0).all()
        assert (pd.to_numeric(ktc["Carousel_stockpiles"]) >= 1).all()
        assert out[out["Code"] == "k"].iloc[0]["CabinetType"] == "Kanban"

    def test_operational_mode_does_not_mutate_input(self):
        df = pd.DataFrame([self._row("b", "Carousel", "M", stock=5)])
        before = df["CabinetType"].tolist()
        cm.apply_operational_mode(
            df, "Helix", min_carousel_compartments=3,
            carousel_reserve_factor=1.0, helix_overfill_factor=1.1)
        assert df["CabinetType"].tolist() == before

    # --- mode-aware unfit flag ---
    def test_flag_unfit_helix_mode(self):
        df = pd.DataFrame([
            self._row("s", "Helix", "S"), self._row("m", "Helix", "M"),
            self._row("l", "Helix", "L"), self._row("xl", "Helix", "XL"),
            self._row("xxl", "Helix", "XXL"),
        ])
        flag = cm.flag_unfit_for_mode(df, "Helix")
        assert not flag[df.index[df["Code"] == "s"][0]]
        assert not flag[df.index[df["Code"] == "m"][0]]
        assert flag[df.index[df["Code"] == "l"][0]]
        assert flag[df.index[df["Code"] == "xl"][0]]
        assert flag[df.index[df["Code"] == "xxl"][0]]

    def test_flag_unfit_carousel_mode(self):
        df = pd.DataFrame([
            self._row("l", "Carousel", "L", stock=3), self._row("xl", "Carousel", "XL", stock=3),
            self._row("xxl", "Carousel", "XXL", stock=3), self._row("xls", "Carousel", "XLS", stock=3),
        ])
        flag = cm.flag_unfit_for_mode(df, "Carousel")
        assert not flag[df.index[df["Code"] == "l"][0]]    # L fits a Carousel
        assert not flag[df.index[df["Code"] == "xl"][0]]   # XL fits a Carousel
        assert flag[df.index[df["Code"] == "xxl"][0]]      # locker size
        assert flag[df.index[df["Code"] == "xls"][0]]

    # --- mode C: carousel cap ---
    def test_carousel_cap_no_change_within_limit(self):
        df = pd.DataFrame([self._row(f"c{i}", "Carousel", "S", stock=100) for i in range(5)])
        out, overflow = cm.apply_carousel_cap(df, max_carousels=1, helix_overfill_factor=1.1)
        # 500 slots <= 720 -> 1 Carousel, no spill
        assert (out["CabinetType"] == "Carousel").all()
        assert overflow == []

    def test_carousel_cap_spills_overflow_to_helix(self):
        df = pd.DataFrame([self._row(f"c{i}", "Carousel", "S", stock=200) for i in range(5)])
        out, overflow = cm.apply_carousel_cap(df, max_carousels=1, helix_overfill_factor=1.1)
        car_slots = pd.to_numeric(
            out.loc[out["CabinetType"] == "Carousel", "Carousel_stockpiles"]).sum()
        import math as _m
        assert _m.ceil(car_slots / 720) <= 1
        assert (out["CabinetType"] == "Helix").any()  # some spilled to Helix
        assert overflow == []  # all S could spill, nothing stuck

    def test_carousel_cap_flags_unspillable_LXL(self):
        # All L items can't spill to a Helix; cap can't be met -> they're flagged.
        df = pd.DataFrame([self._row(f"l{i}", "Carousel", "L", stock=200) for i in range(5)])
        out, overflow = cm.apply_carousel_cap(df, max_carousels=1, helix_overfill_factor=1.1)
        assert (out["CabinetType"] == "Carousel").all()  # none moved
        assert len(overflow) == 5
