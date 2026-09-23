"""Tests for engine.colmap — AI-assisted column-mapping helpers (pure logic)."""

from __future__ import annotations

from engine import colmap as cm
from engine.colmap import (
    CANONICAL_FIELD_KEYS,
    build_colmap_prompt,
    colmap_response_schema,
    parse_colmap_response,
)


class TestPrompt:
    def test_includes_headers_and_samples(self):
        headers = ["Article SAP", "Désignation", "Quantité Annuelle"]
        sample = [{"Article SAP": "12345", "Désignation": "DRILL", "Quantité Annuelle": "120"}]
        prompt = build_colmap_prompt(headers, sample)
        for h in headers:
            assert h in prompt
        assert "DRILL" in prompt

    def test_lists_all_canonical_fields(self):
        prompt = build_colmap_prompt(["A"], [{"A": "1"}])
        for key in CANONICAL_FIELD_KEYS:
            assert key in prompt

    def test_marks_required_fields(self):
        prompt = build_colmap_prompt(["A"], [{"A": "1"}])
        assert "(required)" in prompt

    def test_caps_sample_rows(self):
        rows = [{"A": str(i)} for i in range(20)]
        prompt = build_colmap_prompt(["A"], rows)
        # Only the first 5 are embedded.
        assert '"19"' not in prompt
        assert '"0"' in prompt


class TestSchema:
    def test_schema_shape(self):
        schema = colmap_response_schema()
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema["properties"].keys()) == set(CANONICAL_FIELD_KEYS)
        assert set(schema["required"]) == set(CANONICAL_FIELD_KEYS)

    def test_all_properties_are_strings(self):
        schema = colmap_response_schema()
        for prop in schema["properties"].values():
            assert prop == {"type": "string"}


class TestParse:
    AVAILABLE = ["Article SAP", "Désignation Outil", "Quantité Annuelle", "Programme", "Sites"]

    def test_valid_mapping(self):
        raw = {
            "Code": "Article SAP",
            "Description": "Désignation Outil",
            "Consumption_pcs": "Quantité Annuelle",
            "Program": "Programme",
            "Site": "Sites",
        }
        out = parse_colmap_response(raw, self.AVAILABLE)
        assert out["Code"] == "Article SAP"
        assert out["Description"] == "Désignation Outil"
        assert out["Consumption_pcs"] == "Quantité Annuelle"
        assert out["Program"] == "Programme"
        assert out["Site"] == "Sites"

    def test_invented_column_dropped(self):
        raw = {"Code": "Article SAP", "Description": "DOES_NOT_EXIST"}
        out = parse_colmap_response(raw, self.AVAILABLE)
        assert out["Code"] == "Article SAP"
        assert "Description" not in out

    def test_empty_string_means_unmapped(self):
        raw = {"Code": "Article SAP", "SupplierCode": ""}
        out = parse_colmap_response(raw, self.AVAILABLE)
        assert "SupplierCode" not in out

    def test_case_and_space_insensitive_resolution(self):
        raw = {"Code": "  article  sap ", "Consumption_pcs": "QUANTITÉ ANNUELLE"}
        out = parse_colmap_response(raw, self.AVAILABLE)
        assert out["Code"] == "Article SAP"
        assert out["Consumption_pcs"] == "Quantité Annuelle"

    def test_no_column_assigned_to_two_fields(self):
        # Model maps the same column to both Description and Description_2.
        raw = {"Description": "Désignation Outil", "Description_2": "Désignation Outil"}
        out = parse_colmap_response(raw, self.AVAILABLE)
        # Description wins (higher priority); Description_2 must not reuse the column.
        assert out["Description"] == "Désignation Outil"
        assert "Description_2" not in out

    def test_required_fields_resolved_first_on_conflict(self):
        # Code (required) and Year (optional) both claim the same column.
        raw = {"Year": "Article SAP", "Code": "Article SAP"}
        out = parse_colmap_response(raw, self.AVAILABLE)
        assert out["Code"] == "Article SAP"
        assert "Year" not in out

    def test_non_dict_returns_empty(self):
        assert parse_colmap_response("not a dict", self.AVAILABLE) == {}
        assert parse_colmap_response(None, self.AVAILABLE) == {}
        assert parse_colmap_response(["a", "b"], self.AVAILABLE) == {}

    def test_non_string_values_skipped(self):
        raw = {"Code": 123, "Description": ["x"], "Consumption_pcs": "Quantité Annuelle"}
        out = parse_colmap_response(raw, self.AVAILABLE)
        assert "Code" not in out
        assert "Description" not in out
        assert out["Consumption_pcs"] == "Quantité Annuelle"

    def test_unknown_keys_ignored(self):
        raw = {"Code": "Article SAP", "Nonsense": "Sites"}
        out = parse_colmap_response(raw, self.AVAILABLE)
        assert out == {"Code": "Article SAP"}

    def test_empty_available_cols(self):
        raw = {"Code": "Article SAP"}
        assert parse_colmap_response(raw, []) == {}


# ---------------------------------------------------------------------------
# resolve_optional_default — hide-optional clearing / ghost-mapping prevention
# ---------------------------------------------------------------------------
from engine.colmap import resolve_optional_default


class TestResolveOptionalDefault:
    def test_normal_uses_auto_default(self):
        # No hide, no manual mode -> auto-detected column is pre-selected.
        assert resolve_optional_default(False, False, "Werk") == "Werk"

    def test_normal_with_no_auto_default(self):
        assert resolve_optional_default(False, False, None) is None

    def test_hidden_returns_none(self):
        # While hidden, the field is unassigned regardless of auto-default.
        assert resolve_optional_default(True, False, "Werk") is None

    def test_manual_mode_suppresses_auto_default(self):
        # After the user has hidden optional columns once, auto-detection is
        # suppressed: a re-shown field starts unassigned (no ghost mapping).
        assert resolve_optional_default(False, True, "Werk") is None

    def test_hidden_and_manual_returns_none(self):
        assert resolve_optional_default(True, True, "Werk") is None

    def test_manual_mode_unaffected_by_auto_default_value(self):
        for auto in ["Werk", "SupplierCode", "", None]:
            assert resolve_optional_default(False, True, auto) is None


# ---- E6: reset mapping-scoped state on file change ----

class TestResetMappingStateOnFileChange:
    def _state(self):
        return {
            "_optional_manual_mode": True,
            "_std_special_mapped": True,
            "cm_year": "Year", "cm_site": "Plant", "cm_prod": "Type",
            "has_results": True,          # NOT mapping-scoped — must survive
            "_run_fingerprint": ("x",),   # NOT mapping-scoped — must survive
        }

    def test_first_file_sets_id_and_clears_nothing_meaningful(self):
        st = {}
        did = cm.reset_mapping_state_on_file_change(st, ("A.xlsx", 100))
        assert did is True
        assert st["_mapping_file_id"] == ("A.xlsx", 100)

    def test_same_file_no_reset(self):
        st = self._state(); st["_mapping_file_id"] = ("A.xlsx", 100)
        did = cm.reset_mapping_state_on_file_change(st, ("A.xlsx", 100))
        assert did is False
        # within-file: mapping state preserved (hide/un-hide behaviour intact)
        assert st["_optional_manual_mode"] is True
        assert st["cm_year"] == "Year"

    def test_new_file_clears_mapping_state(self):
        st = self._state(); st["_mapping_file_id"] = ("A.xlsx", 100)
        did = cm.reset_mapping_state_on_file_change(st, ("B.xlsx", 200))
        assert did is True
        for k in ("_optional_manual_mode", "_std_special_mapped",
                  "cm_year", "cm_site", "cm_prod"):
            assert k not in st
        assert st["_mapping_file_id"] == ("B.xlsx", 200)

    def test_new_file_preserves_non_mapping_state(self):
        st = self._state(); st["_mapping_file_id"] = ("A.xlsx", 100)
        cm.reset_mapping_state_on_file_change(st, ("B.xlsx", 200))
        assert st["has_results"] is True
        assert st["_run_fingerprint"] == ("x",)

    def test_file_removed_clears_mapping_state(self):
        st = self._state(); st["_mapping_file_id"] = ("A.xlsx", 100)
        did = cm.reset_mapping_state_on_file_change(st, (None, None))
        assert did is True
        assert "cm_year" not in st and "_optional_manual_mode" not in st

    def test_optional_manual_mode_no_longer_sticky_across_files(self):
        # The demonstrated leak: manual mode set on file A must not suppress
        # auto-detection on file B.
        st = {"_mapping_file_id": ("A.xlsx", 100), "_optional_manual_mode": True}
        cm.reset_mapping_state_on_file_change(st, ("B.xlsx", 200))
        assert st.get("_optional_manual_mode", False) is False


# --- German header synonyms + collision-safe required default (v33.56) -------
import pandas as pd
from engine.text_utils import guess_column


class TestGermanSynonyms:
    def test_german_code_description_consumption_detected(self):
        df = pd.DataFrame(columns=["WZIntNr", "Werk", "WZBez",
                                   "Consumption Last 16 Months", "Lieferant"])
        assert guess_column(df, cm.CODE_SYNONYMS) == "WZIntNr"
        assert guess_column(df, cm.DESCRIPTION_SYNONYMS) == "WZBez"
        assert guess_column(df, cm.CONSUMPTION_SYNONYMS) == "Consumption Last 16 Months"

    def test_english_headers_still_resolve(self):
        df = pd.DataFrame(columns=["Code", "Description", "Consumption"])
        assert guess_column(df, cm.CODE_SYNONYMS) == "Code"
        assert guess_column(df, cm.DESCRIPTION_SYNONYMS) == "Description"
        assert guess_column(df, cm.CONSUMPTION_SYNONYMS) == "Consumption"

    def test_synonyms_do_not_cross_match_each_other(self):
        # The Description synonym set must not grab the Code column and vice versa
        # on the German file (a regression guard against loose substring matches).
        df = pd.DataFrame(columns=["WZIntNr", "WZBez"])
        assert guess_column(df, cm.CODE_SYNONYMS) == "WZIntNr"
        assert guess_column(df, cm.DESCRIPTION_SYNONYMS) == "WZBez"


class TestResolveRequiredDefault:
    def test_uses_auto_default_when_present_and_free(self):
        assert cm.resolve_required_default("WZBez", set(), ["WZIntNr", "WZBez"]) == "WZBez"

    def test_avoids_a_column_already_taken(self):
        cols = ["WZIntNr", "Werk", "WZBez"]
        assert cm.resolve_required_default(None, {"WZIntNr"}, cols) == "Werk"

    def test_two_required_fields_never_collapse_onto_one_column(self):
        cols = ["WZIntNr", "WZBez", "Consumption"]
        taken: set = set()
        d1 = cm.resolve_required_default(None, taken, cols); taken.add(d1)
        d2 = cm.resolve_required_default(None, taken, cols); taken.add(d2)
        assert d1 != d2

    def test_auto_default_taken_falls_back_to_free_column(self):
        cols = ["WZIntNr", "Werk"]
        # auto-detect would pick WZIntNr but it's already used by Code -> pick Werk
        assert cm.resolve_required_default("WZIntNr", {"WZIntNr"}, cols) == "Werk"

    def test_no_columns_returns_none(self):
        assert cm.resolve_required_default(None, set(), []) is None

    def test_all_taken_degenerate_falls_back_to_first(self):
        cols = ["A", "B"]
        assert cm.resolve_required_default(None, {"A", "B"}, cols) == "A"


class TestResolveRequiredStored:
    """A stored/seeded required pick must heal a collision instead of
    perpetuating it (the bug where a recomputed run seeded Code, Description,
    and Consumption all onto the same column)."""

    COLS = ["WZIntNr", "Werk", "WZBez", "Consumption Last 16 Months"]

    def test_honors_non_colliding_stored_pick(self):
        assert cm.resolve_required_stored("WZBez", "Description", {"WZIntNr"}, self.COLS) == "WZBez"

    def test_reresolves_colliding_stored_pick_to_auto_default(self):
        # stored WZIntNr collides with an earlier required field -> use the auto-detected column
        assert cm.resolve_required_stored("WZIntNr", "WZBez", {"WZIntNr"}, self.COLS) == "WZBez"

    def test_colliding_stored_and_taken_auto_default_falls_to_first_free(self):
        # stored collides AND the auto-default is also taken -> first unclaimed column
        assert cm.resolve_required_stored("WZIntNr", "WZIntNr", {"WZIntNr"}, self.COLS) == "Werk"

    def test_stale_stored_not_in_columns_reresolves(self):
        assert cm.resolve_required_stored("OldFileCol", "WZBez", {"WZIntNr"}, self.COLS) == "WZBez"

    def test_all_three_required_resolve_distinct_from_all_wzintnr_seed(self):
        # The exact bug: a saved mapping with all three required fields on WZIntNr.
        cols = self.COLS
        taken: set = set()
        c = cm.resolve_required_stored("WZIntNr", "WZIntNr", taken, cols); taken.add(c)
        d = cm.resolve_required_stored("WZIntNr", "WZBez", taken, cols); taken.add(d)
        s = cm.resolve_required_stored("WZIntNr", "Consumption Last 16 Months", taken, cols); taken.add(s)
        assert c == "WZIntNr"
        assert d == "WZBez"
        assert s == "Consumption Last 16 Months"
        assert len({c, d, s}) == 3

    def test_empty_columns_returns_none(self):
        assert cm.resolve_required_stored("X", "Y", set(), []) is None
