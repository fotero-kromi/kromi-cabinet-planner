"""The FastAPI application.

    uvicorn kromi_api.main:app      (with KROMI_DATABASE_URL set)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, sessionmaker

from . import config
from .api.routes import router
from .storage.db import make_engine, make_session_factory

#: The version of the HTTP API (the OpenAPI ``info.version``). The engine build
#: is reported by ``/api/v1/health``; it stays out of the schema, so a release
#: on main does not change the schema the front-end client is generated from.
API_VERSION = "1"


def create_app(session_factory: sessionmaker[Session] | None = None,
               frontend_dir: Path | None = None) -> FastAPI:
    """The app; tests pass their own session factory (a test database) and
    front-end folder."""
    app = FastAPI(title="Kromi Cabinet Planner", version=API_VERSION,
                  openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs", redoc_url=None)
    app.state.session_factory = (session_factory if session_factory is not None
                                 else make_session_factory(make_engine(config.database_url())))
    app.include_router(router)
    # The built front end at "/", after the API so /api/... always reaches the
    # router (an unknown API path stays a JSON 404). Starlette refuses paths
    # outside the folder.
    pages = frontend_dir if frontend_dir is not None else config.frontend_dir()
    if (pages / "index.html").is_file():
        app.mount("/", StaticFiles(directory=pages, html=True), name="frontend")
    return app


app = create_app()
