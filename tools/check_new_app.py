"""The new app's checks, as CI runs them (.github/workflows/new-app.yml).

Usage:
    python tools/check_new_app.py              # back end and front end
    python tools/check_new_app.py --backend    # back end only
    python tools/check_new_app.py --frontend   # front end only

Back end: ruff, mypy and pytest in backend/, against the PostgreSQL named by
KROMI_TEST_DATABASE_URL (default: the local test database that
tools/cloud_setup.sh starts).

Front end (frontend/, Node 22, packages from ``npm ci``): the generated API
client must match frontend/openapi.json, then ESLint, TypeScript, Vitest and
the production build.

The Streamlit app keeps its own gate: python tools/check.py --tests.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"


def _steps(backend: bool, frontend: bool) -> list[tuple[str, list[str], Path]]:
    py = sys.executable
    steps: list[tuple[str, list[str], Path]] = []
    if backend:
        steps += [
            ("back end lint", [py, "-m", "ruff", "check", "."], BACKEND),
            ("back end types", [py, "-m", "mypy"], BACKEND),
            ("back end tests", [py, "-m", "pytest", "-p", "no:cacheprovider"], BACKEND),
        ]
    if frontend:
        npm = shutil.which("npm") or "npm"
        steps += [
            ("front end client", [npm, "run", "gen:api"], FRONTEND),
            ("front end client is committed",
             ["git", "diff", "--exit-code", "--", "src/api/schema.d.ts"], FRONTEND),
            ("front end lint", [npm, "run", "lint"], FRONTEND),
            ("front end types", [npm, "run", "typecheck"], FRONTEND),
            ("front end tests", [npm, "test"], FRONTEND),
            ("front end build", [npm, "run", "build"], FRONTEND),
        ]
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", action="store_true", help="back end only")
    parser.add_argument("--frontend", action="store_true", help="front end only")
    args = parser.parse_args(argv)
    both = not (args.backend or args.frontend)
    failures = []
    for label, cmd, cwd in _steps(both or args.backend, both or args.frontend):
        print(f"== {label}: {' '.join(Path(cmd[0]).name if i == 0 else c for i, c in enumerate(cmd))}",
              flush=True)
        try:
            ok = subprocess.run(cmd, cwd=cwd).returncode == 0
        except FileNotFoundError:
            print(f"   {cmd[0]} is not installed")
            ok = False
        if not ok:
            failures.append(label)
    print("All checks passed." if not failures else "FAILED: " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
