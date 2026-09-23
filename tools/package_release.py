"""Build a release zip from an explicit allow-list (v34.48, audit S10).

Usage:
    python tools/package_release.py <app_root> <out.zip>

Only the files a user needs to run, test and understand the app are packaged.
Secrets (.env, .streamlit/secrets.toml), runtime state (runs/, preference
files), databases and caches are refused even inside allowed folders, so a
developer's local API key or customer data can never ship by accident. Entry
order is sorted, so the same tree always gives the same file list.
"""
from __future__ import annotations

import fnmatch
import sys
import zipfile
from pathlib import Path

#: Top-level files that ship.
ALLOWED_FILES: tuple[str, ...] = (
    "Home.py", "README.md", "CHANGELOG.md", "PROJECT_REVIEW_v34.02.md",
    "requirements.txt", "requirements-dev.txt", "pyproject.toml", "run.bat",
    ".env.example", ".gitignore",
    "styling.py", "presentation.py", "optimization.py", "controls_model.py",
    "app_log.py",
    ".streamlit/config.toml",
    # v34.59: the working rules and the cloud-session hook travel with the code.
    "CLAUDE.md", ".claude/settings.json",
)

#: Top-level folders whose contents ship (subject to the refusal rules below).
ALLOWED_DIRS: tuple[str, ...] = (
    "pages", "engine", "db", "ui", "tools", "tests", "assets", ".github", "docs",
)

#: Never packaged, wherever they appear (matched against every path part and
#: the file name).
REFUSED_PARTS: tuple[str, ...] = (
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "runs",
    ".venv", "venv", ".git",
)
REFUSED_NAMES: tuple[str, ...] = (
    ".env", ".env.*", "secrets.toml", "*.db", "*.db-*", "*.sqlite*", "*.pyc",
    "*.zip", "file_prefs.json", "*.log", ".DS_Store", "Thumbs.db", "desktop.ini",
    "*.bak",
)


def _refused(rel: Path) -> bool:
    if any(part in REFUSED_PARTS for part in rel.parts[:-1]):
        return True
    name = rel.name
    if name == ".env.example":
        return False
    return any(fnmatch.fnmatch(name, pat) for pat in REFUSED_NAMES)


def release_file_list(root: Path) -> list[str]:
    """Sorted POSIX paths (relative to ``root``) that belong in a release."""
    root = Path(root)
    out: set[str] = set()
    for rel_s in ALLOWED_FILES:
        p = root / rel_s
        if p.is_file() and not _refused(Path(rel_s)):
            out.add(rel_s)
    for d in ALLOWED_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(root)
            if _refused(rel):
                continue
            out.add(rel.as_posix())
    return sorted(out)


def build_release_zip(root: Path, out_path: Path) -> list[str]:
    """Write the release zip and return the packaged paths (sorted)."""
    root = Path(root)
    names = release_file_list(root)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for rel in names:
            z.write(root / rel, arcname=rel)
    return names


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    names = build_release_zip(Path(argv[1]), Path(argv[2]))
    print(f"{len(names)} files packaged into {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
