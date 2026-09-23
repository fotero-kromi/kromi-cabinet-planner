"""Tests for engine.classification — 19 functions.

This is the largest test file because classification is the most complex
engine module. It owns: ISO insert detection, supplier-code patterns,
French shorthand, the evidence-tracking classifier, and ToolClass derivation.

Earlier validation established
the module behaves like the original; these tests lock individual behaviors
so future refactors are safe."""

import pandas as pd
import pytest

from engine import classification as cl

# ---- looks_like_insert_code ----

class TestLooksLikeInsertCode:
    """ISO insert codes need a word boundary on both sides to match."""

    def test_turning_cnmg(self):
        assert cl.looks_like_insert_code("CNMG 120408") is True

    def test_turning_tnmg(self):
        assert cl.looks_like_insert_code("plaquette TNMG") is True

    def test_turning_wnmg(self):
        assert cl.looks_like_insert_code("WNMG 080408") is True

    def test_turning_ccmt(self):
        assert cl.looks_like_insert_code("CCMT 09T308") is True

    def test_turning_vbmt(self):
        assert cl.looks_like_insert_code("VBMT 160404") is True

    def test_drilling_wcmx_via_iso_recognizer(self):
        """The looks_like_insert_code pattern doesn't include drilling-specific
        codes like WCMX/WOMT — those are only handled at the derive_tool_class
        level. So they shouldn't match here."""
        # This documents current behavior; if drilling support is added later
        # this test should be updated.
        assert cl.looks_like_insert_code("WCMX 0903") is False

    def test_milling_apkt(self):
        assert cl.looks_like_insert_code("APKT 1003") is True

    def test_milling_spmx(self):
        assert cl.looks_like_insert_code("SPMX 1503") is True

    def test_boring_rcmt(self):
        assert cl.looks_like_insert_code("RCMT 0803") is True

    def test_specialty_wxcu(self):
        assert cl.looks_like_insert_code("WXCU 040208") is True

    def test_specialty_hngx(self):
        assert cl.looks_like_insert_code("HNGX 0905") is True

    def test_case_insensitive(self):
        assert cl.looks_like_insert_code("cnmg 120408") is True
        assert cl.looks_like_insert_code("CnMg 120408") is True

    def test_word_boundary_protected(self):
        """No partial-substring matches inside larger words."""
        assert cl.looks_like_insert_code("XCNMGX") is False

    def test_no_separator_no_match(self):
        """Without whitespace, CNMG120408 doesn't break to a word boundary."""
        assert cl.looks_like_insert_code("CNMG120408") is False

    def test_drill_text_not_insert(self):
        assert cl.looks_like_insert_code("foret D5") is False

    def test_empty(self):
        assert cl.looks_like_insert_code("") is False

    def test_none(self):
        assert cl.looks_like_insert_code(None) is False


# ---- is_insert_text ----

class TestIsInsertText:
    def test_via_iso_code(self):
        assert cl.is_insert_text("WNMG 080408") is True

    def test_via_keyword_plaquette(self):
        assert cl.is_insert_text("plaquette carbure") is True

    def test_via_keyword_wsp_german(self):
        assert cl.is_insert_text("Wendeschneidplatte") is True

    def test_multiple_parts(self):
        assert cl.is_insert_text("WSP", "CNMG 12", "") is True

    def test_not_an_insert(self):
        assert cl.is_insert_text("foret HSS") is False

    def test_empty(self):
        assert cl.is_insert_text("") is False


# ---- is_ppe_text ----

class TestIsPpeText:
    def test_helmet(self):
        assert cl.is_ppe_text("safety helmet") is True

    def test_french_casque(self):
        assert cl.is_ppe_text("casque de protection") is True

    def test_not_ppe(self):
        assert cl.is_ppe_text("foret D5") is False

    def test_empty(self):
        assert cl.is_ppe_text("") is False


# ---- normalize_product_category ----

class TestNormalizeProductCategory:
    def test_iso_code_to_inserts(self):
        assert cl.normalize_product_category("CNMG") == "inserts"

    def test_word_insert(self):
        assert cl.normalize_product_category("insert") == "inserts"

    def test_drills_french(self):
        assert cl.normalize_product_category("foret") == "drills"

    def test_drills_english(self):
        assert cl.normalize_product_category("drill") == "drills"

    def test_mills_french(self):
        assert cl.normalize_product_category("fraise") == "mills"

    def test_helmet_ppe(self):
        assert cl.normalize_product_category("helmet") == "ppe"

    def test_boring_bar(self):
        assert cl.normalize_product_category("boring bar") == "boring_bars"

    def test_garbage_returns_other(self):
        assert cl.normalize_product_category("nonsense12345") == "other"

    def test_empty(self):
        assert cl.normalize_product_category("") == ""

    def test_none(self):
        assert cl.normalize_product_category(None) == ""

    # ---- compound German thread-tool words must beat the generic drill/mill
    # substring match (Gewindebohrer contains 'bohrer', Gewindefräser contains
    # 'fräser'). These are taps / thread mills, not drills / mills. ----
    def test_gewindebohrer_is_taps_not_drills(self):
        assert cl.normalize_product_category("Gewindebohrer") == "taps"

    def test_gewindefraeser_is_thread_mills_not_mills(self):
        assert cl.normalize_product_category("Gewindefräser") == "thread_mills"

    def test_gewindebohrfraeser_is_thread_mills(self):
        assert cl.normalize_product_category("Gewindebohrfräser") == "thread_mills"

    def test_schneideisen_is_thread_dies(self):
        assert cl.normalize_product_category("Schneideisen") == "thread_dies"

    # ---- controls: real drills/mills with compound names must STAY drills/mills ----
    def test_stufenbohrer_stays_drills(self):
        # A step drill is a drill at the product-category level; the step-drill
        # distinction is handled separately at KROMI-code time.
        assert cl.normalize_product_category("Stufenbohrer") == "drills"

    def test_plain_bohrer_stays_drills(self):
        assert cl.normalize_product_category("Bohrer") == "drills"

    def test_schaftfraeser_stays_mills(self):
        assert cl.normalize_product_category("Schaftfräser") == "mills"

    def test_insert_priority_over_drill(self):
        """INSERT must win over drilling/milling wording in the same text."""
        assert cl.normalize_product_category("CNMG drill") == "inserts"


# ---- first_valid_product_category ----

class TestFirstValidProductCategory:
    def test_first_valid_wins(self):
        result = cl.first_valid_product_category(pd.Series(["", "foret"]))
        assert result == "drills"

    def test_other_skipped(self):
        """'other' is treated as not-valid; first real category wins."""
        result = cl.first_valid_product_category(pd.Series(["nonsense", "foret"]))
        assert result == "drills"

    def test_empty_series_default(self):
        result = cl.first_valid_product_category(pd.Series([]), default="X")
        assert result == "X"

    def test_all_empty_default(self):
        result = cl.first_valid_product_category(pd.Series(["", ""]), default="Y")
        assert result == "Y"


# ---- is_weak_category ----

class TestIsWeakCategory:
    def test_empty_is_weak(self):
        assert cl.is_weak_category("") is True

    def test_other_is_weak(self):
        assert cl.is_weak_category("other") is True

    def test_other_uppercase_is_weak(self):
        assert cl.is_weak_category("OTHER") is True

    def test_whitespace_is_weak(self):
        assert cl.is_weak_category("  ") is True

    def test_none_is_weak(self):
        assert cl.is_weak_category(None) is True

    def test_drills_not_weak(self):
        assert cl.is_weak_category("drills") is False

    def test_inserts_not_weak(self):
        assert cl.is_weak_category("inserts") is False


# ---- _kw_matches ----

class TestKwMatches:
    def test_long_keyword_substring(self):
        """Long keyword (>4 chars) matches as substring."""
        assert cl._kw_matches("hello foret here", "foret") is True

    def test_short_keyword_word_boundary(self):
        """Short keyword (≤4 chars) requires word boundary."""
        assert cl._kw_matches("vis m6", "vis") is True

    def test_short_keyword_not_inside_word(self):
        """'vis' must not match inside 'tournevis'."""
        assert cl._kw_matches("tournevis", "vis") is False

    def test_empty_keyword(self):
        assert cl._kw_matches("anything", "") is False

    def test_4_char_threshold(self):
        """4-char keywords still use word boundary."""
        assert cl._kw_matches("test bohr here", "bohr") is True
        # But "bohr" inside a word should fail
        assert cl._kw_matches("aabohrbb", "bohr") is False


# ---- _shorthand_matches ----

class TestShorthandMatches:
    def test_fo_at_start(self):
        assert cl._shorthand_matches("FO DAG D3,27", "FO") is True

    def test_fo_after_dot(self):
        assert cl._shorthand_matches("X.FO 5", "FO") is True

    def test_fo_before_dot(self):
        assert cl._shorthand_matches("FO.CW", "FO") is True

    def test_fo_in_middle(self):
        assert cl._shorthand_matches("X FO Y", "FO") is True

    def test_foret_does_not_match_fo(self):
        """'FORET' (the full word) should NOT match shorthand 'FO'."""
        assert cl._shorthand_matches("FORET", "FO") is False

    def test_info_does_not_match_fo(self):
        assert cl._shorthand_matches("INFO 5", "FO") is False

    def test_lowercase_does_not_match(self):
        """Shorthand matching requires UPPERCASE input."""
        assert cl._shorthand_matches("fo foo", "FO") is False

    def test_al_shorthand(self):
        assert cl._shorthand_matches("AL 1T D8H7", "AL") is True

    def test_empty(self):
        assert cl._shorthand_matches("", "FO") is False
        assert cl._shorthand_matches("FO X", "") is False


# ---- _supplier_brand_matches ----

class TestSupplierBrandMatches:
    def test_exact_match(self):
        assert cl._supplier_brand_matches("seco", "seco") is True

    def test_long_corporate_name(self):
        assert cl._supplier_brand_matches("SECO TOOLS FRANCE", "seco") is True

    def test_case_insensitive(self):
        assert cl._supplier_brand_matches("ISCAR FRANCE", "iscar") is True

    def test_no_match(self):
        assert cl._supplier_brand_matches("Sandvik", "seco") is False

    def test_empty_supplier(self):
        assert cl._supplier_brand_matches("", "seco") is False

    def test_empty_brand(self):
        assert cl._supplier_brand_matches("seco", "") is False

    def test_none_supplier(self):
        assert cl._supplier_brand_matches(None, "seco") is False


# ---- _check_supplier_code_pattern ----

class TestCheckSupplierCodePattern:
    def test_seco_wnw(self):
        result = cl._check_supplier_code_pattern("WNW08HD", "seco")
        assert result is not None
        assert result[0] == "inserts"

    def test_iscar_ic_grade(self):
        result = cl._check_supplier_code_pattern("IC8250", "iscar")
        assert result is not None
        assert result[0] == "inserts"

    def test_sandvik(self):
        result = cl._check_supplier_code_pattern("5322-425-04", "sandvik")
        assert result is not None

    def test_no_supplier(self):
        assert cl._check_supplier_code_pattern("WNW08HD", "") is None

    def test_wrong_supplier(self):
        """Right code, wrong brand → no match."""
        assert cl._check_supplier_code_pattern("WNW08HD", "sandvik") is None

    def test_empty_code(self):
        assert cl._check_supplier_code_pattern("", "seco") is None

    def test_evidence_format(self):
        """Returned evidence starts with 'supplier_pattern:'."""
        result = cl._check_supplier_code_pattern("WNW08HD", "seco")
        assert result[1].startswith("supplier_pattern:")


# ---- _check_supplier_specialty ----

class TestCheckSupplierSpecialty:
    def test_guhring_drills(self):
        result = cl._check_supplier_specialty("GUHRING FRANCE")
        assert result is not None
        assert result[0] == "drills"

    def test_mapal(self):
        result = cl._check_supplier_specialty("MAPAL")
        assert result is not None

    def test_unknown_brand(self):
        assert cl._check_supplier_specialty("UnknownBrand") is None

    def test_empty(self):
        assert cl._check_supplier_specialty("") is None

    def test_evidence_format(self):
        result = cl._check_supplier_specialty("GUHRING FRANCE")
        assert result[1].startswith("supplier_specialty:")


# ---- derive_tool_class ----

class TestDeriveToolClass:
    def test_iso_cnmg_turning(self):
        assert cl.derive_tool_class("iso:CNMG", "", "", "inserts") == "turning_insert"

    def test_iso_tnmg_turning(self):
        assert cl.derive_tool_class("iso:TNMG", "", "", "inserts") == "turning_insert"

    def test_iso_apkt_milling(self):
        assert cl.derive_tool_class("iso:APKT", "", "", "inserts") == "milling_insert"

    def test_iso_spmx_milling(self):
        assert cl.derive_tool_class("iso:SPMX", "", "", "inserts") == "milling_insert"

    def test_iso_wpmt_drilling(self):
        assert cl.derive_tool_class("iso:WPMT", "", "", "inserts") == "drilling_insert"

    def test_shorthand_fo(self):
        assert cl.derive_tool_class("shorthand:FO", "", "", "drills") == "solid_carbide_drill"

    def test_shorthand_fr(self):
        assert cl.derive_tool_class("shorthand:FR", "", "", "mills") == "solid_end_mill"

    def test_shorthand_al(self):
        assert cl.derive_tool_class("shorthand:AL", "", "", "reamers") == "reamer"

    def test_shorthand_me(self):
        assert cl.derive_tool_class("shorthand:ME", "", "", "accessories") == "grinding_wheel"

    def test_keyword_derives_from_pc(self):
        """Generic keyword evidence falls back to PC-based lookup."""
        result = cl.derive_tool_class("keyword:foret", "", "", "drills")
        assert result != "other"

    def test_empty_evidence_returns_other(self):
        assert cl.derive_tool_class("", "", "", "drills") == "other"

    def test_none_evidence_returns_other(self):
        assert cl.derive_tool_class(None, "", "", "drills") == "other"

    def test_unknown_pc_returns_other(self):
        assert cl.derive_tool_class("keyword:xyz", "", "", "nonexistent_pc") == "other"


# ---- classify_with_evidence ----

class TestClassifyWithEvidence:
    def test_iso_cnmg(self):
        cat, ev = cl.classify_with_evidence("CNMG 120408", "", "", "", "Tools")
        assert cat == "inserts"
        assert "iso:CNMG" in ev

    def test_insert_keyword_plaquette(self):
        cat, ev = cl.classify_with_evidence("plaquette carbure", "", "", "", "Tools")
        assert cat == "inserts"
        assert "keyword:" in ev

    def test_shorthand_fo_drills(self):
        cat, ev = cl.classify_with_evidence("FO DAG D3,27", "", "", "", "Tools")
        assert cat == "drills"
        assert ev == "shorthand:FO"

    def test_shorthand_fr_mills(self):
        cat, ev = cl.classify_with_evidence("FR D8 carb", "", "", "", "Tools")
        assert cat == "mills"
        assert ev == "shorthand:FR"

    def test_supplier_pattern_seco_wnw(self):
        """Seco WNW pattern requires the whole code to match WNW\\d{2,3}[A-Z]+
        with no trailing separator. The bare grade code WNW08HD matches."""
        cat, ev = cl.classify_with_evidence("WNW08HD", "", "WNW08HD", "seco", "Tools")
        assert cat == "inserts"
        assert "supplier_pattern" in ev

    def test_supplier_pattern_with_trailing_does_not_match(self):
        """WNW08HD-04 doesn't match — anchored pattern excludes trailing -04."""
        cat, ev = cl.classify_with_evidence("WNW08HD-04", "", "WNW08HD-04", "seco", "Tools")
        # Falls through to other paths (or no-match)
        # We just verify the supplier_pattern branch didn't trigger
        assert "supplier_pattern" not in ev

    def test_ppe_listing_masque(self):
        cat, ev = cl.classify_with_evidence("masque", "", "", "", "PPE")
        assert cat == "ppe"

    def test_foret_keyword(self):
        cat, ev = cl.classify_with_evidence("foret HSS D2.5", "", "", "", "Tools")
        assert cat == "drills"
        assert "keyword:" in ev

    def test_fraise_keyword(self):
        cat, ev = cl.classify_with_evidence("fraise carbure D10", "", "", "", "Tools")
        assert cat == "mills"

    def test_specialty_supplier_guhring(self):
        cat, ev = cl.classify_with_evidence("Z6 D8 carb HM", "", "ABC123", "GUHRING FRANCE", "Tools")
        assert cat == "drills"
        assert "supplier_specialty" in ev

    def test_no_match_returns_none(self):
        cat, ev = cl.classify_with_evidence("xyz123 nonsense", "", "", "", "Tools")
        assert cat is None
        assert ev == "no-match"

    def test_empty_returns_none(self):
        cat, ev = cl.classify_with_evidence("", "", "", "", "Tools")
        assert cat is None

    def test_shorthand_only_on_tools_listing(self):
        """FO shorthand should NOT trigger on PPE listing."""
        cat, ev = cl.classify_with_evidence("FO test", "", "", "", "PPE")
        # On PPE listing, FO doesn't match shorthand path
        assert ev != "shorthand:FO"


# ---- heuristic_size_category ----

class TestHeuristicSizeCategory:
    def test_inserts_always_s(self):
        assert cl.heuristic_size_category("inserts", "anything", "") == "S"

    def test_screws_always_s(self):
        assert cl.heuristic_size_category("screws", "anything", "") == "S"

    def test_boring_bars_no_dims_default_xl(self):
        # An unspecified boring bar (no measurable dimension) still defaults to XL.
        assert cl.heuristic_size_category("boring_bars", "anything", "") == "XL"

    def test_boring_bars_small_diameter_is_not_xl(self):
        # A thin boring bar must be sized by its measured diameter, not blanket
        # XL: Ø1.42 mm reads as S so it can share a Carousel/Helix.
        assert cl.heuristic_size_category(
            "boring_bars", "VHM- Bohrstange Ø 01,42 x R0,03 x 4,5 4x 40mm TiAlN", ""
        ) == "S"

    def test_boring_bars_large_diameter_sized_by_dimension(self):
        # A genuinely fat boring bar is sized up from its diameter.
        assert cl.heuristic_size_category("boring_bars", "Bohrstange Ø 20,0 x 150mm", "") == "L"
        assert cl.heuristic_size_category("boring_bars", "Bohrstange Ø 50 x 300mm", "") == "XL"

    def test_ppe_helmet_xl(self):
        assert cl.heuristic_size_category("ppe", "safety helmet", "") == "XL"

    def test_ppe_boot_xl(self):
        assert cl.heuristic_size_category("ppe", "safety boot", "") == "XL"

    def test_ppe_coverall_xxl(self):
        assert cl.heuristic_size_category("ppe", "coverall", "") == "XXL"

    def test_ppe_earplug_s(self):
        assert cl.heuristic_size_category("ppe", "earplug", "") == "S"

    def test_ppe_generic_m(self):
        assert cl.heuristic_size_category("ppe", "unknown ppe item", "") == "M"

    def test_diameter_3mm_s(self):
        assert cl.heuristic_size_category("drills", "D 3 mm", "") == "S"

    def test_diameter_8mm_m(self):
        assert cl.heuristic_size_category("drills", "D 8mm", "") == "M"

    def test_diameter_25mm_l(self):
        assert cl.heuristic_size_category("drills", "D25 mm", "") == "L"

    def test_diameter_40mm_xl(self):
        assert cl.heuristic_size_category("drills", "D40 carb", "") == "XL"

    # v33 regression: European metric formatting (comma decimals, leading zeros,
    # space after Ø) used to be mis-parsed so tiny drills read as XL. e.g.
    # "Ø 02,40mm" grabbed the "40mm" fragment -> 40 mm -> XL.
    def test_euro_decimal_small_drill_is_s(self):
        assert cl.heuristic_size_category("drills", "VHM- Bohrer Ø 02,40mm SB IK", "") == "S"

    def test_euro_decimal_tiny_drill_is_s(self):
        assert cl.heuristic_size_category("drills", "HSS- Bohrer Ø 01,50mm Typ N DIN 1897", "") == "S"

    def test_euro_decimal_with_leading_zero_micro_drill_is_s(self):
        # 1.02 mm, with deep-hole "6xD" and a 130° point angle that must NOT be
        # read as a diameter.
        assert cl.heuristic_size_category("drills", "VHM- Bohrer Ø 01,02mm x 6,50mm 6xD 130°", "") == "S"

    def test_euro_decimal_mid_drill_is_m(self):
        assert cl.heuristic_size_category("drills", "VHM- Bohrer Ø 08,40mm 3xD TiAlN", "") == "M"

    def test_euro_decimal_16mm_mill_is_l_not_xxl(self):
        # Was returning None (-> AI guessed XXL -> a whole Locker cabinet for one
        # tool). 16 mm is L.
        assert cl.heuristic_size_category("mills", "VHM- Schaftfräser Ø 16,00 x 48 Z4", "") == "L"

    def test_deep_hole_notation_not_a_diameter(self):
        # No Ø here; the "6xD" must not be read as a diameter, and the 130° angle
        # must not become 130 mm.
        assert cl.heuristic_size_category("drills", "Bohrer 6xD 130° TiAlN", "") != "XL"

    def test_no_info_returns_none(self):
        assert cl.heuristic_size_category("drills", "drill", "") is None


# ---- heuristic_pack_units ----

class TestHeuristicPackUnits:
    def test_inserts_default_10(self):
        assert cl.heuristic_pack_units("inserts") == 10

    def test_drills_default_1(self):
        assert cl.heuristic_pack_units("drills") == 1

    def test_mills_default_1(self):
        assert cl.heuristic_pack_units("mills") == 1

    def test_ppe_default_1(self):
        assert cl.heuristic_pack_units("ppe") == 1

    def test_screws_default_1(self):
        assert cl.heuristic_pack_units("screws") == 1

    def test_other_returns_none(self):
        assert cl.heuristic_pack_units("other") is None

    def test_empty_returns_none(self):
        assert cl.heuristic_pack_units("") is None


# ---- heuristic_pack_units_from_text ----

class TestHeuristicPackUnitsFromText:
    def test_carton_de_60(self):
        q, label = cl.heuristic_pack_units_from_text("carton de 60")
        assert q == 60
        assert label != ""

    def test_qte_50(self):
        q, label = cl.heuristic_pack_units_from_text("qte 50")
        assert q == 50

    def test_qte_accented(self):
        """qté gets normalized to qte then parsed."""
        q, label = cl.heuristic_pack_units_from_text("qté25")
        assert q == 25

    def test_boite_de_10(self):
        q, label = cl.heuristic_pack_units_from_text("boite de 10")
        assert q == 10

    def test_no_hint(self):
        q, label = cl.heuristic_pack_units_from_text("no hint here")
        assert q is None
        assert label == ""

    def test_empty(self):
        q, label = cl.heuristic_pack_units_from_text("")
        assert q is None


# ---- detect_item_family ----

class TestDetectItemFamily:
    def test_disque_velcro_abrasive(self):
        assert cl.detect_item_family("DISQUE VELCRO", "") == "abrasive_discs"

    def test_abrasif(self):
        assert cl.detect_item_family("abrasif", "") == "abrasive_discs"

    def test_trizact(self):
        assert cl.detect_item_family("Trizact pad", "") == "abrasive_discs"

    def test_godet_paint(self):
        assert cl.detect_item_family("godet de peinture", "") == "paint_consumables"

    def test_etiquette_label(self):
        assert cl.detect_item_family("Etiquette adhesif", "") == "tapes_labels"

    def test_chiffon_wipes(self):
        assert cl.detect_item_family("chiffon coton", "") == "cloth_wipes"

    def test_mastic_adhesive(self):
        assert cl.detect_item_family("Mastic RTV", "") == "adhesives_sealants"

    def test_charlotte_disposable_ppe(self):
        assert cl.detect_item_family("Charlotte capilaire", "") == "disposable_ppe"

    def test_filtre_p3_respirator(self):
        assert cl.detect_item_family("filtre P3", "") == "respirator_filters"

    def test_foret_other(self):
        assert cl.detect_item_family("foret D5", "") == "other"

    def test_empty_other(self):
        assert cl.detect_item_family("", "") == "other"


# ---- Integration: full SampleCo reclassification ----

@pytest.mark.integration
class TestSampleCatalogIntegration:
    """Reclassify every SampleCo row and verify expected baseline properties."""

    def test_classifies_at_least_half_of_sample(self, sample_dataframe):
        """At least 50% of SampleCo rows should classify deterministically without
        falling through to AI ('no-match')."""
        desc_col = "Bezeichnung 1 / Description 1"
        desc2_col = "Bezeichnung 2 / Description 2"
        code_col = "Kromi Artikelnummer / Kromi Art.-No."
        sup_col = "Kunden Artikelnummer / Customer Art.-No"

        matched = 0
        for _, row in sample_dataframe.iterrows():
            d1 = str(row.get(desc_col, "") or "")
            d2 = str(row.get(desc2_col, "") or "")
            code = str(row.get(code_col, "") or "")
            sup = str(row.get(sup_col, "") or "")
            cat, _ev = cl.classify_with_evidence(d1, d2, code, sup, "Tools")
            if cat is not None:
                matched += 1
        # 50% baseline; SampleCo typically gets ~80% matched
        assert matched / len(sample_dataframe) >= 0.5

    def test_no_classification_errors(self, sample_dataframe):
        """Every row should classify without raising an exception."""
        desc_col = "Bezeichnung 1 / Description 1"
        code_col = "Kromi Artikelnummer / Kromi Art.-No."
        sup_col = "Kunden Artikelnummer / Customer Art.-No"

        for _, row in sample_dataframe.iterrows():
            d1 = str(row.get(desc_col, "") or "")
            code = str(row.get(code_col, "") or "")
            sup = str(row.get(sup_col, "") or "")
            cat, ev = cl.classify_with_evidence(d1, "", code, sup, "Tools")
            assert cat is None or isinstance(cat, str)
            assert isinstance(ev, str)




class TestInchSizeEstimation:
    """Inch-diameter parsing feeding the size heuristic (engine.classification)."""

    # --- parser: positive cases (value -> mm, within tolerance) ---
    def test_bare_leading_dot_decimal(self):
        assert abs(cl.parse_inch_diameter_mm(".370") - 9.398) < 1e-6

    def test_zero_prefixed_four_decimals(self):
        assert abs(cl.parse_inch_diameter_mm("0.2502") - 6.35508) < 1e-4

    def test_multiple_dims_takes_largest(self):
        assert abs(cl.parse_inch_diameter_mm(".1605 X .127") - (0.1605 * 25.4)) < 1e-6

    def test_marked_decimal(self):
        assert abs(cl.parse_inch_diameter_mm('0.5"') - 12.7) < 1e-6

    def test_marked_whole(self):
        assert abs(cl.parse_inch_diameter_mm("2 inch") - 50.8) < 1e-6

    def test_fraction_quarter(self):
        assert abs(cl.parse_inch_diameter_mm('1/4"') - 6.35) < 1e-6

    def test_fraction_half_not_confused_by_denominator(self):
        # Regression: the "2" in 1/2" must not be read as 2 inches.
        assert abs(cl.parse_inch_diameter_mm('1/2"') - 12.7) < 1e-6

    # --- parser: conservative negatives (must NOT fire) ---
    def test_millimetre_value_ignored(self):
        assert cl.parse_inch_diameter_mm("12.5 mm") is None

    def test_diameter_symbol_mm_ignored(self):
        assert cl.parse_inch_diameter_mm("Ø12") is None

    def test_quantity_ignored(self):
        assert cl.parse_inch_diameter_mm("qty 100 pcs") is None

    def test_one_decimal_bare_ignored(self):
        assert cl.parse_inch_diameter_mm(".5") is None

    def test_leading_digit_bare_ignored(self):
        assert cl.parse_inch_diameter_mm("1.250") is None

    def test_empty(self):
        assert cl.parse_inch_diameter_mm("") is None
        assert cl.parse_inch_diameter_mm(None) is None

    # --- integration with the size heuristic + bands ---
    def test_heuristic_inch_drill_medium(self):
        assert cl.heuristic_size_category("drills", "DRILL .370", "") == "M"

    def test_heuristic_inch_reamer_medium(self):
        assert cl.heuristic_size_category("drills", "REAMER 0.2502", "") == "M"

    def test_heuristic_inch_small(self):
        assert cl.heuristic_size_category("drills", "DRILL .1605 X .127", "") == "S"

    def test_heuristic_fraction_large(self):
        assert cl.heuristic_size_category("drills", '1/2" DRILL', "") == "L"

    def test_heuristic_mm_still_works(self):
        assert cl.heuristic_size_category("drills", "Ø8 drill", "") == "M"

    def test_heuristic_no_size_when_no_signal(self):
        assert cl.heuristic_size_category("drills", "drill 100 pcs", "") is None
