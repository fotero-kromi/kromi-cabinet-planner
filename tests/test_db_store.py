"""Phase 0 data-layer tests.

Cover the foundation only: migrations apply and are idempotent, the machine
configuration seeds from the engine constants without duplicating, files
deduplicate by content hash, runs round-trip and search correctly, and foreign
keys are enforced. None of this touches the calculation path.
"""

import os
import sqlite3

import pytest

import db
from db import store


_EXPECTED_TABLES = {
    "uploaded_files",
    "machine_configurations",
    "tool_records",
    "tool_classifications",
    "override_sets",
    "overrides",
    "analysis_runs",
    "cabinet_calculations",
    "cabinet_plan_summary",
    "rebalance_events",
    "engine_executions",
    "validation_results",
    "ai_training_feedback",
}


@pytest.fixture()
def conn(tmp_path):
    """A fresh migrated + seeded database on a temp file per test."""
    path = os.path.join(str(tmp_path), "test.db")
    c = store.init_db(path)
    yield c
    c.close()


def _table_names(c) -> set:
    rows = c.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {r["name"] for r in rows}


# --- migrations ---

def test_migrate_creates_all_tables(conn):
    names = _table_names(conn)
    assert _EXPECTED_TABLES.issubset(names)
    assert "schema_migrations" in names


def test_schema_version_matches_latest_migration(conn):
    from db.store import _migration_files
    latest = max(v for v, _, _ in _migration_files())
    assert store.current_schema_version(conn) == latest


def test_migrate_is_idempotent(conn):
    # Already migrated by the fixture; a second call applies nothing.
    before = store.current_schema_version(conn)
    applied = store.migrate(conn)
    assert applied == []
    assert store.current_schema_version(conn) == before


def test_all_migrations_recorded(conn):
    from db.store import _migration_files
    expected = sorted(v for v, _, _ in _migration_files())
    rows = conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    versions = [int(r["version"]) for r in rows]
    assert versions == expected


# --- machine configuration seed ---

def test_seed_matches_engine_constants(conn):
    from engine import constants as c
    cfg = store.get_active_machine_config(conn)
    assert cfg is not None
    assert cfg["name"] == "Standard Kromi"
    assert cfg["helix_spirals_per_cab"] == int(c.HELIX_SPIRALS_PER_CAB)
    assert cfg["carousel_slots_per_cab"] == int(c.CAROUSEL_SLOTS_PER_CAB)
    assert cfg["locker_a_capacity"] == int(c.LOCKER_A_CAP)
    assert cfg["locker_b_capacity"] == int(c.LOCKER_B_CAP)
    assert cfg["locker_c_capacity"] == int(c.LOCKER_C_CAP)
    assert abs(cfg["carousel_reserve_factor"] - float(c.CAROUSEL_RESERVE_FACTOR)) < 1e-9
    assert abs(cfg["helix_overfill_factor"] - float(c.HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR)) < 1e-9
    assert abs(cfg["days_per_month"] - float(c.DAYS_PER_MONTH)) < 1e-9


def test_seed_is_idempotent(conn):
    first = store.seed_default_machine_config(conn)
    second = store.seed_default_machine_config(conn)
    assert first == second
    n = conn.execute("SELECT COUNT(*) AS n FROM machine_configurations").fetchone()["n"]
    assert n == 1


# --- file deduplication ---

def test_upsert_file_inserts_then_dedups_by_hash(conn):
    fid1 = store.upsert_file(conn, sha256="abc123", original_filename="cat.xlsx",
                             content=b"x" * 10, first_seen_customer="PlantA",
                             first_seen_ktc_id="191")
    fid2 = store.upsert_file(conn, sha256="abc123", original_filename="cat-again.xlsx")
    assert fid1 == fid2  # same content hash -> same row
    fid3 = store.upsert_file(conn, sha256="def456", original_filename="other.xlsx")
    assert fid3 != fid1
    n = conn.execute("SELECT COUNT(*) AS n FROM uploaded_files").fetchone()["n"]
    assert n == 2


def test_get_file_round_trip(conn):
    fid = store.upsert_file(conn, sha256="hash1", original_filename="c.xlsx",
                            content=b"binary-bytes", row_count=409,
                            first_seen_customer="PlantA", first_seen_ktc_id="191")
    row = store.get_file(conn, fid)
    assert row["original_filename"] == "c.xlsx"
    assert row["row_count"] == 409
    assert row["byte_size"] == len(b"binary-bytes")
    assert bytes(row["content"]) == b"binary-bytes"
    assert store.get_file_by_hash(conn, "hash1")["file_id"] == fid


# --- runs ---

def test_insert_and_get_run(conn):
    fid = store.upsert_file(conn, sha256="h", original_filename="c.xlsx")
    cfg = store.get_active_machine_config(conn)
    rid = store.insert_run(conn, file_id=fid, machine_config_id=cfg["config_id"],
                           build_version="v33.45", customer="PlantA", site="P1",
                           operational_mode="Helix", settings_json='{"buffer": 15}')
    run = store.get_run(conn, rid)
    assert run["customer"] == "PlantA"
    assert run["operational_mode"] == "Helix"
    assert run["build_version"] == "v33.45"
    assert run["settings_json"] == '{"buffer": 15}'


def test_search_runs_filters_and_orders(conn):
    fid = store.upsert_file(conn, sha256="h", original_filename="c.xlsx")
    store.insert_run(conn, file_id=fid, customer="PlantA", site="P1")
    store.insert_run(conn, file_id=fid, customer="PlantB", site="P2")
    store.insert_run(conn, file_id=fid, customer="PlantA", site="P3")

    by_customer = store.search_runs(conn, customer="planta")  # case-insensitive
    assert len(by_customer) == 2
    assert all(r["customer"] == "PlantA" for r in by_customer)

    by_site = store.search_runs(conn, site="P2")
    assert len(by_site) == 1
    assert by_site[0]["customer"] == "PlantB"

    both = store.search_runs(conn, customer="PlantA", site="P3")
    assert len(both) == 1


def test_search_runs_newest_first(conn):
    fid = store.upsert_file(conn, sha256="h", original_filename="c.xlsx")
    r1 = store.insert_run(conn, file_id=fid, customer="PlantA")
    r2 = store.insert_run(conn, file_id=fid, customer="PlantA")
    runs = store.search_runs(conn, customer="PlantA")
    # Newest first: the higher run_id (inserted later) comes first.
    assert runs[0]["run_id"] == max(r1, r2)


# --- foreign key enforcement ---

def test_foreign_keys_enforced_on_run(conn):
    # A run referencing a non-existent file must be rejected.
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_run(conn, file_id=999999, customer="PlantA")


def test_foreign_keys_enforced_on_override_row(conn):
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_row(conn, "overrides", {
            "set_id": 999999, "tool_code": "X", "field": "size",
            "value": "M", "created_at": "2026-01-01T00:00:00+00:00",
        })


# --- generic helpers ---

def test_insert_rows_bulk(conn):
    fid = store.upsert_file(conn, sha256="h", original_filename="c.xlsx")
    rows = [
        {"file_id": fid, "code": f"T{i}", "description": "tool", "listing": "Tools"}
        for i in range(5)
    ]
    n = store.insert_rows(conn, "tool_records", rows)
    assert n == 5
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM tool_records WHERE file_id = ?", (fid,)
    ).fetchone()["n"]
    assert count == 5


def test_init_db_bootstraps(tmp_path):
    path = os.path.join(str(tmp_path), "boot.db")
    c = store.init_db(path)
    try:
        from db.store import _migration_files
        latest = max(v for v, _, _ in _migration_files())
        assert store.current_schema_version(c) == latest
        assert store.get_active_machine_config(c) is not None
    finally:
        c.close()
