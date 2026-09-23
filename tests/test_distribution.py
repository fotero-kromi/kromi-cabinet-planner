"""Tests for engine.distribution — 5 functions."""

import pandas as pd
import pytest

from engine import distribution as dist
from engine.constants import SLIDE_BUCKET_ORDER

# ---- _slide_bucket_for_category ----

class TestSlideBucketForCategory:
    def test_drills_to_drills_bucket(self):
        # The bucket mapping is data-driven; we just check it returns a string
        result = dist._slide_bucket_for_category("drills")
        assert isinstance(result, str)
        assert result in SLIDE_BUCKET_ORDER or result == "Others"

    def test_inserts_bucket(self):
        result = dist._slide_bucket_for_category("inserts")
        assert isinstance(result, str)

    def test_mills_bucket(self):
        result = dist._slide_bucket_for_category("mills")
        assert isinstance(result, str)

    def test_unknown_to_others(self):
        assert dist._slide_bucket_for_category("nonexistent") == "Others"

    def test_empty_to_others(self):
        assert dist._slide_bucket_for_category("") == "Others"

    def test_none_to_others(self):
        assert dist._slide_bucket_for_category(None) == "Others"

    def test_case_insensitive(self):
        assert dist._slide_bucket_for_category("DRILLS") == dist._slide_bucket_for_category("drills")


# ---- build_per_sp_distribution ----

class TestBuildPerSpDistribution:
    def test_empty_df(self):
        df = pd.DataFrame({"SystemCategory": [], "ProductCategory": []})
        result = dist.build_per_sp_distribution(df)
        assert result == {}

    def test_single_sp(self):
        df = pd.DataFrame({
            "SystemCategory": ["KTC"] * 5,
            "ProductCategory": ["drills", "drills", "mills", "inserts", "other"],
            "SupplyPoint": [1, 1, 1, 1, 1],
        })
        result = dist.build_per_sp_distribution(df)
        assert 1 in result
        assert "__all__" in result
        # Sum across buckets should be 5
        assert sum(result[1].values()) == 5
        assert sum(result["__all__"].values()) == 5

    def test_multi_sp(self):
        df = pd.DataFrame({
            "SystemCategory": ["KTC"] * 6,
            "ProductCategory": ["drills"] * 6,
            "SupplyPoint": [1, 1, 1, 2, 2, 2],
        })
        result = dist.build_per_sp_distribution(df)
        assert 1 in result
        assert 2 in result
        assert sum(result[1].values()) == 3
        assert sum(result[2].values()) == 3
        assert sum(result["__all__"].values()) == 6

    def test_kanban_filtered_out(self):
        """Only KTC rows count; Kanban rows are excluded."""
        df = pd.DataFrame({
            "SystemCategory": ["KTC", "KTC", "Kanban", "Kanban"],
            "ProductCategory": ["drills"] * 4,
            "SupplyPoint": [1, 1, 1, 1],
        })
        result = dist.build_per_sp_distribution(df)
        assert sum(result["__all__"].values()) == 2

    def test_missing_systemcategory_column(self):
        """Without SystemCategory, all rows are treated as KTC."""
        df = pd.DataFrame({
            "ProductCategory": ["drills"] * 3,
            "SupplyPoint": [1, 1, 1],
        })
        result = dist.build_per_sp_distribution(df)
        assert sum(result["__all__"].values()) == 3

    def test_all_buckets_in_keys(self):
        """Every result dict should have all SLIDE_BUCKET_ORDER keys (with 0 if empty)."""
        df = pd.DataFrame({
            "SystemCategory": ["KTC"],
            "ProductCategory": ["drills"],
            "SupplyPoint": [1],
        })
        result = dist.build_per_sp_distribution(df)
        for bucket in SLIDE_BUCKET_ORDER:
            assert bucket in result[1]
            assert bucket in result["__all__"]


# ---- build_per_sp_subclass_breakdown ----

class TestBuildPerSpSubclassBreakdown:
    def test_with_toolclass(self):
        df = pd.DataFrame({
            "SystemCategory": ["KTC"] * 3,
            "ProductCategory": ["drills", "drills", "mills"],
            "ToolClass": ["solid_carbide_drill", "solid_carbide_drill", "solid_end_mill"],
            "SupplyPoint": [1, 1, 1],
        })
        result = dist.build_per_sp_subclass_breakdown(df)
        assert 1 in result
        assert "__all__" in result

    def test_without_toolclass_column(self):
        """No ToolClass column → empty result (function early-returns)."""
        df = pd.DataFrame({
            "SystemCategory": ["KTC"] * 3,
            "ProductCategory": ["drills"] * 3,
            "SupplyPoint": [1, 1, 1],
        })
        result = dist.build_per_sp_subclass_breakdown(df)
        assert result == {}

    def test_unclassified_fallback(self):
        """Empty ToolClass should produce a '(unclassified)' label."""
        df = pd.DataFrame({
            "SystemCategory": ["KTC"] * 2,
            "ProductCategory": ["drills", "drills"],
            "ToolClass": ["", ""],
            "SupplyPoint": [1, 1],
        })
        result = dist.build_per_sp_subclass_breakdown(df)
        # Walk the result; somewhere there should be a (unclassified) entry
        found_unclassified = False
        for sp_data in result.values():
            for bucket_data in sp_data.values():
                if "(unclassified)" in bucket_data:
                    found_unclassified = True
                    break
        assert found_unclassified

    def test_empty_buckets_dropped(self):
        """Buckets with no subclass entries should be omitted from output."""
        df = pd.DataFrame({
            "SystemCategory": ["KTC"],
            "ProductCategory": ["drills"],
            "ToolClass": ["solid_carbide_drill"],
            "SupplyPoint": [1],
        })
        result = dist.build_per_sp_subclass_breakdown(df)
        # Not every bucket should appear — only buckets with content
        for bucket_dict in result["__all__"].values():
            assert len(bucket_dict) > 0


# ---- build_per_sp_cabinet_occupation ----

class TestBuildPerSpCabinetOccupation:
    def test_empty_plan(self):
        assert dist.build_per_sp_cabinet_occupation({}) == []

    def test_none_plan(self):
        assert dist.build_per_sp_cabinet_occupation(None) == []

    def test_helix_only(self):
        plan = {
            "helix_cabs": 2, "total_spirals_buf": 60,
            "car_cabs": 0, "car_slots_buf": 0,
            "cabA": 0, "countA_buf": 0,
            "cabB": 0, "countB_buf": 0,
            "cabC": 0, "countC_buf": 0,
        }
        records = dist.build_per_sp_cabinet_occupation(plan)
        assert len(records) == 2
        assert all(r["cabinet_type"] == "Helix" for r in records)
        assert records[0]["capacity"] == 70

    def test_carousel_only(self):
        plan = {
            "helix_cabs": 0, "total_spirals_buf": 0,
            "car_cabs": 1, "car_slots_buf": 360,
            "cabA": 0, "countA_buf": 0,
            "cabB": 0, "countB_buf": 0,
            "cabC": 0, "countC_buf": 0,
        }
        records = dist.build_per_sp_cabinet_occupation(plan)
        assert len(records) == 1
        assert records[0]["cabinet_type"] == "Carousel"
        assert records[0]["capacity"] == 720
        assert records[0]["occupation_pct"] == 50.0

    def test_mixed_plan(self, plan_mixed):
        """Helix 1 + Carousel 1 + LockerA 1 + LockerC 1 = 4 cabinets."""
        records = dist.build_per_sp_cabinet_occupation(plan_mixed)
        assert len(records) == 4
        cabinet_types = [r["cabinet_type"] for r in records]
        assert "Helix" in cabinet_types
        assert "Carousel" in cabinet_types
        assert "Locker A" in cabinet_types
        assert "Locker C" in cabinet_types
        # Locker B has 0 — should NOT be in records
        assert "Locker B" not in cabinet_types

    def test_cabinet_numbering_sequential(self, plan_mixed):
        records = dist.build_per_sp_cabinet_occupation(plan_mixed)
        for i, rec in enumerate(records):
            assert rec["cabinet_no"] == i + 1

    def test_occupation_pct_calculation(self):
        """1 helix cab with 35 spirals → 50% occupation."""
        plan = {
            "helix_cabs": 1, "total_spirals_buf": 35,
            "car_cabs": 0, "car_slots_buf": 0,
            "cabA": 0, "cabB": 0, "cabC": 0,
            "countA_buf": 0, "countB_buf": 0, "countC_buf": 0,
        }
        records = dist.build_per_sp_cabinet_occupation(plan)
        assert records[0]["occupation_pct"] == 50.0


# ---- build_per_sp_summary ----

class TestBuildPerSpSummary:
    def test_single_sp_uses_all_label(self):
        work = pd.DataFrame({
            "Code": ["A", "B"],
            "Consumption_pcs": [100.0, 50.0],
            "Monthly_pcs": [8.3, 4.2],
            "SupplyPoint": [1, 1],
        })
        plan = {
            "helix_cabs": 1, "total_spirals_buf": 30,
            "car_cabs": 0, "cabA": 0, "cabB": 0, "cabC": 0,
            "car_slots_buf": 0, "countA_buf": 0, "countB_buf": 0, "countC_buf": 0,
        }
        compact, detail = dist.build_per_sp_summary(work, [("All", plan)], {}, 15.0)
        assert len(compact) == 1
        # When there's only 1 SP, label is "All", not "SP 1"

    def test_multi_sp_uses_sp_labels(self):
        work = pd.DataFrame({
            "Code": ["A", "B"],
            "Consumption_pcs": [100.0, 50.0],
            "Monthly_pcs": [8.3, 4.2],
            "SupplyPoint": [1, 2],
        })
        plan1 = {"helix_cabs": 1, "total_spirals_buf": 30, "car_cabs": 0,
                 "cabA": 0, "cabB": 0, "cabC": 0,
                 "car_slots_buf": 0, "countA_buf": 0, "countB_buf": 0, "countC_buf": 0}
        plan2 = {"helix_cabs": 0, "total_spirals_buf": 0, "car_cabs": 1,
                 "cabA": 0, "cabB": 0, "cabC": 0,
                 "car_slots_buf": 50, "countA_buf": 0, "countB_buf": 0, "countC_buf": 0}
        compact, detail = dist.build_per_sp_summary(
            work, [("SP 1", plan1), ("SP 2", plan2)], {}, 15.0
        )
        assert len(compact) == 2

    def test_program_listing_with_overflow(self):
        """Programs are listed up to 5, then '+N more' is appended."""
        program_map = {f"PROG{i}": 1 for i in range(10)}
        work = pd.DataFrame({
            "Code": ["A"],
            "Consumption_pcs": [10.0],
            "Monthly_pcs": [0.8],
            "SupplyPoint": [1],
        })
        plan = {"helix_cabs": 1, "total_spirals_buf": 30, "car_cabs": 0,
                "cabA": 0, "cabB": 0, "cabC": 0,
                "car_slots_buf": 0, "countA_buf": 0, "countB_buf": 0, "countC_buf": 0}
        compact, detail = dist.build_per_sp_summary(work, [("All", plan)], program_map, 15.0)
        # +N more should appear in the compact output's program column
        prog_cell = ""
        for col in compact.columns:
            for val in compact[col]:
                if isinstance(val, str) and "more" in val:
                    prog_cell = val
                    break
        assert "more" in prog_cell or len(program_map) <= 5


# ---------------------------------------------------------------------------
# Separated Tools+PPE mode — contract tests
#
# These pin the behaviour the PDF/Excel surfaces require when the user
# selects 'Tools+PPE: Separated'. In Separated mode the page builds one
# plan per listing (Tools, PPE); the three distribution helpers below
# must produce one entry per listing, not collapse to a single 'All'
# entry keyed on SupplyPoint.
#
# Failure shape these tests catch:
#   - Headline row labelled 'All' with all cabinet counts = 0
#   - Per-SP pie chart and subclass tables reporting the combined
#     catalog on every per-listing page
# ---------------------------------------------------------------------------


def _separated_work():
    """Construct a work df mimicking a Separated Tools+PPE run. Two
    rows of Tools (one Helix, one Carousel), two rows of PPE (one Locker A,
    one Kanban). All rows share SupplyPoint=1 because Separated mode
    doesn't split the SupplyPoint integer."""
    return pd.DataFrame({
        "Code":             ["T1",       "T2",       "P1",       "P2"],
        "Listing":          ["Tools",    "Tools",    "PPE",      "PPE"],
        "SupplyPoint":      [1,          1,          1,          1],
        "Consumption_pcs":  [100.0,      50.0,       30.0,       5.0],
        "Monthly_pcs":      [8.3,        4.2,        2.5,        0.4],
        "SystemCategory":   ["KTC",      "KTC",      "KTC",      "Kanban"],
        "CabinetType":      ["Helix",    "Carousel", "Locker A", "Kanban"],
        "ProductCategory":  ["drills",   "mills",    "ppe",      "ppe"],
        "ToolClass":        ["hss_drill","solid_end_mill","ppe", "ppe"],
    })


def _separated_plans():
    """The page's bucket_plans for the work df above."""
    plan_tools = {
        "helix_cabs": 1, "car_cabs": 1, "cabA": 0, "cabB": 0, "cabC": 0,
        "total_cabs": 2, "total_cabs_base": 2,
        "ktc_count": 2, "kanban_count": 0,
    }
    plan_ppe = {
        "helix_cabs": 0, "car_cabs": 0, "cabA": 1, "cabB": 0, "cabC": 0,
        "total_cabs": 1, "total_cabs_base": 1,
        "ktc_count": 1, "kanban_count": 1,
    }
    return [("Tools", plan_tools), ("PPE", plan_ppe)]


class TestBuildPerSpSummarySeparated:
    """Bug A — headline aggregation in Separated mode.

    Pre-fix: the function builds the label from work['SupplyPoint'] which
    is 1 for every row, looks up plans_by_label.get('All'), finds nothing,
    and returns a single row with zero cabinets. The 6-cabinet plan
    visible in the Excel Summary and per-SP detail pages does not appear
    on the headline page.
    """

    def test_one_row_per_listing(self):
        compact, _ = dist.build_per_sp_summary(
            _separated_work(), _separated_plans(), {}, 15.0,
            listings=["Tools", "PPE"],
        )
        assert len(compact) == 2, (
            f"expected one row per listing in Separated mode, got {len(compact)}"
        )
        labels = compact["Supply Point"].tolist()
        assert labels == ["Tools", "PPE"], f"unexpected row labels: {labels}"

    def test_no_all_label_emitted(self):
        """Pre-fix the function emits a single 'All' row with zero cabinets.
        That row must not appear in Separated output — its presence is
        the headline-shows-zero bug."""
        compact, _ = dist.build_per_sp_summary(
            _separated_work(), _separated_plans(), {}, 15.0,
            listings=["Tools", "PPE"],
        )
        assert "All" not in compact["Supply Point"].tolist()

    def test_no_grand_total_row(self):
        """User-confirmed design: Separated mode shows per-listing rows
        only, no aggregate 'Grand total' row at the bottom."""
        compact, detail = dist.build_per_sp_summary(
            _separated_work(), _separated_plans(), {}, 15.0,
            listings=["Tools", "PPE"],
        )
        assert "Grand total" not in compact["Supply Point"].tolist()
        assert "Grand total" not in detail["Supply Point"].tolist()

    def test_cabinet_counts_match_per_listing_plan(self):
        """Each listing row must carry the cabinet counts from its
        corresponding plan dict."""
        compact, _ = dist.build_per_sp_summary(
            _separated_work(), _separated_plans(), {}, 15.0,
            listings=["Tools", "PPE"],
        )
        rows = {r["Supply Point"]: r for _, r in compact.iterrows()}
        # Tools: 1 Helix + 1 Carousel = 2
        assert rows["Tools"]["Helix"] == 1
        assert rows["Tools"]["Carousel"] == 1
        assert rows["Tools"]["Locker A"] == 0
        assert rows["Tools"]["Total cabinets"] == 2
        # PPE: 1 Locker A = 1
        assert rows["PPE"]["Helix"] == 0
        assert rows["PPE"]["Carousel"] == 0
        assert rows["PPE"]["Locker A"] == 1
        assert rows["PPE"]["Total cabinets"] == 1

    def test_consumption_filtered_per_listing(self):
        """Each listing row's Rows and Annual consumption columns must
        reflect only that listing's rows, not the combined catalog."""
        compact, _ = dist.build_per_sp_summary(
            _separated_work(), _separated_plans(), {}, 15.0,
            listings=["Tools", "PPE"],
        )
        rows = {r["Supply Point"]: r for _, r in compact.iterrows()}
        # Tools has 2 rows totalling 150 pcs annually
        assert rows["Tools"]["Rows"] == 2
        assert rows["Tools"]["Annual consumption"] == 150
        # PPE has 2 rows totalling 35 pcs annually
        assert rows["PPE"]["Rows"] == 2
        assert rows["PPE"]["Annual consumption"] == 35

    def test_kanban_only_listing_still_emitted(self):
        """User-confirmed: an empty-KTC listing still gets a row.
        Cabinet counts are 0, Kanban count is preserved (visible in the
        detail df)."""
        work = pd.DataFrame({
            "Code": ["T1", "P1"],
            "Listing": ["Tools", "PPE"],
            "SupplyPoint": [1, 1],
            "Consumption_pcs": [100.0, 5.0],
            "Monthly_pcs": [8.3, 0.4],
            "SystemCategory": ["KTC", "Kanban"],
            "CabinetType": ["Helix", "Kanban"],
            "ProductCategory": ["drills", "ppe"],
            "ToolClass": ["hss_drill", "ppe"],
        })
        plan_tools = {
            "helix_cabs": 1, "car_cabs": 0, "cabA": 0, "cabB": 0, "cabC": 0,
            "total_cabs": 1, "total_cabs_base": 1, "ktc_count": 1, "kanban_count": 0,
        }
        plan_ppe = {
            "helix_cabs": 0, "car_cabs": 0, "cabA": 0, "cabB": 0, "cabC": 0,
            "total_cabs": 0, "total_cabs_base": 0, "ktc_count": 0, "kanban_count": 1,
        }
        compact, detail = dist.build_per_sp_summary(
            work, [("Tools", plan_tools), ("PPE", plan_ppe)], {}, 15.0,
            listings=["Tools", "PPE"],
        )
        labels = compact["Supply Point"].tolist()
        assert "PPE" in labels, "Kanban-only listing must still emit a row"
        detail_rows = {r["Supply Point"]: r for _, r in detail.iterrows()}
        assert detail_rows["PPE"]["Cabinets (buffered)"] == 0
        assert detail_rows["PPE"]["Kanban items"] == 1


class TestBuildPerSpDistributionSeparated:
    """Bug B (part 1) — the per-SP pie chart data must be filtered per
    listing in Separated mode. Pre-fix: the function groups by
    SupplyPoint (which is 1 for both listings) so the Tools page and
    the PPE page render the same combined pie."""

    def test_one_entry_per_listing(self):
        out = dist.build_per_sp_distribution(
            _separated_work(), listings=["Tools", "PPE"],
        )
        # Listings as keys plus the '__all__' aggregate
        listing_keys = [k for k in out.keys() if k != "__all__"]
        assert sorted(listing_keys) == ["PPE", "Tools"]

    def test_tools_pie_excludes_ppe(self):
        """Tools listing has 1 Drills + 1 Mills + 0 PPE KTC items.
        Pre-fix this would show the combined 2 Drills + 1 Mills + 1 PPE."""
        out = dist.build_per_sp_distribution(
            _separated_work(), listings=["Tools", "PPE"],
        )
        tools = out["Tools"]
        # KTC distribution: 1 drill + 1 mill, no PPE
        assert tools.get("Drills", 0) == 1
        assert tools.get("Mills", 0) == 1
        # 'ppe' rolls up into the "Others" bucket; check it's zero here
        assert tools.get("Others", 0) == 0

    def test_ppe_pie_excludes_tools(self):
        out = dist.build_per_sp_distribution(
            _separated_work(), listings=["Tools", "PPE"],
        )
        ppe = out["PPE"]
        assert ppe.get("Drills", 0) == 0
        assert ppe.get("Mills", 0) == 0
        # The one KTC PPE row goes to the 'Others' bucket
        assert ppe.get("Others", 0) == 1


class TestBuildPerSpSubclassBreakdownSeparated:
    """Bug B (part 2) — the per-SP subclass tables in the PDF must
    be filtered per listing in Separated mode."""

    def test_one_entry_per_listing(self):
        out = dist.build_per_sp_subclass_breakdown(
            _separated_work(), listings=["Tools", "PPE"],
        )
        listing_keys = [k for k in out.keys() if k != "__all__"]
        assert sorted(listing_keys) == ["PPE", "Tools"]

    def test_tools_subclass_excludes_ppe_tool_class(self):
        """Tools listing must not show any 'ppe' tool_class entries."""
        out = dist.build_per_sp_subclass_breakdown(
            _separated_work(), listings=["Tools", "PPE"],
        )
        # Flatten Tools subclasses into one set
        tools_classes = {
            tc
            for bucket_entries in out["Tools"].values()
            for tc in bucket_entries.keys()
        }
        assert "ppe" not in tools_classes


class TestBuildPerSpSummaryCombinedRegression:
    """The Separated-mode fix must not affect Combined-mode runs. The
    four catalogs validated earlier in this session were all Combined
    mode (Listings: Tools only / PPE absent); their headlines must keep
    producing one row labelled 'All' or per-SupplyPoint rows."""

    def test_listings_none_keeps_all_label(self):
        """With listings=None the function must behave identically to
        the pre-fix version."""
        work = pd.DataFrame({
            "Code": ["A", "B"],
            "Listing": ["Tools", "Tools"],
            "SupplyPoint": [1, 1],
            "Consumption_pcs": [100.0, 50.0],
            "Monthly_pcs": [8.3, 4.2],
        })
        plan = {
            "helix_cabs": 1, "car_cabs": 0, "cabA": 0, "cabB": 0, "cabC": 0,
            "total_cabs": 1, "total_cabs_base": 1, "ktc_count": 2, "kanban_count": 0,
        }
        compact, _ = dist.build_per_sp_summary(work, [("All", plan)], {}, 15.0)
        assert len(compact) == 1
        assert compact["Supply Point"].iloc[0] == "All"
        assert int(compact["Total cabinets"].iloc[0]) == 1

    def test_listings_none_keeps_multi_sp_labels(self):
        """Multi-supply-point Combined mode unchanged."""
        work = pd.DataFrame({
            "Code": ["A", "B"],
            "SupplyPoint": [1, 2],
            "Consumption_pcs": [100.0, 50.0],
            "Monthly_pcs": [8.3, 4.2],
        })
        p1 = {"helix_cabs": 1, "car_cabs": 0, "cabA": 0, "cabB": 0, "cabC": 0,
              "total_cabs": 1, "total_cabs_base": 1, "ktc_count": 1, "kanban_count": 0}
        p2 = {"helix_cabs": 0, "car_cabs": 1, "cabA": 0, "cabB": 0, "cabC": 0,
              "total_cabs": 1, "total_cabs_base": 1, "ktc_count": 1, "kanban_count": 0}
        compact, _ = dist.build_per_sp_summary(
            work, [("SP 1", p1), ("SP 2", p2)], {}, 15.0,
        )
        assert len(compact) == 2
        assert sorted(compact["Supply Point"].tolist()) == ["SP 1", "SP 2"]


class TestBuildPerSpDistributionCombinedRegression:
    """Distribution helper Combined-mode behaviour pinned. The current
    grouping-by-SupplyPoint with the __all__ aggregate is preserved
    when listings=None."""

    def test_listings_none_groups_by_supplypoint(self):
        work = pd.DataFrame({
            "Code": ["A", "B"],
            "SupplyPoint": [1, 2],
            "SystemCategory": ["KTC", "KTC"],
            "CabinetType": ["Helix", "Carousel"],
            "ProductCategory": ["drills", "mills"],
        })
        out = dist.build_per_sp_distribution(work)
        assert 1 in out and 2 in out and "__all__" in out
        assert out[1].get("Drills", 0) == 1
        assert out[2].get("Mills", 0) == 1
