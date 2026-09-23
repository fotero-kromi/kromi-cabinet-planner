"""Unreadable uploads end in a plain message, not a traceback (v34.49, audit reliability).

The uploader accepts .xlsx, .xlsm and .xls. A corrupt or non-Excel file, or a
legacy .xls without the optional xlrd reader installed, used to raise an
uncaught exception at the first workbook read.
"""
from tests._paths import PLANNER_PAGE

OLE2_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 2048


def _drive(raw, filename):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    st.cache_data.clear()
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=120)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": raw, "filename": filename,
        "customer": "C", "site": "S", "classifications": {},
        "override_mode": "none", "override_set_id": None}
    at.run()
    return at


def test_corrupt_file_shows_a_readable_error():
    at = _drive(b"this is not a workbook at all" * 50, "broken.xlsx")
    assert not at.exception, at.exception
    errors = " ".join(str(e.value) for e in at.error)
    assert "could not be read as an Excel workbook" in errors


def test_legacy_xls_without_reader_explains_the_fix():
    import importlib.util
    if importlib.util.find_spec("xlrd") is not None:
        import pytest
        pytest.skip("xlrd installed: .xls files are readable here")
    at = _drive(OLE2_HEADER, "legacy.xls")
    assert not at.exception, at.exception
    errors = " ".join(str(e.value) for e in at.error)
    assert ".xls" in errors and ".xlsx" in errors
