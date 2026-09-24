"""A real PostgreSQL for the tests (never a SQLite stand-in).

The URL comes from KROMI_TEST_DATABASE_URL; the default is the local test
database tools/cloud_setup.sh starts in cloud sessions. CI runs a PostgreSQL 18
service container. The schema is rebuilt from the migrations once per test
session and every table is emptied before each test that uses the database.
"""
from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine, text

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_TEST_URL = "postgresql+psycopg://kromi@127.0.0.1:5432/kromi_test"


def database_url_for_tests() -> str:
    return os.environ.get("KROMI_TEST_DATABASE_URL", DEFAULT_TEST_URL)


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "kromi_api" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def reset_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def empty_tables(engine: Engine, tables: list[str]) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"))
