"""The FastAPI application.

    uvicorn kromi_api.main:app      (with KROMI_DATABASE_URL set)
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from engine.build_info import BUILD

from . import config
from .api.routes import router
from .storage.db import make_engine, make_session_factory


def create_app(session_factory: sessionmaker[Session] | None = None) -> FastAPI:
    """The app; tests pass their own session factory (a test database)."""
    app = FastAPI(title="Kromi Cabinet Planner", version=BUILD,
                  openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs", redoc_url=None)
    app.state.session_factory = (session_factory if session_factory is not None
                                 else make_session_factory(make_engine(config.database_url())))
    app.include_router(router)
    return app


app = create_app()
