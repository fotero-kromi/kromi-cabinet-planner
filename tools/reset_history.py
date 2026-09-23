#!/usr/bin/env python3
"""Reset the Kromi Cabinet Planner run history.

Flushes saved planning runs so the app starts from a clean history. By default
it deletes the database run records (their snapshot children cascade) and the
on-disk run and catalog folders, while keeping imported files, AI
classifications, and technician overrides so no AI work or corrections are lost.

The tool is dry-run by default and prints what it would remove. Pass --yes to perform
the deletion. Pass --full to wipe the entire database (every table) by
deleting the database file; the app recreates an empty one on next start.

This script uses only the Python standard library so it keeps working after the
file-archive code is removed from the app.

Usage:
    python tools/reset_history.py                  # dry run against the default DB
    python tools/reset_history.py --yes            # flush runs + remove runs/ and catalogs/
    python tools/reset_history.py --full --yes     # wipe the whole database
    python tools/reset_history.py --db PATH --yes  # target an explicit database file
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Optional, Sequence


def default_db_path() -> str:
    """The database path the app uses: KROMI_DB_PATH, else a per-user folder."""
    env = os.getenv("KROMI_DB_PATH")
    if env:
        return env
    return str(Path.home() / ".kromi_cabinet_planner" / "kromi.db")


def _count(conn: sqlite3.Connection, table: str) -> Optional[int]:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.Error:
        return None


def _dir_item_count(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    return sum(1 for _ in path.iterdir())


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Reset the Kromi Cabinet Planner run history."
    )
    ap.add_argument("--db", default=default_db_path(),
                    help="database file to reset (defaults to the app's path)")
    ap.add_argument("--app-dir",
                    default=str(Path(__file__).resolve().parent.parent),
                    help="app directory that holds runs/ and catalogs/")
    ap.add_argument("--yes", action="store_true",
                    help="perform the deletion (otherwise this is a dry run)")
    ap.add_argument("--full", action="store_true",
                    help="wipe the entire database, not just runs")
    args = ap.parse_args(argv)

    db_path = args.db
    app_dir = Path(args.app_dir)
    runs_dir = app_dir / "runs"
    catalogs_dir = app_dir / "catalogs"

    db_exists = os.path.exists(db_path)
    print(f"Database: {db_path}")
    if db_exists:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys=ON")
        print(f"  analysis_runs:  {_count(conn, 'analysis_runs')}")
        print(f"  uploaded_files: {_count(conn, 'uploaded_files')}")
        conn.close()
    else:
        print("  (no database file yet)")

    for label, path in (("run archive", runs_dir), ("catalog folder", catalogs_dir)):
        n = _dir_item_count(path)
        print(f"On-disk {label} ({path}): "
              + ("absent" if n is None else f"{n} item(s)"))

    if not args.yes:
        tail = "." if args.full else " (add --full to wipe the whole database)."
        print("\nDRY RUN — nothing deleted. Re-run with --yes to apply" + tail)
        return 0

    if args.full:
        if db_exists:
            os.remove(db_path)
            print(f"\nDeleted database file: {db_path}")
        else:
            print("\nNo database file to delete.")
    elif db_exists:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("DELETE FROM analysis_runs")
        conn.commit()
        remaining = _count(conn, "analysis_runs")
        conn.close()
        print(f"\nFlushed analysis_runs (remaining: {remaining}). "
              "Files, classifications, and overrides were kept.")

    for path in (runs_dir, catalogs_dir):
        if path.exists():
            shutil.rmtree(path)
            print(f"Removed folder: {path}")

    print("\nDone. The app recreates an empty database (and any needed folders) "
          "on next start.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
