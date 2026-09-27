"""One planning run: uploaded workbook + settings -> the planner's result.

Every step is an engine function, called in the order the Streamlit page
calls it (so the parity oracle can hold):

    read sheet -> build_tool_list -> override scope -> programme supply points
    -> prepare_planning_base -> classification columns -> heuristics (no AI)
    -> effective_settings -> build_plan_params -> run_plan

This version plans the standard mode from one sheet, without AI, stored
classifications or technician overrides (the new app starts with an empty
database, so none of them could apply yet).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from engine.boundary import apply_post_ai_safety, apply_pre_ai_heuristics
from engine.constants import OVERRIDE_COLUMNS
from engine.plan import PlanResult, run_plan
from engine.preprocessing import prepare_planning_base
from engine.run_settings import (
    RunSettings,
    build_plan_params,
    effective_settings,
    program_mapping_active,
)
from engine.tool_list import (
    ColumnMapping,
    add_classification_audit_columns,
    assign_supply_points,
    build_tool_list,
    distinct_programs,
    effective_mapping,
    mapping_collisions,
    resolve_override_scope,
    unassigned_programs,
)

from ..settings import RunRequest
from .errors import PlanningError
from .workbook import read_sheet


@dataclass
class PlanOutcome:
    """A finished run: the planner's result, untouched, and what it was built from."""

    request: RunRequest
    settings: RunSettings  # after the mode rules
    mapping: ColumnMapping  # as planned
    customer: str
    site: str
    base_info: dict
    result: PlanResult
    program_mapping_active: bool
    program_to_sp: dict[str, int]
    notes: list[str] = field(default_factory=list)


def run(raw: bytes, request: RunRequest) -> PlanOutcome:
    """Plan ``raw`` (an .xlsx upload) with ``request``; raise PlanningError when it cannot."""
    use_desc2 = request.planning.use_description_2
    mapping = effective_mapping(request.mapping.to_engine(), use_description_2=use_desc2)
    collisions = mapping_collisions(mapping)
    if collisions:
        raise PlanningError(
            "mapping_conflict",
            "The same source column is mapped to more than one field. Pick one field per column.",
            collisions)

    notes: list[str] = []
    tools = build_tool_list(read_sheet(raw, request.sheet, request.header_row), None,
                            mapping, use_description_2=use_desc2)
    if tools.blocking:
        raise PlanningError(
            "missing_columns",
            "The sheet does not contain the mapped article code or consumption column.",
            [{"listing": m.listing, "missing": [src for src, _dst in m.missing]}
             for m in tools.missing])
    for gap in tools.missing:
        notes.append(f"The {gap.listing} sheet does not contain the mapped column(s) "
                     + ", ".join(f"'{src}'" for src, _dst in gap.missing)
                     + "; those fields stay empty.")
    if len(tools.dropped_empty_codes):
        notes.append(f"{len(tools.dropped_empty_codes)} row(s) without an article code "
                     "were left out.")
    work = tools.work

    customer, site, _sites = resolve_override_scope(
        request.scope.customer, request.scope.site, work, site_mapped=bool(mapping.site))

    planning = request.planning.to_engine()
    active = program_mapping_active(work, mapping, n_supply_points=planning.n_supply_points,
                                    op_mode=planning.op_mode)
    program_to_sp: dict[str, int] = {}
    if active:
        program_to_sp = dict(request.program_to_sp)
        missing = unassigned_programs(distinct_programs(work), program_to_sp)
        if missing:
            raise PlanningError("unassigned_programs",
                                "Every programme needs a supply point before planning.",
                                {"programs": missing})
        assign_supply_points(work, program_to_sp)

    has_year = bool(work["Year"].notna().any()) if "Year" in work.columns else False
    planning_base, base_info = prepare_planning_base(
        work, dedup_mode=planning.dedup_mode, year_mode=planning.year_mode, has_year=has_year)
    if len(planning_base) == 0:
        raise PlanningError(
            "empty_planning_base",
            "No usable rows after preprocessing: the sheet has no data rows, or the column "
            "mapped as the article code is empty.")

    work = planning_base.copy()
    add_classification_audit_columns(work)
    insert_pack = float(planning.insert_pack_units)
    work = apply_pre_ai_heuristics(
        work, enable_pack_hint_extraction=bool(planning.pack_hint_extraction),
        insert_default_pack_units=insert_pack)
    work = apply_post_ai_safety(work, insert_default_pack_units=insert_pack)

    settings = effective_settings(planning, stdspecial_mapped=bool(mapping.std_special),
                                  both_listings=False)
    params = build_plan_params(settings, mapping=mapping, base_info=base_info)
    result = run_plan(work, pd.DataFrame(columns=OVERRIDE_COLUMNS), params)
    return PlanOutcome(request=request, settings=settings, mapping=mapping,
                       customer=customer, site=site, base_info=dict(base_info), result=result,
                       program_mapping_active=active, program_to_sp=program_to_sp, notes=notes)
