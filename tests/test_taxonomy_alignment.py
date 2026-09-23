"""Tests for the Kromi-aligned product taxonomy.

Verifies the new product categories (taps, thread_mills, thread_dies,
counterbores, tool_holders, grinding_tools, etc.) classify correctly AND
that no behavior regressed for the original 10 categories."""

import pandas as pd
import pytest

from engine import classification as cl
from engine import constants as c

# ---- PC_VALID expansion ----

class TestKromiAlignedPcValid:
    def test_taps_in_pc_valid(self):
        assert "taps" in c.PC_VALID

    def test_thread_mills_in_pc_valid(self):
        assert "thread_mills" in c.PC_VALID

    def test_thread_dies_in_pc_valid(self):
        assert "thread_dies" in c.PC_VALID

    def test_counterbores_in_pc_valid(self):
        assert "counterbores" in c.PC_VALID

    def test_tool_holders_in_pc_valid(self):
        assert "tool_holders" in c.PC_VALID

    def test_grinding_tools_in_pc_valid(self):
        assert "grinding_tools" in c.PC_VALID

    def test_all_kromi_l1_have_pc(self):
        """Every Kromi L1 category maps to at least one engine PC."""
        kromi_pcs = {
            "drills", "mills", "taps", "thread_mills", "thread_dies",
            "reamers", "counterbores", "inserts", "holders", "tool_holders",
            "accessories", "grinding_tools", "brushes", "form_steel",
            "honing_tools", "broaches", "gear_cutting", "center_points",
            "welding", "punching", "other",
        }
        for pc in kromi_pcs:
            assert pc in c.PC_VALID, f"{pc} missing from PC_VALID"


# ---- TAPS — must not be misclassified as drills ----

class TestTapsClassification:
    """Verifies taps are NO LONGER misclassified as drills."""

    def test_gewindebohrer_hss(self):
        cat, ev = cl.classify_with_evidence("Gewindebohrer HSS", "", "", "", "Tools")
        assert cat == "taps", f"Expected taps but got {cat}"

    def test_gewindebohrer_vhm(self):
        cat, ev = cl.classify_with_evidence("Gewindebohrer VHM", "", "", "", "Tools")
        assert cat == "taps"

    def test_gewindebohrer_pm(self):
        cat, ev = cl.classify_with_evidence("Gewindebohrer PM", "", "", "", "Tools")
        assert cat == "taps"

    def test_gewindebohrer_does_not_match_drills(self):
        """Specifically verify it doesn't fall through to keyword:bohrer."""
        cat, ev = cl.classify_with_evidence("Gewindebohrer HSS-E", "", "", "", "Tools")
        assert cat != "drills"
        assert "keyword:bohrer" not in ev

    def test_thread_former_classifies_as_tap(self):
        """Gewindeformer (thread-forming tap) → taps PC."""
        cat, ev = cl.classify_with_evidence("Gewindeformer HSS", "", "", "", "Tools")
        assert cat == "taps"

    def test_english_tap(self):
        cat, ev = cl.classify_with_evidence("Thread Tap M6", "", "", "", "Tools")
        assert cat == "taps"

    def test_french_taraud(self):
        cat, ev = cl.classify_with_evidence("Taraud M8", "", "", "", "Tools")
        assert cat == "taps"

    def test_spanish_macho(self):
        cat, ev = cl.classify_with_evidence("Macho de roscar M10", "", "", "", "Tools")
        assert cat == "taps"

    def test_tap_tool_class_is_tap(self):
        cat, ev = cl.classify_with_evidence("Gewindebohrer HSS", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "tap"

    def test_gewindeformer_tool_class(self):
        cat, ev = cl.classify_with_evidence("Gewindeformer VHM", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "thread_former"


# ---- THREAD MILLS — Gewindefräser / Gewindebohrfräser ----

class TestThreadMillsClassification:
    def test_gewindefraeser(self):
        cat, ev = cl.classify_with_evidence("Gewindefräser HSS", "", "", "", "Tools")
        assert cat == "thread_mills"

    def test_does_not_match_mills(self):
        cat, ev = cl.classify_with_evidence("Gewindefräser VHM", "", "", "", "Tools")
        assert cat != "mills"
        assert "keyword:fräser" not in ev

    def test_thread_hole_cutter(self):
        cat, ev = cl.classify_with_evidence("Gewindebohrfräser VHM", "", "", "", "Tools")
        assert cat == "thread_mills"

    def test_tool_class_thread_mill(self):
        cat, ev = cl.classify_with_evidence("Gewindefräser HSS", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "thread_mill"

    def test_tool_class_thread_hole_cutter(self):
        cat, ev = cl.classify_with_evidence("Gewindebohrfräser VHM", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "thread_hole_cutter"

    def test_english_thread_mill(self):
        cat, ev = cl.classify_with_evidence("Thread mill carbide", "", "", "", "Tools")
        assert cat == "thread_mills"


# ---- THREAD DIES — Schneideisen / Gewinderoller ----

class TestThreadDiesClassification:
    def test_schneideisen(self):
        cat, ev = cl.classify_with_evidence("Schneideisen", "", "", "", "Tools")
        assert cat == "thread_dies"

    def test_gewinderoller(self):
        cat, ev = cl.classify_with_evidence("Gewinderoller", "", "", "", "Tools")
        assert cat == "thread_dies"

    def test_english_threading_die(self):
        cat, ev = cl.classify_with_evidence("Threading die M10", "", "", "", "Tools")
        assert cat == "thread_dies"


# ---- COUNTERBORES — Senker ----

class TestCounterboresClassification:
    def test_kegelsenker(self):
        cat, ev = cl.classify_with_evidence("Kegelsenker HSS", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_flachsenker(self):
        cat, ev = cl.classify_with_evidence("Flachsenker", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_rueckwaertssenker(self):
        cat, ev = cl.classify_with_evidence("Rückwärtssenker HM-bestückt", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_stufensenker(self):
        cat, ev = cl.classify_with_evidence("Stufensenker", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_entgratgabel(self):
        cat, ev = cl.classify_with_evidence("Entgratgabel", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_english_countersink(self):
        cat, ev = cl.classify_with_evidence("Countersink HSS", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_avellanador(self):
        cat, ev = cl.classify_with_evidence("Avellanador cónico", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_l2_detail_kegelsenker(self):
        cat, ev = cl.classify_with_evidence("Kegelsenker", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "countersink"

    def test_l2_detail_flachsenker(self):
        cat, ev = cl.classify_with_evidence("Flachsenker", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "flat_countersink"

    def test_l2_detail_rueckwaertssenker(self):
        cat, ev = cl.classify_with_evidence("Rückwärtssenker", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "back_countersink"


# ---- TOOL HOLDERS — Werkzeugaufnahme (HSK / SK / VDI / Capto / etc.) ----

class TestToolHoldersClassification:
    def test_hsk50(self):
        cat, ev = cl.classify_with_evidence("HSK50 ABS", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_hsk63(self):
        cat, ev = cl.classify_with_evidence("HSK63 Hydro-Dehn", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_sk40(self):
        cat, ev = cl.classify_with_evidence("SK40 Capto", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_vdi30(self):
        cat, ev = cl.classify_with_evidence("VDI30", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_capto_alone(self):
        cat, ev = cl.classify_with_evidence("Capto", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_abs25(self):
        cat, ev = cl.classify_with_evidence("ABS25", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_masbt40(self):
        cat, ev = cl.classify_with_evidence("MASBT40", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_spannzangenfutter(self):
        cat, ev = cl.classify_with_evidence("Spannzangenfutter", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_l2_hsk_holder(self):
        cat, ev = cl.classify_with_evidence("HSK50", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "hsk_holder"

    def test_l2_sk_holder(self):
        cat, ev = cl.classify_with_evidence("SK40", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "sk_holder"

    def test_l2_vdi_holder(self):
        cat, ev = cl.classify_with_evidence("VDI30", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "vdi_holder"

    def test_l2_capto_holder(self):
        cat, ev = cl.classify_with_evidence("Capto", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "capto_holder"


# ---- GRINDING TOOLS — Schleifkörper ----

class TestGrindingToolsClassification:
    def test_schleifscheibe(self):
        cat, ev = cl.classify_with_evidence("Schleifscheibe CBN", "", "", "", "Tools")
        assert cat == "grinding_tools"

    def test_honstein(self):
        cat, ev = cl.classify_with_evidence("Honstein", "", "", "", "Tools")
        assert cat == "grinding_tools"

    def test_abrichter(self):
        cat, ev = cl.classify_with_evidence("Abrichter", "", "", "", "Tools")
        assert cat == "grinding_tools"

    def test_trennscheibe(self):
        cat, ev = cl.classify_with_evidence("Trennscheibe", "", "", "", "Tools")
        assert cat == "grinding_tools"

    def test_schleifband(self):
        cat, ev = cl.classify_with_evidence("Schleifband", "", "", "", "Tools")
        assert cat == "grinding_tools"

    def test_english_grinding_wheel(self):
        cat, ev = cl.classify_with_evidence("Grinding wheel CBN", "", "", "", "Tools")
        assert cat == "grinding_tools"

    def test_l2_grinding_wheel(self):
        cat, ev = cl.classify_with_evidence("Schleifscheibe", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "grinding_wheel"

    def test_l2_honing_stone(self):
        cat, ev = cl.classify_with_evidence("Honstein", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "honing_stone"

    def test_l2_dressing_tool(self):
        cat, ev = cl.classify_with_evidence("Abrichter", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "dressing_tool"


# ---- DRILLS — L2 detail (spiral / step / NC / core / etc.) ----

class TestDrillsL2Detail:
    def test_spiralbohrer_l2(self):
        cat, ev = cl.classify_with_evidence("Spiralbohrer HSS", "", "", "", "Tools")
        assert cat == "drills"
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "spiral_drill"

    def test_bohrkrone_l2(self):
        cat, ev = cl.classify_with_evidence("Bohrkrone VHM", "", "", "", "Tools")
        assert cat == "drills"
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "core_drill"

    def test_bohrfraeser_l2(self):
        """Bohrfräser (hole cutter) — Kromi puts it under Bohrer L1."""
        cat, ev = cl.classify_with_evidence("Bohrfräser HM-bestückt", "", "", "", "Tools")
        assert cat == "drills"
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "core_drill"


# ---- MILLS — L2 detail (burr / saw blade / form mill) ----

class TestMillsL2Detail:
    def test_fraesstift_l2(self):
        cat, ev = cl.classify_with_evidence("Frässtift HSS", "", "", "", "Tools")
        assert cat == "mills"
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "burr"

    def test_kreissaegeblatt_l2(self):
        cat, ev = cl.classify_with_evidence("Kreissägeblatt HSS", "", "", "", "Tools")
        assert cat == "mills"
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "saw_blade"

    def test_waelzfraeser_l2(self):
        """Wälzfräser is a hob — Kromi keeps it under Fräser L1."""
        cat, ev = cl.classify_with_evidence("Wälzfräser VHM", "", "", "", "Tools")
        assert cat == "mills"
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "form_mill"


# ---- BRUSHES, BROACHES, etc. — smaller Kromi L1 families ----

class TestSmallerKromiCategories:
    def test_brush_bürste(self):
        cat, ev = cl.classify_with_evidence("Rundbürste", "", "", "", "Tools")
        assert cat == "brushes"

    def test_brush_english(self):
        cat, ev = cl.classify_with_evidence("Wire brush", "", "", "", "Tools")
        assert cat == "brushes"

    def test_center_point(self):
        cat, ev = cl.classify_with_evidence("Zentrierspitze mitlaufend", "", "", "", "Tools")
        assert cat == "center_points"

    def test_gear_cutter(self):
        cat, ev = cl.classify_with_evidence("Stoßwerkzeug außen", "", "", "", "Tools")
        assert cat == "gear_cutting"

    def test_welding(self):
        cat, ev = cl.classify_with_evidence("Schweißelektrode", "", "", "", "Tools")
        assert cat == "welding"

    def test_punching(self):
        cat, ev = cl.classify_with_evidence("Stanzwerkzeug", "", "", "", "Tools")
        assert cat == "punching"


# ---- Regression: original categories still work ----

class TestRegressionOriginalCategories:
    """Original-category classification must remain correct."""

    def test_drill_foret(self):
        cat, ev = cl.classify_with_evidence("foret HSS D2.5", "", "", "", "Tools")
        assert cat == "drills"

    def test_drill_bohrer(self):
        cat, ev = cl.classify_with_evidence("Spiralbohrer HSS", "", "", "", "Tools")
        assert cat == "drills"

    def test_mill_fraise(self):
        cat, ev = cl.classify_with_evidence("fraise carbure D10", "", "", "", "Tools")
        assert cat == "mills"

    def test_mill_endmill(self):
        cat, ev = cl.classify_with_evidence("Schaftfräser VHM", "", "", "", "Tools")
        assert cat == "mills"

    def test_insert_cnmg(self):
        cat, ev = cl.classify_with_evidence("CNMG 120408", "", "", "", "Tools")
        assert cat == "inserts"

    def test_insert_plaquette(self):
        cat, ev = cl.classify_with_evidence("plaquette carbure", "", "", "", "Tools")
        assert cat == "inserts"

    def test_insert_wsp_added_in_patch_5(self):
        """WSP is recognized as an insert abbreviation."""
        cat, ev = cl.classify_with_evidence("WSP Bohren VHM", "", "", "", "Tools")
        assert cat == "inserts"

    def test_reamer(self):
        cat, ev = cl.classify_with_evidence("Reibahle einstufig HSS", "", "", "", "Tools")
        assert cat == "reamers"

    def test_french_shorthand_fo(self):
        cat, ev = cl.classify_with_evidence("FO DAG D3,27", "", "", "", "Tools")
        assert cat == "drills"

    def test_supplier_pattern_seco_wnw(self):
        cat, ev = cl.classify_with_evidence("WNW08HD", "", "WNW08HD", "seco", "Tools")
        assert cat == "inserts"


# ---- Integration: full Kromi taxonomy ----

@pytest.mark.integration
class TestKromiTaxonomyIntegration:
    """Validate against the full 977-row Kromi product taxonomy."""

    @staticmethod
    @pytest.fixture(scope="class")
    def kromi_taxonomy():
        import os
        from pathlib import Path
        fixture_dir = Path(os.environ.get(
            "KROMI_FIXTURE_DIR", Path(__file__).parent / "fixtures"))
        path = fixture_dir / "kromi-structure-translations.xlsx"
        if not path.exists():
            pytest.skip(f"Kromi taxonomy fixture not at {path}")
        return pd.read_excel(path, sheet_name="Result 1")

    def test_at_least_90_pct_accuracy(self, kromi_taxonomy):
        """Overall classification accuracy across all Kromi L1 categories should
        be >= 90% (latest measurement: 96.4%)."""
        L1_TO_PC = {
            "Bohrer": ["drills"], "Fräser": ["mills"],
            "Gewindewerkzeuge": ["taps", "thread_mills", "thread_dies"],
            "Reibahlen": ["reamers"], "Senker": ["counterbores"],
            "Wendeschneidplatten": ["inserts"],
            "Halter": ["holders", "boring_bars"],
            "Werkzeugaufnahme": ["tool_holders"], "Weitere": None,
            "Zubehör": ["accessories", "screws"],
            "Schleifkörper": ["grinding_tools"],
            "Bürste": ["brushes"], "Formstahl": ["form_steel"],
            "Honahlen": ["honing_tools"], "Räumwerkzeug": ["broaches"],
            "Verzahnungswerkzeug": ["gear_cutting"],
            "Zentrierspitzen": ["center_points"],
            "Schweißen": ["welding"], "Stanzwerkzeug": ["punching"],
        }
        total = correct = 0
        for _, row in kromi_taxonomy.iterrows():
            desc = " ".join(str(row.get(col, "")) for col in ["2_DEU", "3_DEU"]
                            if pd.notna(row.get(col))).strip()
            if not desc: continue
            total += 1
            cat, _ = cl.classify_with_evidence(desc, "", "", "", "Tools")
            expected = L1_TO_PC.get(row["1_DEU"])
            if expected is None and cat is not None:
                correct += 1
            elif expected and cat in expected:
                correct += 1
        accuracy = correct / total * 100
        assert accuracy >= 90.0, f"Kromi taxonomy accuracy dropped to {accuracy:.1f}%"

    def test_taps_correctly_identified_in_taxonomy(self, kromi_taxonomy):
        """All Gewindebohrer rows in the taxonomy classify as taps (NOT drills)."""
        sub = kromi_taxonomy[kromi_taxonomy["2_DEU"] == "Gewindebohrer"]
        for _, row in sub.iterrows():
            desc = f"{row['2_DEU']} {row.get('3_DEU') or ''}".strip()
            cat, _ = cl.classify_with_evidence(desc, "", "", "", "Tools")
            assert cat == "taps", f"'{desc}' should be taps, got {cat}"


# ---- Integration: SampleCo production data ----

@pytest.mark.integration
class TestSampleProductionData:
    """Validate against real SampleCo production data."""

    def test_sample_100_pct_heuristic_match(self, sample_dataframe):
        """Post-Patch-5, every SampleCo row should classify via heuristic
        (no AI fallback needed)."""
        desc1 = "Bezeichnung 1 / Description 1"
        desc2 = "Bezeichnung 2 / Description 2"
        matched = 0
        for _, row in sample_dataframe.iterrows():
            cat, _ = cl.classify_with_evidence(
                str(row.get(desc1, "") or ""),
                str(row.get(desc2, "") or ""),
                "", "", "Tools",
            )
            if cat is not None:
                matched += 1
        match_rate = matched / len(sample_dataframe) * 100
        # Strict: 99%+ heuristic match rate
        assert match_rate >= 99.0, f"SampleCo match rate dropped to {match_rate:.1f}%"
