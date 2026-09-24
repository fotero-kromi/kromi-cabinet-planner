"""Runtime configuration, from environment variables only."""

from __future__ import annotations

import os
from pathlib import Path

#: SQLAlchemy URL of the PostgreSQL database (psycopg 3 driver).
DEFAULT_DATABASE_URL = "postgresql+psycopg://kromi:kromi@127.0.0.1:5432/kromi"
#: Uploads above this size are refused before they are read.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def database_url() -> str:
    return os.environ.get("KROMI_DATABASE_URL", DEFAULT_DATABASE_URL)


def frontend_dir() -> Path:
    """The built front end the app serves at ``/`` (``npm run build`` output).

    ``KROMI_FRONTEND_DIR`` names it (the Docker image sets it); by default it is
    ``frontend/dist`` in the repository. Without a build only the API runs.
    """
    configured = os.environ.get("KROMI_FRONTEND_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"
