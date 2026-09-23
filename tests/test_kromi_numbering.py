"""Contract tests for engine.kromi_numbering.

Pins the four invariants the user requires for every generated number:
12 characters, all numeric, ends in 0, unique within the catalog. Also
covers the code matrix, the holder special case, the variant counter,
dimension extraction, and the System column derivation.
"""
import pandas as pd
import pytest

from engine import kromi_numbering as kn


# ---------------------------------------------------------------------------
# kromi_code_for — the ToolClass -> code mapping
# ---------------------------------------------------------------------------
class TestKromiCodeFor:
    def test_drill_family_maps_to_13(self):
        for tc in ["solid_carbide_drill", "hss_drill", "spiral_drill",
                   "nc_drill", "pilot_drill", "center_drill", "core_drill"]:
            code, is_holder = kn.kromi_code_for(tc, "VHM- Bohrer Ø 5,0")
            assert code == "13", f"{tc} should map to 13, got {code}"
            assert is_holder is False

    def test_mill_family_maps_to_16(self):
        for tc in ["solid_end_mill", "face_mill", "burr", "radius_mill",
                   "ball_track_mill", "disc_mill", "form_mill", "shell_mill"]:
            code, _ = kn.kromi_code_for(tc, "VHM- Fräser Ø 8,0")
            assert code == "16", f"{tc} should map to 16, got {code}"

    def test_thread_family_maps_to_15(self):
        for tc in ["tap", "tap_carbide", "tap_hss", "thread_mill",
                   "thread_former", "thread_roller", "threading_die"]:
            code, _ = kn.kromi_code_for(tc, "Gewinde")
            assert code == "15", f"{tc} should map to 15, got {code}"

    def test_reamer_maps_to_11(self):
        code, _ = kn.kromi_code_for("reamer", "Reibahle Ø 6,0")
        assert code == "11"

    def test_counter_maps_to_17(self):
        code, _ = kn.kromi_code_for("countersink", "Senker 90°")
        assert code == "17"

    def test_insert_maps_to_12(self):
        for tc in ["turning_insert", "milling_insert", "drilling_insert"]:
            code, _ = kn.kromi_code_for(tc, "Wendeplatte")
            assert code == "12"

    def test_accessories_map_to_20(self):
        for tc in ["accessory", "screw", "wrench"]:
            code, _ = kn.kromi_code_for(tc, "Schraube M6")
            assert code == "20"

    def test_holders_map_to_20008_and_flag_holder(self):
        for tc in ["hsk_holder", "collet", "turning_holder", "milling_holder",
                   "vdi_holder", "capto_holder"]:
            code, is_holder = kn.kromi_code_for(tc, "Aufnahme HSK63")
            assert code == "20008", f"{tc} should map to 20008, got {code}"
            assert is_holder is True

    def test_unknown_toolclass_falls_back_to_19(self):
        code, is_holder = kn.kromi_code_for("totally_unknown_class", "X")
        assert code == "19"
        assert is_holder is False

    def test_empty_toolclass_falls_back_to_19(self):
        code, _ = kn.kromi_code_for("", "X")
        assert code == "19"
        code, _ = kn.kromi_code_for(None, "X")
        assert code == "19"

    def test_step_drill_detected_from_description_overrides_class(self):
        # Even if the classifier said solid_carbide_drill, a Stufenbohrer
        # in the description forces code 14.
        code, _ = kn.kromi_code_for("solid_carbide_drill",
                                    "VHM- Stufenbohrer Ø 5,0/8,0")
        assert code == "14"

    def test_step_drill_toolclass_maps_to_14(self):
        code, _ = kn.kromi_code_for("step_drill", "Stufenbohrer")
        assert code == "14"


# ---------------------------------------------------------------------------
# build_kromi_number — single-number construction + invariants
# ---------------------------------------------------------------------------
class TestBuildKromiNumber:
    def test_normal_anatomy_is_12_numeric_ending_zero(self):
        num = kn.build_kromi_number("191", "solid_end_mill",
                                    "VHM- Schaftfräser Ø 12,00 x 19", 0)
        assert len(num) == 12
        assert num.isdigit()
        assert num.endswith("0")
        assert num.startswith("191")
        assert num[3:5] == "16"  # mill code

    def test_holder_anatomy_carries_20008(self):
        num = kn.build_kromi_number("191", "hsk_holder", "Aufnahme HSK63 Ø 25", 0)
        assert len(num) == 12
        assert num.isdigit()
        assert num.endswith("0")
        assert num[3:8] == "20008"

    def test_variant_is_zero_padded(self):
        n0 = kn.build_kromi_number("191", "solid_end_mill", "Ø 12,00 x 19", 0)
        n7 = kn.build_kromi_number("191", "solid_end_mill", "Ø 12,00 x 19", 7)
        # variant occupies positions 10-11 (0-indexed 9:11), zero-padded
        assert n0[9:11] == "00"
        assert n7[9:11] == "07"

    def test_variant_overflow_raises(self):
        with pytest.raises(ValueError, match="exceeds"):
            kn.build_kromi_number("191", "solid_end_mill", "Ø 12,00 x 19", 100)

    def test_invalid_ktc_id_raises(self):
        with pytest.raises(ValueError, match="3 digits"):
            kn.build_kromi_number("19", "solid_end_mill", "Ø 12,00 x 19", 0)
        with pytest.raises(ValueError, match="3 digits"):
            kn.build_kromi_number("1911", "solid_end_mill", "Ø 12,00 x 19", 0)
        with pytest.raises(ValueError, match="3 digits"):
            kn.build_kromi_number("19A", "solid_end_mill", "Ø 12,00 x 19", 0)

    def test_description_with_no_digits_pads_zeros(self):
        num = kn.build_kromi_number("191", "brush", "Drahtbürste fein", 0)
        assert len(num) == 12
        assert num.isdigit()
        # dim portion (positions 6-9) should be all zeros
        assert num[5:9] == "0000"

    def test_different_ktc_id_changes_prefix(self):
        num = kn.build_kromi_number("315", "solid_end_mill", "Ø 12,00 x 19", 0)
        assert num.startswith("315")


# ---------------------------------------------------------------------------
# assign_kromi_numbers — catalog-level assignment + uniqueness
# ---------------------------------------------------------------------------
class TestAssignKromiNumbers:
    def _catalog(self):
        return pd.DataFrame({
            "Code": [1, 2, 3, 4, 5],
            "Description": [
                "VHM- Schaftfräser Ø 12,00 x 19",   # mill, dim 1200
                "VHM- Schaftfräser Ø 12,00 x 19",   # same fingerprint -> variant 1
                "VHM- Bohrer Ø 05,00 x 30",          # drill
                "VHM- Schaftfräser Ø 12,00 x 26",    # mill, different dim
                "Reibahle Ø 06,00",                  # reamer
            ],
            "ToolClass": [
                "solid_end_mill", "solid_end_mill", "solid_carbide_drill",
                "solid_end_mill", "reamer",
            ],
        })

    def test_all_numbers_12_digits(self):
        out = kn.assign_kromi_numbers(self._catalog(), "191")
        assert (out["Kromi_Art_No"].str.len() == 12).all()

    def test_all_numbers_all_numeric(self):
        out = kn.assign_kromi_numbers(self._catalog(), "191")
        assert out["Kromi_Art_No"].str.match(r"^\d{12}$").all()

    def test_all_numbers_end_in_zero(self):
        out = kn.assign_kromi_numbers(self._catalog(), "191")
        assert out["Kromi_Art_No"].str.endswith("0").all()

    def test_all_numbers_unique(self):
        out = kn.assign_kromi_numbers(self._catalog(), "191")
        assert out["Kromi_Art_No"].nunique() == len(out)

    def test_same_fingerprint_gets_distinct_variants(self):
        out = kn.assign_kromi_numbers(self._catalog(), "191")
        # Rows 0 and 1 share dimension fingerprint; their numbers must differ
        n0 = out.iloc[0]["Kromi_Art_No"]
        n1 = out.iloc[1]["Kromi_Art_No"]
        assert n0 != n1
        assert n0[:9] == n1[:9]      # same base
        assert n0[9:11] == "00"
        assert n1[9:11] == "01"

    def test_original_columns_unchanged(self):
        src = self._catalog()
        out = kn.assign_kromi_numbers(src, "191")
        for col in src.columns:
            assert (out[col].reset_index(drop=True)
                    .equals(src[col].reset_index(drop=True))), f"{col} changed"

    def test_only_one_column_added(self):
        src = self._catalog()
        out = kn.assign_kromi_numbers(src, "191")
        assert set(out.columns) - set(src.columns) == {"Kromi_Art_No"}

    def test_empty_dataframe_returns_empty_with_column(self):
        empty = pd.DataFrame(columns=["Code", "Description", "ToolClass"])
        out = kn.assign_kromi_numbers(empty, "191")
        assert "Kromi_Art_No" in out.columns
        assert len(out) == 0

    def test_large_group_within_99_succeeds(self):
        # 50 identical-fingerprint mills -> variants 00..49, all unique
        df = pd.DataFrame({
            "Code": list(range(50)),
            "Description": ["VHM- Schaftfräser Ø 10,00 x 22"] * 50,
            "ToolClass": ["solid_end_mill"] * 50,
        })
        out = kn.assign_kromi_numbers(df, "191")
        assert out["Kromi_Art_No"].nunique() == 50
        assert (out["Kromi_Art_No"].str.len() == 12).all()

    def test_group_over_99_raises(self):
        # 101 identical-fingerprint items -> variant 100 overflows 2-digit field
        df = pd.DataFrame({
            "Code": list(range(101)),
            "Description": ["VHM- Schaftfräser Ø 10,00 x 22"] * 101,
            "ToolClass": ["solid_end_mill"] * 101,
        })
        with pytest.raises(ValueError, match="exceeds"):
            kn.assign_kromi_numbers(df, "191")


# ---------------------------------------------------------------------------
# derive_system_column — KTC / Kanban surfacing
# ---------------------------------------------------------------------------
class TestDeriveSystemColumn:
    def test_uses_system_category_when_present(self):
        df = pd.DataFrame({
            "Code": [1, 2, 3],
            "SystemCategory": ["KTC", "Kanban", "KTC"],
            "CabinetType": ["Helix", "Kanban", "Carousel"],
        })
        out = kn.derive_system_column(df)
        assert out["System"].tolist() == ["KTC", "Kanban", "KTC"]

    def test_falls_back_to_cabinet_type(self):
        df = pd.DataFrame({
            "Code": [1, 2, 3, 4],
            "CabinetType": ["Helix", "Carousel", "Locker A", "Kanban"],
        })
        out = kn.derive_system_column(df)
        assert out["System"].tolist() == ["KTC", "KTC", "KTC", "Kanban"]

    def test_blank_when_no_source_columns(self):
        df = pd.DataFrame({"Code": [1, 2]})
        out = kn.derive_system_column(df)
        assert (out["System"] == "").all()

    def test_original_columns_unchanged(self):
        df = pd.DataFrame({
            "Code": [1, 2],
            "SystemCategory": ["KTC", "Kanban"],
        })
        out = kn.derive_system_column(df)
        assert out["Code"].tolist() == [1, 2]
        assert out["SystemCategory"].tolist() == ["KTC", "Kanban"]


# ---------------------------------------------------------------------------
# Ruleset parameterization — other customers differ
# ---------------------------------------------------------------------------
class TestRulesetParameterization:
    def test_valid_alternate_ruleset_5dim_1variant(self):
        # 3 (ktc) + 2 (code) + 5 (dim) + 1 (variant) + 1 (zero) = 12
        custom = kn.KromiRuleset(
            name="ALT", code_matrix=kn.KROMI_CODE_MATRIX,
            dim_digits_normal=5, variant_digits=1,
        )
        num = kn.build_kromi_number("200", "solid_end_mill",
                                    "Ø 12,00 x 19", 0, ruleset=custom)
        assert len(num) == 12
        assert num.isdigit()
        assert num.endswith("0")
        assert num.startswith("200")
        assert num[3:5] == "16"

    def test_malformed_ruleset_is_caught_by_invariant(self):
        # 3 + 2 + 6 (dim) + 1 (variant) + 1 (zero) = 13 -> must raise
        bad = kn.KromiRuleset(
            name="BAD", code_matrix=kn.KROMI_CODE_MATRIX,
            dim_digits_normal=6, variant_digits=1,
        )
        with pytest.raises(ValueError, match="chars"):
            kn.build_kromi_number("200", "solid_end_mill",
                                  "Ø 12,00 x 19", 0, ruleset=bad)


# ---------------------------------------------------------------------------
# augment_for_export — shared export path (live + archived download)
# ---------------------------------------------------------------------------
class TestAugmentForExport:
    def _df(self):
        return pd.DataFrame({
            "Code": [1, 2, 3],
            "Description": ["VHM- Schaftfräser Ø 12,00 x 19",
                            "VHM- Bohrer Ø 05,00 x 30",
                            "Reibahle Ø 06,00"],
            "ToolClass": ["solid_end_mill", "solid_carbide_drill", "reamer"],
            "SystemCategory": ["KTC", "Kanban", "KTC"],
        })

    def test_adds_both_columns_with_valid_ktc(self):
        out = kn.augment_for_export(self._df(), "191")
        assert "System" in out.columns
        assert "Kromi_Art_No" in out.columns
        assert out["System"].tolist() == ["KTC", "Kanban", "KTC"]
        assert (out["Kromi_Art_No"].str.len() == 12).all()
        assert out["Kromi_Art_No"].str.match(r"^[0-9]{12}$").all()

    def test_system_only_when_ktc_invalid(self):
        out = kn.augment_for_export(self._df(), "19")  # not 3 digits
        assert "System" in out.columns
        assert "Kromi_Art_No" not in out.columns

    def test_system_only_when_no_toolclass(self):
        df = self._df().drop(columns=["ToolClass"])
        out = kn.augment_for_export(df, "191")
        assert "System" in out.columns
        assert "Kromi_Art_No" not in out.columns

    def test_falls_back_to_description_2(self):
        df = self._df().rename(columns={"Description": "Description_2"})
        out = kn.augment_for_export(df, "191")
        assert "Kromi_Art_No" in out.columns

    def test_oversized_kanban_group_keeps_system_drops_kromi(self):
        # 101 identical-fingerprint Kanban mills -> legacy variant overflows,
        # KROMI raises, System survives. (KTC rows can no longer overflow:
        # they use the running counter, not the dimension/variant scheme.)
        df = pd.DataFrame({
            "Code": list(range(101)),
            "Description": ["VHM- Schaftfräser Ø 10,00 x 22"] * 101,
            "ToolClass": ["solid_end_mill"] * 101,
            "SystemCategory": ["Kanban"] * 101,
        })
        out = kn.augment_for_export(df, "191")
        assert "System" in out.columns
        assert "Kromi_Art_No" not in out.columns

    def test_original_columns_unchanged(self):
        src = self._df()
        out = kn.augment_for_export(src, "191")
        for col in src.columns:
            assert out[col].reset_index(drop=True).equals(
                src[col].reset_index(drop=True))


# ---------------------------------------------------------------------------
# build_ktc_number — simple KTC running-counter scheme (no dimension/desc)
# ---------------------------------------------------------------------------
class TestBuildKtcNumber:
    def test_first_articles_match_scheme(self):
        assert kn.build_ktc_number("193", 1) == "193100001000"
        assert kn.build_ktc_number("193", 2) == "193100002000"
        assert kn.build_ktc_number("193", 10) == "193100010000"
        assert kn.build_ktc_number("193", 100) == "193100100000"
        assert kn.build_ktc_number("193", 6000) == "193106000000"
        assert kn.build_ktc_number("193", 9999) == "193109999000"

    def test_anatomy_is_12_numeric_ending_zero_with_fixed_10(self):
        for c in (1, 57, 6000, 9999):
            num = kn.build_ktc_number("193", c)
            assert len(num) == 12
            assert num.isdigit()
            assert num.endswith("0")
            assert num[:3] == "193"      # KTC-ID
            assert num[3:5] == "10"      # fixed segment for KTC

    def test_counter_is_zero_padded_four_digits(self):
        assert kn.build_ktc_number("193", 7)[5:9] == "0007"
        assert kn.build_ktc_number("193", 42)[5:9] == "0042"
        assert kn.build_ktc_number("193", 6000)[5:9] == "6000"

    def test_different_ktc_id_changes_prefix(self):
        assert kn.build_ktc_number("315", 1).startswith("315")

    def test_counter_below_one_raises(self):
        with pytest.raises(ValueError):
            kn.build_ktc_number("193", 0)
        with pytest.raises(ValueError):
            kn.build_ktc_number("193", -1)

    def test_counter_over_9999_raises(self):
        with pytest.raises(ValueError):
            kn.build_ktc_number("193", 10000)

    def test_invalid_ktc_id_raises(self):
        for bad in ("19", "1933", "19A"):
            with pytest.raises(ValueError):
                kn.build_ktc_number(bad, 1)


# ---------------------------------------------------------------------------
# assign_split_numbers — KTC counter for KTC rows, legacy scheme for the rest
# ---------------------------------------------------------------------------
class TestAssignSplitNumbers:
    def _mixed(self):
        # interleaved KTC / Kanban; two KTC rows share a description on purpose
        return pd.DataFrame({
            "Code": [1, 2, 3, 4, 5],
            "Description": [
                "VHM- Schaftfräser Ø 12,00 x 19",   # KTC    -> counter 1
                "VHM- Bohrer Ø 05,00 x 30",          # Kanban -> legacy drill 13
                "VHM- Schaftfräser Ø 12,00 x 19",    # KTC    -> counter 2 (same desc)
                "Reibahle Ø 06,00",                  # KTC    -> counter 3
                "VHM- Bohrer Ø 05,00 x 30",          # Kanban -> legacy drill 13 (variant 1)
            ],
            "ToolClass": [
                "solid_end_mill", "solid_carbide_drill", "solid_end_mill",
                "reamer", "solid_carbide_drill",
            ],
            "System": ["KTC", "Kanban", "KTC", "KTC", "Kanban"],
        })

    def test_ktc_rows_get_running_counter_in_order(self):
        out = kn.assign_split_numbers(self._mixed(), "193")
        ktc_nums = out.loc[out["System"] == "KTC", "Kromi_Art_No"].tolist()
        assert ktc_nums == ["193100001000", "193100002000", "193100003000"]

    def test_ktc_numbers_ignore_description(self):
        # rows 0 and 2 share an identical description yet get distinct sequential numbers
        out = kn.assign_split_numbers(self._mixed(), "193")
        assert out.iloc[0]["Kromi_Art_No"] == "193100001000"
        assert out.iloc[2]["Kromi_Art_No"] == "193100002000"

    def test_kanban_rows_keep_legacy_dimension_scheme(self):
        out = kn.assign_split_numbers(self._mixed(), "193")
        kanban = out.loc[out["System"] == "Kanban", "Kromi_Art_No"].tolist()
        # drill -> code 13 at [3:5]; dimension 0500; variant 00 then 01
        assert all(n[3:5] == "13" for n in kanban)
        assert kanban[0][5:9] == "0500"
        assert kanban[0][9:11] == "00"
        assert kanban[1][9:11] == "01"

    def test_ktc_and_kanban_never_share_position_3_5(self):
        out = kn.assign_split_numbers(self._mixed(), "193")
        ktc = out.loc[out["System"] == "KTC", "Kromi_Art_No"]
        kanban = out.loc[out["System"] == "Kanban", "Kromi_Art_No"]
        assert (ktc.str[3:5] == "10").all()
        assert (kanban.str[3:5] != "10").all()

    def test_all_numbers_unique(self):
        out = kn.assign_split_numbers(self._mixed(), "193")
        assert out["Kromi_Art_No"].nunique() == len(out)

    def test_mixed_catalog_passes_e3_invariant(self):
        from engine import invariants as inv
        out = kn.assign_split_numbers(self._mixed(), "193")
        assert inv.check_kromi_uniqueness(out) == []

    def test_pure_ktc_catalog_over_99_does_not_overflow(self):
        # 200 identical-description KTC rows: the legacy variant field would
        # overflow at 100, the counter scheme numbers them 1..200 cleanly.
        df = pd.DataFrame({
            "Code": list(range(200)),
            "Description": ["VHM- Schaftfräser Ø 10,00 x 22"] * 200,
            "ToolClass": ["solid_end_mill"] * 200,
            "System": ["KTC"] * 200,
        })
        out = kn.assign_split_numbers(df, "193")
        assert out["Kromi_Art_No"].nunique() == 200
        assert out.iloc[0]["Kromi_Art_No"] == "193100001000"
        assert out.iloc[199]["Kromi_Art_No"] == "193100200000"

    def test_kanban_only_matches_legacy_assign(self):
        # a pure-Kanban catalog must be numbered exactly as the legacy path
        df = pd.DataFrame({
            "Code": [1, 2, 3],
            "Description": ["VHM- Schaftfräser Ø 12,00 x 19",
                            "VHM- Schaftfräser Ø 12,00 x 19",
                            "VHM- Bohrer Ø 05,00 x 30"],
            "ToolClass": ["solid_end_mill", "solid_end_mill", "solid_carbide_drill"],
            "System": ["Kanban", "Kanban", "Kanban"],
        })
        split = kn.assign_split_numbers(df, "193")["Kromi_Art_No"].tolist()
        legacy = kn.assign_kromi_numbers(df, "193")["Kromi_Art_No"].tolist()
        assert split == legacy

    def test_blank_system_uses_legacy(self):
        # rows with no System (blank) keep the legacy scheme, not the counter
        df = pd.DataFrame({
            "Code": [1],
            "Description": ["VHM- Bohrer Ø 05,00 x 30"],
            "ToolClass": ["solid_carbide_drill"],
            "System": [""],
        })
        out = kn.assign_split_numbers(df, "193")
        assert out.iloc[0]["Kromi_Art_No"][3:5] == "13"  # drill code, legacy

    def test_empty_dataframe_returns_empty_with_column(self):
        empty = pd.DataFrame(columns=["Code", "Description", "ToolClass", "System"])
        out = kn.assign_split_numbers(empty, "193")
        assert "Kromi_Art_No" in out.columns
        assert len(out) == 0


# ---------------------------------------------------------------------------
# augment_for_export — KTC counter + Kanban legacy through the export path
# ---------------------------------------------------------------------------
class TestAugmentForExportKtcSplit:
    def _df(self):
        return pd.DataFrame({
            "Code": [1, 2, 3],
            "Description": ["VHM- Schaftfräser Ø 12,00 x 19",
                            "VHM- Bohrer Ø 05,00 x 30",
                            "Reibahle Ø 06,00"],
            "ToolClass": ["solid_end_mill", "solid_carbide_drill", "reamer"],
            "SystemCategory": ["KTC", "Kanban", "KTC"],
        })

    def test_ktc_rows_use_counter_kanban_uses_legacy(self):
        out = kn.augment_for_export(self._df(), "191")
        nums = out["Kromi_Art_No"].tolist()
        assert nums[0] == "191100001000"   # first KTC -> counter 1
        assert nums[2] == "191100002000"   # second KTC -> counter 2
        assert nums[1][3:5] == "13"        # Kanban drill -> legacy code 13
        assert out["Kromi_Art_No"].nunique() == 3
