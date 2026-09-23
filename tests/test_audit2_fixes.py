"""Contracts for the v34.42 audit-#2 fix release: the equality-collapse in
the vectorized restock layer (C1v2), the content-keyed mapping identity
(M1v2), and the run_plan index precondition (m2v2).
"""

import hashlib
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from tests._paths import PLANNER_PAGE

REPO = Path(__file__).resolve().parents[1]


# ---- C1v2 ---------------------------------------------------------------------

def test_hash_equal_raws_normalize_independently():
    """True, 1, and 1.0 are equal as dict keys but not as restocking tokens:
    each cell must get its own normalization, exactly as the frozen row-wise
    reference decides it."""
    from engine.plan import run_restock_segment
    from tests.test_restock_vectorization import _reference_segment

    df = pd.DataFrame({
        "SystemCategory": ["KTC"] * 4,
        "CabinetType": ["Helix"] * 4,
        "ProductCategory": ["inserts"] * 4,
        "Restocking": pd.Series([True, 1.0, 1, 0.0], dtype=object),
    })
    ref_out, ref_info = _reference_segment(df, restock_categories=(), op_mode="Standard")
    new_out, new_info = run_restock_segment(df, restock_categories=(), op_mode="Standard")
    assert new_info == ref_info
    pd.testing.assert_frame_equal(new_out, ref_out)


def test_float_dtype_column_matches_reference():
    """A numeric Excel column parses as float64; 1.0 and 0.0 are unrecognized
    tokens for both implementations, cell by cell."""
    from engine.plan import run_restock_segment
    from tests.test_restock_vectorization import _reference_segment

    df = pd.DataFrame({
        "SystemCategory": ["KTC"] * 3,
        "CabinetType": ["Helix"] * 3,
        "ProductCategory": ["inserts"] * 3,
    })
    df["Restocking"] = pd.Series([1.0, 0.0, 1.0], dtype="float64")
    ref_out, ref_info = _reference_segment(df, restock_categories=(), op_mode="Standard")
    new_out, new_info = run_restock_segment(df, restock_categories=(), op_mode="Standard")
    assert new_info == ref_info
    pd.testing.assert_frame_equal(new_out, ref_out)


# ---- m2v2 ---------------------------------------------------------------------

def test_run_plan_rejects_duplicate_index_legibly():
    """The pipeline guarantees a unique row index; run_plan states the
    assumption instead of failing deep inside a row loop or, worse, writing
    to the wrong rows."""
    import dataclasses  # noqa: F401  (parallel with the other preconditions)
    from engine.plan import run_plan
    from tests.test_run_plan_equivalence import _boundary_frame, _params

    df = _boundary_frame()
    dup = pd.concat([df.iloc[[0]], df], ignore_index=False)
    with pytest.raises(ValueError, match="unique"):
        run_plan(dup, (), _params(df))


# ---- M1v2 ---------------------------------------------------------------------

def test_mapping_identity_is_content_keyed():
    """The E6 mapping reset and the pending-corrections signature key on the
    upload's content hash, restoring the documented contract that a
    same-content re-upload never clears a technician's state, while the C1
    fix keeps the byte memo on the file-event identity."""
    src = (REPO / "pages" / "1_Kromi_Planner.py").read_text(encoding="utf-8")
    assert src.count('("content", _input_sha)') >= 2, (
        "both the mapping reset and the apply-set signature must use the "
        "content identity"
    )
    i_memo = src.index('_upload_fid = _file_identity(file)')
    i_reset = src.index('reset_mapping_state_on_file_change(')
    assert i_memo < i_reset, (
        "the digest memo must run first so the content identity exists "
        "before the reset consumes it"
    )


def _book(cons):
    df = pd.DataFrame({"ItemCode": ["A1", "B2", "C3"],
                       "ItemName": ["drill 5mm", "mill 6mm", "insert x"],
                       "Cons16": cons})
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Sheet1")
    return bio.getvalue()


def test_same_content_reload_keeps_mapping_state(tmp_path, monkeypatch):
    import streamlit as st
    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "m1v2.db"))
    st.cache_data.clear()
    from streamlit.testing.v1 import AppTest
    from engine.run_restore import build_seed

    data = _book([6000.0, 12000.0, 18000.0])
    other = _book([90000.0, 90000.0, 90000.0])
    seed = build_seed({"cm_code": "ItemCode", "cm_desc1": "ItemName",
                       "cm_cons": "Cons16", "ks_sheet_tools": "Sheet1"},
                      ["ItemCode", "ItemName", "Cons16"])
    seed["ks_hide_optional"] = False
    seed["ks_ai_colmap"] = False
    seed["_std_special_mapped"] = False

    def ctx(run_id, blob):
        return {"run_id": run_id, "bytes": blob, "filename": "catalog.xlsx",
                "customer": "M1v2", "site": "S", "classifications": {},
                "override_mode": "none", "override_set_id": None,
                "sha256": hashlib.sha256(blob).hexdigest()}

    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = ctx(1, data)
    at.session_state["_pending_restore"] = dict(seed)
    at.run()
    assert not at.exception, at.exception
    at.session_state["_optional_manual_mode"] = True  # a mapping-scoped key

    at.session_state["_reload_ctx"] = ctx(2, data)  # same content, new run
    at.session_state["_pending_restore"] = dict(seed)
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["_optional_manual_mode"] is True, (
        "a same-content load must not clear mapping-scoped state (E6)"
    )

    at.session_state["_reload_ctx"] = ctx(3, other)  # different content
    at.session_state["_pending_restore"] = dict(seed)
    at.run()
    assert not at.exception, at.exception
    with pytest.raises(KeyError):
        at.session_state["_optional_manual_mode"]  # cleared by the content change
