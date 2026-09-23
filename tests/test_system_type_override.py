"""Tests for the customer-specified System type override (Lagersystem):
- routing_rules.parse_system_type: KTC / KTC_OR_KANBAN / LOCKER / "" parsing
- cabinet_math.locker_for_size: size -> Locker A/B/C (consistent with decide_cabinet_type)
- cabinet_math.route_and_size_row: force_ktc skips the Kanban gate
- apply_bulk_routing + rebalance_cabinets protect Routing_Pinned rows
"""
import pandas as pd
import pytest

from engine import routing_rules as rr
from engine import cabinet_math as cm


class TestParseSystemType:
    @pytest.mark.parametrize("val,expected", [
        ("KTC", "KTC"),
        ("ktc", "KTC"),
        (" KTC ", "KTC"),
        ("KTC or Kanban", "KTC_OR_KANBAN"),
        ("ktc/kanban", "KTC_OR_KANBAN"),
        ("KTC oder Kanban", "KTC_OR_KANBAN"),
        ("Locker", "LOCKER"),
        ("locker", "LOCKER"),
        ("Schrank", "LOCKER"),
        ("", ""),
        ("  ", ""),
        (None, ""),
        ("something else", ""),
    ])
    def test_parse(self, val, expected):
        assert rr.parse_system_type(val) == expected


class TestLockerForSize:
    def test_consistent_with_decide_cabinet_type_oversize(self):
        # The oversize taxonomy must map the same way decide_cabinet_type does.
        assert cm.locker_for_size("XXL") == "Locker A"
        assert cm.locker_for_size("XXLS") == "Locker B"
        assert cm.locker_for_size("XLS") == "Locker C"

    def test_regular_sizes_extend_by_magnitude(self):
        assert cm.locker_for_size("XL") == "Locker A"
        assert cm.locker_for_size("L") == "Locker B"
        assert cm.locker_for_size("M") == "Locker C"
        assert cm.locker_for_size("S") == "Locker C"
        assert cm.locker_for_size("") == "Locker C"


class TestForceKtc:
    def _common(self):
        return dict(
            size_cat="S", product_category="drills", threshold=1.0,
            helix_threshold=5.0, min_carousel_compartments=3,
            carousel_reserve_factor=0.85, helix_overfill_factor=1.1,
        )

    def test_force_ktc_keeps_low_velocity_item_in_ktc(self):
        # Monthly_pcs 0.2 is below threshold 1.0 -> normally Kanban; force_ktc
        # must keep it KTC and give it a (Carousel) cabinet.
        res = cm.route_and_size_row(
            monthly_packs=0.2, monthly_pcs=0.2, target_packs=0.1,
            force_ktc=True, **self._common()
        )
        assert res["SystemCategory"] == "KTC"
        assert res["CabinetType"] in ("Carousel", "Helix")
        assert res["Carousel_stockpiles"] >= 1 or res["Spirals_needed"] >= 1

    def test_force_ktc_off_low_velocity_is_kanban(self):
        res = cm.route_and_size_row(
            monthly_packs=0.2, monthly_pcs=0.2, target_packs=0.1, **self._common()
        )
        assert res["SystemCategory"] == "Kanban"

    def test_force_kanban_wins_over_force_ktc(self):
        # If both somehow set, force_kanban takes precedence (defensive).
        res = cm.route_and_size_row(
            monthly_packs=9.0, monthly_pcs=90.0, target_packs=5.0,
            force_ktc=True, force_kanban=True, **self._common()
        )
        assert res["SystemCategory"] == "Kanban"

    def test_force_ktc_high_velocity_helix_with_regrind(self):
        common = self._common(); common["helix_threshold"] = 5.0
        res = cm.route_and_size_row(
            monthly_packs=6.0, monthly_pcs=60.0, target_packs=6.0,
            force_ktc=True, regrind=True, **common
        )
        assert res["SystemCategory"] == "KTC"
        assert res["CabinetType"] == "Helix"
        assert res["Spirals_needed"] >= 2


class TestSystemTypProtection:
    def _df(self):
        # Two bulk-family rows (sealant) — normally bulk-routed to Kanban. One is
        # Routing_Pinned (must survive), one is not (gets routed).
        return pd.DataFrame([
            {"Code": "A", "Description": "sealant tube", "Description_2": "", "SupplierCode": "",
             "SystemCategory": "KTC", "CabinetType": "Carousel", "Spirals_needed": 0,
             "Carousel_stockpiles": 5, "Spiral_capacity": pd.NA, "Routing_Pinned": True},
            {"Code": "B", "Description": "sealant tube", "Description_2": "", "SupplierCode": "",
             "SystemCategory": "KTC", "CabinetType": "Carousel", "Spirals_needed": 0,
             "Carousel_stockpiles": 5, "Spiral_capacity": pd.NA, "Routing_Pinned": False},
        ])

    def test_bulk_routing_skips_system_typ_forced(self):
        out, stats = cm.apply_bulk_routing(self._df())
        a = out[out["Code"] == "A"].iloc[0]
        b = out[out["Code"] == "B"].iloc[0]
        # forced row keeps KTC/Carousel; only the non-forced bulk-family row may move
        assert a["SystemCategory"] == "KTC"
        assert a["CabinetType"] == "Carousel"
        # B is a bulk family and not protected -> routed to Kanban
        assert b["VendMode"] == "Bulk/Kanban"
        assert b["SystemCategory"] == "Kanban"

    def _helix_rows(self, n=3):
        return [
            {"Code": f"H{i}", "Description": "drill", "Description_2": "", "SupplierCode": "",
             "SystemCategory": "KTC", "CabinetType": "Helix", "Spirals_needed": 5,
             "Carousel_stockpiles": 0, "Spiral_capacity": 10, "Target_packs": 40.0,
             "Monthly_packs": 40.0, "Consumption_pcs": 640.0, "ProductCategory": "drills",
             "SizeCategory": "S", "Routing_Pinned": False, "SupplyPoint": 1}
            for i in range(n)
        ]

    def test_rebalancer_protects_locker_forced(self):
        # A forced-Locker row must stay in its locker: the rebalancer must not
        # pull it into Helix/Carousel even though size S would be eligible.
        df = pd.DataFrame(self._helix_rows() + [
            {"Code": "LK", "Description": "insert", "Description_2": "", "SupplierCode": "",
             "SystemCategory": "KTC", "CabinetType": "Locker A", "Spirals_needed": 0,
             "Carousel_stockpiles": 0, "Spiral_capacity": pd.NA, "Target_packs": 1.0,
             "Monthly_packs": 1.0, "Consumption_pcs": 16.0, "ProductCategory": "inserts",
             "SizeCategory": "S", "Routing_Pinned": True, "SupplyPoint": 1},
        ])
        out, _ = cm.rebalance_cabinets(
            df, buf_pct=0.0, minimum_carousel_allocation=3, underuse_threshold_pct=30.0
        )
        lk = out[out["Code"] == "LK"].iloc[0]
        assert lk["CabinetType"] == "Locker A"
        assert lk["SystemCategory"] == "KTC"

    def test_rebalancer_does_not_pin_ktc_forced(self):
        # A forced-KTC row is NOT pinned — it is a normal KTC vending item and
        # may be consolidated. Identical setups with the flag True vs False must
        # rebalance to the SAME cabinet, proving the KTC fix changes nothing here.
        def make(forced):
            return pd.DataFrame(self._helix_rows() + [
                {"Code": "C1", "Description": "insert", "Description_2": "", "SupplierCode": "",
                 "SystemCategory": "KTC", "CabinetType": "Carousel", "Spirals_needed": 0,
                 "Carousel_stockpiles": 3, "Spiral_capacity": pd.NA, "Target_packs": 1.0,
                 "Monthly_packs": 1.0, "Consumption_pcs": 16.0, "ProductCategory": "inserts",
                 "SizeCategory": "S", "Routing_Pinned": forced, "SupplyPoint": 1},
            ])
        out_forced, _ = cm.rebalance_cabinets(
            make(True), buf_pct=0.0, minimum_carousel_allocation=3, underuse_threshold_pct=30.0)
        out_free, _ = cm.rebalance_cabinets(
            make(False), buf_pct=0.0, minimum_carousel_allocation=3, underuse_threshold_pct=30.0)
        c_forced = out_forced[out_forced["Code"] == "C1"].iloc[0]["CabinetType"]
        c_free = out_free[out_free["Code"] == "C1"].iloc[0]["CabinetType"]
        assert c_forced == c_free

