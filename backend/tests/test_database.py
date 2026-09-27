"""The test database is a real PostgreSQL of the expected major version."""
import os

from sqlalchemy import text


def test_the_database_is_postgresql_of_the_expected_version(migrated_engine):
    with migrated_engine.connect() as conn:
        num = int(conn.execute(text("SHOW server_version_num")).scalar_one())
    major = num // 10000
    # CI pins major 18 (the same image tag as the Docker setup); cloud sessions
    # use the PostgreSQL the image provides.
    expected = os.environ.get("KROMI_EXPECT_POSTGRES_MAJOR")
    if expected:
        assert major == int(expected)
    assert major >= 16
