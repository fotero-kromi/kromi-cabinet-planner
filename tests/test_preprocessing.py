"""Tests for engine.preprocessing — 1 function (prepare_planning_base)."""

import pandas as pd
import pytest

from engine import preprocessing as pp


class TestNoFutureWarning:
    """The stale-latest-year diagnostic (B4) runs groupby.apply; it must not
    emit the pandas 'apply operated on the grouping columns' FutureWarning.
    Reproduces the deferred warning seen on pandas >= 2.2 by promoting it to an
    error around a dedup run that exercises the stale-year path."""

    def _stale_year_df(self):
        # Code A: latest year (2025) has blank ProductCategory/SizeCategory while
        # an earlier year (2024) is filled -> exercises _n_stale_latest.
        return pd.DataFrame({
            "Code": ["A", "A", "B"],
            "SupplierCode": ["s1", "s1", "s2"],
            "Listing": ["Tools", "Tools", "Tools"],
            "Description": ["a", "a", "b"],
            "Description_2": ["", "", ""],
            "Consumption_pcs": [10.0, 12.0, 5.0],
            "PackUnits": [1.0, 1.0, 1.0],
            "ProductCategory": ["drills", "", "mills"],
            "SizeCategory": ["M", "", "S"],
            "Year": [2024, 2025, 2025],
        })

    def test_dedup_code_no_future_warning(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            _out, info = pp.prepare_planning_base(self._stale_year_df(), "code", "all_rows", True)
        # the diagnostic still detects the stale group
        assert info["stale_latest_year_groups"]["ProductCategory"] == 1
        assert info["stale_latest_year_groups"]["SizeCategory"] == 1


def _make_test_df(with_year=True):
    """Helper: create a base test DataFrame with optional Year column."""
    df = pd.DataFrame({
        "Code": ["A", "A", "B", "B", "C"],
        "SupplierCode": ["s1", "s1", "s2", "s2", "s3"],
        "Listing": ["Tools", "Tools", "Tools", "PPE", "Tools"],
        "Description": ["a", "a", "b", "b", "c"],
        "Description_2": ["", "", "", "x", ""],
        "Consumption_pcs": [10.0, 20.0, 5.0, 8.0, 3.0],
        "PackUnits": [1.0, 1.0, 10.0, 1.0, 0.0],
        "ProductCategory": ["drills", "drills", "mills", "ppe", "other"],
        "SizeCategory": ["S", "M", "L", "M", ""],
    })
    if with_year:
        df["Year"] = [2023, 2024, 2023, 2024, 2024]
    return df


# ---- dedup_mode = none ----

class TestDedupNone:
    def test_all_rows_preserved(self):
        df = _make_test_df()
        out, info = pp.prepare_planning_base(df, "none", "all_years", False)
        assert len(out) == 5
        assert info["rows_before"] == 5
        assert info["rows_after_dedup"] == 5
        assert info["dedup_groups"] is None


# ---- year filtering ----

class TestYearFiltering:
    def test_latest_year_only_filters(self):
        df = _make_test_df()
        out, info = pp.prepare_planning_base(df, "none", "latest_year_only", True)
        # Year=2024 rows: A(2024), B(2024), C(2024) = 3
        # Year=2023 rows: A(2023), B(2023) — dropped
        # No NaN years in this fixture
        assert len(out) == 3
        assert info["latest_year_used"] == 2024

    def test_nan_year_preserved(self):
        df = _make_test_df()
        df["Year"] = [2024, 2024, float("nan"), float("nan"), 2023]
        out, info = pp.prepare_planning_base(df, "none", "latest_year_only", True)
        # 2024 + NaN rows kept: 4
        assert len(out) == 4

    def test_no_valid_years(self):
        df = _make_test_df()
        df["Year"] = [float("nan")] * 5
        out, info = pp.prepare_planning_base(df, "none", "latest_year_only", True)
        # No filtering happens; latest_year_used stays None
        assert len(out) == 5
        assert info["latest_year_used"] is None

    def test_has_year_false_skips_filter(self):
        df = _make_test_df()
        out, info = pp.prepare_planning_base(df, "none", "latest_year_only", False)
        # has_year=False → skip filter, all rows kept
        assert len(out) == 5
        assert info["latest_year_used"] is None


# ---- dedup_mode = code ----

class TestDedupCode:
    def test_listing_included_in_key(self):
        df = _make_test_df()
        out, info = pp.prepare_planning_base(df, "code", "all_years", False)
        # Listing splits B/Tools and B/PPE
        # Result: A/Tools, B/Tools, B/PPE, C/Tools = 4
        assert len(out) == 4

    def test_consumption_summed(self):
        df = _make_test_df()
        out, info = pp.prepare_planning_base(df, "code", "all_years", False)
        # A has 2 rows: 10 + 20 = 30
        a_row = out[(out["Code"] == "A") & (out["Listing"] == "Tools")]
        assert float(a_row["Consumption_pcs"].iloc[0]) == 30.0

    def test_dedup_groups_set(self):
        df = _make_test_df()
        out, info = pp.prepare_planning_base(df, "code", "all_years", False)
        assert info["dedup_groups"] == 4


# ---- dedup_mode = code_and_supplier ----

class TestDedupCodeAndSupplier:
    def test_supplier_in_key(self):
        df = pd.DataFrame({
            "Code": ["A", "A"],
            "SupplierCode": ["s1", "s2"],  # different suppliers
            "Listing": ["Tools", "Tools"],
            "Description": ["a"] * 2, "Description_2": [""] * 2,
            "Consumption_pcs": [10.0, 20.0],
            "PackUnits": [1.0] * 2,
            "ProductCategory": ["drills"] * 2,
            "SizeCategory": ["S"] * 2,
            "Year": [2024] * 2,
        })
        out, info = pp.prepare_planning_base(df, "code_and_supplier", "all_years", False)
        # Different suppliers → 2 separate groups
        assert len(out) == 2


# ---- Aggregation behavior ----

class TestAggregation:
    def test_first_nonempty_description(self):
        df = pd.DataFrame({
            "Code": ["A"] * 3,
            "Listing": ["Tools"] * 3,
            "Description": ["", "first non-empty", "second"],
            "Description_2": ["", "", ""],
            "Consumption_pcs": [10.0, 20.0, 30.0],
            "PackUnits": [1.0] * 3,
            "ProductCategory": ["drills"] * 3,
            "SizeCategory": ["S"] * 3,
            "Year": [2024] * 3,
        })
        out, info = pp.prepare_planning_base(df, "code", "all_years", False)
        # Selection is now deterministic (HMA-2): with Year tied, the highest-
        # consumption row wins, and first_nonempty still skips the empty value.
        assert out.iloc[0]["Description"] == "second"

    def test_first_positive_pack_units(self):
        df = pd.DataFrame({
            "Code": ["A"] * 4,
            "Listing": ["Tools"] * 4,
            "Description": ["a"] * 4, "Description_2": [""] * 4,
            "Consumption_pcs": [10.0] * 4,
            "PackUnits": [0.0, 0.0, 5.0, 10.0],  # first POSITIVE = 5
            "ProductCategory": ["drills"] * 4,
            "SizeCategory": ["S"] * 4,
            "Year": [2024] * 4,
        })
        out, info = pp.prepare_planning_base(df, "code", "all_years", False)
        assert float(out.iloc[0]["PackUnits"]) == 5.0

    def test_first_valid_product_category(self):
        df = pd.DataFrame({
            "Code": ["A"] * 4,
            "Listing": ["Tools"] * 4,
            "Description": ["a"] * 4, "Description_2": [""] * 4,
            "Consumption_pcs": [10.0] * 4,
            "PackUnits": [1.0] * 4,
            "ProductCategory": ["", "other", "drills", "mills"],
            "SizeCategory": ["S"] * 4,
            "Year": [2024] * 4,
        })
        out, info = pp.prepare_planning_base(df, "code", "all_years", False)
        # 'other' and '' are weak; first valid = 'drills'
        assert out.iloc[0]["ProductCategory"] == "drills"

    def test_first_valid_size(self):
        df = pd.DataFrame({
            "Code": ["A"] * 4,
            "Listing": ["Tools"] * 4,
            "Description": ["a"] * 4, "Description_2": [""] * 4,
            "Consumption_pcs": [10.0] * 4,
            "PackUnits": [1.0] * 4,
            "ProductCategory": ["drills"] * 4,
            "SizeCategory": ["", "GARBAGE", "M", "L"],
            "Year": [2024] * 4,
        })
        out, info = pp.prepare_planning_base(df, "code", "all_years", False)
        # Deterministic (HMA-2): all other fields tied, SizeCategory sorted
        # ascending, first_valid_size skips "" and "GARBAGE" -> "L".
        assert out.iloc[0]["SizeCategory"] == "L"

    def test_year_max(self):
        df = pd.DataFrame({
            "Code": ["A"] * 3,
            "Listing": ["Tools"] * 3,
            "Description": ["a"] * 3, "Description_2": [""] * 3,
            "Consumption_pcs": [10.0] * 3,
            "PackUnits": [1.0] * 3,
            "ProductCategory": ["drills"] * 3,
            "SizeCategory": ["S"] * 3,
            "Year": [2020, 2024, 2022],
        })
        out, info = pp.prepare_planning_base(df, "code", "all_years", False)
        assert int(out.iloc[0]["Year"]) == 2024


# ---- SupplyPoint in dedup key ----

class TestSupplyPointInKey:
    def test_sp_splits_same_code(self):
        df = pd.DataFrame({
            "Code": ["A"] * 4,
            "Listing": ["Tools"] * 4,
            "SupplyPoint": [1, 1, 2, 2],
            "Description": ["a"] * 4, "Description_2": [""] * 4,
            "Consumption_pcs": [10.0, 20.0, 30.0, 40.0],
            "PackUnits": [1.0] * 4,
            "ProductCategory": ["drills"] * 4,
            "SizeCategory": ["S"] * 4,
            "Year": [2024] * 4,
        })
        out, info = pp.prepare_planning_base(df, "code", "all_years", False)
        # Same Code, different SP → 2 groups
        assert len(out) == 2
        sp1_row = out[out["SupplyPoint"] == 1]
        sp2_row = out[out["SupplyPoint"] == 2]
        assert float(sp1_row["Consumption_pcs"].iloc[0]) == 30.0
        assert float(sp2_row["Consumption_pcs"].iloc[0]) == 70.0


# ---- Program column ----

class TestProgramColumn:
    def test_programs_joined(self):
        df = pd.DataFrame({
            "Code": ["A"] * 3,
            "Listing": ["Tools"] * 3,
            "Description": ["a"] * 3, "Description_2": [""] * 3,
            "Consumption_pcs": [10.0] * 3,
            "PackUnits": [1.0] * 3,
            "ProductCategory": ["drills"] * 3,
            "SizeCategory": ["S"] * 3,
            "Year": [2024] * 3,
            "Program": ["PROG1", "PROG2", "PROG1"],  # PROG1 repeated
        })
        out, info = pp.prepare_planning_base(df, "code", "all_years", False)
        prog = out.iloc[0]["Program"]
        assert "PROG1" in prog
        assert "PROG2" in prog
        # Unique + sorted = "PROG1, PROG2"
        assert prog == "PROG1, PROG2"

    def test_program_truncated_to_200_chars(self):
        df = pd.DataFrame({
            "Code": ["A"] * 20,
            "Listing": ["Tools"] * 20,
            "Description": ["a"] * 20, "Description_2": [""] * 20,
            "Consumption_pcs": [10.0] * 20,
            "PackUnits": [1.0] * 20,
            "ProductCategory": ["drills"] * 20,
            "SizeCategory": ["S"] * 20,
            "Year": [2024] * 20,
            "Program": [f"VERY_LONG_PROGRAM_NAME_{i:03d}" for i in range(20)],
        })
        out, info = pp.prepare_planning_base(df, "code", "all_years", False)
        assert len(out.iloc[0]["Program"]) <= 200


# ---- Edge cases ----

class TestEdgeCases:
    def test_single_row(self):
        df = pd.DataFrame({
            "Code": ["A"], "Listing": ["Tools"],
            "Description": ["x"], "Description_2": [""],
            "Consumption_pcs": [10.0], "PackUnits": [1.0],
            "ProductCategory": ["drills"], "SizeCategory": ["S"],
            "Year": [2024],
        })
        out, info = pp.prepare_planning_base(df, "code", "all_years", False)
        assert len(out) == 1
        assert info["dedup_groups"] == 1

    def test_empty_df_with_year(self):
        df = pd.DataFrame({
            "Code": [], "Listing": [], "Description": [], "Description_2": [],
            "Consumption_pcs": [], "PackUnits": [], "ProductCategory": [],
            "SizeCategory": [], "Year": [],
        })
        out, info = pp.prepare_planning_base(df, "none", "all_years", False)
        assert len(out) == 0
        assert info["rows_before"] == 0


class TestOptionalColumnsPreservedThroughDedup:
    """Optional source-mapped columns (PackageDimensions, Site) must survive
    the dedup groupby — otherwise downstream features that read them silently
    no-op."""

    def _df(self, extra_col_name, extra_col_value):
        # Two identical rows so dedup activates.
        return pd.DataFrame({
            "Code": ["A", "A"],
            "SupplierCode": ["s1", "s1"],
            "Description": ["t", "t"],
            "Description_2": ["", ""],
            "Consumption_pcs": [1.0, 2.0],
            "PackUnits": [1.0, 1.0],
            "ProductCategory": ["", ""],
            "SizeCategory": ["", ""],
            "Year": [2025, 2025],
            extra_col_name: [extra_col_value, extra_col_value],
        })

    def test_package_dimensions_preserved(self):
        df = self._df("PackageDimensions", "Ø 16 x 88 mm")
        out, _ = pp.prepare_planning_base(df, "code", "all_years", True)
        assert len(out) == 1
        assert "PackageDimensions" in out.columns
        assert out["PackageDimensions"].iloc[0] == "Ø 16 x 88 mm"

    def test_site_preserved(self):
        df = self._df("Site", "PLANT_42")
        out, _ = pp.prepare_planning_base(df, "code", "all_years", True)
        assert len(out) == 1
        assert "Site" in out.columns
        assert out["Site"].iloc[0] == "PLANT_42"

    def test_no_optional_columns_still_works(self):
        """Regression guard: adding the new agg_spec entries must not break
        the case where neither optional column is mapped."""
        df = pd.DataFrame({
            "Code": ["A", "A"], "SupplierCode": ["s1", "s1"],
            "Description": ["t", "t"], "Description_2": ["", ""],
            "Consumption_pcs": [1.0, 2.0], "PackUnits": [1.0, 1.0],
            "ProductCategory": ["", ""], "SizeCategory": ["", ""],
            "Year": [2025, 2025],
        })
        out, _ = pp.prepare_planning_base(df, "code", "all_years", True)
        assert len(out) == 1


# ---- optional-column survival through dedup (audit fixes) ----

class TestOptionalColumnSurvivalThroughDedup:
    """Columns the planner reads after dedup must not be dropped by the
    groupby().agg() — regression guard for the StdSpecial/SupplierCode/
    PackageDimensions/Site silent-drop bug."""

    def _df_with(self, extra_col):
        df = _make_test_df(with_year=True)
        df[extra_col] = ["Standard", "Standard", "Sonder", "Sonder", "Special"]
        return df

    @pytest.mark.parametrize("col", ["StdSpecial", "PackageDimensions", "Site"])
    def test_optional_column_survives_code_dedup(self, col):
        df = self._df_with(col)
        base, _ = pp.prepare_planning_base(df, dedup_mode="code",
                                           year_mode="Use all rows", has_year=True)
        assert col in base.columns

    def test_suppliercode_survives_code_dedup(self):
        df = _make_test_df(with_year=True)
        base, _ = pp.prepare_planning_base(df, dedup_mode="code",
                                           year_mode="Use all rows", has_year=True)
        assert "SupplierCode" in base.columns

    def test_suppliercode_survives_code_supplier_dedup(self):
        # SupplierCode is a dedup KEY here; it must still be present and not
        # cause an aggregation conflict.
        df = _make_test_df(with_year=True)
        base, _ = pp.prepare_planning_base(df, dedup_mode="code_supplier",
                                           year_mode="Use all rows", has_year=True)
        assert "SupplierCode" in base.columns

    def test_stdspecial_survives_code_supplier_dedup(self):
        df = self._df_with("StdSpecial")
        base, _ = pp.prepare_planning_base(df, dedup_mode="code_supplier",
                                           year_mode="Use all rows", has_year=True)
        assert "StdSpecial" in base.columns

    def test_dedup_without_year_column_does_not_crash(self):
        # agg_spec must not reference 'Year' when the frame has no Year column.
        df = _make_test_df(with_year=False)
        base, _ = pp.prepare_planning_base(df, dedup_mode="code",
                                           year_mode="Use all rows", has_year=False)
        assert len(base) > 0
        assert "Year" not in base.columns


# ---- year_mode hardening + dedup conflict detection (hidden-miscalc audit) ----

class TestYearModeHardening:
    def test_ui_label_still_filters(self):
        # Passing the UI label (not the internal value) must NOT silently skip.
        df = _make_test_df(with_year=True)
        base, info = pp.prepare_planning_base(
            df, dedup_mode="none", year_mode="Keep latest year only", has_year=True)
        assert info["latest_year_used"] == 2024

    def test_internal_value_filters(self):
        df = _make_test_df(with_year=True)
        base, info = pp.prepare_planning_base(
            df, dedup_mode="none", year_mode="latest_year_only", has_year=True)
        assert info["latest_year_used"] == 2024

    def test_all_rows_does_not_filter(self):
        df = _make_test_df(with_year=True)
        base, info = pp.prepare_planning_base(
            df, dedup_mode="none", year_mode="all_rows", has_year=True)
        assert info["latest_year_used"] is None


class TestDedupConflictDetection:
    def test_conflicting_category_flagged(self):
        df = pd.DataFrame({
            "Code": ["A", "A"], "SupplierCode": ["s", "s"], "Listing": ["Tools", "Tools"],
            "Description": ["d", "d"], "Description_2": ["", ""], "Consumption_pcs": [1.0, 2.0],
            "PackUnits": [1.0, 1.0], "ProductCategory": ["inserts", "drills"],
            "SizeCategory": ["S", "S"], "Year": [2024, 2025],
        })
        _, info = pp.prepare_planning_base(df, dedup_mode="code",
                                           year_mode="all_rows", has_year=True)
        assert info["dedup_conflict_groups"]["ProductCategory"] == 1

    def test_conflicting_packunits_flagged(self):
        df = pd.DataFrame({
            "Code": ["A", "A"], "SupplierCode": ["s", "s"], "Listing": ["Tools", "Tools"],
            "Description": ["d", "d"], "Description_2": ["", ""], "Consumption_pcs": [1.0, 2.0],
            "PackUnits": [5.0, 1.0], "ProductCategory": ["mills", "mills"],
            "SizeCategory": ["S", "S"], "Year": [2024, 2025],
        })
        _, info = pp.prepare_planning_base(df, dedup_mode="code",
                                           year_mode="all_rows", has_year=True)
        assert info["dedup_conflict_groups"]["PackUnits"] == 1

    def test_no_conflict_when_consistent(self):
        df = pd.DataFrame({
            "Code": ["A", "A"], "SupplierCode": ["s", "s"], "Listing": ["Tools", "Tools"],
            "Description": ["d", "d"], "Description_2": ["", ""], "Consumption_pcs": [1.0, 2.0],
            "PackUnits": [5.0, 5.0], "ProductCategory": ["mills", "mills"],
            "SizeCategory": ["S", "S"], "Year": [2024, 2025],
        })
        _, info = pp.prepare_planning_base(df, dedup_mode="code",
                                           year_mode="all_rows", has_year=True)
        assert info["dedup_conflict_groups"] == {"ProductCategory": 0, "PackUnits": 0}


# ---- HMA-2: dedup determinism (order independence) ----

class TestDedupDeterminism:
    def _conflicting(self, order):
        rows = [
            {"Code":"A","SupplierCode":"s","Listing":"Tools","Description":"d","Description_2":"",
             "Consumption_pcs":10.0,"PackUnits":5.0,"ProductCategory":"inserts","SizeCategory":"S","Year":2024},
            {"Code":"A","SupplierCode":"s","Listing":"Tools","Description":"d","Description_2":"",
             "Consumption_pcs":10.0,"PackUnits":1.0,"ProductCategory":"drills","SizeCategory":"M","Year":2025},
        ]
        return pd.DataFrame(order(rows))

    def test_same_data_any_order_same_result(self):
        a, _ = pp.prepare_planning_base(self._conflicting(lambda r: r), "code", "all_rows", True)
        b, _ = pp.prepare_planning_base(self._conflicting(lambda r: r[::-1]), "code", "all_rows", True)
        ra, rb = a.iloc[0], b.iloc[0]
        assert ra["ProductCategory"] == rb["ProductCategory"]
        assert ra["PackUnits"] == rb["PackUnits"]
        assert ra["SizeCategory"] == rb["SizeCategory"]

    def test_latest_year_wins(self):
        # Conflicting attributes resolve to the most recent year deterministically.
        a, _ = pp.prepare_planning_base(self._conflicting(lambda r: r), "code", "all_rows", True)
        assert a.iloc[0]["ProductCategory"] == "drills"   # 2025 row
        assert a.iloc[0]["PackUnits"] == 1.0

    def test_consumption_still_conserved(self):
        a, _ = pp.prepare_planning_base(self._conflicting(lambda r: r), "code", "all_rows", True)
        assert a["Consumption_pcs"].iloc[0] == 20.0


# ---- HMA-3: site-aware dedup ----

class TestSiteAwareDedup:
    def _two_sites(self):
        return pd.DataFrame({
            "Code":["A","A"], "SupplierCode":["s","s"], "Listing":["Tools","Tools"],
            "Description":["d","d"], "Description_2":["",""], "Consumption_pcs":[10.0,30.0],
            "PackUnits":[1.0,1.0], "ProductCategory":["mills","mills"], "SizeCategory":["S","S"],
            "Year":[2025,2025], "Site":["Plant1","Plant2"],
        })

    def test_same_code_different_sites_kept_separate(self):
        base, _ = pp.prepare_planning_base(self._two_sites(), "code", "all_rows", True)
        assert len(base) == 2
        # per-site consumption preserved, not merged into one
        assert sorted(base["Consumption_pcs"].tolist()) == [10.0, 30.0]
        assert set(base["Site"]) == {"Plant1", "Plant2"}

    def test_single_site_still_dedups(self):
        df = self._two_sites(); df["Site"] = "Plant1"
        base, _ = pp.prepare_planning_base(df, "code", "all_rows", True)
        assert len(base) == 1
        assert base["Consumption_pcs"].iloc[0] == 40.0  # summed within the one site


# ---- C2: Site normalization before key construction ----

class TestSiteNormalization:
    def _df(self, sites):
        n = len(sites)
        return pd.DataFrame({
            "Code": ["A"] * n, "SupplierCode": ["s"] * n, "Listing": ["Tools"] * n,
            "Description": ["d"] * n, "Description_2": [""] * n,
            "Consumption_pcs": [10.0] * n, "PackUnits": [1.0] * n,
            "ProductCategory": ["mills"] * n, "SizeCategory": ["S"] * n,
            "Year": [2025] * n, "Site": sites,
        })

    def test_case_variants_merge(self):
        base, _ = pp.prepare_planning_base(self._df(["PlantA", "PLANTA", "planta"]), "code", "all_rows", True)
        assert len(base) == 1
        assert base["Consumption_pcs"].iloc[0] == 30.0

    def test_whitespace_variants_merge(self):
        base, _ = pp.prepare_planning_base(self._df(["PlantA", "PlantA ", "  PlantA"]), "code", "all_rows", True)
        assert len(base) == 1

    def test_numeric_site_codes_merge(self):
        # A site code stored as int 1, float 1.0, and string "1" is one site.
        base, _ = pp.prepare_planning_base(self._df([1, 1.0, "1"]), "code", "all_rows", True)
        assert len(base) == 1

    def test_distinct_sites_still_separate(self):
        base, _ = pp.prepare_planning_base(self._df(["P1", "P2"]), "code", "all_rows", True)
        assert len(base) == 2

    def test_original_casing_preserved_in_output(self):
        # Normalization affects the KEY only; the displayed Site keeps an
        # original (non-lowercased) value.
        base, _ = pp.prepare_planning_base(self._df(["PlantA", "PLANTA"]), "code", "all_rows", True)
        assert base["Site"].iloc[0] in ("PlantA", "PLANTA")

    def test_no_internal_key_column_leaks(self):
        base, _ = pp.prepare_planning_base(self._df(["P1", "P2"]), "code", "all_rows", True)
        assert not any(c.startswith("_site_key") for c in base.columns)


# ---- B4: stale latest-year metadata diagnostic (detection only) ----

class TestStaleLatestYearDiagnostic:
    def _df(self, cats, years):
        n = len(cats)
        return pd.DataFrame({
            "Code": ["A"] * n, "SupplierCode": ["s"] * n, "Listing": ["Tools"] * n,
            "Description": ["d"] * n, "Description_2": [""] * n,
            "Consumption_pcs": [10.0] * n, "PackUnits": [1.0] * n,
            "ProductCategory": cats, "SizeCategory": ["S"] * n, "Year": years,
        })

    def test_latest_blank_earlier_filled_flagged(self):
        _, info = pp.prepare_planning_base(self._df(["drills", ""], [2024, 2025]), "code", "all_rows", True)
        assert info["stale_latest_year_groups"]["ProductCategory"] == 1

    def test_latest_filled_not_flagged(self):
        _, info = pp.prepare_planning_base(self._df(["", "drills"], [2024, 2025]), "code", "all_rows", True)
        assert info["stale_latest_year_groups"]["ProductCategory"] == 0

    def test_all_filled_not_flagged(self):
        _, info = pp.prepare_planning_base(self._df(["drills", "drills"], [2024, 2025]), "code", "all_rows", True)
        assert info["stale_latest_year_groups"]["ProductCategory"] == 0

    def test_behavior_unchanged_value_still_retained(self):
        # Detection only: the earlier-year value is STILL retained (no behavior change).
        base, _ = pp.prepare_planning_base(self._df(["drills", ""], [2024, 2025]), "code", "all_rows", True)
        assert base["ProductCategory"].iloc[0] == "drills"

    def test_latest_only_mode_not_flagged(self):
        # In latest-year-only mode the earlier row is filtered out, so there is
        # no fallback and nothing to flag.
        _, info = pp.prepare_planning_base(self._df(["drills", ""], [2024, 2025]), "code", "latest_year_only", True)
        assert info["stale_latest_year_groups"]["ProductCategory"] == 0


# ---- empty input robustness (0 rows reaching the engine) ----

class TestEmptyInput:
    """A 0-row planning base can reach prepare_planning_base when an upload has
    headers but no data rows, or when the mapped Code column is entirely blank
    (all rows dropped upstream). The diagnostics must not crash on an empty
    groupby; they should report zero counts and return an empty base."""

    _COLS = ["Code", "SupplierCode", "Listing", "Description", "Description_2",
             "Consumption_pcs", "PackUnits", "ProductCategory", "SizeCategory", "Year"]

    def _empty(self):
        return pd.DataFrame({c: pd.Series(dtype="object") for c in self._COLS})

    def test_empty_with_year_dedup_code_does_not_crash(self):
        out, info = pp.prepare_planning_base(self._empty(), "code", "all_years", True)
        assert len(out) == 0
        assert info["rows_after_dedup"] == 0
        assert info["stale_latest_year_groups"]["ProductCategory"] == 0
        assert info["stale_latest_year_groups"]["SizeCategory"] == 0
        assert info["dedup_conflict_groups"]["ProductCategory"] == 0
        assert info["dedup_conflict_groups"]["PackUnits"] == 0

    def test_empty_with_year_dedup_code_supplier_does_not_crash(self):
        out, info = pp.prepare_planning_base(self._empty(), "code_supplier", "latest_year_only", True)
        assert len(out) == 0
        assert info["rows_after_dedup"] == 0

    def test_empty_no_dedup_does_not_crash(self):
        out, info = pp.prepare_planning_base(self._empty(), "none", "all_years", False)
        assert len(out) == 0

    def test_empty_consumption_conserved_zero(self):
        _, info = pp.prepare_planning_base(self._empty(), "code", "all_years", True)
        assert info["consumption_after_dedup"] == 0
        assert info["consumption_after_year"] == 0
