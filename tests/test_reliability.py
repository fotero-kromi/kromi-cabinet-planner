"""Reliability contracts (v34.55, audit reliability table and P2 items).

* A migration that fails half-way used to leave a half-applied schema
  (executescript commits as it goes); every later start then failed with
  "duplicate column" and the app ran without its database. Each migration is
  now one transaction, and an existing database is copied before any pending
  migration runs.
* Two first saves of the same workbook raced on the unique file hash and one
  failed with IntegrityError.
* KROMI_DB_PATH set to a bare file name crashed the page at load.
* Errors the app catches (database copy skipped, deck or optimizer failures,
  unreadable database) left no trace. They now go to a local rotating log.
"""
import os
import shutil
import sqlite3

import pandas as pd
import pytest

from db import store


# ---- migrations --------------------------------------------------------------------

def _migrations_with(tmp_path, extra_name, extra_sql):
    mdir = tmp_path / "migrations"
    shutil.copytree(store._MIGRATIONS_DIR, mdir)
    (mdir / extra_name).write_text(extra_sql, encoding="utf-8")
    return str(mdir)


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_a_failing_migration_leaves_no_half_applied_schema(tmp_path, monkeypatch):
    db_path = str(tmp_path / "m.db")
    store.init_db(db_path).close()
    before = store.current_schema_version(store.connect(db_path))
    bad = ("ALTER TABLE analysis_runs ADD COLUMN half_applied TEXT;\n"
           "ALTER TABLE no_such_table ADD COLUMN y TEXT;\n")
    monkeypatch.setattr(store, "_MIGRATIONS_DIR",
                        _migrations_with(tmp_path, "099_bad.sql", bad))
    with pytest.raises(sqlite3.Error):
        store.init_db(db_path)
    conn = store.connect(db_path)
    assert "half_applied" not in _columns(conn, "analysis_runs")
    assert store.current_schema_version(conn) == before
    conn.close()
    # A retry fails for the real reason again, never "duplicate column".
    with pytest.raises(sqlite3.Error) as err:
        store.init_db(db_path)
    assert "duplicate column" not in str(err.value).lower()


def test_an_existing_database_is_backed_up_before_migrating(tmp_path, monkeypatch):
    db_path = str(tmp_path / "b.db")
    conn = store.init_db(db_path)
    conn.execute("INSERT INTO override_sets (customer, site, active, created_at) "
                 "VALUES ('C', 'S', 1, 'now')")
    conn.commit()
    conn.close()
    good = "ALTER TABLE analysis_runs ADD COLUMN later_column TEXT;\n"
    monkeypatch.setattr(store, "_MIGRATIONS_DIR",
                        _migrations_with(tmp_path, "099_good.sql", good))
    store.init_db(db_path).close()
    backups = [p for p in os.listdir(tmp_path) if p.startswith("b.db.pre-migration")]
    assert len(backups) == 1
    old = sqlite3.connect(str(tmp_path / backups[0]))
    assert old.execute("SELECT COUNT(*) FROM override_sets").fetchone()[0] == 1
    assert "later_column" not in {r[1] for r in old.execute(
        "PRAGMA table_info(analysis_runs)").fetchall()}
    old.close()


def test_a_new_database_needs_no_backup(tmp_path):
    store.init_db(str(tmp_path / "n.db")).close()
    assert not [p for p in os.listdir(tmp_path) if "pre-migration" in p]


# ---- database path ---------------------------------------------------------------------

def test_bare_database_file_name_is_accepted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KROMI_DB_PATH", "kromi.db")
    path = store.default_db_path()
    assert os.path.isabs(path) and path.endswith("kromi.db")


# ---- the first save of a workbook from two sessions at once ----------------------------------

class _RacingConnection:
    """Proxies a connection; right after the first read of uploaded_files, a
    second session stores the same workbook, as two tabs saving at once do."""

    def __init__(self, conn, db_path, sha):
        self._conn, self._db_path, self._sha, self._fired = conn, db_path, sha, False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *exc):
        return self._conn.__exit__(*exc)

    def execute(self, sql, *args):
        cur = self._conn.execute(sql, *args)
        if (not self._fired and "uploaded_files" in sql
                and sql.lstrip().upper().startswith("SELECT")):
            self._fired = True
            other = sqlite3.connect(self._db_path, timeout=0.2)
            try:
                other.execute(
                    "INSERT OR IGNORE INTO uploaded_files (sha256, original_filename, "
                    "uploaded_at) VALUES (?, 'other tab', 'now')", (self._sha,))
                other.commit()
            except sqlite3.OperationalError:
                pass  # this session already holds the write lock: no race
            finally:
                other.close()
        return cur


def test_two_first_saves_of_the_same_workbook_both_succeed(tmp_path):
    from db.persist_run import persist_run, summary_rows_from_plans, tools_from_dataframe
    db_path = str(tmp_path / "race.db")
    conn = store.init_db(db_path)
    cfg = store.get_active_machine_config(conn)
    work = pd.DataFrame([{
        "Code": "A", "Description": "a", "Listing": "Tools", "SizeCategory": "M",
        "ProductCategory": "drills", "SizeCategory_Source": "Heuristic",
        "ProductCategory_Source": "Heuristic", "SystemCategory": "KTC",
        "CabinetType": "Helix", "Spirals_needed": 1, "Carousel_stockpiles": 0,
        "Consumption_pcs": 10.0, "Monthly_packs": 1.0, "SupplyPoint": 1,
    }])
    run_id = persist_run(
        _RacingConnection(conn, db_path, "same-sha"),
        file={"sha256": "same-sha", "original_filename": "w.xlsx", "content": b"x",
              "byte_size": 1},
        run={"machine_config_id": cfg["config_id"], "build_version": "t"},
        tools=tools_from_dataframe(work),
        plan_rows=summary_rows_from_plans([], {}),
        rebalance_events=[],
        execution={"build_version": "t", "inputs_hash": "h"},
    )
    assert run_id > 0
    assert conn.execute("SELECT COUNT(*) FROM uploaded_files").fetchone()[0] == 1
    conn.close()


# ---- the local log -----------------------------------------------------------------------

def test_log_exception_writes_the_traceback(tmp_path, monkeypatch):
    import app_log
    log_file = tmp_path / "logs" / "planner.log"
    monkeypatch.setenv("KROMI_LOG_PATH", str(log_file))
    try:
        raise ValueError("boom in the archive")
    except ValueError as exc:
        app_log.log_exception("Database copy skipped", exc)
    text = log_file.read_text(encoding="utf-8")
    assert "Database copy skipped" in text and "ValueError: boom in the archive" in text
    assert "Traceback" in text


def test_logging_can_be_switched_off(tmp_path, monkeypatch):
    import app_log
    monkeypatch.setenv("KROMI_LOG_PATH", "off")
    assert app_log.log_path() is None
    app_log.log_exception("nothing is written", RuntimeError("x"))   # no error


def test_a_skipped_database_copy_is_logged(tmp_path, monkeypatch):
    import streamlit as st
    from io import BytesIO
    from streamlit.testing.v1 import AppTest
    import db as kdb
    from engine.run_restore import build_seed
    from tests._paths import PLANNER_PAGE

    log_file = tmp_path / "logs" / "planner.log"
    monkeypatch.setenv("KROMI_LOG_PATH", str(log_file))
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "skip.db"))

    def failing_persist(*a, **k):
        raise RuntimeError("disk full while archiving")
    monkeypatch.setattr(kdb, "persist_run", failing_persist)
    st.cache_data.clear()
    df = pd.DataFrame({"ItemCode": ["A1", "A2"], "ItemName": ["Bohrer D5", "Bohrer D6"],
                       "Cons16": [300.0, 600.0]})
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Sheet1")
    seed = build_seed({"cm_code": "ItemCode", "cm_desc1": "ItemName", "cm_cons": "Cons16",
                       "ks_sheet_tools": "Sheet1"}, list(df.columns))
    seed.update({"ks_hide_optional": False, "ks_ai_colmap": False, "_std_special_mapped": False})
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 0, "bytes": bio.getvalue(), "filename": "in.xlsx", "customer": "LgC",
        "site": "LgS", "classifications": {}, "override_mode": "none", "override_set_id": None}
    at.session_state["_pending_restore"] = seed
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception
    captions = " ".join(str(c.value) for c in at.caption)
    assert "Database copy skipped" in captions
    assert "disk full while archiving" in log_file.read_text(encoding="utf-8")


def test_release_ships_the_log_module_and_never_a_backup(tmp_path):
    import zipfile
    from tools.package_release import build_release_zip
    src = tmp_path / "app"
    for rel in ("Home.py", "app_log.py", "engine/plan.py",
                "kromi.db.pre-migration-v4-20260922T000000Z.bak",
                "db/old.db.pre-migration-v3-20260101T000000Z.bak"):
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    names = build_release_zip(src, tmp_path / "r.zip")
    assert "app_log.py" in names
    assert not [n for n in names if n.endswith(".bak")]
    with zipfile.ZipFile(tmp_path / "r.zip") as z:
        assert z.testzip() is None
