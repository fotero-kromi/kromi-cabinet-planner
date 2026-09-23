"""Absolute paths for tests (v34.49, audit C4).

Streamlit 1.6x resolves ``AppTest.from_file`` relative to the calling test
file, and plain ``open("pages/...")`` depends on the working directory, so
tests that used repository-relative strings failed on newer Streamlit or when
pytest was started from another folder. Every test resolves files from here.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLANNER_PAGE = str(REPO / "pages" / "1_Kromi_Planner.py")
PLAN_MODULE = str(REPO / "engine" / "plan.py")
