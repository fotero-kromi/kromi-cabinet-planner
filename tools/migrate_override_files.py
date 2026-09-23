"""Migrate the legacy per-customer override file library into database sets.

Since v34.20 the planner resolves the default override source from the
database (newest active set for the exact customer and site), and since
v34.23 the database is the only runtime source: the application no longer
reads the file library at all. This instrument is the bridge that moves a
legacy library into the database, under three hard rules:

1. The database stays authoritative. A scope that already has any set in the
   database is skipped, so a stale file can never resurrect over newer
   corrections saved from the editor.
2. The operator owns the scope names. Folder names are sanitized and lossy
   ("ACME GmbH" becomes "ACME_GmbH"), while the resolver matches raw names,
   so the dry run writes migration_map.csv with folder-derived guesses; edit
   the customer and site columns to the real names before applying.
3. The files are never modified or deleted. Retiring the library is a manual
   step after sign-off; a second run of --apply is a no-op.

Usage (dry run is the default and writes the report plus the map):

    python tools/migrate_override_files.py
    python tools/migrate_override_files.py --apply --map migration_map.csv

--base-dir defaults to pages/overrides next to this repository checkout;
--db-path defaults to the application's own database location (KROMI_DB_PATH
or the local dot-folder), so the applied sets land where the planner reads.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import db as kromi_db  # noqa: E402
from engine.overrides import load_overrides  # noqa: E402


@dataclass
class Scope:
    folder: str
    path: Path
    guessed_customer: str
    guessed_site: str
    frame: pd.DataFrame


@dataclass
class PlanItem:
    folder: str
    customer: str
    site: str
    rows: int
    verdict: str  # CREATE | SKIP_DB_EXISTS | SKIP_EMPTY
    source: Path


def scan_library(base_dir: Path) -> list[Scope]:
    """Every scope folder under the library, with its loaded frame and the
    folder-derived name guesses (the separator between the two sanitized
    components is always a double underscore)."""
    scopes: list[Scope] = []
    if not base_dir.exists():
        return scopes
    for folder in sorted(p for p in base_dir.iterdir() if p.is_dir()):
        if "__" in folder.name:
            cust_guess, site_guess = folder.name.split("__", 1)
        else:
            cust_guess, site_guess = folder.name, ""
        frame = load_overrides(cust_guess, site_guess, base_dir)
        scopes.append(Scope(folder.name, folder, cust_guess, site_guess, frame))
    return scopes


def plan_migration(scopes, conn, mapping) -> list[PlanItem]:
    """One verdict per scope. The mapping carries the operator-confirmed raw
    (customer, site) per folder; missing entries fall back to the guesses."""
    plan: list[PlanItem] = []
    for s in scopes:
        customer, site = mapping.get(s.folder, (s.guessed_customer, s.guessed_site))
        if len(s.frame) == 0:
            verdict = "SKIP_EMPTY"
        elif kromi_db.latest_override_set(
            conn, customer=customer, site=site, active_only=False
        ) is not None:
            verdict = "SKIP_DB_EXISTS"
        else:
            verdict = "CREATE"
        plan.append(PlanItem(s.folder, customer, site, len(s.frame), verdict,
                             s.path / "overrides.csv"))
    return plan


def execute_plan(plan, conn) -> list[PlanItem]:
    """Create one database set per CREATE item; the source files stay as they
    are. Returns the items that were created."""
    created: list[PlanItem] = []
    for item in plan:
        if item.verdict != "CREATE":
            continue
        frame = pd.read_csv(item.source, dtype=str, keep_default_na=False)
        mtime = datetime.fromtimestamp(
            item.source.stat().st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds")
        kromi_db.save_override_set(
            conn,
            customer=item.customer,
            site=item.site,
            reviewer_name="file-migration",
            notes=f"Migrated from {item.source} (file modified {mtime})",
            overrides_df=frame,
        )
        created.append(item)
    return created


def write_map(scopes, map_path: Path) -> None:
    rows = [{"folder": s.folder, "customer": s.guessed_customer,
             "site": s.guessed_site, "rows": len(s.frame)} for s in scopes]
    pd.DataFrame(rows, columns=["folder", "customer", "site", "rows"]).to_csv(
        map_path, index=False
    )


def read_map(map_path: Path) -> dict:
    m = pd.read_csv(map_path, dtype=str, keep_default_na=False)
    return {r["folder"]: (r["customer"], r["site"]) for _, r in m.iterrows()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-dir", type=Path, default=_REPO / "pages" / "overrides")
    ap.add_argument("--db-path", default=kromi_db.default_db_path())
    ap.add_argument("--map", type=Path, default=None,
                    help="operator-corrected migration_map.csv (required for --apply)")
    ap.add_argument("--apply", action="store_true",
                    help="create the database sets; without it, dry run only")
    args = ap.parse_args(argv)

    scopes = scan_library(args.base_dir)
    if not scopes:
        print(f"No scope folders under {args.base_dir}; nothing to do.")
        return 0

    mapping = read_map(args.map) if args.map else {}
    conn = kromi_db.init_db(str(args.db_path))
    try:
        plan = plan_migration(scopes, conn, mapping)
        print(f"Library: {args.base_dir}\nDatabase: {args.db_path}\n")
        for item in plan:
            print(f"  {item.verdict:15s} {item.folder:35s} "
                  f"-> customer='{item.customer}' site='{item.site}' rows={item.rows}")
        if not args.apply:
            map_path = Path.cwd() / "migration_map.csv"
            write_map(scopes, map_path)
            print(f"\nDry run only. Map written to {map_path} — correct the "
                  f"customer/site columns where the folder guess is lossy, then "
                  f"re-run with --apply --map {map_path.name}.")
            return 0
        if args.map is None:
            print("\n--apply requires --map with the operator-confirmed names.")
            return 2
        created = execute_plan(plan, conn)
        print(f"\nCreated {len(created)} set(s). The source files were not "
              f"modified; retire the library manually after sign-off.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
