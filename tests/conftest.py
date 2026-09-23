"""Shared pytest fixtures for the engine test suite."""

from pathlib import Path

import pandas as pd
import pytest

# ---- Isolation (v34.48, audit F9) ----

@pytest.fixture(autouse=True)
def _isolate_runtime_state(tmp_path, monkeypatch):
    """Every test gets its own preference store and database, and no API key.

    Page drives used to write remembered KTC-IDs into the repository's
    runs/file_prefs.json (keyed by file name), so one test's input leaked into
    the next, and a developer's .env key could make a page test call OpenAI.
    Tests that need a specific database still set KROMI_DB_PATH themselves.
    """
    import engine.run_prefs as _run_prefs

    monkeypatch.setattr(_run_prefs, "DEFAULT_PREFS_PATH",
                        tmp_path / "_isolated" / "file_prefs.json")
    monkeypatch.setenv("KROMI_FILE_PREFS_PATH",
                       str(tmp_path / "_isolated" / "file_prefs.json"))
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "_isolated" / "kromi.db"))
    # v34.55: the local log goes to the test's folder, never the user profile.
    monkeypatch.setenv("KROMI_LOG_PATH", str(tmp_path / "_isolated" / "planner.log"))
    # Empty rather than deleted: load_dotenv() never overrides a variable that
    # is already set, so a developer's .env cannot re-insert a real key.
    monkeypatch.setenv("OPENAI_API_KEY", "")


# ---- Filesystem fixtures ----

@pytest.fixture
def tmp_base_dir(tmp_path):
    """A clean temporary base directory for tests that need filesystem
    access (overrides, archive). pytest's tmp_path already creates a
    unique-per-test folder; we just return its Path."""
    return tmp_path


# ---- DataFrame fixtures ----

@pytest.fixture
def work_minimal():
    """Minimal valid work DataFrame for pipeline tests. 3 rows, KTC,
    mixed cabinet types."""
    return pd.DataFrame({
        "Code": ["A", "B", "C"],
        "Description": ["a", "b", "c"],
        "Listing": ["Tools"] * 3,
        "SystemCategory": ["KTC"] * 3,
        "CabinetType": ["Helix", "Carousel", "Locker A"],
        "Monthly_packs": [12.0, 2.0, 1.0],
        "Target_packs": [12.0, 2.0, 1.0],
        "SizeCategory": ["S", "S", "XXL"],
        "Spiral_capacity": [22, None, None],
        "Spirals_needed": [1, 0, 0],
        "Carousel_stockpiles": [0, 3, 0],
        "Consumption_pcs": [144, 24, 12],
        "ProductCategory": ["drills", "drills", "drills"],
        "Override_Applied": [False, False, False],
        "Override_Fields": ["", "", ""],
    })


@pytest.fixture
def work_consolidatable():
    """30 helix items + 5 underused carousel items.

    The classic consolidation case: 30 fast-movers fill ~1 helix cabinet
    (~30 spirals), 5 slow carousel items take 3 stockpiles each (15 slots).
    The 5 carousel items fit easily into the helix's remaining headroom,
    so a single rebalancer pass should drop from 2 cabinets to 1."""
    rows = []
    for i in range(30):
        rows.append({
            "Code": f"H{i}", "Description": f"H{i}", "Listing": "Tools",
            "SystemCategory": "KTC", "CabinetType": "Helix",
            "Monthly_packs": 12.0, "Target_packs": 12.0,
            "SizeCategory": "S", "Spiral_capacity": 22,
            "Spirals_needed": 1, "Carousel_stockpiles": 0,
            "Consumption_pcs": 144, "ProductCategory": "drills",
            "Override_Applied": False, "Override_Fields": "",
        })
    for i in range(5):
        rows.append({
            "Code": f"C{i}", "Description": f"C{i}", "Listing": "Tools",
            "SystemCategory": "KTC", "CabinetType": "Carousel",
            "Monthly_packs": 2.0, "Target_packs": 2.0,
            "SizeCategory": "S", "Spiral_capacity": None,
            "Spirals_needed": 0, "Carousel_stockpiles": 3,
            "Consumption_pcs": 24, "ProductCategory": "drills",
            "Override_Applied": False, "Override_Fields": "",
        })
    return pd.DataFrame(rows)


@pytest.fixture
def overrides_csv_data():
    """A representative overrides DataFrame: one valid, one invalid, one
    unmatched (code Z9 doesn't exist in a typical work df)."""
    return pd.DataFrame({
        "code": ["A1", "B2", "Z9"],
        "listing": ["Tools"] * 3,
        "product_category_override": ["drills", "INVALID_CAT", "mills"],
        "pack_units_override": ["50", "", ""],
        "size_category_override": ["", "XXL", ""],
        "cabinet_type_override": ["", "Locker B", ""],
        "vend_mode_override": ["", "", "Bulk/Kanban"],
        "note": ["note A", "note B", "note Z"],
        "reviewed_by": ["alice", "bob", "carol"],
        "reviewed_at": ["2025-01-01", "2025-01-02", "2025-01-03"],
    })


@pytest.fixture
def work_for_overrides():
    """Work DataFrame matching overrides_csv_data — has A1, B2, C3, D4
    but not Z9 (so Z9 stays unmatched)."""
    return pd.DataFrame({
        "Code": ["A1", "B2", "C3", "D4"],
        "Listing": ["Tools"] * 4,
        "ProductCategory": ["other", "other", "other", "drills"],
        "ProductCategory_Source": ["Default"] * 4,
        "ProductCategory_Evidence": [""] * 4,
        "ProductCategory_Confidence": [""] * 4,
        "PackUnits": [1.0, 1.0, 1.0, 5.0],
        "PackUnits_Source": ["Default"] * 4,
        "PackUnits_Evidence": [""] * 4,
        "PackUnits_Confidence": [""] * 4,
        "SizeCategory": ["L"] * 4,
        "SizeCategory_Source": ["Default"] * 4,
        "CabinetType": ["Helix", "Helix", "Carousel", "Helix"],
        "SystemCategory": ["KTC"] * 4,
        "VendMode": ["Vending"] * 4,
        "VendBlockReason": [""] * 4,
    })


# ---- Plan-dict fixtures (for rebalancer / occupation tests) ----

@pytest.fixture
def plan_mixed():
    """Plan dict with all cabinet types populated."""
    return {
        "helix_cabs": 1, "total_spirals_buf": 30,
        "car_cabs": 1, "car_slots_buf": 100,
        "cabA": 1, "countA_buf": 20,
        "cabB": 0, "countB_buf": 0,
        "cabC": 1, "countC_buf": 50,
        "total_cabs": 4, "total_cabs_base": 4,
        "ktc_count": 30, "kanban_count": 0,
    }


# ---- Integration-test fixtures (optional sample data) ----
#
# Integration tests read sample spreadsheets that are NOT bundled with the
# repository (they contain real customer catalog data). Point the
# KROMI_FIXTURE_DIR environment variable at a folder containing them, or drop
# them in tests/fixtures/. When absent, the integration tests skip cleanly.

import os

_FIXTURE_DIR = Path(os.environ.get(
    "KROMI_FIXTURE_DIR",
    Path(__file__).parent / "fixtures",
))

SAMPLE_UPLOAD_PATH = _FIXTURE_DIR / "Customer_All_Tools.xlsx"
SAMPLE_RESULT_PATH = _FIXTURE_DIR / "Customer_Planner_Result.xlsx"


@pytest.fixture(scope="session")
def sample_dataframe():
    """Sample 'All Tools' catalog sheet, loaded once per session.
    Skips when the fixture file is not present."""
    if not Path(SAMPLE_UPLOAD_PATH).exists():
        pytest.skip(f"sample catalog not available at {SAMPLE_UPLOAD_PATH}")
    return pd.read_excel(SAMPLE_UPLOAD_PATH, sheet_name="All Tools")


@pytest.fixture(scope="session")
def sample_result_dataframe():
    """Sample planner output sheet, for cross-checking classifier evidence."""
    if not Path(SAMPLE_RESULT_PATH).exists():
        pytest.skip(f"sample result not available at {SAMPLE_RESULT_PATH}")
    return pd.read_excel(SAMPLE_RESULT_PATH, sheet_name="Result")
