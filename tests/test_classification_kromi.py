"""Tests for the Kromi-aligned taxonomy classifier.

Verifies that the new categories (taps, thread_mills, thread_dies, counterbores,
tool_holders, grinding_tools, brushes, broaches, honing_tools, gear_cutting,
center_points, welding, punching, form_steel) classify correctly, and that
the L2 lift in derive_tool_class produces sharp subcategory labels."""

import pytest

from engine import classification as cl
from engine import constants as c

# ---- Taps must classify as taps, never drills ----

class TestTapClassification:
    """Taps (Gewindebohrer) must classify as taps, not drills
    because 'bohrer' substring-matched inside the compound German word
    'gewindebohrer'. The fix: check TAP_KEYWORDS before DRILL_KEYWORDS."""

    def test_gewindebohrer_is_tap_not_drill(self):
        """Gewindebohrer HSS classifies as taps."""
        cat, ev = cl.classify_with_evidence("Gewindebohrer HSS", "", "", "", "Tools")
        assert cat == "taps", f"Expected 'taps', got '{cat}' (ev={ev})"

    def test_gewindebohrer_evidence_correct(self):
        cat, ev = cl.classify_with_evidence("Gewindebohrer HSS", "", "", "", "Tools")
        assert "gewindebohrer" in ev or "tap" in ev.lower()

    def test_gewindebohrer_vhm(self):
        cat, _ = cl.classify_with_evidence("Gewindebohrer VHM", "", "", "", "Tools")
        assert cat == "taps"

    def test_gewindebohrer_pm(self):
        cat, _ = cl.classify_with_evidence("Gewindebohrer PM", "", "", "", "Tools")
        assert cat == "taps"

    def test_gewindeformer_is_tap(self):
        cat, _ = cl.classify_with_evidence("Gewindeformer HSS", "", "", "", "Tools")
        assert cat == "taps"

    def test_taraud_french(self):
        cat, _ = cl.classify_with_evidence("Taraud HSS M6", "", "", "", "Tools")
        assert cat == "taps"

    def test_tap_english(self):
        cat, _ = cl.classify_with_evidence("Tap M8 HSS", "", "", "", "Tools")
        assert cat == "taps"

    def test_macho_spanish(self):
        cat, _ = cl.classify_with_evidence("Macho de roscar M10", "", "", "", "Tools")
        assert cat == "taps"

    def test_gwintownik_polish(self):
        cat, _ = cl.classify_with_evidence("Gwintownik M6 HSS", "", "", "", "Tools")
        assert cat == "taps"

    def test_zavitnik_czech(self):
        cat, _ = cl.classify_with_evidence("Závitník M8", "", "", "", "Tools")
        assert cat == "taps"


# ---- Thread mills ----

class TestThreadMillClassification:
    def test_gewindefraeser_german(self):
        cat, _ = cl.classify_with_evidence("Gewindefräser VHM M6", "", "", "", "Tools")
        assert cat == "thread_mills"

    def test_thread_mill_english(self):
        cat, _ = cl.classify_with_evidence("Thread mill M8", "", "", "", "Tools")
        assert cat == "thread_mills"

    def test_gewindebohrfraeser_is_thread_mill(self):
        """Combined thread-hole cutter."""
        cat, _ = cl.classify_with_evidence("Gewindebohrfräser M5", "", "", "", "Tools")
        assert cat == "thread_mills"

    def test_fresa_de_roscar(self):
        cat, _ = cl.classify_with_evidence("Fresa de roscar M6", "", "", "", "Tools")
        assert cat == "thread_mills"


# ---- Thread dies ----

class TestThreadDieClassification:
    def test_schneideisen(self):
        cat, _ = cl.classify_with_evidence("Schneideisen M8", "", "", "", "Tools")
        assert cat == "thread_dies"

    def test_threading_die(self):
        cat, _ = cl.classify_with_evidence("Threading die M10", "", "", "", "Tools")
        assert cat == "thread_dies"

    def test_filiere_french(self):
        cat, _ = cl.classify_with_evidence("Filière M6", "", "", "", "Tools")
        assert cat == "thread_dies"


# ---- Counterbores ----

class TestCounterboreClassification:
    """Counterbores (Senker) previously fell to 'no-match' (AI)."""

    def test_kegelsenker(self):
        cat, _ = cl.classify_with_evidence("Kegelsenker HSS", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_flachsenker(self):
        cat, _ = cl.classify_with_evidence("Flachsenker D10", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_rueckwaertssenker(self):
        cat, _ = cl.classify_with_evidence("Rückwärtssenker HM", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_stufensenker(self):
        cat, _ = cl.classify_with_evidence("Stufensenker VHM", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_countersink_english(self):
        cat, _ = cl.classify_with_evidence("Countersink D8", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_entgratgabel_deburring(self):
        cat, _ = cl.classify_with_evidence("Entgratgabel", "", "", "", "Tools")
        assert cat == "counterbores"

    def test_senken_alone_not_counterbore(self):
        """'WSP Senken' is an insert for countersinking — not a counterbore.
        Verifies the 'senken' bare keyword was correctly removed."""
        cat, _ = cl.classify_with_evidence("WSP Senken VHM", "", "", "", "Tools")
        assert cat == "inserts"

    def test_zum_senken_not_counterbore(self):
        """'Halter zum Senken' is an insert holder — not a counterbore."""
        cat, _ = cl.classify_with_evidence("Halter zum Senken", "", "", "", "Tools")
        # Either holders (if "halter" matched) or no-match — but NOT counterbores
        assert cat != "counterbores"


# ---- Tool holders ----

class TestToolHolderClassification:
    """Tool holders (Werkzeugaufnahme) — the BIGGEST L1 by volume (612 leaves).
    All previously fell to AI."""

    def test_hsk50(self):
        cat, _ = cl.classify_with_evidence("HSK50 ABS", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_hsk63(self):
        cat, _ = cl.classify_with_evidence("HSK63 Hydro-Dehn", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_sk40(self):
        cat, _ = cl.classify_with_evidence("SK40 Capto", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_vdi30(self):
        cat, _ = cl.classify_with_evidence("VDI30", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_capto(self):
        cat, _ = cl.classify_with_evidence("Capto C5", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_abs50(self):
        cat, _ = cl.classify_with_evidence("ABS50 Schrumpf", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_masbt40(self):
        cat, _ = cl.classify_with_evidence("MASBT40 Reduzierung", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_km_short_code(self):
        """KM is 2 chars — word-boundary matched."""
        cat, _ = cl.classify_with_evidence("KM Bohrfutter", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_mk_short_code(self):
        """MK = Morse Kegel = Morse Taper."""
        cat, _ = cl.classify_with_evidence("MK Spannzangen", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_varia_does_not_match_variant(self):
        """Critical: 'VARIANT' must NOT trigger tool_holder classification.
        Guards a known edge case: bare 'varia' as a
        5-char keyword was substring-matching inside 'variant'."""
        cat, _ = cl.classify_with_evidence(
            "Gewindebohrer PM", "M3,0 6HX VARIANT 1 MHST HK", "", "", "Tools"
        )
        # Should be taps (Gewindebohrer), not tool_holders
        assert cat == "taps"

    def test_spannzangenfutter_recognized(self):
        cat, _ = cl.classify_with_evidence("Spannzangenfutter ER25", "", "", "", "Tools")
        assert cat == "tool_holders"

    def test_werkzeugaufnahme_recognized(self):
        cat, _ = cl.classify_with_evidence("Werkzeugaufnahme WTO-CM-SRK-04", "", "", "", "Tools")
        assert cat == "tool_holders"


# ---- Grinding tools ----

class TestGrindingToolClassification:
    def test_schleifscheibe(self):
        cat, _ = cl.classify_with_evidence("Schleifscheibe CBN", "", "", "", "Tools")
        assert cat == "grinding_tools"

    def test_honstein(self):
        cat, _ = cl.classify_with_evidence("Honstein", "", "", "", "Tools")
        assert cat == "grinding_tools"

    def test_abrichter(self):
        cat, _ = cl.classify_with_evidence("Abrichter Diamant", "", "", "", "Tools")
        assert cat == "grinding_tools"

    def test_trennscheibe(self):
        cat, _ = cl.classify_with_evidence("Trennscheibe 230mm", "", "", "", "Tools")
        assert cat == "grinding_tools"

    def test_grinding_wheel_english(self):
        cat, _ = cl.classify_with_evidence("Grinding wheel D100", "", "", "", "Tools")
        assert cat == "grinding_tools"


# ---- Smaller new categories ----

class TestSmallerCategories:
    def test_brush(self):
        cat, _ = cl.classify_with_evidence("Wire brush D50", "", "", "", "Tools")
        assert cat == "brushes"

    def test_brosse_french(self):
        cat, _ = cl.classify_with_evidence("Brosse métallique", "", "", "", "Tools")
        assert cat == "brushes"

    def test_zentrierspitze(self):
        cat, _ = cl.classify_with_evidence("Mitlaufende Zentrierspitze MK3", "", "", "", "Tools")
        assert cat == "center_points"

    def test_live_center_english(self):
        cat, _ = cl.classify_with_evidence("Live center 60° MT2", "", "", "", "Tools")
        assert cat == "center_points"

    def test_stosswerkzeug_gear(self):
        cat, _ = cl.classify_with_evidence("Stoßwerkzeug außen", "", "", "", "Tools")
        assert cat == "gear_cutting"

    def test_walzfraeser_is_mill_not_gear(self):
        """Wälzfräser is in Kromi Fräser L1 (mill), not Verzahnungswerkzeug.
        Guards a known edge case."""
        cat, _ = cl.classify_with_evidence("Wälzfräser HSS", "", "", "", "Tools")
        assert cat == "mills"


# ---- Backward-compat: existing categories still classify ----

class TestBackwardCompat:
    """Regression guard: the original classifications must remain stable. The key
    cases from the original sanity batteries."""

    def test_foret_still_drills(self):
        cat, _ = cl.classify_with_evidence("foret HSS D2.5", "", "", "", "Tools")
        assert cat == "drills"

    def test_fraise_still_mills(self):
        cat, _ = cl.classify_with_evidence("fraise carbure D10", "", "", "", "Tools")
        assert cat == "mills"

    def test_reibahle_still_reamers(self):
        cat, _ = cl.classify_with_evidence("Reibahle einstufig HSS", "", "", "", "Tools")
        assert cat == "reamers"

    def test_cnmg_still_inserts(self):
        cat, ev = cl.classify_with_evidence("CNMG 120408", "", "", "", "Tools")
        assert cat == "inserts"
        assert "iso:CNMG" in ev

    def test_plaquette_still_inserts(self):
        cat, _ = cl.classify_with_evidence("plaquette carbure", "", "", "", "Tools")
        assert cat == "inserts"

    def test_fo_shorthand_still_drills(self):
        cat, _ = cl.classify_with_evidence("FO DAG D3,27", "", "", "", "Tools")
        assert cat == "drills"

    def test_seco_wnw_still_inserts(self):
        cat, _ = cl.classify_with_evidence("WNW08HD", "", "WNW08HD", "seco", "Tools")
        assert cat == "inserts"

    def test_guhring_specialty_still_drills(self):
        cat, _ = cl.classify_with_evidence("Z6 D8 carb HM", "", "ABC123", "GUHRING FRANCE", "Tools")
        assert cat == "drills"

    def test_compound_drills_still_drills(self):
        """Bohrer compound words: Stufenbohrer, Kernbohrer, etc.
        Must NOT be misclassified as taps (regression test)."""
        for desc in ["Stufenbohrer HSS", "Kernbohrer HM", "Spiralbohrer VHM",
                     "Sichelbohrer", "Pilotbohrer HSS"]:
            cat, _ = cl.classify_with_evidence(desc, "", "", "", "Tools")
            assert cat == "drills", f"Regression: '{desc}' classified as {cat}"


# ---- L2 lift via derive_tool_class ----

class TestL2Lift:
    """Verify derive_tool_class lifts L2 keywords to specific ToolClass values."""

    def test_gewindeformer_to_thread_former(self):
        cat, ev = cl.classify_with_evidence("Gewindeformer VHM", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "thread_former"

    def test_gewindebohrfraeser_to_thread_hole_cutter(self):
        cat, ev = cl.classify_with_evidence("Gewindebohrfräser VHM", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "thread_hole_cutter"

    def test_kegelsenker_to_countersink(self):
        cat, ev = cl.classify_with_evidence("Kegelsenker HSS", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "countersink"

    def test_flachsenker_to_flat_countersink(self):
        cat, ev = cl.classify_with_evidence("Flachsenker D10", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "flat_countersink"

    def test_rueckwaertssenker_to_back(self):
        cat, ev = cl.classify_with_evidence("Rückwärtssenker HM", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "back_countersink"

    def test_hsk50_to_hsk_holder(self):
        cat, ev = cl.classify_with_evidence("HSK50 ABS", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "hsk_holder"

    def test_vdi30_to_vdi_holder(self):
        cat, ev = cl.classify_with_evidence("VDI30", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "vdi_holder"

    def test_frässtift_to_burr(self):
        cat, ev = cl.classify_with_evidence("Frässtift HM", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "burr"

    def test_kreissaegeblatt_to_saw(self):
        cat, ev = cl.classify_with_evidence("Kreissägeblatt HSS", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "saw_blade"

    def test_schleifscheibe_to_grinding_wheel(self):
        cat, ev = cl.classify_with_evidence("Schleifscheibe CBN", "", "", "", "Tools")
        tc = cl.derive_tool_class(ev, "", "", cat)
        assert tc == "grinding_wheel"


# ---- Taxonomy alignment: every new PC is in PC_VALID and TOOLCLASS_FROM_PRODUCT_CATEGORY ----

class TestTaxonomyAlignment:
    NEW_PCS = [
        "taps", "thread_mills", "thread_dies", "counterbores", "tool_holders",
        "grinding_tools", "brushes", "broaches", "honing_tools",
        "gear_cutting", "center_points", "welding", "punching", "form_steel",
    ]

    @pytest.mark.parametrize("pc", NEW_PCS)
    def test_pc_in_pc_valid(self, pc):
        assert pc in c.PC_VALID

    @pytest.mark.parametrize("pc", NEW_PCS)
    def test_pc_has_toolclass_default(self, pc):
        """Every PC must have a default ToolClass in TOOLCLASS_FROM_PRODUCT_CATEGORY."""
        assert pc in c.TOOLCLASS_FROM_PRODUCT_CATEGORY
        default_tc = c.TOOLCLASS_FROM_PRODUCT_CATEGORY[pc]
        assert default_tc in c.TOOL_CLASS_VALID


# ---- INSERT_KEYWORDS expansion ----

class TestInsertKeywords:
    def test_wsp_recognized(self):
        """WSP = Wendeschneidplatte abbreviation. Used in Kromi L2 names."""
        cat, _ = cl.classify_with_evidence("WSP Drehen VHM", "", "", "", "Tools")
        assert cat == "inserts"

    def test_fuehrungsleiste_recognized(self):
        """Guide bar — Kromi L2 under Wendeschneidplatten."""
        cat, _ = cl.classify_with_evidence("Führungsleiste Cermet", "", "", "", "Tools")
        assert cat == "inserts"
