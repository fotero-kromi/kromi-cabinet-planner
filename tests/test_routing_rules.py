"""Tests for engine.routing_rules — insert threshold override and
standard/special coverage classification."""
import pytest

from engine import routing_rules as rr


# ---------------------------------------------------------------------------
# Part 1: insert detection + threshold selection
# ---------------------------------------------------------------------------
class TestIsInsert:
    def test_product_category_inserts(self):
        assert rr.is_insert("inserts") is True
        assert rr.is_insert("Inserts") is True
        assert rr.is_insert(" INSERTS ") is True

    def test_toolclass_fallback(self):
        assert rr.is_insert("", "turning_insert") is True
        assert rr.is_insert("", "milling_insert") is True
        assert rr.is_insert("other", "drilling_insert") is True

    def test_non_insert(self):
        assert rr.is_insert("drills", "solid_carbide_drill") is False
        assert rr.is_insert("mills", "solid_end_mill") is False
        assert rr.is_insert("") is False
        assert rr.is_insert(None) is False


class TestKtcThresholdFor:
    def test_override_off_uses_standard_for_inserts(self):
        assert rr.ktc_threshold_for(True, 0.7, 10.0, False) == 0.7

    def test_override_off_uses_standard_for_non_inserts(self):
        assert rr.ktc_threshold_for(False, 0.7, 10.0, False) == 0.7

    def test_override_on_inserts_use_insert_threshold(self):
        assert rr.ktc_threshold_for(True, 0.7, 10.0, True) == 10.0

    def test_override_on_non_inserts_use_standard(self):
        assert rr.ktc_threshold_for(False, 0.7, 10.0, True) == 0.7

    def test_returns_float(self):
        assert isinstance(rr.ktc_threshold_for(True, 0.7, 10, True), float)


# ---------------------------------------------------------------------------
# Part 2: standard / special classification (7 languages)
# ---------------------------------------------------------------------------
class TestClassifyStandardSpecial:
    @pytest.mark.parametrize("value", [
        "standard", "Standard", "STD", "normal", "regular",          # en
        "ordinaire", "courant",                                       # fr
        "Serie", "Serienteil", "Katalogartikel", "Lagerartikel",      # de
        "estándar", "Estandar",                                       # es
        "standardowy", "zwykły", "katalogowy",                        # pl
        "štandardný", "bežný",                                        # sk
        "standardni", "navadni", "običajni", "serijski",              # sl
    ])
    def test_standard_terms(self, value):
        assert rr.classify_standard_special(value) == rr.STANDARD

    @pytest.mark.parametrize("value", [
        "special", "Special", "custom", "non-standard", "made to order",  # en
        "spécial", "spécifique", "sur mesure", "particulier",             # fr
        "Sonder", "Sonderwerkzeug", "Sonderteil", "Spezial", "speziell",  # de
        "especial", "específico", "a medida",                             # es
        "specjalny", "niestandardowy", "na zamówienie",                   # pl
        "špeciálny", "neštandardný", "zvláštny", "na mieru",              # sk
        "poseben", "specialni", "po naročilu",                            # sl
    ])
    def test_special_terms(self, value):
        assert rr.classify_standard_special(value) == rr.SPECIAL

    def test_non_standard_variants_classify_as_special_not_standard(self):
        # These literally contain 'standard' but mean the opposite.
        assert rr.classify_standard_special("non-standard") == rr.SPECIAL
        assert rr.classify_standard_special("niestandardowy") == rr.SPECIAL
        assert rr.classify_standard_special("neštandardný") == rr.SPECIAL

    def test_unknown_and_empty(self):
        assert rr.classify_standard_special("") == rr.UNKNOWN
        assert rr.classify_standard_special(None) == rr.UNKNOWN
        assert rr.classify_standard_special("12345") == rr.UNKNOWN
        assert rr.classify_standard_special("blue") == rr.UNKNOWN

    def test_accent_insensitive(self):
        assert rr.classify_standard_special("SPÉCIAL") == rr.SPECIAL
        assert rr.classify_standard_special("Štandard") == rr.STANDARD

    @pytest.mark.parametrize("value,expected", [
        (1, rr.STANDARD), ("1", rr.STANDARD), (1.0, rr.STANDARD), ("1.0", rr.STANDARD),
        ("yes", rr.STANDARD), ("Yes", rr.STANDARD), ("Y", rr.STANDARD), ("true", rr.STANDARD),
        (2, rr.SPECIAL), ("2", rr.SPECIAL), (2.0, rr.SPECIAL), ("2.0", rr.SPECIAL),
        ("no", rr.SPECIAL), ("No", rr.SPECIAL), ("N", rr.SPECIAL), ("false", rr.SPECIAL),
    ])
    def test_binary_tokens(self, value, expected):
        assert rr.classify_standard_special(value) == expected

    def test_unsupported_numeric_codes_are_unknown(self):
        # The numeric encoding is 1 = standard, 2 = special. Every other bare
        # code is deliberately NOT mapped; a site must rewrite to 1/2, yes/no,
        # or the standard/special words. 0 is no longer special (dropped with
        # the move to the 1/2 scheme), and 8 was never mapped.
        assert rr.classify_standard_special(0) == rr.UNKNOWN
        assert rr.classify_standard_special("0") == rr.UNKNOWN
        assert rr.classify_standard_special(8) == rr.UNKNOWN
        assert rr.classify_standard_special("8.0") == rr.UNKNOWN

    def test_binary_exact_match_does_not_false_trigger(self):
        # 'no' must not match inside 'normal' (standard); '1' not inside '12'.
        assert rr.classify_standard_special("normal") == rr.STANDARD
        assert rr.classify_standard_special("12345") == rr.UNKNOWN


class TestCoverageDaysFor:
    def test_split_inactive_always_standard(self):
        assert rr.coverage_days_for("special", 18, 30, False) == 18.0
        assert rr.coverage_days_for("standard", 18, 30, False) == 18.0
        assert rr.coverage_days_for("", 18, 30, False) == 18.0

    def test_split_active_special_uses_special(self):
        assert rr.coverage_days_for("special", 18, 30, True) == 30.0

    def test_split_active_standard_uses_standard(self):
        assert rr.coverage_days_for("standard", 18, 30, True) == 18.0

    def test_split_active_unknown_defaults_to_standard(self):
        assert rr.coverage_days_for("", 18, 30, True) == 18.0

    def test_returns_float(self):
        assert isinstance(rr.coverage_days_for("special", 18, 30, True), float)
