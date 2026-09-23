"""Tests for engine.overrides — 10 functions."""

import pandas as pd
import pytest

from engine import overrides as ov
from engine.constants import OVERRIDE_VALID_CABINETS, OVERRIDE_VALID_SIZES, OVERRIDE_VALID_VEND

# ---- _safe_scope_component ----

class TestSafeScopeComponent:
    def test_lowercase_alnum(self):
        assert ov._safe_scope_component("SampleCo") == "SampleCo"

    def test_replaces_special_chars(self):
        assert ov._safe_scope_component("E/L O*S") == "E_L_O_S"

    def test_collapses_consecutive_underscores(self):
        # Already in source code via re.sub(r"_+", "_", ...)
        assert "__" not in ov._safe_scope_component("a@@@b###c")

    def test_strips_leading_trailing_underscores(self):
        result = ov._safe_scope_component("@@@sample@@@")
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_length_capped_at_40(self):
        result = ov._safe_scope_component("a" * 100)
        assert len(result) <= 40

    def test_empty_returns_default(self):
        assert ov._safe_scope_component("") == "default"

    def test_whitespace_only_returns_default(self):
        assert ov._safe_scope_component("   ") == "default"


# ---- overrides_folder ----

class TestOverridesFolder:
    def test_path_uses_double_underscore_separator(self, tmp_base_dir):
        result = ov.overrides_folder("SampleCo", "Site1", tmp_base_dir)
        assert "SampleCo__Site1" in str(result)

    def test_under_base_dir(self, tmp_base_dir):
        result = ov.overrides_folder("SampleCo", "Site1", tmp_base_dir)
        assert tmp_base_dir in result.parents

    def test_special_chars_sanitized(self, tmp_base_dir):
        result = ov.overrides_folder("E*LOS", "Tar/bes", tmp_base_dir)
        assert "*" not in str(result)
        assert "/" not in str(result.relative_to(tmp_base_dir))

    def test_does_not_create_folder(self, tmp_base_dir):
        """overrides_folder only computes the path; it doesn't mkdir."""
        result = ov.overrides_folder("SampleCo", "Site1", tmp_base_dir)
        assert not result.exists()


# ---- load_overrides ----

class TestLoadOverrides:
    def test_missing_file_returns_empty_df(self, tmp_base_dir):
        df = ov.load_overrides("X", "Y", tmp_base_dir)
        assert len(df) == 0
        # Should still have the standard schema
        assert "code" in df.columns

    def test_load_after_save_round_trip(self, tmp_base_dir, overrides_csv_data):
        ok, _ = ov.save_overrides("X", "Y", overrides_csv_data, tmp_base_dir)
        assert ok
        loaded = ov.load_overrides("X", "Y", tmp_base_dir)
        assert len(loaded) >= 1

    def test_empty_rows_filtered(self, tmp_base_dir):
        """Rows with no code or no override values should be dropped on load."""
        bad_df = pd.DataFrame({
            "code": ["A", ""],  # blank code
            "listing": ["Tools", "Tools"],
            "product_category_override": ["drills", ""],
            "pack_units_override": ["", ""],
            "size_category_override": ["", ""],
            "cabinet_type_override": ["", ""],
            "vend_mode_override": ["", ""],
            "note": ["", ""],
            "reviewed_by": ["", ""],
            "reviewed_at": ["", ""],
        })
        ov.save_overrides("X", "Y", bad_df, tmp_base_dir)
        loaded = ov.load_overrides("X", "Y", tmp_base_dir)
        # Only the row with code='A' should remain
        assert len(loaded) == 1
        assert loaded.iloc[0]["code"] == "A"

    def test_dedupe_keeps_latest_reviewed_at(self, tmp_base_dir):
        """Multiple rows for same (code, listing) keep the latest reviewed_at."""
        df = pd.DataFrame({
            "code": ["A", "A"],
            "listing": ["Tools", "Tools"],
            "product_category_override": ["drills", "mills"],
            "pack_units_override": ["", ""],
            "size_category_override": ["", ""],
            "cabinet_type_override": ["", ""],
            "vend_mode_override": ["", ""],
            "note": ["old", "new"],
            "reviewed_by": ["alice", "bob"],
            "reviewed_at": ["2025-01-01", "2025-02-01"],
        })
        ov.save_overrides("X", "Y", df, tmp_base_dir)
        loaded = ov.load_overrides("X", "Y", tmp_base_dir)
        assert len(loaded) == 1
        assert loaded.iloc[0]["product_category_override"] == "mills"
        assert loaded.iloc[0]["note"] == "new"

    def test_history_written_when_dedupe_drops(self, tmp_base_dir):
        df = pd.DataFrame({
            "code": ["A", "A"],
            "listing": ["Tools", "Tools"],
            "product_category_override": ["drills", "mills"],
            "pack_units_override": ["", ""],
            "size_category_override": ["", ""],
            "cabinet_type_override": ["", ""],
            "vend_mode_override": ["", ""],
            "note": ["old", "new"],
            "reviewed_by": ["a", "b"],
            "reviewed_at": ["2025-01-01", "2025-02-01"],
        })
        ov.save_overrides("X", "Y", df, tmp_base_dir)
        ov.load_overrides("X", "Y", tmp_base_dir)
        # History file should exist with the dropped (old) row
        hist = ov.overrides_folder("X", "Y", tmp_base_dir) / "overrides.history.csv"
        assert hist.exists()


# ---- save_overrides ----

class TestSaveOverrides:
    def test_atomic_save(self, tmp_base_dir, overrides_csv_data):
        ok, path = ov.save_overrides("X", "Y", overrides_csv_data, tmp_base_dir)
        assert ok
        # Final file exists, .tmp doesn't
        from pathlib import Path
        p = Path(path)
        assert p.exists()
        assert not (p.parent / "overrides.csv.tmp").exists()

    def test_creates_scope_folder(self, tmp_base_dir, overrides_csv_data):
        ov.save_overrides("X", "Y", overrides_csv_data, tmp_base_dir)
        folder = ov.overrides_folder("X", "Y", tmp_base_dir)
        assert folder.exists()
        assert folder.is_dir()

    def test_empty_df_succeeds(self, tmp_base_dir):
        df = pd.DataFrame({c: [] for c in ["code", "listing"]})
        ok, _ = ov.save_overrides("X", "Y", df, tmp_base_dir)
        assert ok


# ---- Field validators ----

class TestValidators:
    def test_valid_category_drills(self):
        assert ov._valid_category("drills") is True

    def test_valid_category_uppercase(self):
        assert ov._valid_category("DRILLS") is True

    def test_invalid_category(self):
        assert ov._valid_category("nonexistent") is False

    def test_valid_category_empty(self):
        assert ov._valid_category("") is False

    def test_valid_cabinet_type(self):
        # Test with the first valid value from the constant
        valid_ct = list(OVERRIDE_VALID_CABINETS)[0]
        assert ov._valid_cabinet_type(valid_ct) is True

    def test_invalid_cabinet_type(self):
        assert ov._valid_cabinet_type("garbage") is False

    def test_valid_vend_mode(self):
        valid_vm = list(OVERRIDE_VALID_VEND)[0]
        assert ov._valid_vend_mode(valid_vm) is True

    def test_invalid_vend_mode(self):
        assert ov._valid_vend_mode("xyz") is False

    def test_valid_size(self):
        valid_sz = list(OVERRIDE_VALID_SIZES)[0]
        assert ov._valid_size(valid_sz) is True

    def test_valid_size_case_insensitive(self):
        valid_sz = list(OVERRIDE_VALID_SIZES)[0]
        assert ov._valid_size(valid_sz.lower()) is True

    def test_invalid_size(self):
        assert ov._valid_size("ZZZ") is False


# ---- _parse_pack_override ----

class TestParsePackOverride:
    def test_valid_integer(self):
        assert ov._parse_pack_override("50") == 50

    def test_valid_float_string(self):
        assert ov._parse_pack_override("50.0") == 50

    def test_one_minimum(self):
        assert ov._parse_pack_override("1") == 1

    def test_max(self):
        assert ov._parse_pack_override("10000") == 10000

    def test_zero_rejected(self):
        assert ov._parse_pack_override("0") is None

    def test_negative_rejected(self):
        assert ov._parse_pack_override("-5") is None

    def test_over_max_rejected(self):
        assert ov._parse_pack_override("10001") is None

    def test_garbage_rejected(self):
        assert ov._parse_pack_override("abc") is None

    def test_empty_rejected(self):
        assert ov._parse_pack_override("") is None

    def test_none_rejected(self):
        assert ov._parse_pack_override(None) is None


# ---- apply_overrides ----

class TestApplyOverrides:
    def test_valid_override_applies_category(self, work_for_overrides, overrides_csv_data):
        out, stats = ov.apply_overrides(work_for_overrides, overrides_csv_data)
        a1_row = out[out["Code"] == "A1"].iloc[0]
        assert a1_row["ProductCategory"] == "drills"
        assert a1_row["Override_Applied"] is True or a1_row["Override_Applied"] == True

    def test_valid_pack_units_applies(self, work_for_overrides, overrides_csv_data):
        out, stats = ov.apply_overrides(work_for_overrides, overrides_csv_data)
        a1_row = out[out["Code"] == "A1"].iloc[0]
        assert float(a1_row["PackUnits"]) == 50.0

    def test_invalid_category_recorded(self, work_for_overrides, overrides_csv_data):
        """B2 has product_category_override='INVALID_CAT' — should be in invalid_overrides."""
        out, stats = ov.apply_overrides(work_for_overrides, overrides_csv_data)
        assert len(stats["invalid_overrides"]) > 0
        codes = [x["code"] for x in stats["invalid_overrides"]]
        assert "B2" in codes

    def test_unmatched_code_recorded(self, work_for_overrides, overrides_csv_data):
        """Z9 doesn't exist in work — should be in unmatched_overrides."""
        out, stats = ov.apply_overrides(work_for_overrides, overrides_csv_data)
        codes = [x["code"] for x in stats["unmatched_overrides"]]
        assert "Z9" in codes

    def test_routing_overridden_only_for_cabinet_or_vendmode(self, work_for_overrides, overrides_csv_data):
        """Routing_Overridden marks rows whose routing was explicitly set
        (cabinet_type/vend_mode), so the page knows not to re-route them; a
        ProductCategory/PackUnits-only override must NOT set it (those rows
        get re-routed from their new attributes — HMA-1)."""
        out, _ = ov.apply_overrides(work_for_overrides, overrides_csv_data)
        a1 = out[out["Code"] == "A1"].iloc[0]   # category + pack only
        b2 = out[out["Code"] == "B2"].iloc[0]   # cabinet_type override
        assert bool(a1["Override_Applied"]) is True
        assert bool(a1["Routing_Overridden"]) is False
        assert bool(b2["Routing_Overridden"]) is True

    def test_routing_overridden_initialized_false(self, work_for_overrides):
        """With no overrides, the column exists and is all False."""
        empty = work_for_overrides.iloc[0:0].copy()
        out, _ = ov.apply_overrides(work_for_overrides, empty)
        assert "Routing_Overridden" in out.columns
        assert not out["Routing_Overridden"].any()

    def test_fields_changed_tracked(self, work_for_overrides, overrides_csv_data):
        out, stats = ov.apply_overrides(work_for_overrides, overrides_csv_data)
        # category and pack_units fields should be tracked
        assert "category" in stats["fields_changed"]
        assert stats["fields_changed"]["category"] >= 1

    def test_audit_columns_added(self, work_for_overrides, overrides_csv_data):
        out, stats = ov.apply_overrides(work_for_overrides, overrides_csv_data)
        for col in ["Override_Applied", "Override_Fields", "Override_Note",
                    "Override_ReviewedBy", "Override_ReviewedAt"]:
            assert col in out.columns

    def test_empty_overrides_no_op(self, work_for_overrides):
        empty_df = pd.DataFrame()
        out, stats = ov.apply_overrides(work_for_overrides, empty_df)
        assert stats["rows_touched"] == 0
        assert len(out) == len(work_for_overrides)

    def test_no_modifications_to_unmatched_rows(self, work_for_overrides, overrides_csv_data):
        """Rows in work that aren't matched by any override should be unchanged."""
        out, _ = ov.apply_overrides(work_for_overrides, overrides_csv_data)
        d4_row = out[out["Code"] == "D4"].iloc[0]
        # D4 isn't in overrides_csv_data; ProductCategory should still be 'drills'
        assert d4_row["ProductCategory"] == "drills"


class TestPendingOverridesAccumulator:
    def test_merge_accumulates_across_views(self):
        p = ov.merge_pending_overrides({}, [{"code": "A", "listing": "Tools", "cabinet_type_override": "Helix"}])
        p = ov.merge_pending_overrides(p, [{"code": "B", "listing": "Tools", "size_category_override": "M"}])
        assert set(p) == {"A", "B"}
        assert p["A"]["cabinet_type_override"] == "Helix"
        assert p["B"]["size_category_override"] == "M"

    def test_merge_later_edit_overwrites_same_field(self):
        p = ov.merge_pending_overrides({}, [{"code": "A", "cabinet_type_override": "Helix"}])
        p = ov.merge_pending_overrides(p, [{"code": "A", "cabinet_type_override": "Carousel"}])
        assert p["A"]["cabinet_type_override"] == "Carousel"

    def test_merge_preserves_other_fields_of_same_code(self):
        p = ov.merge_pending_overrides({}, [{"code": "A", "cabinet_type_override": "Helix"}])
        p = ov.merge_pending_overrides(p, [{"code": "A", "size_category_override": "M"}])
        assert p["A"]["cabinet_type_override"] == "Helix"
        assert p["A"]["size_category_override"] == "M"

    def test_merge_skips_blank_code(self):
        assert ov.merge_pending_overrides({}, [{"code": "  ", "cabinet_type_override": "Helix"}]) == {}

    def test_merge_does_not_mutate_input(self):
        p0 = {"A": {"cabinet_type_override": "Helix"}}
        p1 = ov.merge_pending_overrides(p0, [{"code": "A", "size_category_override": "M"}])
        assert "size_category_override" not in p0["A"]
        assert p1["A"]["size_category_override"] == "M"

    def test_to_df_shape_and_values(self):
        from engine.constants import OVERRIDE_COLUMNS
        p = {"A": {"listing": "Tools", "cabinet_type_override": "Helix"}, "B": {"size_category_override": "M"}}
        df = ov.pending_overrides_to_df(p)
        assert list(df.columns) == OVERRIDE_COLUMNS
        by = {r["code"]: r for r in df.to_dict("records")}
        assert by["A"]["cabinet_type_override"] == "Helix"
        assert by["A"]["listing"] == "Tools"
        assert by["B"]["size_category_override"] == "M"
        assert by["B"]["cabinet_type_override"] == ""
        assert by["B"]["listing"] == "Tools"

    def test_to_df_empty_keeps_columns(self):
        from engine.constants import OVERRIDE_COLUMNS
        df = ov.pending_overrides_to_df({})
        assert list(df.columns) == OVERRIDE_COLUMNS
        assert len(df) == 0
