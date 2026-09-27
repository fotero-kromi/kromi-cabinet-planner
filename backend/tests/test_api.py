"""The HTTP API (kromi_api/api): the vertical slice from upload to download,
against a real PostgreSQL, with the parity oracle at the end."""
import pytest
from fastapi.testclient import TestClient

from engine.classification_tables import PC_VALID
from engine.planning_defaults import DEFAULTS, LIMITS, OP_MODE_LABELS
from kromi_api import config
from kromi_api.main import create_app
from kromi_api.settings import ColumnMappingIn
from tools import synthetic_golden as sg

from .test_parity import request_for

API = "/api/v1"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def client(session_factory):
    with TestClient(create_app(session_factory=session_factory)) as c:
        yield c


def _upload(client, data: bytes, name="synthetic.xlsx"):
    return client.post(f"{API}/workbooks", files={"file": (name, data, XLSX)})


def test_health_reports_the_build_and_the_database(client):
    body = client.get(f"{API}/health").json()
    assert body["status"] == "ok" and body["database"] == "ok" and body["build"]


def test_the_openapi_schema_is_served(client):
    schema = client.get(f"{API}/openapi.json").json()
    assert "/api/v1/runs" in schema["paths"] and "/api/v1/workbooks" in schema["paths"]


def test_upload_returns_the_sheets_and_stores_a_file_once(client, catalog_bytes):
    first = _upload(client, catalog_bytes)
    assert first.status_code == 201
    body = first.json()
    assert body["sheets"] == [sg.SHEET] and len(body["sha256"]) == 64
    assert body["size_bytes"] == len(catalog_bytes)
    again = _upload(client, catalog_bytes, name="other.xlsx")
    assert again.status_code == 200 and again.json()["id"] == body["id"]


def test_upload_refuses_other_files_and_oversize(client, monkeypatch):
    bad = _upload(client, b"plain text", name="notes.txt")
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "unreadable_workbook"
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    big = _upload(client, b"x" * 11)
    assert big.status_code == 413


def test_sheet_inspection_suggests_the_mapping(client, catalog_bytes):
    wb = _upload(client, catalog_bytes).json()
    r = client.get(f"{API}/workbooks/{wb['id']}/sheets/{sg.SHEET}", params={"header_row": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["columns"] == sg.COLUMNS and body["row_count"] == len(sg.build_catalog())
    assert len(body["preview"]) == 20
    m = body["suggested_mapping"]
    assert m["code"] == "Article No" and m["description"] == "Description"
    assert m["consumption"] == "Consumption 12 months"
    assert set(m) == set(ColumnMappingIn.model_fields)


def test_unknown_workbook_and_sheet(client, catalog_bytes):
    assert client.get(f"{API}/workbooks/999/sheets/x").status_code == 404
    wb = _upload(client, catalog_bytes).json()
    r = client.get(f"{API}/workbooks/{wb['id']}/sheets/Nope")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unknown_sheet"


def test_mapping_check_reports_conflicts_and_missing_columns(client, catalog_bytes):
    wb = _upload(client, catalog_bytes).json()
    body = {"sheet": sg.SHEET, "header_row": 1,
            "mapping": {"code": "Article No", "description": "Description",
                        "consumption": "Consumption 12 months", "category": "Description",
                        "stock": "Not a column"}}
    r = client.post(f"{API}/workbooks/{wb['id']}/mapping/check", json=body).json()
    assert r["ok"] is False
    assert r["conflicts"] == {"Description": ["Description", "ProductCategory"]}
    assert r["missing_columns"] == ["Not a column"]
    body["mapping"].pop("category")
    body["mapping"].pop("stock")
    ok = client.post(f"{API}/workbooks/{wb['id']}/mapping/check", json=body).json()
    assert ok == {"ok": True, "conflicts": {}, "missing_columns": []}


def test_defaults_come_from_the_engine(client):
    body = client.get(f"{API}/settings/defaults").json()
    assert body["planning"]["helix_threshold"] == DEFAULTS.helix_threshold
    assert body["planning"]["coverage_days"] == DEFAULTS.coverage_days
    assert body["scope"]["ktc_id"] == DEFAULTS.ktc_id
    assert body["header_row"] == DEFAULTS.header_row
    assert body["limits"]["coverage_days"] == list(LIMITS["coverage_days"])
    assert body["labels"]["op_mode"] == {"": OP_MODE_LABELS[""]}


def test_defaults_offer_the_restock_categories_of_the_engine(client):
    # The settings screen offers the same categories as the Streamlit page's
    # "Restockable categories (rule)" choice (engine PC_VALID, sorted).
    body = client.get(f"{API}/settings/defaults").json()
    assert body["choices"]["restock_categories"] == sorted(PC_VALID)


def _run(client, catalog_bytes, settings=None):
    wb = _upload(client, catalog_bytes).json()
    payload = {"workbook_id": wb["id"],
               "settings": (settings or request_for("standard")).model_dump(mode="json")}
    return client.post(f"{API}/runs", json=payload)


def test_a_standard_run_end_to_end_matches_the_streamlit_app(client, catalog_bytes, manifest):
    created = _run(client, catalog_bytes)
    assert created.status_code == 202
    run_id = created.json()["id"]
    run = client.get(f"{API}/runs/{run_id}").json()  # the background run has finished
    assert run["status"] == "succeeded", run
    s = run["summary"]
    assert (s["customer"], s["site"]) == ("Synthetic", "Golden")
    assert [b["label"] for b in s["buckets"]] == ["All"]
    assert s["grand"]["total_cabs"] == s["buckets"][0]["total_cabinets"]
    assert s["export_problems"] == []
    tools = client.get(f"{API}/runs/{run_id}/tools").json()
    assert len(tools) == 360 and tools[0]["line_no"] == 1
    book = client.get(f"{API}/runs/{run_id}/workbook")
    assert book.status_code == 200 and book.headers["content-type"] == XLSX
    assert "attachment" in book.headers["content-disposition"]
    assert sg.workbook_digest(book.content) == manifest["standard"]["workbook"]["sha256"]


def test_the_same_inputs_reuse_the_finished_run(client, catalog_bytes):
    first = _run(client, catalog_bytes).json()["id"]
    again = _run(client, catalog_bytes)
    assert again.status_code == 200
    assert again.json()["id"] == first and again.json()["reused"] is True


def test_a_run_that_cannot_plan_is_failed_with_the_reason(client, catalog_bytes):
    bad = request_for("standard").model_copy(update={
        "mapping": request_for("standard").mapping.model_copy(update={"category": "Description"})})
    run_id = _run(client, catalog_bytes, bad).json()["id"]
    run = client.get(f"{API}/runs/{run_id}").json()
    assert run["status"] == "failed" and run["summary"] is None
    assert run["error"]["code"] == "mapping_conflict"
    assert client.get(f"{API}/runs/{run_id}/workbook").status_code == 409


def test_invalid_settings_are_refused_before_a_run(client, catalog_bytes):
    wb = _upload(client, catalog_bytes).json()
    settings = request_for("standard").model_dump(mode="json")
    settings["planning"]["op_mode"] = "Capped"
    r = client.post(f"{API}/runs", json={"workbook_id": wb["id"], "settings": settings})
    assert r.status_code == 422
    unknown = client.post(f"{API}/runs", json={"workbook_id": 999,
                                               "settings": request_for("standard").model_dump(mode="json")})
    assert unknown.status_code == 404


def test_recent_runs_newest_first(client, catalog_bytes):
    a = _run(client, catalog_bytes).json()["id"]
    other = request_for("standard").model_copy(update={"header_row": 1})
    other = other.model_copy(update={"planning": other.planning.model_copy(
        update={"helix_threshold": 2.0})})
    b = _run(client, catalog_bytes, other).json()["id"]
    runs = client.get(f"{API}/runs").json()
    assert [r["id"] for r in runs][:2] == [b, a]


def test_unknown_run(client):
    assert client.get(f"{API}/runs/999").status_code == 404
    assert client.get(f"{API}/runs/999/tools").status_code == 404
    assert client.get(f"{API}/runs/999/workbook").status_code == 404
