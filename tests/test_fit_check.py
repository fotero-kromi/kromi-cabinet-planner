"""Tests for engine.fitting.apply_fit_check (v33.92).

The optional dimensional fit-check was lifted out of the page into a single
engine function. It is advisory and additive: it reads CabinetType and
PackageDimensions and writes four Fit_* columns, only for KTC rows, and never
changes routing. These tests pin that contract branch by branch, prove the
function leaves the input frame and its index untouched, and run a real-data
simulation when a planner Result workbook is supplied.
"""

import os

import pandas as pd
import pytest

from engine.fitting import apply_fit_check, fit_disposition
from engine.dimensions import extract_package_dims

_COLS = ["Fit_status", "Fit_recommended", "Fit_evidence", "Fit_package_mm"]


def _row(system="KTC", cabinet="Helix", dims="Ø 12 x 80 mm", **extra):
    return dict(SystemCategory=system, CabinetType=cabinet, PackageDimensions=dims, **extra)


# ---------------------------------------------------------------------------
# Column contract
# ---------------------------------------------------------------------------

def test_adds_exactly_the_four_fit_columns():
    out = apply_fit_check(pd.DataFrame([_row()]))
    for c in _COLS:
        assert c in out.columns


def test_does_not_mutate_input_frame():
    df = pd.DataFrame([_row()])
    before = df.copy()
    apply_fit_check(df)
    pd.testing.assert_frame_equal(df, before)  # no Fit_ columns leaked back


def test_preserves_index():
    df = pd.DataFrame([_row(), _row(), _row()], index=[7, 19, 33])
    out = apply_fit_check(df)
    assert list(out.index) == [7, 19, 33]


def test_preserves_original_columns_and_row_count():
    df = pd.DataFrame([_row(Code="X"), _row(Code="Y", system="Kanban")])
    out = apply_fit_check(df)
    assert len(out) == 2
    assert out["Code"].tolist() == ["X", "Y"]


def test_empty_frame_returns_empty_with_columns():
    df = pd.DataFrame(columns=["SystemCategory", "CabinetType", "PackageDimensions"])
    out = apply_fit_check(df)
    assert len(out) == 0
    for c in _COLS:
        assert c in out.columns


# ---------------------------------------------------------------------------
# KTC branches
# ---------------------------------------------------------------------------

def test_ktc_fits_current_is_ok():
    out = apply_fit_check(pd.DataFrame([_row(cabinet="Helix", dims="Ø 10 x 70 mm")]))
    assert out.loc[0, "Fit_status"] == "ok"


def test_ktc_too_large_is_misfit_with_recommendation():
    out = apply_fit_check(pd.DataFrame([_row(cabinet="Helix", dims="120 x 90 x 250")]))
    assert out.loc[0, "Fit_status"] == "misfit"
    assert out.loc[0, "Fit_recommended"]  # names a larger cabinet


def test_ktc_empty_dims_is_no_dims():
    out = apply_fit_check(pd.DataFrame([_row(dims="")]))
    assert out.loc[0, "Fit_status"] == "no-dims"
    assert out.loc[0, "Fit_recommended"] == ""
    assert out.loc[0, "Fit_package_mm"] == ""


def test_ktc_unparseable_dims_is_no_dims():
    out = apply_fit_check(pd.DataFrame([_row(dims="not a size")]))
    assert out.loc[0, "Fit_status"] == "no-dims"


def test_package_mm_is_sorted_descending_string():
    out = apply_fit_check(pd.DataFrame([_row(cabinet="Carousel", dims="40 x 60 x 40")]))
    # parsed, sorted, joined; matches the underlying parser's ordering
    pkg = extract_package_dims("40 x 60 x 40")
    assert out.loc[0, "Fit_package_mm"] == " x ".join(f"{v:g}" for v in pkg.sorted_mm)


def test_missing_recommendation_when_nothing_fits():
    # oversized for every envelope -> misfit, empty recommendation
    out = apply_fit_check(pd.DataFrame([_row(cabinet="Locker A", dims="500 x 400 x 600")]))
    assert out.loc[0, "Fit_status"] == "misfit"
    assert out.loc[0, "Fit_recommended"] == ""


# ---------------------------------------------------------------------------
# Non-KTC rows are blank
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("system", ["Kanban", "PPE", "", "Bulk"])
def test_non_ktc_rows_get_blank_fit_columns(system):
    out = apply_fit_check(pd.DataFrame([_row(system=system, dims="50 x 50 x 50")]))
    assert out.loc[0, "Fit_status"] == ""
    assert out.loc[0, "Fit_recommended"] == ""
    assert out.loc[0, "Fit_evidence"] == ""
    assert out.loc[0, "Fit_package_mm"] == ""


def test_mixed_frame_only_ktc_checked():
    df = pd.DataFrame([
        _row(system="KTC", cabinet="Helix", dims="Ø 10 x 70 mm"),
        _row(system="Kanban", dims="10 x 10 x 10"),
        _row(system="KTC", cabinet="Helix", dims="120 x 90 x 250"),
    ])
    out = apply_fit_check(df)
    assert out["Fit_status"].tolist() == ["ok", "", "misfit"]


# ---------------------------------------------------------------------------
# Equivalence with the row-level primitive, and determinism
# ---------------------------------------------------------------------------

def test_matches_row_level_fit_disposition():
    df = pd.DataFrame([
        _row(cabinet="Helix", dims="Ø 16 x 100 mm"),
        _row(cabinet="Carousel", dims="80 x 60 x 40"),
        _row(cabinet="Locker C", dims="150 x 100 x 200"),
    ])
    out = apply_fit_check(df)
    for i, row in df.iterrows():
        pkg = extract_package_dims(row["PackageDimensions"])
        disp = fit_disposition(row["CabinetType"], pkg)
        assert out.loc[i, "Fit_status"] == disp["status"]
        assert out.loc[i, "Fit_recommended"] == (disp["recommended"] or "")
        assert out.loc[i, "Fit_evidence"] == disp["evidence"]


def test_deterministic():
    df = pd.DataFrame([_row(cabinet="Carousel", dims="50 x 50 x 90"),
                       _row(system="Kanban", dims="x")])
    a = apply_fit_check(df)
    b = apply_fit_check(df)
    pd.testing.assert_frame_equal(a[_COLS], b[_COLS])


def test_handles_missing_system_or_cabinet_keys_gracefully():
    # rows without SystemCategory are treated as non-KTC (blank)
    df = pd.DataFrame([{"PackageDimensions": "50 x 50 x 50"}])
    out = apply_fit_check(df)
    assert out.loc[0, "Fit_status"] == ""


# ---------------------------------------------------------------------------
# Real-data simulation
# ---------------------------------------------------------------------------

_GROUND_TRUTH = os.environ.get("KROMI_GROUNDTRUTH_XLSX", "")


@pytest.mark.skipif(not (_GROUND_TRUTH and os.path.exists(_GROUND_TRUTH)),
                    reason="set KROMI_GROUNDTRUTH_XLSX to a planner Result workbook to run")
def test_real_data_fit_check_conserves_rows_and_blanks_non_ktc():
    res = pd.ExcelFile(_GROUND_TRUTH).parse("Result")
    n = len(res)
    sys = res.System.astype(str).where(res.System.astype(str).str.contains("KTC"), "Kanban")
    sys = sys.where(~sys.str.contains("KTC"), "KTC")
    sizes = {"S": "Ø 10 x 70 mm", "M": "Ø 20 x 120 mm", "L": "60 x 40 x 200", "XL": "200 x 150 x 350"}
    sc = res.SizeCategory.astype(str).str[:1].str.upper()
    sim = pd.DataFrame({
        "Code": res.Code.astype(str),
        "SystemCategory": sys.values,
        "CabinetType": res.CabinetType.astype(str),
        "PackageDimensions": sc.map(lambda s: sizes.get(s, "120 x 90 x 250")).values,
    }, index=res.index)
    out = apply_fit_check(sim)
    assert len(out) == n  # every customer row survives
    non_ktc = out[out["SystemCategory"] != "KTC"]
    assert (non_ktc["Fit_status"] == "").all()
    ktc = out[out["SystemCategory"] == "KTC"]
    assert ktc["Fit_status"].isin({"ok", "misfit", "no-dims"}).all()
