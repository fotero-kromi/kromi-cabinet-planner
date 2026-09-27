"""Alembic migrations: they build exactly the tables the models describe, and
they can be undone and redone."""
from alembic import command
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from kromi_api.storage.models import Base

from .conftest_db import alembic_config


def test_the_migrated_schema_matches_the_models(migrated_engine):
    from alembic.autogenerate import compare_metadata

    with migrated_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_downgrade_and_upgrade_again(migrated_engine, db_url):
    cfg = alembic_config(db_url)
    command.downgrade(cfg, "base")
    assert set(inspect(migrated_engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(cfg, "head")
    tables = set(inspect(migrated_engine).get_table_names())
    assert {"workbooks", "runs", "run_summaries", "run_buckets", "run_tools",
            "run_files"} <= tables
