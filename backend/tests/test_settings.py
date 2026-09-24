"""kromi_api/settings.py: the API's settings map field by field onto the
engine's RunSettings and ColumnMapping, with the engine's defaults and limits."""
import dataclasses

import pytest
from pydantic import ValidationError

from engine.planning_defaults import DEFAULTS, LIMITS
from engine.run_settings import RunSettings
from engine.tool_list import ColumnMapping
from kromi_api import settings as s


def test_planning_fields_are_the_engine_fields():
    assert set(s.PlanningIn.model_fields) == {f.name for f in dataclasses.fields(RunSettings)}


def test_mapping_fields_are_the_engine_fields():
    assert set(s.ColumnMappingIn.model_fields) == {f.name for f in dataclasses.fields(ColumnMapping)}


def test_default_planning_is_the_engine_default():
    assert s.PlanningIn().to_engine() == RunSettings()


def test_planning_converts_lists_to_the_engine_tuples():
    p = s.PlanningIn(optional_thresholds_active=True,
                     per_class_thresholds=[["mills", 2.0], ["drills", 1.5]],
                     restock_categories=["taps"])
    e = p.to_engine()
    assert e.per_class_thresholds == (("drills", 1.5), ("mills", 2.0))
    assert e.restock_categories == ("taps",)


@pytest.mark.parametrize("name", sorted(LIMITS))
def test_the_engine_limits_are_enforced(name):
    low, high = LIMITS[name]
    if name == "header_row":
        field_owner = s.RunRequest
        base = {"sheet": "S", "mapping": {"code": "A", "description": "B", "consumption": "C"}}
    else:
        field_owner = s.PlanningIn
        base = {}
    if low is not None:
        with pytest.raises(ValidationError):
            field_owner(**base, **{name: low - 1})
    if high is not None:
        with pytest.raises(ValidationError):
            field_owner(**base, **{name: high + 1})


def test_only_the_standard_mode_in_this_version():
    with pytest.raises(ValidationError, match="standard operation mode"):
        s.PlanningIn(op_mode="Capped")


def test_unknown_choices_are_refused():
    for field, value in (("sp_mode", "spread"), ("calc_mode", "mixed"),
                         ("year_mode", "odd"), ("dedup_mode", "all")):
        with pytest.raises(ValidationError):
            s.PlanningIn(**{field: value})


def test_unknown_fields_are_refused():
    with pytest.raises(ValidationError):
        s.PlanningIn(helix_treshold=2.0)


def test_mapping_round_trip_and_required_fields():
    m = s.ColumnMappingIn(code="Art", description="Text", consumption="Use", stock="Qty")
    assert m.to_engine() == ColumnMapping(code="Art", description="Text", consumption="Use",
                                          stock="Qty")
    for missing in ("code", "description", "consumption"):
        kwargs = {"code": "A", "description": "B", "consumption": "C"}
        kwargs[missing] = ""
        with pytest.raises(ValidationError):
            s.ColumnMappingIn(**kwargs)


def test_scope_and_export_defaults():
    r = s.RunRequest(sheet="S", mapping={"code": "A", "description": "B", "consumption": "C"})
    assert r.header_row == DEFAULTS.header_row
    assert r.scope.ktc_id == DEFAULTS.ktc_id and r.scope.apply_overrides is DEFAULTS.apply_overrides
    assert r.export.include_planogram is DEFAULTS.include_planogram
    assert r.export.include_technical is DEFAULTS.include_technical
    assert r.program_to_sp == {}
