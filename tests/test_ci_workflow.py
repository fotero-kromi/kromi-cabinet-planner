"""CI workflow contracts (v34.49, audit C4).

The old undefined-name gate grepped pyflakes output for "undefined name",
which also matched pyflakes' notice about star imports ("unable to detect
undefined names"), so the gate failed every run and pytest, ruff and mypy
never executed. The gate now uses ruff's F821 rule, which reports real
undefined names only, and a dependency audit runs alongside.
"""
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
