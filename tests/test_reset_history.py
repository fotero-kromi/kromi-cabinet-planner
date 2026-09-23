"""Tests for tools.reset_history — the run-history flush utility (stdlib only)."""
import json
import sqlite3
from pathlib import Path

import db
from tools.reset_history import main, default_db_path


def _seed_db(path: str) -> None:
    conn = db.init_db(path)
    fid = db.upsert_file(conn, sha256="abc123", original_filename="f.xlsx",
                         content=b"x", byte_size=1, sheet_tools="Sheet1", row_count=1)
    db.insert_run(conn, file_id=fid, build_version="vX", customer="C", site="default",
                  settings_json=json.dumps({"ui_state": {}}), status="completed")
    db.insert_run(conn, file_id=fid, build_version="vX", customer="C", site="default",
                  settings_json=json.dumps({"ui_state": {}}), status="completed")
    conn.commit()
    conn.close()


def _runs(path: str) -> int:
    conn = sqlite3.connect(path)
    n = conn.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
    conn.close()
    return n


def _files(path: str) -> int:
    conn = sqlite3.connect(path)
    n = conn.execute("SELECT COUNT(*) FROM uploaded_files").fetchone()[0]
    conn.close()
    return n


def _make_app_dir(tmp_path: Path) -> Path:
    app = tmp_path / "app"
    (app / "runs" / "run1").mkdir(parents=True)
    (app / "runs" / "run1" / "meta.json").write_text("{}")
    (app / "catalogs" / "cat1").mkdir(parents=True)
    (app / "catalogs" / "cat1" / "x.txt").write_text("x")
    return app


def test_dry_run_deletes_nothing(tmp_path):
    db_path = str(tmp_path / "k.db")
    _seed_db(db_path)
    app = _make_app_dir(tmp_path)
    rc = main(["--db", db_path, "--app-dir", str(app)])  # no --yes
    assert rc == 0
    assert _runs(db_path) == 2
    assert (app / "runs").exists() and (app / "catalogs").exists()


def test_default_flush_clears_runs_keeps_files_and_removes_folders(tmp_path):
    db_path = str(tmp_path / "k.db")
    _seed_db(db_path)
    app = _make_app_dir(tmp_path)
    rc = main(["--db", db_path, "--app-dir", str(app), "--yes"])
    assert rc == 0
    assert _runs(db_path) == 0          # runs flushed
    assert _files(db_path) == 1         # imported files preserved
    assert not (app / "runs").exists()  # on-disk archive removed
    assert not (app / "catalogs").exists()


def test_full_wipe_removes_database_file(tmp_path):
    db_path = str(tmp_path / "k.db")
    _seed_db(db_path)
    app = _make_app_dir(tmp_path)
    rc = main(["--db", db_path, "--app-dir", str(app), "--full", "--yes"])
    assert rc == 0
    assert not Path(db_path).exists()   # whole DB gone; app recreates empty

    # And it is safe to run against a missing DB.
    rc2 = main(["--db", db_path, "--app-dir", str(app), "--full", "--yes"])
    assert rc2 == 0


def test_default_db_path_uses_env(monkeypatch):
    monkeypatch.setenv("KROMI_DB_PATH", "/tmp/some/where/kromi.db")
    assert default_db_path() == "/tmp/some/where/kromi.db"
