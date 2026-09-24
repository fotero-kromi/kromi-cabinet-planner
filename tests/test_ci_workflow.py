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


def _triggers(text: str) -> dict:
    """'push' / 'pull_request' -> the branches listed for it."""
    out = {}
    for event in ("push", "pull_request"):
        m = re.search(rf"^  {event}:\s*\n    branches:\s*\[([^\]]*)\]", text, flags=re.M)
        out[event] = [b.strip().strip("'\"") for b in m.group(1).split(",")] if m else []
    return out


def test_the_gate_also_runs_on_the_rewrite_branch():
    # The rewrite branch keeps the Streamlit app and its gate until parity.
    for event, branches in _triggers(_text()).items():
        assert "main" in branches and "rewrite/fastapi-react" in branches, event


NEW_APP = REPO / ".github" / "workflows" / "new-app.yml"


def test_the_new_app_workflow_runs_on_the_rewrite_branch():
    for event, branches in _triggers(NEW_APP.read_text(encoding="utf-8")).items():
        assert branches == ["rewrite/fastapi-react"], event


def test_the_new_app_back_end_tests_run_against_postgresql_18():
    t = NEW_APP.read_text(encoding="utf-8")
    assert re.search(r"image:\s*postgres:18\s*$", t, flags=re.M)  # major 18, latest minor
    assert "KROMI_TEST_DATABASE_URL: postgresql+psycopg://" in t
    assert "KROMI_EXPECT_POSTGRES_MAJOR: \"18\"" in t
    assert re.search(r"""python-version:\s*["']?3\.12["']?""", t)
    for step in ("pip install -r requirements-dev.txt", "ruff check .", "mypy", "pytest"):
        assert step in t, step
    assert "working-directory: backend" in t
    assert "sqlite" not in t.lower()


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


def _new_app_jobs():
    body = NEW_APP.read_text(encoding="utf-8").split("\njobs:\n", 1)[1]
    blocks = re.split(r"^  (?=[\w-]+:\s*$)", body, flags=re.M)
    return {b.split(":", 1)[0]: b for b in blocks if b.strip()}


def test_the_new_app_front_end_is_checked():
    job = _new_app_jobs()["frontend"]
    assert "working-directory: frontend" in job
    assert re.search(r"""node-version:\s*["']?22["']?""", job)
    assert "cache-dependency-path: frontend/package-lock.json" in job
    # A locked install, then lint, types, unit tests and the production build.
    for step in ("npm ci", "npm run lint", "npm run typecheck", "npm test", "npm run build"):
        assert step in job, step


def test_the_generated_client_cannot_drift_from_the_back_end():
    # The back-end tests check frontend/openapi.json against the served schema;
    # the front-end job regenerates the client from it and fails on any change.
    job = _new_app_jobs()["frontend"]
    assert "npm run gen:api" in job
    assert "git diff --exit-code -- src/api/schema.d.ts" in job
