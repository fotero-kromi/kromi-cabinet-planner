"""Integration test for the optional dimensional fit-check page wiring.

These tests reproduce the exact per-row logic the planner page runs after
assigning CabinetType, verifying that:
  - when the package-dimensions column is mapped, each row gets a correct
    fit disposition (ok / misfit + suggestion / no-dims), and
  - non-KTC rows (Kanban / PPE) are skipped, and
  - the logic is purely additive (it only reads CabinetType + PackageDimensions
    and writes Fit_* fields).
"""

import pandas as pd

from engine.dimensions import extract_package_dims
from engine.fitting import fit_disposition


def _apply_fitcheck(work: pd.DataFrame, col_dims_mapped: bool) -> pd.DataFrame:
    """Mirror of the page's fit-check block (kept in sync with
    pages/1_Kromi_Planner.py). Returns a new frame; never mutates input."""
    work = work.copy()
    if col_dims_mapped and "PackageDimensions" in work.columns:
        fs, fr, fe, fp = [], [], [], []
        for _, row in work.iterrows():
            if row.get("SystemCategory") != "KTC":
                fs.append("")
                fr.append("")
                fe.append("")
                fp.append("")
                continue
            pkg = extract_package_dims(row.get("PackageDimensions", ""))
            disp = fit_disposition(str(row.get("CabinetType", "")), pkg)
            fs.append(disp["status"])
            fr.append(disp["recommended"] or "")
            fe.append(disp["evidence"])
            fp.append(" x ".join(f"{v:g}" for v in pkg.sorted_mm) if pkg.ok else "")
        work["Fit_status"] = fs
        work["Fit_recommended"] = fr
        work["Fit_evidence"] = fe
        work["Fit_package_mm"] = fp
    return work


def _frame():
    return pd.DataFrame([
        {"Code": "A1", "SystemCategory": "KTC", "CabinetType": "Helix",
         "PackageDimensions": "40x40x30"},      # fits Helix
        {"Code": "A2", "SystemCategory": "KTC", "CabinetType": "Helix",
         "PackageDimensions": "80x60x150"},     # misfit -> Carousel
        {"Code": "A3", "SystemCategory": "KTC", "CabinetType": "Locker A",
         "PackageDimensions": "170x480x280"},   # misfit -> Locker B
        {"Code": "A4", "SystemCategory": "KTC", "CabinetType": "Carousel",
         "PackageDimensions": ""},              # no-dims
        {"Code": "K1", "SystemCategory": "Kanban", "CabinetType": "Kanban",
         "PackageDimensions": "10x10x10"},      # skipped (non-KTC)
    ])


class TestFitCheckWiringOff:
    """With the column unmapped, the feature must be completely inert."""

    def test_no_fit_columns_added(self):
        work = _frame().drop(columns=["PackageDimensions"])
        result = _apply_fitcheck(work, col_dims_mapped=False)
        assert "Fit_status" not in result.columns

    def test_frame_byte_identical(self):
        work = _frame().drop(columns=["PackageDimensions"])
        result = _apply_fitcheck(work, col_dims_mapped=False)
        assert result.equals(work)

    def test_mapped_false_even_with_column_present(self):
        """If the column exists but the user didn't map it, still inert."""
        work = _frame()
        result = _apply_fitcheck(work, col_dims_mapped=False)
        assert "Fit_status" not in result.columns


class TestFitCheckWiringOn:
    def test_fitting_item_ok(self):
        result = _apply_fitcheck(_frame(), col_dims_mapped=True)
        assert result.loc[0, "Fit_status"] == "ok"

    def test_misfit_suggests_carousel(self):
        result = _apply_fitcheck(_frame(), col_dims_mapped=True)
        assert result.loc[1, "Fit_status"] == "misfit"
        assert result.loc[1, "Fit_recommended"] == "Carousel"

    def test_misfit_suggests_locker_b(self):
        result = _apply_fitcheck(_frame(), col_dims_mapped=True)
        assert result.loc[2, "Fit_status"] == "misfit"
        assert result.loc[2, "Fit_recommended"] == "Locker B"

    def test_blank_dims_is_no_dims(self):
        result = _apply_fitcheck(_frame(), col_dims_mapped=True)
        assert result.loc[3, "Fit_status"] == "no-dims"

    def test_non_ktc_row_skipped(self):
        result = _apply_fitcheck(_frame(), col_dims_mapped=True)
        assert result.loc[4, "Fit_status"] == ""

    def test_package_mm_rendered(self):
        result = _apply_fitcheck(_frame(), col_dims_mapped=True)
        # 40x40x30 sorted desc -> "40 x 40 x 30"
        assert result.loc[0, "Fit_package_mm"] == "40 x 40 x 30"

    def test_input_frame_not_mutated(self):
        work = _frame()
        _apply_fitcheck(work, col_dims_mapped=True)
        assert "Fit_status" not in work.columns  # original untouched


# ---------------------------------------------------------------------------
# Integration test: preprocessing → fit-check (the v33.12 bug path)
# ---------------------------------------------------------------------------

from engine import preprocessing as pp


class TestFitCheckSurvivesDedup:
    """Integration regression for the v33.12 silent-no-op bug.

    The original bug: ``prepare_planning_base`` aggregated only the
    columns named in its ``agg_spec`` dict during dedup. Because
    ``PackageDimensions`` wasn't in that dict, the column was silently
    dropped, and the page's fit-check guard
    ``if "PackageDimensions" in work.columns`` evaluated false — the
    feature looked enabled but produced no output.

    The fit-check unit tests above all bypassed dedup by constructing
    ``work`` directly. This class exercises the real path:
    upload → preprocessing (dedup) → fit-check.
    """

    def _input_with_duplicates(self):
        """Two rows per Code so dedup activates — mirrors a real catalog
        that has a duplicate code (which is what triggered the bug in
        the v33.11 fit-check run)."""
        rows = []
        for code, dims, cab in [
            ("A1", "40x40x30", "Helix"),       # fits
            ("A2", "80x60x150", "Helix"),      # misfit → carousel
            ("A3", "Ø 65 x 200 mm", "Helix"),  # diameter > Helix ring
            ("A4", "", "Carousel"),            # no dims
        ]:
            for _ in range(2):                  # duplicate every row
                rows.append({
                    "Code": code,
                    "Description": "tool",
                    "Description_2": "",
                    "Consumption_pcs": 10.0,
                    "PackUnits": 1.0,
                    "ProductCategory": "",
                    "SizeCategory": "",
                    "Year": 2025,
                    "PackageDimensions": dims,
                    "SystemCategory": "KTC",
                    "CabinetType": cab,
                })
        return pd.DataFrame(rows)

    def test_package_dimensions_survives_dedup(self):
        """The most direct guard: dedup must not drop the column."""
        df = self._input_with_duplicates()
        out, _ = pp.prepare_planning_base(df, "code", "all_years", True)
        assert "PackageDimensions" in out.columns, (
            "PackageDimensions dropped by dedup — the v33.12 bug has regressed"
        )
        # Four distinct Codes after dedup
        assert len(out) == 4

    def test_fit_check_engages_after_dedup(self):
        """The full integration: input → dedup → fit-check produces
        Fit_status with the expected dispositions."""
        df = self._input_with_duplicates()
        out, _ = pp.prepare_planning_base(df, "code", "all_years", True)
        # The page also passes SystemCategory + CabinetType through; the
        # preprocessing aggregator doesn't list those (they're set later
        # in the page), so re-attach them here as the page would.
        cab_map = {"A1": "Helix", "A2": "Helix", "A3": "Helix", "A4": "Carousel"}
        out = out.copy()
        out["SystemCategory"] = "KTC"
        out["CabinetType"] = out["Code"].map(cab_map)

        result = _apply_fitcheck(out, col_dims_mapped=True)
        assert "Fit_status" in result.columns
        statuses = dict(zip(result["Code"], result["Fit_status"]))
        assert statuses["A1"] == "ok"
        assert statuses["A2"] == "misfit"
        assert statuses["A3"] == "misfit"
        assert statuses["A4"] == "no-dims"
