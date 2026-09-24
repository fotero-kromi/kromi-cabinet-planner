"""kromi_api/storage: values survive PostgreSQL exactly, so the planner's result
read back from the database has the same fingerprint as the Streamlit app's."""
import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from kromi_api.services import export, planning
from kromi_api.storage import repository as repo
from kromi_api.storage.models import Run, RunBucket, RunFile, RunSummary, RunTool
from tools import synthetic_golden as sg

from .test_parity import request_for

# ---- value conversion ---------------------------------------------------------------

def test_json_values_are_plain_and_exact():
    assert repo.to_json(np.int64(3)) == 3 and type(repo.to_json(np.int64(3))) is int
    assert repo.to_json(np.float64(0.1)) == 0.1
    assert repo.to_json(np.bool_(True)) is True
    assert repo.to_json(float("nan")) is None
    assert repo.to_json(pd.NA) is None and repo.to_json(pd.NaT) is None
    assert repo.to_json(("a", (1, 2))) == ["a", [1, 2]]
    assert repo.to_json({"k": np.float64(1.5), "n": None}) == {"k": 1.5, "n": None}


def test_unknown_values_are_refused():
    with pytest.raises(TypeError):
        repo.to_json(object())
    with pytest.raises(ValueError):
        repo.to_json(float("inf"))


def test_a_planner_frame_survives_rows_and_back(catalog_bytes):
    work = planning.run(catalog_bytes, request_for("standard")).result.work
    columns, rows = repo.frame_to_rows(work)
    back = repo.rows_to_frame(columns, rows)
    assert list(back.columns) == list(work.columns)
    assert sg.frame_digest(back) == sg.frame_digest(work)


def test_the_frame_round_trip_keeps_types_and_gaps():
    frame = pd.DataFrame({
        "f": [1.0, float("nan"), 0.1 + 0.2], "i": [1, 2, 3], "b": [True, False, True],
        "o": ["x", None, float("nan")], "n": pd.array([1, None, 3], dtype="Int64"),
    })
    columns, rows = repo.frame_to_rows(frame)
    back = repo.rows_to_frame(columns, rows)
    assert [str(t) for t in back.dtypes] == [str(t) for t in frame.dtypes]
    assert sg.frame_digest(back) == sg.frame_digest(frame)
    assert math.isnan(back["f"].iloc[1]) and back["f"].iloc[2] == 0.1 + 0.2


# ---- database -----------------------------------------------------------------------

def _stored_run(db, catalog_bytes):
    req = request_for("standard")
    wb = repo.save_workbook(db, "synthetic.xlsx", catalog_bytes)
    run = repo.create_run(db, wb, req)
    outcome = planning.run(catalog_bytes, req)
    book = export.result_workbook(outcome, req, timestamp=datetime.now(UTC))
    repo.save_result(db, run, outcome, book, filename="result.xlsx")
    db.commit()
    return run, outcome, book


def test_the_planner_result_read_back_matches_the_streamlit_app(db, catalog_bytes, manifest):
    run, outcome, _book = _stored_run(db, catalog_bytes)
    db.expire_all()
    loaded = repo.load_plan_result(db, run.id)
    assert sg.plan_result_digest(loaded) == manifest["standard"]["plan_result"]
    assert sg.plan_result_digest(loaded) == sg.plan_result_digest(outcome.result)


def test_the_stored_workbook_is_the_built_one(db, catalog_bytes, manifest):
    run, _outcome, book = _stored_run(db, catalog_bytes)
    db.expire_all()
    f = repo.result_file(db, run.id)
    assert f is not None and f.content == book.data
    assert sg.workbook_digest(f.content) == manifest["standard"]["workbook"]["sha256"]


def test_typed_tool_columns_and_buckets(db, catalog_bytes):
    run, outcome, _book = _stored_run(db, catalog_bytes)
    tools = repo.tool_rows(db, run.id)
    work = outcome.result.work
    assert len(tools) == len(work)
    first = tools[0]
    assert first.line_no == 1 and first.code == work["Code"].iloc[0]
    assert first.cabinet_type == (work["CabinetType"].iloc[0] or None)
    assert first.spirals == int(work["Spirals_needed"].iloc[0])
    buckets = repo.bucket_rows(db, run.id)
    assert [b.label for b in buckets] == [lbl for lbl, _ in outcome.result.bucket_plans]
    assert buckets[0].total_cabinets == outcome.result.bucket_plans[0][1]["total_cabs"]


def test_a_workbook_is_stored_once_per_content(db, catalog_bytes):
    a = repo.save_workbook(db, "one.xlsx", catalog_bytes)
    b = repo.save_workbook(db, "two.xlsx", catalog_bytes)
    assert a.id == b.id and a.filename == "one.xlsx"


def test_a_run_is_found_by_its_inputs(db, catalog_bytes):
    run, _o, _b = _stored_run(db, catalog_bytes)
    same = repo.find_finished_run(db, run.workbook_id, request_for("standard"))
    assert same is not None and same.id == run.id
    other = request_for("standard").model_copy(update={"header_row": 2})
    assert repo.find_finished_run(db, run.workbook_id, other) is None


def test_failed_runs_record_the_reason(db, catalog_bytes):
    wb = repo.save_workbook(db, "x.xlsx", catalog_bytes)
    run = repo.create_run(db, wb, request_for("standard"))
    repo.mark_failed(db, run, "mapping_conflict", "same column twice", {"A": ["x", "y"]})
    db.commit()
    db.expire_all()
    got = db.get(Run, run.id)
    assert (got.status, got.error_code, got.error_details) == (
        "failed", "mapping_conflict", {"A": ["x", "y"]})
    assert got.finished_at is not None


def test_deleting_a_run_removes_its_results(db, catalog_bytes):
    run, _o, _b = _stored_run(db, catalog_bytes)
    db.delete(db.get(Run, run.id))
    db.commit()
    for model in (RunSummary, RunBucket, RunTool, RunFile):
        assert db.query(model).filter_by(run_id=run.id).count() == 0, model.__name__
