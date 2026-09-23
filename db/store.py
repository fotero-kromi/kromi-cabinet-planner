"""Thin data-access layer for the Kromi Cabinet Planner database.

Standard-library ``sqlite3`` only, no third-party dependency. Every database
access in the application goes through this module so a later move to
PostgreSQL is a change of connection and dialect here rather than across the
codebase.

Responsibilities:
  * open a connection with foreign-key enforcement and WAL journaling
  * run pending schema migrations from db/migrations and track what was applied
  * seed the default machine configuration from the engine constants
  * provide the core file and run repositories the workflow needs

Phase 0 deliberately does not touch the calculation path or the Streamlit page.
Nothing in the running application imports this module yet; it is the
foundation that later phases build on.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

_MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
_MIGRATION_RE = re.compile(r"^(\d+)_.*\.sql$")

_DEFAULT_MACHINE_CONFIG_NAME = "Standard Kromi"


def _utc_now() -> str:
    """ISO-8601 UTC timestamp, written by the application for portability."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect(path: str) -> sqlite3.Connection:
    """Open a connection with the project's standing pragmas.

    Foreign keys are enforced per connection (SQLite does not persist this).
    WAL journaling is enabled for better read/write concurrency on local disk.
    Rows are returned as ``sqlite3.Row`` so callers can index by column name.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL is persistent for file-backed databases and a no-op for :memory:.
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            filename   TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _applied_versions(conn: sqlite3.Connection) -> set:
    _ensure_migration_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(r["version"]) for r in rows}


def _migration_files() -> List[tuple]:
    """Return (version, filename, path) for every migration, sorted by version."""
    out: List[tuple] = []
    if not os.path.isdir(_MIGRATIONS_DIR):
        return out
    for fn in os.listdir(_MIGRATIONS_DIR):
        m = _MIGRATION_RE.match(fn)
        if m:
            out.append((int(m.group(1)), fn, os.path.join(_MIGRATIONS_DIR, fn)))
    out.sort(key=lambda t: t[0])
    return out


def _database_file(conn: sqlite3.Connection) -> Optional[str]:
    """Path of the main database file, or None for an in-memory database."""
    for row in conn.execute("PRAGMA database_list").fetchall():
        if row[1] == "main":
            return row[2] or None
    return None


def backup_database(conn: sqlite3.Connection, label: str) -> Optional[str]:
    """Copy the open database next to itself as ``<file>.<label>-<UTC>.bak``.

    Uses SQLite's online backup, so the copy is consistent even in WAL mode.
    Returns the backup path, or None for an in-memory database.
    """
    src = _database_file(conn)
    if not src:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = f"{src}.{label}-{stamp}.bak"
    target = sqlite3.connect(dest)
    try:
        conn.backup(target)
    finally:
        target.close()
    return dest


def migrate(conn: sqlite3.Connection) -> List[int]:
    """Apply every migration not yet recorded, in version order.

    Idempotent: running it again applies nothing. Returns the list of versions
    applied during this call (empty when already up to date).

    v34.55 (audit reliability): each migration runs in one transaction together
    with its schema_migrations record, so a failing statement rolls the whole
    migration back (SQLite DDL is transactional) instead of leaving a
    half-applied schema that made every later start fail with "duplicate
    column". A database that already has migrations is copied before the first
    pending one runs (``<file>.pre-migration-v<N>-<UTC>.bak``).
    """
    done = _applied_versions(conn)
    pending = [m for m in _migration_files() if m[0] not in done]
    if not pending:
        return []
    if done:
        backup_database(conn, f"pre-migration-v{max(done)}")
    applied: List[int] = []
    for version, filename, path in pending:
        with open(path, "r", encoding="utf-8") as fh:
            sql = fh.read()
        record = (
            "INSERT INTO schema_migrations (version, filename, applied_at) VALUES "
            f"({int(version)}, '{filename.replace(chr(39), chr(39) * 2)}', '{_utc_now()}');"
        )
        try:
            conn.executescript(f"BEGIN;\n{sql}\n;\n{record}\nCOMMIT;")
        except sqlite3.Error:
            if conn.in_transaction:
                conn.rollback()
            raise
        applied.append(version)
    return applied


def current_schema_version(conn: sqlite3.Connection) -> int:
    """Highest applied migration version, or 0 if none."""
    done = _applied_versions(conn)
    return max(done) if done else 0


# ---------------------------------------------------------------------------
# Generic write helpers
# ---------------------------------------------------------------------------

def insert_row(conn: sqlite3.Connection, table: str, row: Dict[str, Any]) -> int:
    """Insert one row and return its generated id. Column names come from the
    dict keys, so callers control exactly which columns are written."""
    cols = list(row.keys())
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    cur = conn.execute(
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
        [row[c] for c in cols],
    )
    conn.commit()
    rid = cur.lastrowid
    assert rid is not None  # the INSERT above always sets it
    return int(rid)


def insert_rows(conn: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> int:
    """Bulk-insert rows that share the same columns. Returns the count written.
    Use when the generated ids are not needed immediately."""
    rows = list(rows)
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    conn.executemany(
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
        [[r[c] for c in cols] for r in rows],
    )
    conn.commit()
    return len(rows)


# ---------------------------------------------------------------------------
# Machine configuration (seed + lookup)
# ---------------------------------------------------------------------------

def seed_default_machine_config(conn: sqlite3.Connection) -> int:
    """Insert the default machine configuration from the engine constants if it
    is not already present. Idempotent: returns the existing id on re-run.

    The current code constants become the seed; from here the table is the
    authoritative source, so a run can pin the configuration it used.
    """
    existing = conn.execute(
        "SELECT config_id FROM machine_configurations WHERE name = ?",
        (_DEFAULT_MACHINE_CONFIG_NAME,),
    ).fetchone()
    if existing:
        return int(existing["config_id"])

    # Lazy import so the data layer has no hard import-time coupling to engine.
    from engine import constants as c

    return insert_row(
        conn,
        "machine_configurations",
        {
            "name": _DEFAULT_MACHINE_CONFIG_NAME,
            "helix_spirals_per_cab": int(c.HELIX_SPIRALS_PER_CAB),
            "carousel_slots_per_cab": int(c.CAROUSEL_SLOTS_PER_CAB),
            "locker_a_capacity": int(c.LOCKER_A_CAP),
            "locker_b_capacity": int(c.LOCKER_B_CAP),
            "locker_c_capacity": int(c.LOCKER_C_CAP),
            "carousel_reserve_factor": float(c.CAROUSEL_RESERVE_FACTOR),
            "helix_overfill_factor": float(c.HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR),
            "days_per_month": float(c.DAYS_PER_MONTH),
            "active": 1,
            "created_at": _utc_now(),
        },
    )


def get_active_machine_config(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """Most recent active machine configuration, or None."""
    return conn.execute(
        "SELECT * FROM machine_configurations WHERE active = 1 "
        "ORDER BY config_id DESC LIMIT 1"
    ).fetchone()


# ---------------------------------------------------------------------------
# Files (deduplicated by content hash)
# ---------------------------------------------------------------------------

def get_file_by_hash(conn: sqlite3.Connection, sha256: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM uploaded_files WHERE sha256 = ?", (sha256,)
    ).fetchone()


def get_file(conn: sqlite3.Connection, file_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM uploaded_files WHERE file_id = ?", (file_id,)
    ).fetchone()


def upsert_file(
    conn: sqlite3.Connection,
    *,
    sha256: str,
    original_filename: Optional[str] = None,
    content: Optional[bytes] = None,
    byte_size: Optional[int] = None,
    sheet_tools: Optional[str] = None,
    sheet_ppe: Optional[str] = None,
    row_count: Optional[int] = None,
    first_seen_customer: Optional[str] = None,
    first_seen_ktc_id: Optional[str] = None,
) -> int:
    """Return the id of the file with this content hash, inserting it if new.

    Re-uploading the same catalog reuses the stored file rather than creating a
    second copy, which is what keeps classifications reusable across runs.
    """
    existing = get_file_by_hash(conn, sha256)
    if existing:
        return int(existing["file_id"])
    return insert_row(
        conn,
        "uploaded_files",
        {
            "sha256": sha256,
            "original_filename": original_filename,
            "byte_size": byte_size if byte_size is not None
            else (len(content) if content is not None else None),
            "content": content,
            "sheet_tools": sheet_tools,
            "sheet_ppe": sheet_ppe,
            "row_count": row_count,
            "first_seen_customer": first_seen_customer,
            "first_seen_ktc_id": first_seen_ktc_id,
            "uploaded_at": _utc_now(),
        },
    )


# ---------------------------------------------------------------------------
# Runs (the hub)
# ---------------------------------------------------------------------------

def insert_run(
    conn: sqlite3.Connection,
    *,
    file_id: int,
    machine_config_id: Optional[int] = None,
    build_version: Optional[str] = None,
    customer: Optional[str] = None,
    site: Optional[str] = None,
    ktc_id: Optional[str] = None,
    calc_mode: Optional[str] = None,
    operational_mode: Optional[str] = None,
    max_carousels: Optional[int] = None,
    supply_points: Optional[int] = None,
    sp_mode: Optional[str] = None,
    settings_json: Optional[str] = None,
    applied_override_set_id: Optional[int] = None,
    status: str = "completed",
    notes: Optional[str] = None,
) -> int:
    """Insert one analysis run (the hub row) and return its id."""
    return insert_row(
        conn,
        "analysis_runs",
        {
            "file_id": file_id,
            "machine_config_id": machine_config_id,
            "build_version": build_version,
            "customer": customer,
            "site": site,
            "ktc_id": ktc_id,
            "calc_mode": calc_mode,
            "operational_mode": operational_mode,
            "max_carousels": max_carousels,
            "supply_points": supply_points,
            "sp_mode": sp_mode,
            "settings_json": settings_json,
            "applied_override_set_id": applied_override_set_id,
            "status": status,
            "notes": notes,
            "created_at": _utc_now(),
        },
    )


def get_run(conn: sqlite3.Connection, run_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM analysis_runs WHERE run_id = ?", (run_id,)
    ).fetchone()


def search_runs(
    conn: sqlite3.Connection,
    *,
    customer: Optional[str] = None,
    site: Optional[str] = None,
    limit: int = 50,
) -> List[sqlite3.Row]:
    """Most recent runs, optionally filtered by customer and/or site.

    Matching is case-insensitive and substring-based, which is what the
    landing-page search needs. Results are newest first.
    """
    clauses: List[str] = []
    params: List[Any] = []
    if customer:
        clauses.append("LOWER(customer) LIKE ?")
        params.append(f"%{customer.lower()}%")
    if site:
        clauses.append("LOWER(site) LIKE ?")
        params.append(f"%{site.lower()}%")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(int(limit))
    sql = (
        "SELECT * FROM analysis_runs "
        f"{where} ORDER BY created_at DESC, run_id DESC LIMIT ?"
    )
    return conn.execute(sql, params).fetchall()


# ---------------------------------------------------------------------------
# One-call bootstrap
# ---------------------------------------------------------------------------

def init_db(path: str) -> sqlite3.Connection:
    """Open the database, apply migrations, and seed the default machine
    configuration. The single entry point a caller needs to obtain a ready
    connection."""
    conn = connect(path)
    migrate(conn)
    seed_default_machine_config(conn)
    return conn


def default_db_path() -> str:
    """Local, non-synced path for the database, overridable with KROMI_DB_PATH.
    Shared by the page and the archive importer so they target the same file.

    Keep this file off cloud-synced folders (OneDrive, Dropbox, Google Drive).
    SQLite holds short-lived file locks during writes; a sync client that copies
    or replaces the file mid-write, or that syncs writes made on two machines,
    can corrupt the database. The default lives under the user home in a
    dot-folder for that reason. If KROMI_DB_PATH must point inside a synced tree,
    run the app on one machine at a time and let the sync settle before opening
    it elsewhere. Never run two instances against the same synced file at once.
    """
    env = os.getenv("KROMI_DB_PATH")
    if env:
        # A bare file name used to crash (os.makedirs("")); resolve it
        # against the working folder (v34.55).
        path = os.path.abspath(os.path.expanduser(env))
    else:
        path = os.path.join(
            os.path.expanduser("~"), ".kromi_cabinet_planner", "kromi.db"
        )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path
