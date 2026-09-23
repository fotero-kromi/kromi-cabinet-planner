"""Portable control model for grouped sidebar controls.

This module is deliberately free of any UI framework import. It describes the
planner's tunable controls as data -- label, default, bounds, help, formatting --
and answers the questions a renderer needs: what is each control's current value,
is a group holding any non-default value (so its button can light up), and what
is the one-line summary of what the user changed.

Keeping this here, separate from Streamlit, means the control definitions and the
"is it non-default / summarise it" logic survive a change of view framework. A
renderer (today a thin Streamlit function, tomorrow whatever) reads these specs
and draws them; the rules for default-detection and summaries live in one place.
"""

from __future__ import annotations

from dataclasses import dataclass

_EPS = 1e-9


@dataclass(frozen=True)
class NumberSpec:
    """One numeric control.

    ``key`` is the persistent state key the renderer binds to. ``suffix`` is
    appended to the value in summaries (e.g. ``%``). ``is_int`` renders/stores an
    integer. ``fmt`` formats the value in the summary line.
    """

    key: str
    label: str
    default: float
    min: float
    max: float
    step: float
    help: str
    fmt: str = "{:g}"
    suffix: str = ""
    is_int: bool = False

    def coerce(self, value: float) -> float:
        return int(round(value)) if self.is_int else float(value)

    def is_nondefault(self, value: float) -> bool:
        return abs(float(value) - float(self.default)) > _EPS

    def summarize(self, value: float) -> str:
        shown = self.fmt.format(self.coerce(value))
        return f"{self.label}: {shown}{self.suffix}"


@dataclass(frozen=True)
class ControlGroup:
    """A named set of controls shown behind one popover button."""

    name: str
    specs: tuple[NumberSpec, ...]

    def current(self, state: dict) -> dict:
        """Resolve each spec's value from ``state``, falling back to its default."""
        return {s.key: s.coerce(state.get(s.key, s.default)) for s in self.specs}

    def any_nondefault(self, state: dict) -> bool:
        return any(s.is_nondefault(state.get(s.key, s.default)) for s in self.specs)

    def summary_lines(self, state: dict) -> list[str]:
        """One line per control that differs from its default."""
        lines = []
        for s in self.specs:
            v = state.get(s.key, s.default)
            if s.is_nondefault(v):
                lines.append(s.summarize(v))
        return lines

    def spec(self, key: str) -> NumberSpec:
        for s in self.specs:
            if s.key == key:
                return s
        raise KeyError(key)
