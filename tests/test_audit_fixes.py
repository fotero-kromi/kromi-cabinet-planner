"""Contracts for the v34.36 audit fix release: C1 (reload identity), M2
(empty Tools sheet), M1 (unguarded size-lock detection), M3 (archive dedup).
Each pins the fix behaviorally, not just structurally, so a regression in any
of the four reopens a red test rather than a silent hole.
"""

import hashlib
import os
import sqlite3
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from tests._paths import PLANNER_PAGE

REPO = Path(__file__).resolve().parents[1]


def _book(descs, cons):
    df = pd.DataFrame({"ItemCode": [f"K{i:03d}" for i in range(len(descs))],
                       "ItemName": descs, "Cons16": cons})
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Sheet1")
    return bio.getvalue()


def _equal_len_books():
    """Two parseable workbooks, same byte length, different content: the
    collision C1 silently accepted. The filler cell is tuned until the
    compressed sizes match."""
    a = _book(["drill 5mm", "mill 6mm", "insert x"], [6000.0, 12000.0, 18000.0])
    for pad in range(0, 4000):
        b = _book(["drill 5mm", "mill 6mm", "insert " + "y" * pad],
                  [90000.0, 90000.0, 90000.0])
        if len(b) == len(a):
            return a, b
        if len(b) > len(a):
            break
    for pad in range(0, 4000):
        a2 = _book(["drill 5mm", "mill 6mm", "insert " + "z" * pad],
                   [6000.0, 12000.0, 18000.0])
        if len(a2) == len(b):
            return a2, b
    pytest.skip("could not craft equal-length workbooks on this openpyxl")


def _seed_for(cols):
    from engine.run_restore import build_seed
    ui = {"cm_code": "ItemCode", "cm_desc1": "ItemName", "cm_cons": "Cons16",
          "ks_sheet_tools": "Sheet1"}
    seed = build_seed(ui, cols)
    seed["ks_hide_optional"] = False
    seed["ks_ai_colmap"] = False
    seed["_std_special_mapped"] = False
    return seed


def _reload_at(tmp_path, monkeypatch):
    import streamlit as st
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "audit.db"))
    st.cache_data.clear()
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(PLANNER_PAGE, default_timeout=300)


def _ctx(run_id, data, name):
    return {"run_id": run_id, "bytes": data, "filename": name,
            "customer": "AuditFix", "site": "S", "classifications": {},
            "override_mode": "none", "override_set_id": None,
            "sha256": hashlib.sha256(data).hexdigest()}


# ---- C1 ----------------------------------------------------------------------

def test_reload_switch_never_reuses_bytes(tmp_path, monkeypatch):
    """Two stored runs sharing a filename and an exact byte length must never
    share the memoized bytes or digest: the reload identity carries content,
    not just (name, size)."""
    a, b = _equal_len_books()
    assert len(a) == len(b) and a != b
    at = _reload_at(tmp_path, monkeypatch)
    at.session_state["_reload_ctx"] = _ctx(1, a, "catalog.xlsx")
    at.session_state["_pending_restore"] = _seed_for(["ItemCode", "ItemName", "Cons16"])
    at.run()
    assert not at.exception, at.exception
    memo_a = at.session_state["_upload_bytes_memo"]
    assert memo_a[2] == hashlib.sha256(a).hexdigest()

    at.session_state["_reload_ctx"] = _ctx(2, b, "catalog.xlsx")
    at.session_state["_pending_restore"] = _seed_for(["ItemCode", "ItemName", "Cons16"])
    at.run()
    assert not at.exception, at.exception
    memo_b = at.session_state["_upload_bytes_memo"]
    assert memo_b[2] == hashlib.sha256(b).hexdigest(), (
        "the second reload was served the first run's digest (C1)"
    )
    assert memo_b[1] == b, "the second reload was served the first run's bytes (C1)"


def test_file_identity_is_unified():
    """Two identities, each in exactly one role (v34.42): the byte memo keys
    on the file-event identity, which must exist before any bytes are read;
    the mapping reset and the pending-corrections signature key on the
    content hash, so a same-content re-upload keeps the technician's state
    while no (name, size) key survives anywhere."""
    src = (REPO / "pages" / "1_Kromi_Planner.py").read_text(encoding="utf-8")
    assert "def _file_identity(" in src
    assert "_upload_fid = _file_identity(file)" in src
    assert src.count('("content", _input_sha)') >= 2
    assert 'getattr(file, "size", None)) if file else' not in src, (
        "no (name, size) identity may remain at the reset or signature sites"
    )
    assert '"sha256": file_row["sha256"]' in src


# ---- M2 ----------------------------------------------------------------------

def test_prep_rejects_unprepared_frames_legibly():
    """A raw or mis-mapped frame gets a message naming the missing planning
    columns, not a pandas KeyError from inside the groupby. The page path
    (prepared columns, possibly zero rows) is pinned end to end by the
    headers-only test below."""
    from engine.preprocessing import prepare_planning_base
    raw = pd.DataFrame({"Code": [], "Description": [], "Listing": [],
                        "Consumption": [], "PackUnits": []})
    with pytest.raises(ValueError, match="missing"):
        prepare_planning_base(raw, dedup_mode="sum", year_mode="latest", has_year=False)


def test_headers_only_upload_shows_an_error_not_a_traceback(tmp_path, monkeypatch):
    empty = _book([], [])
    at = _reload_at(tmp_path, monkeypatch)
    at.session_state["_reload_ctx"] = _ctx(1, empty, "template.xlsx")
    at.session_state["_pending_restore"] = _seed_for(["ItemCode", "ItemName", "Cons16"])
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, f"an empty Tools sheet must not crash: {at.exception}"
    texts = [str(e.value) for e in at.error] + [str(w.value) for w in at.warning]
    assert any("no data rows" in t.lower() for t in texts), texts


# ---- M1 ----------------------------------------------------------------------

def test_size_lock_detection_failures_propagate(monkeypatch):
    """The engine never swallows a failure around the SizeIssue write: a
    raising detector must surface, not vanish."""
    import engine.plan as ep

    def boom(*a, **k):
        raise RuntimeError("detector failure must propagate")

    monkeypatch.setattr(ep, "detect_size_locked_items", boom)
    work = pd.DataFrame({
        "Listing": ["Tools"] * 2, "SupplyPoint": [1, 1],
        "SystemCategory": ["KTC", "KTC"], "CabinetType": ["Helix", "Helix"],
        "SizeCategory": ["S", "S"], "Carousel_stockpiles": [0, 0],
        "Spirals_needed": [2, 2], "Spiral_capacity": [20, 20],
        "Monthly_packs": [1.0, 2.0], "Consumption_pcs": [10.0, 20.0],
    })
    buckets = [("Tools — SP 1", work)]
    with pytest.raises(RuntimeError, match="must propagate"):
        ep.run_bucket_planning_segment(
            work, buckets, op_mode="Standard", enable_rebalancer=True,
            buf_pct=0.0, minimum_carousel_allocation=1,
            underuse_threshold_pct=0.0, max_carousels_cap=0,
            helix_overfill_factor=1.1, carousel_reserve_factor=0.85,
            carousel_fill_ceiling=1.0,
        )


# ---- M3 ----------------------------------------------------------------------

def test_settings_round_trip_archives_no_duplicate(tmp_path, monkeypatch):
    """A -> B -> A archives two runs, not three: the database, not just the
    last session key, is the dedup authority."""
    data = _book(["drill 5mm", "mill 6mm", "insert x"], [6000.0, 12000.0, 18000.0])
    at = _reload_at(tmp_path, monkeypatch)
    at.session_state["_reload_ctx"] = _ctx(1, data, "dedup.xlsx")
    at.session_state["_pending_restore"] = _seed_for(["ItemCode", "ItemName", "Cons16"])
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception

    def runs():
        conn = sqlite3.connect(str(tmp_path / "audit.db"))
        try:
            return conn.execute("SELECT COUNT(*) FROM engine_executions").fetchone()[0]
        finally:
            conn.close()

    assert runs() == 1
    at.session_state["ks_reserve"] = 0.90
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception
    assert runs() == 2, "a changed setting must archive a new run"
    at.session_state["ks_reserve"] = 0.85
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, at.exception
    assert runs() == 2, "returning to earlier settings re-archived a duplicate (M3)"


def test_db_lookup_by_inputs_hash_exists(tmp_path):
    import db.store as store
    from db.persist_run import run_id_by_inputs_hash
    conn = store.init_db(os.path.join(str(tmp_path), "m3.db"))
    assert run_id_by_inputs_hash(conn, "no-such-hash") is None
    conn.close()
