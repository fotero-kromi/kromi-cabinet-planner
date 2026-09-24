"""The new app's checks, as CI runs them (.github/workflows/new-app.yml).

Usage:
    python tools/check_new_app.py

Back end: ruff, mypy and pytest in backend/, against the PostgreSQL named by
KROMI_TEST_DATABASE_URL (default: the local test database that
tools/cloud_setup.sh starts). The Streamlit app keeps its own gate:
python tools/check.py --tests.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def main() -> int:
    py = sys.executable
    failures = []
    for label, cmd in (
        ("back end lint", [py, "-m", "ruff", "check", "."]),
        ("back end types", [py, "-m", "mypy"]),
        ("back end tests", [py, "-m", "pytest", "-p", "no:cacheprovider"]),
    ):
        print(f"== {label}: {' '.join(cmd[1:])}", flush=True)
        if subprocess.run(cmd, cwd=BACKEND).returncode != 0:
            failures.append(label)
    print("All checks passed." if not failures else "FAILED: " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
