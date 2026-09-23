"""Contracts for the release packager (v34.48, audit S10).

Release zips used to be built by hand with an exclusion list, so anything not
explicitly excluded (a developer's .env holding the OpenAI key, runtime
preference files, a stray database) could ship. tools/package_release.py builds
the zip from an explicit allow-list and additionally refuses secrets, runtime
state, databases and caches even inside allowed folders.
"""

import zipfile

from tools.package_release import build_release_zip


def _tree(root):
    files = {
        "Home.py": "x", "README.md": "x", "CHANGELOG.md": "x",
        "requirements.txt": "x", "requirements-dev.txt": "x", "pyproject.toml": "x",
        "run.bat": "x", ".env.example": "x", ".gitignore": "x",
        "styling.py": "x", "presentation.py": "x", "optimization.py": "x",
        "controls_model.py": "x",
        ".streamlit/config.toml": "x", ".streamlit/secrets.toml": "SECRET",
        ".github/workflows/ci.yml": "x",
        "engine/__init__.py": "x", "engine/plan.py": "x",
        "engine/__pycache__/plan.cpython-311.pyc": "x",
        "db/store.py": "x", "db/migrations/001_init.sql": "x",
        "ui/exports_panel.py": "x", "pages/1_Kromi_Planner.py": "x",
        "tools/package_release.py": "x", "tests/test_a.py": "x",
        "assets/logo.png": "x",
        # must never ship
        ".env": "OPENAI_API_KEY=sk-secret", "runs/file_prefs.json": "{}",
        "kromi.db": "x", "engine/kromi.db-wal": "x", ".pytest_cache/v": "x",
        ".mypy_cache/x": "x", "stray_notes.txt": "x", "build.zip": "x",
        "tests/.env": "x",
    }
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def test_zip_holds_only_the_allow_list(tmp_path):
    src = tmp_path / "app"
    _tree(src)
    out = tmp_path / "release.zip"
    names = build_release_zip(src, out)
    with zipfile.ZipFile(out) as z:
        assert sorted(z.namelist()) == sorted(names)
        assert z.testzip() is None
    for must in ("Home.py", "engine/plan.py", "db/migrations/001_init.sql",
                 ".streamlit/config.toml", ".github/workflows/ci.yml",
                 "assets/logo.png", "tests/test_a.py", ".env.example"):
        assert must in names, must
    for never in (".env", "tests/.env", ".streamlit/secrets.toml",
                  "runs/file_prefs.json", "kromi.db", "engine/kromi.db-wal",
                  "engine/__pycache__/plan.cpython-311.pyc",
                  ".pytest_cache/v", ".mypy_cache/x", "stray_notes.txt",
                  "build.zip"):
        assert never not in names, never


def test_zip_is_deterministic(tmp_path):
    src = tmp_path / "app"
    _tree(src)
    a = build_release_zip(src, tmp_path / "a.zip")
    b = build_release_zip(src, tmp_path / "b.zip")
    assert a == b == sorted(a)


def test_zip_carries_the_working_rules_and_docs(tmp_path):
    """v34.59: CLAUDE.md, docs/ and the cloud-session settings travel with the code."""
    src = tmp_path / "app"
    _tree(src)
    for rel in ("CLAUDE.md", "docs/Domain_Rules.md", ".claude/settings.json"):
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    (src / ".claude" / "settings.local.json").write_text("{}", encoding="utf-8")
    names = build_release_zip(src, tmp_path / "release.zip")
    for must in ("CLAUDE.md", "docs/Domain_Rules.md", ".claude/settings.json"):
        assert must in names, must
    assert ".claude/settings.local.json" not in names
