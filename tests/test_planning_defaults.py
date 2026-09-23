"""engine/planning_defaults.py (v34.61): the setting defaults and choice labels
that every front end reads, so the Streamlit page and the new app cannot start
from different values.
"""
import dataclasses

import pytest

from engine import planning_defaults as pd_
from engine.fixed_config import FIXED_MODE
from engine.sizing_factors import (
    CAROUSEL_RESERVE_FACTOR,
    HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR,
    SP_MODE_PARTITION,
    SP_MODE_REPLICATE,
)

D = pd_.DEFAULTS


def test_the_defaults_are_the_validated_values():
    assert D.header_row == 1
    assert D.use_description_2 is True
    assert D.year_mode == "all_rows"
    assert D.dedup_mode == "code_supplier"
    assert D.ktc_threshold == 1.0
    assert D.insert_pack_units == 10
    assert D.helix_threshold == 6.0
    assert D.consumption_months == 12.0
    assert D.helix_overfill_factor == HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR == 1.10
    assert D.min_carousel_allocation == 3
    assert D.coverage_days == 20 and D.coverage_days_special == 20
    assert D.special_ktc is False
    assert D.carousel_reserve_factor == CAROUSEL_RESERVE_FACTOR == 0.85
    assert D.carousel_fill_ceiling == 1.0
    assert D.enable_rebalancer is True
    assert D.underuse_threshold_pct == 30.0
    assert D.capacity_buffer_pct == 15.0
    assert D.pack_hint_extraction is True
    assert D.bulk_routing is False
    assert D.force_screws_kanban is False
    assert D.n_supply_points == 1
    assert D.sp_mode == SP_MODE_REPLICATE
    assert D.calc_mode == pd_.CALC_COMBINED
    assert D.op_mode == pd_.OP_STANDARD == ""
    assert D.max_carousels == 2
    assert D.fixed_headroom_pct == 10.0
    assert D.fixed_allow_spill is True
    assert D.fixed_stock_promotion is False
    assert D.fixed_stock_months == 3.0
    assert D.numbering_system == "Kanban"
    assert D.ktc_id == "191"
    assert D.apply_overrides is True
    assert D.include_planogram is True
    assert D.include_technical is False


def test_the_number_types_match_the_controls():
    """A float default stays a float and a count stays an int, so a number
    control keeps its step behaviour."""
    floats = {"ktc_threshold", "helix_threshold", "consumption_months",
              "helix_overfill_factor", "carousel_reserve_factor", "carousel_fill_ceiling",
              "underuse_threshold_pct", "capacity_buffer_pct", "fixed_headroom_pct",
              "fixed_stock_months"}
    ints = {"header_row", "insert_pack_units", "min_carousel_allocation", "coverage_days",
            "coverage_days_special", "n_supply_points", "max_carousels"}
    for name in floats:
        assert type(getattr(D, name)) is float, name
    for name in ints:
        assert type(getattr(D, name)) is int, name


def test_the_defaults_cannot_be_changed_at_runtime():
    with pytest.raises(dataclasses.FrozenInstanceError):
        D.ktc_threshold = 2.0  # type: ignore[misc]


def test_every_default_lies_within_its_limits():
    for name, (low, high) in pd_.LIMITS.items():
        value = getattr(D, name)
        assert low is None or value >= low, name
        assert high is None or value <= high, name


def test_fixed_machine_defaults():
    assert pd_.FIXED_MACHINE_KINDS == (
        ("helix", "Helix", 1), ("carousel", "Carousel", 1),
        ("locker_a", "Locker A", 0), ("locker_b", "Locker B", 0),
        ("locker_c", "Locker C", 0))
    assert pd_.FIXED_MAX_SUPPLY_POINTS == 10


def test_the_labels_are_the_page_options_in_order():
    assert list(pd_.OP_MODE_LABELS) == ["", "Helix", "Carousel", "Capped", FIXED_MODE,
                                        "NumberingOnly"]
    assert pd_.OP_MODE_LABELS[""] == "Standard (best fit per tool)"
    assert pd_.OP_MODE_LABELS[FIXED_MODE] == "Fixed configuration (existing machines)"
    assert list(pd_.SP_MODE_LABELS) == [SP_MODE_REPLICATE, SP_MODE_PARTITION]
    assert pd_.SP_MODE_LABELS[SP_MODE_REPLICATE].startswith("Replicate \u2014 ")
    assert pd_.CALC_MODE_LABELS == {
        "combined": "Combined (one vending machine plan for both)",
        "separated": "Separated (Tools and PPE each get their own plan)",
    }
    assert pd_.YEAR_MODE_LABELS == {"all_rows": "Use all rows",
                                    "latest_year_only": "Keep latest year only"}
    assert pd_.DEDUP_MODE_LABELS == {"none": "No deduplication",
                                     "code": "Deduplicate by Code",
                                     "code_supplier": "Deduplicate by Code + Supplier"}
    assert list(pd_.NUMBERING_SYSTEM_LABELS) == ["Kanban", "KTC"]


def test_every_default_choice_has_a_label():
    assert D.op_mode in pd_.OP_MODE_LABELS
    assert D.sp_mode in pd_.SP_MODE_LABELS
    assert D.calc_mode in pd_.CALC_MODE_LABELS
    assert D.year_mode in pd_.YEAR_MODE_LABELS
    assert D.dedup_mode in pd_.DEDUP_MODE_LABELS
    assert D.numbering_system in pd_.NUMBERING_SYSTEM_LABELS


def test_label_index_and_token_round_trip():
    for labels in (pd_.OP_MODE_LABELS, pd_.SP_MODE_LABELS, pd_.CALC_MODE_LABELS,
                   pd_.YEAR_MODE_LABELS, pd_.DEDUP_MODE_LABELS, pd_.NUMBERING_SYSTEM_LABELS):
        for i, (token, label) in enumerate(labels.items()):
            assert pd_.label_index(labels, token) == i
            assert pd_.token_for(labels, label) == token


def test_an_unknown_label_falls_back():
    assert pd_.token_for(pd_.OP_MODE_LABELS, "no such mode", default="") == ""
    with pytest.raises(KeyError):
        pd_.token_for(pd_.DEDUP_MODE_LABELS, "no such mode")
