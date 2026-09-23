"""Contract for the content-addressed run fingerprint (I7, v34.16).

The fingerprint used to identify the input source by (file_name, file_size)
only, so replacing a workbook's content while keeping the name and byte size
left a stale plan on screen (the same class of bug the fingerprint exists to
prevent). The fingerprint now carries the SHA-256 of the uploaded bytes,
computed once at the single point where the bytes materialize on the page and
reused by the persistence layer, which already deduplicates stored workbooks
by the same digest.

The unit tests pin the closure of the hole and the identity property; the
page test drives the reload path and asserts the live fingerprint carries the
digest of exactly the bytes that were planned.
"""

import hashlib
from io import BytesIO

import pandas as pd

from engine.run_fingerprint import FingerprintInputs, compute_run_fingerprint
from tests.test_run_fingerprint_scenarios import _inputs
from tests._paths import PLANNER_PAGE


def test_same_name_and_size_different_content_changes_fingerprint():
    a = compute_run_fingerprint(_inputs(content_sha="a" * 64))
    b = compute_run_fingerprint(_inputs(content_sha="b" * 64))
    assert a != b, "a content swap behind an unchanged (name, size) must invalidate results"


def test_identical_content_yields_identical_fingerprint():
    a = compute_run_fingerprint(_inputs(content_sha="c" * 64))
    b = compute_run_fingerprint(_inputs(content_sha="c" * 64))
    assert a == b


def test_sha_sits_beside_the_source_identity():
    fp = compute_run_fingerprint(_inputs(content_sha="d" * 64))
    assert fp[0] == "list.xlsx" and fp[1] == 200000 and fp[2] == "d" * 64


def _synthetic_workbook_bytes():
    rows = 12
    df = pd.DataFrame({
        "ItemCode": [f"K{i:03d}" for i in range(rows)],
        "ItemName": [f"Synthetic tool {i}" for i in range(rows)],
        "Cons16": [(i + 1) * 40.0 for i in range(rows)],
    })
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    return bio.getvalue(), list(df.columns)


def test_page_fingerprint_carries_the_content_sha(monkeypatch, tmp_path):
    from engine.run_restore import build_seed

    monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / "fp.db"))
    raw_bytes, cols = _synthetic_workbook_bytes()
    expected_sha = hashlib.sha256(raw_bytes).hexdigest()

    ui = {"cm_code": "ItemCode", "cm_desc1": "ItemName", "cm_cons": "Cons16",
          "ks_sheet_tools": "Sheet1"}
    restore = build_seed(ui, cols)
    restore["ks_hide_optional"] = False
    restore["ks_ai_colmap"] = False
    restore["_std_special_mapped"] = False

    import streamlit as st
    st.cache_data.clear()
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": raw_bytes, "filename": "input.xlsx",
        "customer": "TestCustomer", "site": "TestSite",
        "classifications": {}, "override_mode": "none", "override_set_id": None,
    }
    at.session_state["_pending_restore"] = restore
    at.run()
    at.session_state["_force_run"] = True
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    fp = at.session_state["_run_fingerprint"]
    assert fp[2] == expected_sha, "the live fingerprint must carry the digest of the planned bytes"
