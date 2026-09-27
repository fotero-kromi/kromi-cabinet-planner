"""A planning run that cannot go ahead, with a plain reason for the user."""

from __future__ import annotations

from typing import Any


class PlanningError(Exception):
    """``code`` is stable for the front end; ``message`` is shown to the user."""

    def __init__(self, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
