"""Runtime configuration, from environment variables only."""

from __future__ import annotations

import os

#: SQLAlchemy URL of the PostgreSQL database (psycopg 3 driver).
DEFAULT_DATABASE_URL = "postgresql+psycopg://kromi:kromi@127.0.0.1:5432/kromi"
#: Uploads above this size are refused before they are read.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def database_url() -> str:
    return os.environ.get("KROMI_DATABASE_URL", DEFAULT_DATABASE_URL)
