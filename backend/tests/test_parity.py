"""Parity oracle (docs/Rewrite_Decision.md): a synthetic scenario sent through the
new app's service must give exactly what the Streamlit app gives, as recorded
in tests/golden/synthetic_manifest.json by tools/synthetic_golden.py:

* ``plan_result``: the planner's own result (article rows, bucket plans, grand
  totals and the other result parts);
* ``workbook``: every cell of every sheet of the exported workbook.

Each scenario joins this list when its screen is built; this version covers
``standard``.
"""
from datetime import UTC, datetime

import pytest

from kromi_api import settings as s
from kromi_api.services import export, planning
from tools import synthetic_golden as sg

#: Streamlit control key -> PlanningIn field, for the scenario translation.
CONTROL_FIELDS = {
    "ks_ktc_threshold": "ktc_threshold", "ks_insert_pack": "insert_pack_units",
    "ks_helix_threshold": "helix_threshold", "ks_consumption_months": "consumption_months",
    "ks_overfill": "helix_overfill_factor", "ks_min_carousel": "min_carousel_allocation",
    "cov_days_standard": "coverage_days", "cov_days_special": "coverage_days_special",
    "ks_special_ktc": "special_ktc", "ks_reserve": "carousel_reserve_factor",
    "ks_fill_ceiling": "carousel_fill_ceiling", "ks_rebalancer": "enable_rebalancer",
    "ks_empty_cab": "underuse_threshold_pct", "ks_buffer": "capacity_buffer_pct",
    "ks_pack_hint": "pack_hint_extraction", "ks_bulk_routing": "bulk_routing",
    "ks_force_screws": "force_screws_kanban", "ks_n_sp": "n_supply_points",
    "ks_max_carousels": "max_carousels", "ks_restock_categories": "restock_categories",
}
#: Streamlit mapping key -> ColumnMappingIn field.
MAPPING_FIELDS = {
    "cm_code": "code", "cm_desc1": "description", "cm_cons": "consumption",
    "cm_desc2": "description_2", "cm_prod": "category", "cm_sup": "supplier_code",
    "cm_size": "size", "cm_pack": "pack_units", "cm_year": "year", "cm_program": "program",
    "cm_restock": "restocking", "cm_site": "site", "cm_stdspecial": "std_special",
    "cm_dims": "dimensions", "cm_regrind": "regrind", "cm_systemtyp": "system_type",
    "cm_stock": "stock",
}
#: The gate's scope: the Streamlit run replays a stored run of this customer and site.
GATE_SCOPE = {"customer": "Synthetic", "site": "Golden", "ktc_id": "191"}

COVERED = ["standard"]


def request_for(name: str) -> s.RunRequest:
    spec = sg.SCENARIOS[name]
    unknown = set(spec["controls"]) - set(CONTROL_FIELDS)
    assert not unknown, f"translate these controls first: {sorted(unknown)}"
    planning_in = {CONTROL_FIELDS[k]: v for k, v in spec["controls"].items()}
    mapping = {MAPPING_FIELDS[k]: v for k, v in {**sg._REQUIRED, **spec["mapping"]}.items()}
    return s.RunRequest(sheet=sg.SHEET, mapping=mapping, planning=planning_in,
                        scope=GATE_SCOPE)


@pytest.mark.parametrize("name", COVERED)
def test_the_plan_result_matches_the_streamlit_app(name, catalog_bytes, manifest):
    outcome = planning.run(catalog_bytes, request_for(name))
    assert sg.plan_result_digest(outcome.result) == manifest[name]["plan_result"]


@pytest.mark.parametrize("name", COVERED)
def test_the_workbook_matches_the_streamlit_app(name, catalog_bytes, manifest):
    req = request_for(name)
    outcome = planning.run(catalog_bytes, req)
    book = export.result_workbook(outcome, req, timestamp=datetime.now(UTC))
    assert book.problems == []
    assert sg.workbook_digest(book.data) == manifest[name]["workbook"]["sha256"]


def test_the_run_does_not_change_the_planner_result_it_reports(catalog_bytes):
    """The display columns go on a copy; the reported result stays the planner's."""
    outcome = planning.run(catalog_bytes, request_for("standard"))
    assert "Std_Special" not in outcome.result.work.columns
    before = sg.plan_result_digest(outcome.result)
    export.result_workbook(outcome, request_for("standard"),
                           timestamp=datetime.now(UTC))
    assert sg.plan_result_digest(outcome.result) == before


def test_the_workbook_is_the_same_on_every_build(catalog_bytes):
    req = request_for("standard")
    outcome = planning.run(catalog_bytes, req)
    t = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    a = export.result_workbook(outcome, req, timestamp=t)
    b = export.result_workbook(outcome, req, timestamp=t)
    assert sg.workbook_digest(a.data) == sg.workbook_digest(b.data)
