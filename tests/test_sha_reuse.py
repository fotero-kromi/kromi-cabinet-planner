"""Contract for reuse-by-SHA (I4, v34.17).

When a freshly uploaded workbook's SHA-256 matches a stored file, the
classifications stored for that file are injected through the same
stored_classifications parameter the reload path already uses, so run_plan
applies them with the mechanism proven since I1, and the covered codes are
subtracted from the AI candidate list so the model is not called for rows the
store already answers. A reload context keeps precedence over the store: its
own classification snapshot wins.

The tests drive the page twice against one database: the first drive persists
the workbook, classifications are then written for three codes directly
through the store, and the second drive of the same bytes must carry exactly
those codes into run_plan and announce the reuse. A third drive with a reload
context carrying different values must win over the store.
"""

from io import BytesIO

import pandas as pd

import engine.plan as ep
from engine.run_restore import build_seed
from tests._paths import PLANNER_PAGE


def _synthetic_workbook_bytes():
    rows = 8
    df = pd.DataFrame({
        "ItemCode": [f"R{i:03d}" for i in range(rows)],
        "ItemName": [f"Reusable tool {i}" for i in range(rows)],
        "Cons16": [(i + 1) * 55.0 for i in range(rows)],
    })
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    return bio.getvalue(), list(df.columns)


def _drive(raw_bytes, cols, db_path, reload_extra=None):
    import streamlit as st
    st.cache_data.clear()
    from streamlit.testing.v1 import AppTest
    ui = {"cm_code": "ItemCode", "cm_desc1": "ItemName", "cm_cons": "Cons16",
          "ks_sheet_tools": "Sheet1"}
    restore = build_seed(ui, cols)
    restore["ks_hide_optional"] = False
    restore["ks_ai_colmap"] = False
    restore["_std_special_mapped"] = False
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    ctx = {"run_id": 1, "bytes": raw_bytes, "filename": "input.xlsx",
           "customer": "TestCustomer", "site": "TestSite",
           "classifications": {}, "override_mode": "none", "override_set_id": None}
    if reload_extra:
        ctx.update(reload_extra)
    at.session_state["_reload_ctx"] = ctx
    at.session_state["_pending_restore"] = restore
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    return at


def _seed_store_classifications(db_path, sha, values):
    import db as kromi_db
    conn = kromi_db.init_db(db_path)
    row = conn.execute("SELECT file_id FROM uploaded_files WHERE sha256 = ?", (sha,)).fetchone()
    assert row is not None, "the first drive must have persisted the workbook"
    file_id = row["file_id"]
    for code, pc in values.items():
        rec = conn.execute(
            "SELECT tool_record_id FROM tool_records WHERE file_id = ? AND code = ?",
            (file_id, code)).fetchone()
        assert rec is not None, f"tool record missing for {code}"
        conn.execute(
            "INSERT INTO tool_classifications (tool_record_id, file_id, size_category, "
            "product_category, source, model, reason, confidence, classified_at) "
            "VALUES (?, ?, ?, ?, 'ai', 'test-model', 'seeded', 'high', '2026-07-05T12:00:00Z')",
            (rec["tool_record_id"], file_id, "M", pc))
    conn.commit()
    conn.close()


def test_fresh_upload_of_known_workbook_reuses_stored_classifications(monkeypatch, tmp_path):
    import hashlib
    db_path = str(tmp_path / "reuse.db")
    monkeypatch.setenv("KROMI_DB_PATH", db_path)
    raw_bytes, cols = _synthetic_workbook_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()

    captured = {}
    _orig = ep.run_plan

    def spying(df, overrides, params):
        captured["stored"] = params.stored_classifications
        return _orig(df, overrides, params)

    monkeypatch.setattr(ep, "run_plan", spying)

    _drive(raw_bytes, cols, db_path)                      # persists the workbook
    assert captured["stored"] == (), "first sight of the file must reuse nothing"

    seeded = {"R001": "reamers", "R003": "taps", "R005": "mills"}
    _seed_store_classifications(db_path, sha, seeded)

    at = _drive(raw_bytes, cols, db_path)                 # same bytes, fresh drive
    got = {c: pc for (c, _size, pc) in captured["stored"]}
    assert got == seeded, f"expected the stored classifications to flow into run_plan, got {got}"
    infos = " | ".join(str(i.value) for i in at.info)
    assert "Known workbook" in infos, "the reuse must be announced"


def test_reload_context_keeps_precedence_over_the_store(monkeypatch, tmp_path):
    import hashlib
    db_path = str(tmp_path / "prec.db")
    monkeypatch.setenv("KROMI_DB_PATH", db_path)
    raw_bytes, cols = _synthetic_workbook_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()

    captured = {}
    _orig = ep.run_plan

    def spying(df, overrides, params):
        captured["stored"] = params.stored_classifications
        return _orig(df, overrides, params)

    monkeypatch.setattr(ep, "run_plan", spying)

    _drive(raw_bytes, cols, db_path)
    _seed_store_classifications(db_path, sha, {"R001": "reamers"})

    reload_cls = {"R002": {"size_category": "L", "product_category": "holders"}}
    _drive(raw_bytes, cols, db_path, reload_extra={"classifications": reload_cls})
    got = {c: pc for (c, _size, pc) in captured["stored"]}
    assert got == {"R002": "holders"}, "a reload's own snapshot must win over the store"
