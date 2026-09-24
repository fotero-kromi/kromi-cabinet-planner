"""The new app stays apart from the Streamlit app: it imports the shared engine
and never the page, its ui/ and db/ packages, Streamlit or SQLite
(owner decision 2026-09-23: PostgreSQL only, no SQLite in the new app)."""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "kromi_api"
FORBIDDEN = {"sqlite3", "streamlit", "db", "pages", "ui", "app_log", "styling", "presentation"}


def _imported_roots(path: Path) -> set:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_app_package_exists():
    assert (APP / "__init__.py").is_file()


def test_no_forbidden_import_anywhere_in_the_app():
    found = {}
    for path in sorted(APP.rglob("*.py")):
        bad = _imported_roots(path) & FORBIDDEN
        if bad:
            found[str(path.relative_to(APP))] = sorted(bad)
    assert found == {}


def test_the_app_starts_from_the_repository_root_layout():
    """The documented start: repository root as working directory, backend/ as
    the app directory (``python -m uvicorn --app-dir backend kromi_api.main:app``).
    A fresh process, so pytest's own path settings cannot hide a missing path."""
    import subprocess
    import sys

    repo = APP.parents[1]
    code = ("import sys; sys.path.insert(0, 'backend'); import kromi_api.main as m; "
            "print(m.app.title)")
    out = subprocess.run([sys.executable, "-c", code], cwd=repo, capture_output=True,
                         text=True, env={"PATH": "", "KROMI_DATABASE_URL":
                                         "postgresql+psycopg://x@127.0.0.1:1/none"})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "Kromi Cabinet Planner"


def test_no_sqlite_connection_string_in_the_app():
    for path in sorted(APP.rglob("*.py")):
        assert "sqlite" not in path.read_text(encoding="utf-8").lower(), path
