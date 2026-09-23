"""Stage 1 of the structural project (v34.39): the workbook builder lives in
engine/workbook.py, pure and Streamlit-free; the page keeps only the thin
cached wrapper. Behavior is proven by the export digests staying
byte-identical; these pins guard the structure itself.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_workbook_module_is_streamlit_free():
    src = (REPO / "engine" / "workbook.py").read_text(encoding="utf-8")
    assert "import streamlit" not in src and "from streamlit" not in src
    assert "def build_result_workbook(" in src
    assert "def _build_layout_items(" in src
    assert "def _render_planogram_sheet(" in src


def test_engine_package_stays_pure():
    """No engine module imports Streamlit; the layering the audit praised is
    now a contract, not a habit. Checked on the syntax tree, since docstrings
    are allowed to talk about Streamlit."""
    import ast
    for p in sorted((REPO / "engine").glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(a.name.split(".")[0] == "streamlit" for a in node.names), p.name
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "streamlit", p.name


def test_the_wrapper_stays_thin_and_the_page_stays_clean():
    """Since v34.40 the cached wrapper lives with the exports panel; the page
    holds neither the builder body nor the planogram helpers, and the
    delegation into the pure engine function is in exactly one place."""
    page = (REPO / "pages" / "1_Kromi_Planner.py").read_text(encoding="utf-8")
    panel = (REPO / "ui" / "exports_panel.py").read_text(encoding="utf-8")
    assert "return build_result_workbook(" in panel
    assert "def _build_layout_items(" not in page
    assert "def _render_planogram_sheet(" not in page
    assert "return build_result_workbook(" not in page
