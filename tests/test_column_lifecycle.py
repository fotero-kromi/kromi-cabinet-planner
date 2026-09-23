"""Column-lifecycle tests — every canonical column mapping must be proven
to survive the input → dedup → downstream-consumer pipeline.

Background
----------
The Kromi planner's page applies a rename map that translates source headers
to canonical names (Article SAP → Code, WZBez → Description, etc.), then
runs :func:`engine.preprocessing.prepare_planning_base` which deduplicates
rows. The dedup uses ``DataFrame.groupby(...).agg(<dict>)`` and *only*
columns named in the agg dict survive — anything else is silently dropped.

This file pins the contract that every canonical column the planner
documents either (a) is a dedup key, or (b) is in the agg dict, or
(c) is explicitly preserved through dedup. New columns added to the rename
map must add a corresponding test class below — that is the development
discipline this file enforces.

Each test class covers ONE canonical column and proves:

  * the column survives dedup,
  * the aggregator behaves as documented (sum, first-non-empty, max, ...),
  * the column being absent does not break preprocessing.

Failures here mean a downstream consumer (classifier, router, fit-check,
overrides scope, distribution panel) will silently no-op. That is the
exact failure mode the v33.12 fit-check fix closed; the goal is to make
that class of bug fail at test time, not in a customer-facing run.
"""

from __future__ import annotations

import pandas as pd

from engine import preprocessing as pp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED = {
    "Code", "Description", "Description_2", "Consumption_pcs",
    "PackUnits", "ProductCategory", "SizeCategory", "Year",
}


def _minimal_required(n: int, code: str = "A") -> pd.DataFrame:
    """Two identical-Code rows so dedup activates. Caller adds the column
    under test on top of this baseline."""
    return pd.DataFrame({
        "Code": [code] * n,
        "Description": ["x"] * n,
        "Description_2": [""] * n,
        "Consumption_pcs": [1.0] * n,
        "PackUnits": [1.0] * n,
        "ProductCategory": [""] * n,
        "SizeCategory": [""] * n,
        "Year": [2025] * n,
    })


def _run_dedup(df: pd.DataFrame, dedup_mode: str = "code"):
    """Standardized invocation used across the file."""
    return pp.prepare_planning_base(df, dedup_mode, "all_years", True)


# ---------------------------------------------------------------------------
# Per-column lifecycle contracts
# ---------------------------------------------------------------------------

class TestCode:
    """Code is the primary dedup key. Two rows with the same Code must
    collapse to one. Two different Codes must stay distinct."""

    def test_same_code_collapses(self):
        df = _minimal_required(2, code="A")
        out, _ = _run_dedup(df)
        assert len(out) == 1
        assert out["Code"].iloc[0] == "A"

    def test_different_codes_stay(self):
        df = pd.concat([_minimal_required(1, "A"), _minimal_required(1, "B")], ignore_index=True)
        out, _ = _run_dedup(df)
        assert sorted(out["Code"].tolist()) == ["A", "B"]


class TestDescription:
    """Description survives dedup via first_nonempty aggregation. Empty
    strings are skipped so a row with a real description wins over a
    blank row carrying the same Code."""

    def test_first_nonempty_wins(self):
        df = _minimal_required(2)
        df.loc[0, "Description"] = ""
        df.loc[1, "Description"] = "real description"
        out, _ = _run_dedup(df)
        assert out["Description"].iloc[0] == "real description"

    def test_survives_dedup(self):
        df = _minimal_required(2)
        out, _ = _run_dedup(df)
        assert "Description" in out.columns


class TestDescription2:
    """Description_2 has the same first_nonempty contract as Description.
    Used downstream by the classifier when the 'Use Description_2' toggle
    is on."""

    def test_first_nonempty_wins(self):
        df = _minimal_required(2)
        df.loc[0, "Description_2"] = ""
        df.loc[1, "Description_2"] = "secondary text"
        out, _ = _run_dedup(df)
        assert out["Description_2"].iloc[0] == "secondary text"

    def test_survives_dedup(self):
        df = _minimal_required(2)
        out, _ = _run_dedup(df)
        assert "Description_2" in out.columns


class TestConsumptionPcs:
    """Consumption_pcs sums across deduplicated rows. Two rows with the
    same Code and 10 + 20 pcs collapse to one row with 30 pcs."""

    def test_sums_across_duplicates(self):
        df = _minimal_required(2)
        df.loc[0, "Consumption_pcs"] = 10.0
        df.loc[1, "Consumption_pcs"] = 20.0
        out, _ = _run_dedup(df)
        assert len(out) == 1
        assert out["Consumption_pcs"].iloc[0] == 30.0

    def test_nan_treated_as_zero(self):
        df = _minimal_required(2)
        df.loc[0, "Consumption_pcs"] = float("nan")
        df.loc[1, "Consumption_pcs"] = 15.0
        out, _ = _run_dedup(df)
        # pandas .sum() default skips NaN; the remaining 15 must survive.
        assert out["Consumption_pcs"].iloc[0] == 15.0


class TestPackUnits:
    """PackUnits picks the first positive value across duplicates. Zero
    and NaN are skipped (preserving the planner's 'positive value wins'
    rule). A row that incorrectly has PackUnits=1 (the placeholder) does
    not silently overwrite a row carrying the real pack size."""

    def test_first_positive_wins_over_zero(self):
        df = _minimal_required(2)
        df.loc[0, "PackUnits"] = 0.0
        df.loc[1, "PackUnits"] = 50.0
        out, _ = _run_dedup(df)
        assert out["PackUnits"].iloc[0] == 50.0

    def test_survives_dedup(self):
        df = _minimal_required(2)
        out, _ = _run_dedup(df)
        assert "PackUnits" in out.columns


class TestProductCategory:
    """ProductCategory survives dedup via first_valid_product_category.
    The aggregator skips blanks and unknown values, so a valid label
    overwrites an empty one."""

    def test_valid_wins_over_blank(self):
        df = _minimal_required(2)
        df.loc[0, "ProductCategory"] = ""
        df.loc[1, "ProductCategory"] = "drills"
        out, _ = _run_dedup(df)
        assert out["ProductCategory"].iloc[0] == "drills"


class TestSizeCategory:
    """SizeCategory survives dedup via first_valid_size. Blanks lose to
    real size labels."""

    def test_valid_wins_over_blank(self):
        df = _minimal_required(2)
        df.loc[0, "SizeCategory"] = ""
        df.loc[1, "SizeCategory"] = "L"
        out, _ = _run_dedup(df)
        assert out["SizeCategory"].iloc[0] == "L"


class TestYear:
    """Year survives dedup via .max(), so the most recent year wins
    when two rows with the same Code carry different years."""

    def test_max_year_wins(self):
        df = _minimal_required(2)
        df.loc[0, "Year"] = 2023
        df.loc[1, "Year"] = 2025
        out, _ = _run_dedup(df)
        assert out["Year"].iloc[0] == 2025


class TestSupplierCode:
    """SupplierCode is added to the dedup key when dedup_mode='code+supplier'.
    Two rows with same Code but different SupplierCode then stay distinct."""

    def test_in_key_keeps_distinct(self):
        df = _minimal_required(2)
        df["SupplierCode"] = ["s1", "s2"]
        out, _ = _run_dedup(df, dedup_mode="code+supplier")
        assert len(out) == 2

    def test_code_only_collapses(self):
        df = _minimal_required(2)
        df["SupplierCode"] = ["s1", "s2"]
        out, _ = _run_dedup(df, dedup_mode="code")
        # SupplierCode is no longer in the key; the two rows collapse.
        # SupplierCode is not in the agg dict; the column is dropped.
        # (Documenting current behaviour — if this changes, downstream
        # code that reads SupplierCode must be checked.)
        assert len(out) == 1


class TestProgram:
    """Program is conditionally aggregated into a comma-joined list of
    distinct values, so a single deduplicated row carries every programme
    that contributed to it. This drives the 'programmes (first 5)' column
    on the headline PDF."""

    def test_concat_distinct_programmes(self):
        df = _minimal_required(2)
        df["Program"] = ["PROG_A", "PROG_B"]
        out, _ = _run_dedup(df)
        # Order is sorted set so deterministic
        assert out["Program"].iloc[0] == "PROG_A, PROG_B"

    def test_absent_program_does_not_break(self):
        df = _minimal_required(2)
        # No Program column at all
        out, _ = _run_dedup(df)
        assert "Program" not in out.columns


class TestSite:
    """Site is part of the dedup key (HMA-3): the same Code at different
    sites stays as distinct rows so per-site consumption is never merged
    and misattributed. When Site has a single value (or is absent) dedup
    behaves as before and the column is preserved."""

    def test_survives_dedup_when_present(self):
        df = _minimal_required(2)
        df["Site"] = ["PLANT_1", "PLANT_1"]
        out, _ = _run_dedup(df)
        assert "Site" in out.columns
        assert out["Site"].iloc[0] == "PLANT_1"

    def test_absent_site_does_not_break(self):
        df = _minimal_required(2)
        out, _ = _run_dedup(df)
        # When Site isn't mapped, dedup must not require it.
        assert len(out) == 1

    def test_distinct_sites_kept_separate(self):
        # Site-aware dedup (HMA-3): Site is part of the dedup key, so the same
        # Code at different sites is NOT merged. A blank site is treated as its
        # own (explicit) group rather than inferred to belong to a named site,
        # so cross-site consumption is never silently misattributed.
        df = _minimal_required(2)
        df["Site"] = ["", "PLANT_42"]
        out, _ = _run_dedup(df)
        assert len(out) == 2
        assert set(out["Site"]) == {"", "PLANT_42"}


class TestPackageDimensions:
    """PackageDimensions is preserved through dedup via first_nonempty
    (v33.12 fix). This is the input to the optional dimensional
    fit-check (engine.fitting). Before the fix, the column was dropped
    by dedup so the fit-check guard ``if "PackageDimensions" in
    work.columns`` evaluated false and the whole block silently no-op'd
    — no error, no warning, no Fit_* columns in the output."""

    def test_survives_dedup_when_present(self):
        df = _minimal_required(2)
        df["PackageDimensions"] = ["Ø 16 x 88 mm", "Ø 16 x 88 mm"]
        out, _ = _run_dedup(df)
        assert "PackageDimensions" in out.columns
        assert out["PackageDimensions"].iloc[0] == "Ø 16 x 88 mm"

    def test_absent_dimensions_does_not_break(self):
        """When no dimensions column is mapped, preprocessing must still
        run cleanly. This is the common path for catalogs without
        package data."""
        df = _minimal_required(2)
        out, _ = _run_dedup(df)
        assert len(out) == 1

    def test_first_nonempty_wins(self):
        df = _minimal_required(2)
        df["PackageDimensions"] = ["", "Ø 30 x 120 mm"]
        out, _ = _run_dedup(df)
        assert out["PackageDimensions"].iloc[0] == "Ø 30 x 120 mm"


class TestListing:
    """Listing is added to the dedup key when present. Same Code in two
    different listings (Tools vs PPE) stays as two distinct rows."""

    def test_in_key_keeps_listings_distinct(self):
        df = _minimal_required(2)
        df["Listing"] = ["Tools", "PPE"]
        out, _ = _run_dedup(df)
        assert len(out) == 2
        assert set(out["Listing"]) == {"Tools", "PPE"}


class TestSupplyPoint:
    """SupplyPoint is added to the dedup key when present, so an item
    appearing at two supply points stays as two distinct rows for
    per-SP planning."""

    def test_in_key_keeps_sps_distinct(self):
        df = _minimal_required(2)
        df["SupplyPoint"] = ["SP_1", "SP_2"]
        out, _ = _run_dedup(df)
        assert len(out) == 2


# ---------------------------------------------------------------------------
# Combined fixture — every column at once
# ---------------------------------------------------------------------------

class TestAllColumnsTogether:
    """A single catalog carrying every documented canonical column,
    deduplicated, must emerge with every column intact. This is the
    'one test the v33.12 fit-check bug would have failed' guard: if any
    optional column ever stops surviving dedup, this case fails fast."""

    def _full_df(self):
        return pd.DataFrame({
            # required
            "Code": ["A", "A"],
            "Description": ["the item", "the item"],
            "Description_2": ["", "secondary"],
            "Consumption_pcs": [10.0, 20.0],
            # PackUnits uses 'first positive' aggregation: 0 is skipped, the
            # first strictly-positive value wins. See TestPackUnits above.
            "PackUnits": [0.0, 50.0],
            "ProductCategory": ["", "drills"],
            "SizeCategory": ["", "M"],
            "Year": [2024, 2025],
            # optional, all mapped
            "SupplierCode": ["s1", "s1"],
            "Program": ["P1", "P2"],
            "Site": ["PLANT_1", "PLANT_1"],
            "PackageDimensions": ["", "Ø 16 x 88 mm"],
            "Listing": ["Tools", "Tools"],
        })

    def test_all_columns_present_after_dedup(self):
        df = self._full_df()
        out, _ = _run_dedup(df, dedup_mode="code")
        assert len(out) == 1
        expected = {
            "Code", "Description", "Description_2", "Consumption_pcs",
            "PackUnits", "ProductCategory", "SizeCategory", "Year",
            "Program", "Site", "PackageDimensions", "Listing",
        }
        missing = expected - set(out.columns)
        assert not missing, f"columns dropped by dedup: {missing}"

    def test_aggregator_semantics_combined(self):
        """End-to-end aggregator check: every column emerges with the
        value the per-column tests above expect."""
        df = self._full_df()
        out, _ = _run_dedup(df, dedup_mode="code")
        row = out.iloc[0]
        assert row["Consumption_pcs"] == 30.0           # sum
        assert row["Description"] == "the item"          # first_nonempty
        assert row["Description_2"] == "secondary"       # first_nonempty
        assert row["PackUnits"] == 50.0                  # first positive
        assert row["ProductCategory"] == "drills"        # first valid
        assert row["SizeCategory"] == "M"                # first valid
        assert row["Year"] == 2025                       # max
        assert row["Program"] == "P1, P2"                # joined distinct
        assert row["Site"] == "PLANT_1"                  # first_nonempty
        assert row["PackageDimensions"] == "Ø 16 x 88 mm"  # first_nonempty


# ---------------------------------------------------------------------------
# Discipline / template guard
# ---------------------------------------------------------------------------

class TestColumnLifecycleDiscipline:
    """If a new canonical column is added to the preprocessing agg_spec or
    the page's rename_map, a dedicated test class should be added above.
    This guard simply enumerates the column-test classes currently in this
    file so adding/removing one is a visible diff in code review."""

    EXPECTED_COLUMN_TESTS = {
        # required (cannot be unmapped)
        "TestCode", "TestDescription", "TestDescription2",
        "TestConsumptionPcs", "TestPackUnits", "TestProductCategory",
        "TestSizeCategory", "TestYear",
        # optional but commonly mapped
        "TestSupplierCode", "TestProgram", "TestSite",
        "TestPackageDimensions", "TestListing", "TestSupplyPoint",
    }

    def test_every_documented_column_has_a_test_class(self):
        import sys
        module = sys.modules[__name__]
        present = {name for name in dir(module) if name.startswith("Test")}
        missing = self.EXPECTED_COLUMN_TESTS - present
        assert not missing, (
            f"column-lifecycle test classes missing: {missing}. "
            "If you removed one intentionally, update EXPECTED_COLUMN_TESTS."
        )
