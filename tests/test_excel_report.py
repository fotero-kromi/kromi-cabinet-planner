"""Contract for the PDF retirement and Excel absorption (v34.25).

The per-supply-point PDF is retired; everything it carried moves into the
workbook. Three pure builders shape the absorbed pieces: the five-metric KPI
row per supply point, the pie series in the fixed slide bucket order with
zero buckets filtered, and the per-SP subclass table. The retirement pins
prove the PDF is gone from the page, the engine, the requirements, and the
capture instrument, so the removal cannot silently regress into a half-alive
state.
"""

from pathlib import Path

import pandas as pd

from engine.constants import SLIDE_BUCKET_ORDER
from engine.export_shaping import (
    build_pie_series,
    build_sp_kpi_frame,
    build_sp_subclass_frame,
)

REPO = Path(__file__).resolve().parents[1]


# ---- KPI row ---------------------------------------------------------------

def test_kpi_frame_five_metrics_buffered_totals():
    plan = {
        "ktc_count": 120, "kanban_count": 30,
        "total_spirals_buf": 250,
        "car_slots_buf": 40, "countA_buf": 5, "countB_buf": 3, "countC_buf": 2,
        "total_cabs": 7,
    }
    df = build_sp_kpi_frame(plan)
    assert list(df.columns) == [
        "KTC items", "Kanban items", "Spirals (total)",
        "Compartments (total)", "Cabinets",
    ]
    assert len(df) == 1
    row = df.iloc[0]
    assert row["KTC items"] == 120 and row["Kanban items"] == 30
    assert row["Spirals (total)"] == 250
    assert row["Compartments (total)"] == 50
    assert row["Cabinets"] == 7


def test_kpi_frame_tolerates_missing_keys():
    df = build_sp_kpi_frame({})
    assert int(df.iloc[0]["Compartments (total)"]) == 0


# ---- pie series ------------------------------------------------------------

def test_pie_series_order_and_zero_filter():
    dist = {"Others": 5, "Inserts": 10, "Drills": 0, "Mills": 3}
    labels, values = build_pie_series(dist)
    assert labels == ["Inserts (10)", "Mills (3)", "Others (5)"]
    assert values == [10, 3, 5]


def test_pie_series_empty_distribution():
    labels, values = build_pie_series({})
    assert labels == [] and values == []


# ---- subclass table --------------------------------------------------------

def test_subclass_frame_bucket_order_and_shares():
    buckets = {
        "Mills": {"end mill": 6, "ball mill": 2},
        "Inserts": {"turning insert": 4},
    }
    df = build_sp_subclass_frame(buckets)
    assert list(df.columns) == ["Bucket", "Subclass", "Items", "Share of bucket %"]
    assert list(df["Bucket"]) == ["Inserts", "Mills", "Mills"]
    assert list(df["Subclass"]) == ["turning insert", "end mill", "ball mill"]
    assert list(df["Share of bucket %"]) == [100.0, 75.0, 25.0]


def test_subclass_frame_empty():
    assert build_sp_subclass_frame({}).empty


# ---- retirement pins -------------------------------------------------------

def test_pdf_module_is_gone():
    assert not (REPO / "engine" / "pdf_summary.py").exists()
    import importlib
    try:
        importlib.import_module("engine.pdf_summary")
        raised = False
    except ImportError:
        raised = True
    assert raised, "engine.pdf_summary must not be importable after retirement"


def test_page_carries_no_pdf_machinery():
    src = (REPO / "pages" / "1_Kromi_Planner.py").read_text(encoding="utf-8")
    for marker in ("reportlab", "pdf_summary", "_combined_pdf_bytes",
                   "build_per_sp_pdf", "REPORTLAB_AVAILABLE"):
        assert marker not in src, f"page still references {marker}"


def test_requirements_carry_no_reportlab():
    req = (REPO / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "reportlab" not in req


def test_capture_instrument_is_excel_only():
    src = (REPO / "tools" / "export_capture.py").read_text(encoding="utf-8")
    for marker in ("_canon_pdf", "pdf_digest", "pdf_bytes"):
        assert marker not in src, f"capture instrument still references {marker}"
