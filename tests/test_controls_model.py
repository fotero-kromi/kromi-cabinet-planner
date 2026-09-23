"""Tests for controls_model.py (v33.90) — the portable control model.

Pins the default-detection and summary logic that drives the green-when-changed
buttons and the applied-settings lines, independent of any UI framework.
"""

import pytest

from controls_model import NumberSpec, ControlGroup


def _spec(**kw):
    base = dict(key="k", label="Reserve", default=0.85, min=0.05, max=2.0, step=0.05, help="h")
    base.update(kw)
    return NumberSpec(**base)


def test_is_nondefault_detects_change():
    s = _spec()
    assert not s.is_nondefault(0.85)
    assert s.is_nondefault(0.80)


def test_is_nondefault_tolerates_float_noise():
    s = _spec()
    assert not s.is_nondefault(0.85 + 1e-12)


def test_int_spec_coerces_and_rounds():
    s = _spec(default=3, is_int=True, fmt="{:d}")
    assert s.coerce(3.0) == 3 and isinstance(s.coerce(3.0), int)
    assert s.summarize(5.0) == "Reserve: 5"


def test_summarize_with_suffix():
    s = _spec(label="Carousel buffer", default=0.0, suffix="%", fmt="{:g}")
    assert s.summarize(15.0) == "Carousel buffer: 15%"


def test_group_any_nondefault_and_summary():
    g = ControlGroup("Carousel Controls", (
        _spec(key="depth", label="Stocking depth", default=0.85),
        _spec(key="ceil", label="Fill ceiling", default=100.0, suffix="%", min=10, max=100, step=5),
        _spec(key="minc", label="Min compartments", default=3, is_int=True, fmt="{:d}", min=1, max=20, step=1),
    ))
    # all defaults -> nothing lit, no lines
    state = {}
    assert g.any_nondefault(state) is False
    assert g.summary_lines(state) == []
    # change one -> lit, one line
    state = {"ceil": 85.0}
    assert g.any_nondefault(state) is True
    assert g.summary_lines(state) == ["Fill ceiling: 85%"]
    # change two -> two lines in spec order
    state = {"ceil": 85.0, "depth": 0.80}
    assert g.summary_lines(state) == ["Stocking depth: 0.8", "Fill ceiling: 85%"]


def test_group_current_fills_defaults():
    g = ControlGroup("G", (_spec(key="a", default=1.0), _spec(key="b", default=2.0)))
    assert g.current({"a": 5.0}) == {"a": 5.0, "b": 2.0}


def test_group_spec_lookup():
    g = ControlGroup("G", (_spec(key="a"), _spec(key="b")))
    assert g.spec("a").key == "a"
    with pytest.raises(KeyError):
        g.spec("missing")
