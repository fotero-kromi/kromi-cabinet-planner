"""HMA-1 integration: a ProductCategory / PackUnits override that is NOT a
routing override must propagate to the KTC/Kanban decision and cabinet sizing.

The page wires this as apply_overrides -> (for touched rows whose
Routing_Overridden is False) route_and_size_row(...). These tests exercise that
exact composition with the real engine functions so the propagation is pinned
even though the page itself is not importable.
"""
import pandas as pd

from engine import overrides as ov
from engine.routing_rules import is_insert, ktc_threshold_for
from engine.cabinet_math import route_and_size_row


def _reroute(row, *, usage_threshold, insert_threshold, insert_active,
             force_screws=False):
    """Mirror of the page's per-row re-route for a non-routing-overridden row."""
    pc = row["ProductCategory"]
    tc = row.get("ToolClass", "")
    thr = ktc_threshold_for(is_insert(pc, tc), usage_threshold, insert_threshold, insert_active)
    fk = force_screws and str(pc).strip().lower() in ("screws", "accessories")
    return route_and_size_row(
        monthly_packs=row["Monthly_packs"], target_packs=row["Target_packs"],
        size_cat=row["SizeCategory"], product_category=pc, threshold=thr,
        helix_threshold=6.0, min_carousel_compartments=3,
        carousel_reserve_factor=0.85, helix_overfill_factor=1.10, force_kanban=fk)


def _work():
    return pd.DataFrame({
        "Code": ["A1"], "Listing": ["Tools"],
        "ProductCategory": ["drills"], "ProductCategory_Source": ["Default"],
        "ProductCategory_Evidence": [""], "ProductCategory_Confidence": [""],
        "ToolClass": ["solid_carbide_drill"],
        "PackUnits": [1.0], "PackUnits_Source": ["Default"],
        "PackUnits_Evidence": [""], "PackUnits_Confidence": [""],
        "SizeCategory": ["S"], "SizeCategory_Source": ["Default"],
        "CabinetType": ["Carousel"], "SystemCategory": ["KTC"],
        "VendMode": ["Vending"], "VendBlockReason": [""],
        "Monthly_packs": [3.0], "Target_packs": [2.0],
    })


class TestOverrideRoutingPropagation:
    def test_category_override_to_insert_reroutes_to_kanban(self):
        ovs = pd.DataFrame({
            "code": ["A1"], "listing": ["Tools"],
            "product_category_override": ["inserts"], "pack_units_override": [""],
            "size_category_override": [""], "cabinet_type_override": [""],
            "vend_mode_override": [""],
        })
        out, _ = ov.apply_overrides(_work(), ovs)
        r = out.iloc[0]
        assert bool(r["Routing_Overridden"]) is False     # category-only -> re-routable
        assert r["ProductCategory"] == "inserts"
        # With the insert threshold (10) active, 3 packs/mo now routes to Kanban.
        assert _reroute(r, usage_threshold=0.7, insert_threshold=10.0, insert_active=True)["SystemCategory"] == "Kanban"
        # The same row with the insert override OFF stays KTC (3 > 0.7).
        assert _reroute(r, usage_threshold=0.7, insert_threshold=10.0, insert_active=False)["SystemCategory"] == "KTC"

    def test_monthly_packs_change_flips_kanban_to_ktc(self):
        r = _work().iloc[0].copy()
        r["SystemCategory"] = "Kanban"; r["CabinetType"] = "Kanban"
        r["Monthly_packs"] = 5.0; r["Target_packs"] = 3.0   # post-override recompute
        res = _reroute(r, usage_threshold=0.7, insert_threshold=10.0, insert_active=False)
        assert res["SystemCategory"] == "KTC"
        assert res["CabinetType"] in ("Helix", "Carousel")

    def test_force_screws_override_routes_to_kanban(self):
        r = _work().iloc[0].copy()
        r["ProductCategory"] = "screws"; r["Monthly_packs"] = 50.0
        res = _reroute(r, usage_threshold=0.7, insert_threshold=10.0,
                       insert_active=False, force_screws=True)
        assert res["SystemCategory"] == "Kanban"

    def test_cabinet_type_override_is_not_rerouted(self):
        ovs = pd.DataFrame({
            "code": ["A1"], "listing": ["Tools"],
            "product_category_override": [""], "pack_units_override": [""],
            "size_category_override": [""], "cabinet_type_override": ["Helix"],
            "vend_mode_override": [""],
        })
        out, _ = ov.apply_overrides(_work(), ovs)
        assert bool(out.iloc[0]["Routing_Overridden"]) is True   # page keeps forced type
        assert out.iloc[0]["CabinetType"] == "Helix"
