"""Executing a queued run: plan, build the workbook, store everything.

Runs execute in the background after the API has answered; the run's status in
the database is what the browser polls. At this user count that small job
table is enough; a separate worker process can take this function over later.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from .services import export, planning
from .services.errors import PlanningError
from .settings import RunRequest
from .storage import repository as repo
from .storage.db import session_scope
from .storage.models import Run

log = logging.getLogger("kromi_api.runner")


def result_filename(run_id: int) -> str:
    return f"KromiPlanner_Run{run_id}_Result.xlsx"


def execute_run(run_id: int, factory: sessionmaker[Session]) -> None:
    """Carry out run ``run_id``; every outcome ends in 'succeeded' or 'failed'."""
    with session_scope(factory) as db:
        run = db.get(Run, run_id)
        if run is None or run.status != "queued":
            return
        repo.mark_running(db, run)
    try:
        with session_scope(factory) as db:
            run = db.get(Run, run_id)
            if run is None:  # deleted while queued
                return
            raw = repo.workbook_bytes(db, run.workbook_id)
            if raw is None:
                raise PlanningError("missing_workbook", "The uploaded workbook is no longer stored.")
            request = RunRequest.model_validate(run.settings)
            outcome = planning.run(raw, request)
            book = export.result_workbook(outcome, request, timestamp=datetime.now(UTC))
            repo.save_result(db, run, outcome, book, filename=result_filename(run_id))
    except PlanningError as exc:
        with session_scope(factory) as db:
            run = db.get(Run, run_id)
            if run is not None:
                repo.mark_failed(db, run, exc.code, exc.message, exc.details)
    except Exception as exc:  # noqa: BLE001 - every failure is recorded, never lost
        log.exception("Run %s failed", run_id)
        with session_scope(factory) as db:
            run = db.get(Run, run_id)
            if run is not None:
                repo.mark_failed(db, run, "internal_error",
                                 "The run failed unexpectedly; the error was logged.",
                                 {"type": type(exc).__name__})
