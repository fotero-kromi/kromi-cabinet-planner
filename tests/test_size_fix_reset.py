"""Manual size fixes belong to one file (v34.50, audit reliability).

Manual Helix-fit size overrides were kept when a different file was loaded,
so they applied to the next customer's articles with the same codes, and that
run was then not saved (saving is skipped while fixes are active) without
telling the user. Fixes are now cleared when the file content changes, like
pending technician corrections, and the user is told what was discarded.
"""
from io import BytesIO

import pandas as pd

from tests._paths import PLANNER_PAGE


def _xlsx(codes):
    df = pd.DataFrame({"ItemCode": codes, "ItemName": ["Bohrer D8"] * len(codes),
                       "Cons16": [100.0] * len(codes)})
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Sheet1")
    return bio.getvalue()


def _ctx(raw, run_id=1, filename="input.xlsx"):
    return {"run_id": run_id, "bytes": raw, "filename": filename, "customer": "C",
            "site": "S", "classifications": {}, "override_mode": "none",
            "override_set_id": None}


def test_new_file_content_clears_manual_size_fixes():
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    st.cache_data.clear()
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = _ctx(_xlsx(["C1", "C2"]))
    at.session_state["_pending_restore"] = {"ks_sheet_tools": "Sheet1",
                                            "cm_code": "ItemCode", "cm_desc1": "ItemName",
                                            "cm_cons": "Cons16", "ks_ai_colmap": False}
    at.run()
    at.session_state["manual_size_fix"] = {"C1": "M"}
    at.run()
    assert at.session_state["manual_size_fix"] == {"C1": "M"}   # same file: kept

    # Another stored run with other content (a different file event).
    at.session_state["_reload_ctx"] = _ctx(_xlsx(["C1", "C9"]), run_id=2, filename="other.xlsx")
    at.run()
    assert not at.exception, at.exception
    assert ("manual_size_fix" not in at.session_state
            or not at.session_state["manual_size_fix"])
    infos = " ".join(str(i.value) for i in at.info)
    assert "discarded" in infos.lower()
