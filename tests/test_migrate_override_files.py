"""Contract for the override file-library migration instrument (v34.22).

The v34.20 resolver made database override sets authoritative with the
per-customer file directory as legacy fallback. This instrument moves the
legacy library into the database, under three hard rules pinned here: the
database stays authoritative (a scope that already has a set is skipped, so
stale files can never resurrect over newer corrections); the operator owns
the scope names (folder names are sanitized and lossy, so the dry run emits a
mapping file with folder-derived guesses that the operator corrects before
apply, and the applied set must match the raw names the resolver will look
up); and the files themselves are never modified or deleted (retirement is a
manual step after sign-off).
"""

import pandas as pd
import pytest

from engine.constants import OVERRIDE_COLUMNS


def _write_library(base_dir):
    """Two scopes on disk: a simple one and one already covered in the db."""
    for folder, codes in (("CustA__Main", ["A001", "A002"]),
                          ("CustB__North", ["B001"])):
        d = base_dir / folder
        d.mkdir(parents=True)
        rows = []
        for code in codes:
            row = {c: "" for c in OVERRIDE_COLUMNS}
            row.update({"code": code, "listing": "TOOLS",
                        "product_category_override": "reamers",
                        "reviewed_by": "tech", "reviewed_at": "2026-06-01T08:00:00Z"})
            rows.append(row)
        pd.DataFrame(rows, columns=OVERRIDE_COLUMNS).to_csv(d / "overrides.csv", index=False)
    (base_dir / "Empty__Scope").mkdir()  # folder without a csv: tolerated


@pytest.fixture
def library(tmp_path):
    base = tmp_path / "overrides"
    _write_library(base)
    return base


@pytest.fixture
def dbconn(tmp_path):
    import db as kromi_db
    conn = kromi_db.init_db(str(tmp_path / "mig.db"))
    row = {c: "" for c in OVERRIDE_COLUMNS}
    row.update({"code": "B999", "listing": "TOOLS",
                "size_category_override": "L"})
    kromi_db.save_override_set(
        conn, customer="CustB", site="North", reviewer_name="editor",
        notes="pre-existing", overrides_df=pd.DataFrame([row], columns=OVERRIDE_COLUMNS))
    return conn


def test_dry_run_reports_verdicts_writes_map_and_touches_nothing(library, dbconn, tmp_path):
    from tools.migrate_override_files import plan_migration, scan_library, write_map

    before = sorted(p.relative_to(library).as_posix() for p in library.rglob("*"))
    scopes = scan_library(library)
    assert sorted(s.folder for s in scopes) == ["CustA__Main", "CustB__North", "Empty__Scope"]

    mapping = {s.folder: (s.guessed_customer, s.guessed_site) for s in scopes}
    assert mapping["CustA__Main"] == ("CustA", "Main")

    plan = plan_migration(scopes, dbconn, mapping)
    verdicts = {p.folder: p.verdict for p in plan}
    assert verdicts == {"CustA__Main": "CREATE",
                        "CustB__North": "SKIP_DB_EXISTS",
                        "Empty__Scope": "SKIP_EMPTY"}

    map_path = tmp_path / "migration_map.csv"
    write_map(scopes, map_path)
    m = pd.read_csv(map_path, dtype=str)
    assert list(m.columns) == ["folder", "customer", "site", "rows"]

    after = sorted(p.relative_to(library).as_posix() for p in library.rglob("*"))
    assert before == after, "a dry run must not touch the library"


def test_apply_is_scoped_idempotent_and_resolver_visible(library, dbconn):
    import db as kromi_db
    from tools.migrate_override_files import execute_plan, plan_migration, scan_library

    scopes = scan_library(library)
    # the operator corrects a lossy folder guess to the raw scope names
    mapping = {s.folder: (s.guessed_customer, s.guessed_site) for s in scopes}
    mapping["CustA__Main"] = ("Cust A", "Main")

    plan = plan_migration(scopes, dbconn, mapping)
    created = execute_plan(plan, dbconn)
    assert len(created) == 1 and created[0].folder == "CustA__Main"

    sid = kromi_db.latest_override_set(dbconn, customer="Cust A", site="Main")
    assert sid is not None, "the resolver must find the migrated set by raw names"
    got = kromi_db.override_set_as_dataframe(dbconn, sid)
    assert sorted(got["code"]) == ["A001", "A002"]

    plan2 = plan_migration(scan_library(library), dbconn,
                           {**mapping, "CustA__Main": ("Cust A", "Main")})
    assert all(p.verdict != "CREATE" for p in plan2), "a second pass must be a no-op"

    b = kromi_db.latest_override_set(dbconn, customer="CustB", site="North")
    assert sorted(kromi_db.override_set_as_dataframe(dbconn, b)["code"]) == ["B999"], (
        "the pre-existing database set stays authoritative and untouched"
    )
