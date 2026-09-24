"""Shared fixtures for the new app's back-end tests."""
import pytest
from alembic import command
from sqlalchemy.exc import OperationalError

from kromi_api.storage.db import make_engine, make_session_factory
from kromi_api.storage.models import Base
from tools import synthetic_golden as sg

from .conftest_db import alembic_config, database_url_for_tests, empty_tables, reset_schema


@pytest.fixture(scope="session")
def catalog_bytes() -> bytes:
    """The synthetic golden catalog as an Excel upload (sheet "Catalog")."""
    return sg.catalog_bytes(sg.build_catalog())


@pytest.fixture(scope="session")
def manifest() -> dict:
    return sg.load_manifest()["scenarios"]


@pytest.fixture(scope="session")
def db_url() -> str:
    return database_url_for_tests()


@pytest.fixture(scope="session")
def migrated_engine(db_url):
    engine = make_engine(db_url)
    try:
        reset_schema(engine)
    except OperationalError as exc:  # a missing database is an error, never a skip
        raise RuntimeError(
            f"The test PostgreSQL at {db_url} is not reachable. Start it (cloud sessions: "
            "bash tools/cloud_setup.sh) or set KROMI_TEST_DATABASE_URL.") from exc
    command.upgrade(alembic_config(db_url), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(migrated_engine):
    empty_tables(migrated_engine, sorted(Base.metadata.tables))
    return make_session_factory(migrated_engine)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    yield session
    session.rollback()
    session.close()
