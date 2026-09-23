"""Tests for engine.invariants — the plan integrity / reconciliation layer."""
import numpy as np
import pandas as pd

from engine import invariants as inv


def _good_plan():
    return pd.DataFrame({
        "SystemCategory": ["KTC", "KTC", "Kanban"],
        "CabinetType": ["Helix", "Carousel", "Kanban"],
        "Spirals_needed": [2, 0, 0],
        "Carousel_stockpiles": [0, 3, 0],
        "PackUnits": [10.0, 5.0, 1.0],
        "Coverage_days": [18, 18, 18],
        "Target_packs": [4.0, 2.0, 0.5],
        "Monthly_packs": [6.0, 3.0, 0.5],
    })


class TestHappyPath:
    def test_clean_plan_passes_all(self):
        rep = inv.verify_plan(_good_plan())
        assert rep.ok
        assert rep.n_passed == rep.n_checks


class TestRoutingPartition:
    def test_invalid_system_value_detected(self):
        df = _good_plan(); df.loc[0, "SystemCategory"] = "Bulk"
        assert inv.check_routing_partition(df)

    def test_null_system_detected(self):
        df = _good_plan(); df.loc[0, "SystemCategory"] = None
        assert inv.check_routing_partition(df)


class TestSizingConsistency:
    def test_kanban_with_spirals_detected(self):
        df = _good_plan(); df.loc[2, "Spirals_needed"] = 1
        assert inv.check_sizing_consistency(df)

    def test_helix_with_zero_spirals_detected(self):
        df = _good_plan(); df.loc[0, "Spirals_needed"] = 0
        assert inv.check_sizing_consistency(df)

    def test_carousel_with_zero_stockpiles_detected(self):
        df = _good_plan(); df.loc[1, "Carousel_stockpiles"] = 0
        assert inv.check_sizing_consistency(df)

    def test_ktc_with_kanban_cabinet_detected(self):
        df = _good_plan(); df.loc[0, "CabinetType"] = "Kanban"
        assert inv.check_sizing_consistency(df)


class TestPackAndCoverage:
    def test_packunits_below_one_detected(self):
        df = _good_plan(); df.loc[0, "PackUnits"] = 0
        assert inv.check_pack_units(df)

    def test_invalid_coverage_detected(self):
        df = _good_plan(); df.loc[0, "Coverage_days"] = 0
        assert inv.check_coverage(df)

    def test_negative_target_packs_detected(self):
        df = _good_plan(); df.loc[0, "Target_packs"] = -1
        assert inv.check_coverage(df)


class TestConservation:
    def test_dedup_must_conserve_consumption(self):
        assert inv.check_consumption_conservation(100.0, 100.0, 90.0)  # dropped -> violation

    def test_year_filter_may_reduce(self):
        assert not inv.check_consumption_conservation(100.0, 80.0, 80.0)  # ok

    def test_filter_cannot_add(self):
        assert inv.check_consumption_conservation(100.0, 120.0, 120.0)  # increased -> violation

    def test_row_accounting_dedup_increase_detected(self):
        assert inv.check_row_accounting(100, 100, 120)


class TestExportPartition:
    def test_mismatch_detected(self):
        assert inv.check_export_partition(100, {"KTC": 40, "Kanban": 50})

    def test_exact_partition_ok(self):
        assert not inv.check_export_partition(90, {"KTC": 40, "Kanban": 50})


# ---- E1: arithmetic identity reconciliation ----

class TestArithmeticIdentities:
    def _plan(self):
        # Monthly_packs = Consumption/period/PackUnits ; Target = Monthly*cov/30
        return pd.DataFrame({
            "Consumption_pcs": [320.0, 160.0],
            "PackUnits": [10.0, 5.0],
            "Monthly_packs": [2.0, 2.0],     # 320/16/10=2 ; 160/16/5=2
            "Coverage_days": [30.0, 15.0],
            "Target_packs": [2.0, 1.0],      # 2*30/30=2 ; 2*15/30=1
        })

    def test_target_identity_holds(self):
        assert inv.check_target_packs_identity(self._plan(), days_per_month=30.0) == []

    def test_target_identity_violation_detected(self):
        df = self._plan(); df.loc[0, "Target_packs"] = 99.0
        assert inv.check_target_packs_identity(df, days_per_month=30.0)

    def test_monthly_identity_holds(self):
        assert inv.check_monthly_packs_identity(self._plan(), period_months=16.0) == []

    def test_monthly_identity_violation_detected(self):
        df = self._plan(); df.loc[1, "Monthly_packs"] = 7.0
        assert inv.check_monthly_packs_identity(df, period_months=16.0)

    def test_coverage_change_without_target_recompute_caught(self):
        # The exact regression class E1 targets: Coverage_days edited but
        # Target_packs not recomputed.
        df = self._plan(); df.loc[0, "Coverage_days"] = 60.0   # Target should now be 4.0
        assert inv.check_target_packs_identity(df, days_per_month=30.0)

    def test_identities_run_via_verify_plan(self):
        df = self._plan()
        df["SystemCategory"] = ["KTC", "Kanban"]; df["CabinetType"] = ["Carousel", "Kanban"]
        df["Spirals_needed"] = [0, 0]; df["Carousel_stockpiles"] = [3, 0]
        rep = inv.verify_plan(df, days_per_month=30.0, consumption_period_months=16.0)
        assert "target_packs_identity" in rep.checks
        assert "monthly_packs_identity" in rep.checks
        assert rep.ok


# ---- D1/D2: actual-exported-dataset reconciliation ----

class TestReconcileExportFrames:
    def test_clean_partition_passes(self):
        assert inv.reconcile_export_frames(n_plan=100, n_result=100, n_ktc=60, n_kanban=40) == []

    def test_result_row_loss_detected(self):
        # augment/user-view dropped rows from Result -> caught (D2 false-negative fix)
        assert inv.reconcile_export_frames(n_plan=100, n_result=98, n_ktc=60, n_kanban=38)

    def test_result_row_duplication_detected(self):
        assert inv.reconcile_export_frames(n_plan=100, n_result=102, n_ktc=62, n_kanban=40)

    def test_subsheets_not_partitioning_result_detected(self):
        # Result intact but KTC+Kanban sheets don't sum to it.
        assert inv.reconcile_export_frames(n_plan=100, n_result=100, n_ktc=60, n_kanban=39)


# ---- E4: supply-point consumption conservation ----

class TestSupplyPointConservation:
    def test_conserved_passes(self):
        assert inv.check_supply_point_conservation(1000.0, 1000.0) == []

    def test_replication_split_conserved(self):
        # 3 copies of 30 each summing to 90 == original 90
        assert inv.check_supply_point_conservation(90.0, 90.0) == []

    def test_loss_detected(self):
        assert inv.check_supply_point_conservation(1000.0, 950.0)

    def test_gain_detected(self):
        assert inv.check_supply_point_conservation(1000.0, 1100.0)

    def test_float_tolerance(self):
        # 90/3 = 30 exactly, but emulate tiny float drift
        assert inv.check_supply_point_conservation(90.0, 90.0 + 1e-9) == []


# ---- E3: KROMI article-number uniqueness ----

class TestKromiUniqueness:
    def test_unique_passes(self):
        df = pd.DataFrame({"Kromi_Art_No": ["191130016010", "191130016020", ""]})
        assert inv.check_kromi_uniqueness(df) == []

    def test_blanks_ignored(self):
        df = pd.DataFrame({"Kromi_Art_No": ["", "", None]})
        assert inv.check_kromi_uniqueness(df) == []

    def test_duplicate_detected(self):
        df = pd.DataFrame({"Kromi_Art_No": ["191130016010", "191130016010"]})
        assert inv.check_kromi_uniqueness(df)

    def test_missing_column_is_noop(self):
        assert inv.check_kromi_uniqueness(pd.DataFrame({"X": [1]})) == []

    def test_malformed_number_detected(self):
        # not 12 digits / does not end in 0
        df = pd.DataFrame({"Kromi_Art_No": ["19113001601", "191130016011"]})
        assert inv.check_kromi_uniqueness(df)


# ---- A5: VendMode <-> SystemCategory consistency ----

class TestVendModeConsistency:
    def test_ktc_vending_ok(self):
        df = pd.DataFrame({"SystemCategory": ["KTC"], "VendMode": ["Vending"]})
        assert inv.check_vendmode_consistency(df) == []

    def test_kanban_bulk_ok(self):
        df = pd.DataFrame({"SystemCategory": ["Kanban"], "VendMode": ["Bulk/Kanban"]})
        assert inv.check_vendmode_consistency(df) == []

    def test_kanban_vending_allowed(self):
        # The pipeline defaults Kanban rows to Vending; not flagged (ambiguous,
        # not a contradiction).
        df = pd.DataFrame({"SystemCategory": ["Kanban"], "VendMode": ["Vending"]})
        assert inv.check_vendmode_consistency(df) == []

    def test_ktc_bulk_is_contradiction(self):
        df = pd.DataFrame({"SystemCategory": ["KTC"], "VendMode": ["Bulk/Kanban"]})
        assert inv.check_vendmode_consistency(df)
