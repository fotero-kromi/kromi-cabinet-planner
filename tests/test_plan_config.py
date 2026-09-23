"""Tests for PlanConfig (engine/plan_config.py).

PlanConfig bundles the two run-time sizing factors into one frozen object built
once per run, replacing the mutable module globals the page used to thread (and
the source of the Helix overfill bug). These tests pin its contract: defaults
match the engine constants, instances are immutable, and custom values stick.
"""

import dataclasses

import pytest

from engine.plan_config import PlanConfig
from engine.constants import (
    HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR,
    CAROUSEL_RESERVE_FACTOR,
)


def test_defaults_match_engine_constants():
    cfg = PlanConfig()
    assert cfg.helix_overfill_factor == HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR
    assert cfg.carousel_reserve_factor == CAROUSEL_RESERVE_FACTOR


def test_is_frozen():
    cfg = PlanConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.helix_overfill_factor = 2.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.carousel_reserve_factor = 0.5


def test_custom_values_stick():
    cfg = PlanConfig(helix_overfill_factor=1.25, carousel_reserve_factor=0.9)
    assert cfg.helix_overfill_factor == 1.25
    assert cfg.carousel_reserve_factor == 0.9


def test_equality_by_value():
    assert PlanConfig(1.1, 0.85) == PlanConfig(1.1, 0.85)
    assert PlanConfig(1.1, 0.85) != PlanConfig(1.2, 0.85)


def test_config_value_equals_old_global_for_any_ui_input():
    # The page builds PlanConfig(helix_overfill_factor=float(ui_h), ...). The old
    # globals were helix_overfill_factor = float(ui_h). So the config field equals
    # the old global for any UI value -- the migration is value-preserving.
    for ui_h, ui_c in [("1.10", "0.85"), ("1.25", "0.70"), (1.0, 1.5)]:
        cfg = PlanConfig(helix_overfill_factor=float(ui_h),
                         carousel_reserve_factor=float(ui_c))
        assert cfg.helix_overfill_factor == float(ui_h)
        assert cfg.carousel_reserve_factor == float(ui_c)
