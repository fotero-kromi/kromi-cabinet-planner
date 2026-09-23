"""CI workflow contracts (v34.49, audit C4).

The old undefined-name gate grepped pyflakes output for "undefined name",
which also matched pyflakes' notice about star imports ("unable to detect
undefined names"), so the gate failed every run and pytest, ruff and mypy
never executed. The gate now uses ruff's F821 rule, which reports real
undefined names only, and a dependency audit runs alongside.
"""
import re
import shutil
import subprocess
import sys

from tests._paths import REPO

WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def _text():
    return WORKFLOW.read_text(encoding="utf-8")


def test_gate_uses_a_precise_undefined_name_rule():
    t = _text()
    assert 'grep "undefined name"' not in t
    assert "--select F821" in t


def test_all_quality_steps_are_present():
    t = _text()
    for step in ("pytest", "ruff check", "mypy", "pip-audit"):
        assert step in t, step


def test_undefined_name_gate_passes_on_this_tree():
    if shutil.which("ruff") is None:
        import importlib.util
        if importlib.util.find_spec("ruff") is None:
            import pytest
            pytest.skip("ruff not installed")
    r = subprocess.run([sys.executable, "-m", "ruff", "check", "--select", "F821", "."],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _jobs():
    """Job name -> its text block (two-space indented keys under 'jobs:')."""
    body = _text().split("\njobs:\n", 1)[1]
    blocks = re.split(r"^  (?=[\w-]+:\s*$)", body, flags=re.M)
    return {b.split(":", 1)[0]: b for b in blocks if b.strip()}


def test_a_windows_job_runs_the_suite():
    # v34.60: users run the app on Windows, where the suite broke on line
    # endings and cp1252. The job reports without blocking until it is proven.
    windows = [b for b in _jobs().values() if re.search(r"runs-on:\s*windows-latest", b)]
    assert len(windows) == 1
    job = windows[0]
    assert re.search(r"""python-version:\s*["']?3\.11["']?""", job)
    assert re.search(r"^    continue-on-error:\s*true", job, flags=re.M)
    for step in ("requirements-dev.txt", "pytest", "mypy", "ruff check"):
        assert step in job, step
