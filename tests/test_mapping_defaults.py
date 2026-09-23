"""Auto-detected mappings never collide (v34.50, audit C11).

Synonym matching is by substring on purpose (German compounds such as
"Jahresverbrauch" must still be recognised as consumption), which let an
optional field grab a column a required field already uses: Year took
"Jahresverbrauch" next to Consumption, Standard/Special took "Artikel" (via
"Art") next to Code. The page then stopped with a mapping-conflict error the
user had not caused. Optional defaults now skip any column a required field
(or an earlier optional field) already claims; explicit picks are untouched
and the conflict guard stays as the safety net.
"""
from io import BytesIO

import pandas as pd

from engine.colmap import deconflict_defaults
from tests._paths import PLANNER_PAGE


def test_optional_defaults_skip_required_claims():
    required = {"Code": "Artikel", "Description": "Bezeichnung",
                "Consumption_pcs": "Jahresverbrauch"}
    optional = {"Year": "Jahresverbrauch", "StdSpecial": "Artikel",
                "SupplierCode": "Lieferant"}
    out = deconflict_defaults(required, optional)
    assert out == {"Year": None, "StdSpecial": None, "SupplierCode": "Lieferant"}


def test_earlier_optional_field_wins_a_shared_column():
    out = deconflict_defaults({"Code": "A"}, {"SupplierCode": "Lief", "Site": "Lief"})
    assert out == {"SupplierCode": "Lief", "Site": None}


def test_missing_defaults_stay_missing_and_input_is_not_mutated():
    optional = {"Year": None, "Site": "Werk"}
    out = deconflict_defaults({"Code": None}, optional)
    assert out == {"Year": None, "Site": "Werk"}
    assert optional == {"Year": None, "Site": "Werk"}


def _kds_like_bytes():
    df = pd.DataFrame({
        "Artikel": ["A1", "A2", "A3"],
        "Bezeichnung": ["Bohrer D8,5", "Fraeser D12", "Gewindebohrer M6"],
        "Jahresverbrauch": [120, 60, 30],
        "Lieferant": ["X", "Y", "Z"],
    })
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Import")
    return bio.getvalue()


def test_page_auto_detection_does_not_block_a_kds_style_file():
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    st.cache_data.clear()
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": _kds_like_bytes(), "filename": "kds.xlsx",
        "customer": "C", "site": "S", "classifications": {},
        "override_mode": "none", "override_set_id": None}
    at.session_state["_pending_restore"] = {"ks_sheet_tools": "Import",
                                            "ks_hide_optional": False,
                                            "ks_ai_colmap": False}
    at.run()
    assert not at.exception, at.exception
    errors = " ".join(str(e.value) for e in at.error)
    assert "Column-mapping conflict" not in errors
    picks = {sb.key: sb.value for sb in at.selectbox if sb.key}
    assert picks["cm_code"] == "Artikel"
    assert picks["cm_cons"] == "Jahresverbrauch"
    assert picks["cm_year"] != "Jahresverbrauch"
    assert picks.get("cm_stdspecial") != "Artikel"
