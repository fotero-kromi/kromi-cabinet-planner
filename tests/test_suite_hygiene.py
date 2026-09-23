"""Suite hygiene contracts (v34.49, audit C4/F9).

The suite must pass from any working directory and on newer Streamlit
releases, so tests never refer to project files by repository-relative
strings; they use tests/_paths.py. The test run must also leave the working
tree untouched (no remembered KTC-IDs written into runs/).
"""
import re
from pathlib import Path

from tests._paths import REPO

_RELATIVE = re.compile(
    r"""(from_file|open|Path|read_text)\(\s*["'](pages|engine|ui|db|tools)/""")
_CONST = re.compile(r"""^\s*[A-Z_]+\s*=\s*["'](pages|engine|ui|db)/[^"']+\.py["']""", re.M)


def test_no_test_uses_a_cwd_relative_project_path():
    offenders = []
    for p in sorted((REPO / "tests").glob("test_*.py")):
        if p.name in ("test_suite_hygiene.py", "test_release_packaging.py"):
            continue
        text = p.read_text(encoding="utf-8")
        if _RELATIVE.search(text) or _CONST.search(text):
            offenders.append(p.name)
    assert offenders == [], offenders


def test_suite_does_not_write_runtime_state_into_the_tree():
    # runs/ holds remembered KTC-IDs; the autouse isolation fixture redirects
    # it, so after any number of page drives it must not exist in the repo.
    assert not (REPO / "runs" / "file_prefs.json").exists()


def test_tests_run_from_another_working_directory(tmp_path, monkeypatch):
    # A cheap proxy for "pytest started from the parent folder": a page path
    # built from tests/_paths.py still resolves after changing directory.
    from tests._paths import PLANNER_PAGE
    monkeypatch.chdir(tmp_path)
    assert Path(PLANNER_PAGE).is_file()
