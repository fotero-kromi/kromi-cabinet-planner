"""Tests for engine.dimensions — package dimension extraction."""

from engine import dimensions as dim
from engine.dimensions import extract_package_dims as ex


# ---- Three-dimension formats ----

class TestThreeDimensions:
    def test_plain_x(self):
        r = ex("200x40x40")
        assert r.values_mm == [200.0, 40.0, 40.0]
        assert r.count == 3

    def test_spaced_with_unit(self):
        r = ex("200 x 40 x 40 mm")
        assert r.values_mm == [200.0, 40.0, 40.0]

    def test_unicode_multiplication_sign(self):
        r = ex("200×40×40")
        assert r.values_mm == [200.0, 40.0, 40.0]

    def test_asterisk_separator(self):
        r = ex("200*40*40")
        assert r.values_mm == [200.0, 40.0, 40.0]

    def test_labelled_lbh(self):
        r = ex("L200 B40 H40")
        assert sorted(r.values_mm, reverse=True) == [200.0, 40.0, 40.0]
        assert "labelled" in r.evidence

    def test_evidence_tag_3d(self):
        r = ex("200x40x40")
        assert r.evidence == "parsed:3d"


# ---- Two-dimension / cylinder formats ----

class TestTwoDimensions:
    def test_diameter_length(self):
        r = ex("Ø25 x 180")
        assert r.values_mm == [25.0, 180.0]
        assert r.is_diameter is True
        assert "diameter" in r.evidence

    def test_slash_separator(self):
        r = ex("25/180")
        assert r.values_mm == [25.0, 180.0]
        assert "slash" in r.evidence

    def test_d_equals_l_equals(self):
        r = ex("D=25 L=180")
        assert sorted(r.values_mm) == [25.0, 180.0]
        assert r.is_diameter is True

    def test_unit_suffix(self):
        r = ex("25x180mm")
        assert r.values_mm == [25.0, 180.0]


# ---- Unit conversion ----

class TestUnitConversion:
    def test_cm_to_mm(self):
        r = ex("12 cm x 4 cm")
        assert r.values_mm == [120.0, 40.0]

    def test_m_to_mm(self):
        r = ex("1 m x 0.5 m")
        assert r.values_mm == [1000.0, 500.0]

    def test_trailing_unit_applies_to_all(self):
        r = ex("20 x 4 x 4 cm")
        assert r.values_mm == [200.0, 40.0, 40.0]


# ---- Decimal / thousands disambiguation ----

class TestNumberFormats:
    def test_comma_decimal(self):
        r = ex("150,5 x 40,5")
        assert r.values_mm == [150.5, 40.5]

    def test_comma_thousands(self):
        """1,234 (comma + 3 digits) is a thousands separator -> 1234."""
        r = ex("1,234x40")
        assert r.values_mm == [1234.0, 40.0]

    def test_dot_thousands(self):
        """European dot thousands: 1.234 -> 1234."""
        r = ex("1.234x40")
        assert r.values_mm == [1234.0, 40.0]

    def test_dot_decimal(self):
        r = ex("40.5x30")
        assert r.values_mm == [40.5, 30.0]


# ---- Single value ----

class TestSingleValue:
    def test_plain_single(self):
        r = ex("200")
        assert r.values_mm == [200.0]
        assert r.count == 1
        assert r.evidence == "parsed:1d"

    def test_single_with_unit(self):
        r = ex("20 cm")
        assert r.values_mm == [200.0]


# ---- No-match / fallback cases ----

class TestNoMatch:
    def test_empty(self):
        r = ex("")
        assert r.count == 0
        assert r.evidence == "no-match"
        assert r.ok is False

    def test_none(self):
        r = ex(None)
        assert r.count == 0

    def test_text_only(self):
        r = ex("no dimensions here")
        assert r.count == 0

    def test_article_number_ignored(self):
        """An article number shouldn't be misread as a single dimension if
        it's clearly non-numeric context."""
        r = ex("Artikel ABC")
        assert r.count == 0


# ---- Out-of-bounds guarding ----

class TestBounds:
    def test_too_large_rejected(self):
        """A 5000 mm dimension is out of range (>3000); with only one other
        valid dim the parse fails safe to no-match."""
        r = ex("5000x40")
        assert r.count == 0

    def test_too_small_rejected(self):
        r = ex("0.5x0.5")
        assert r.count == 0

    def test_partial_valid_kept_when_enough(self):
        """5000 rejected but 40 and 30 are valid -> keep the two valid dims."""
        r = ex("5000x40x30")
        assert r.values_mm == [40.0, 30.0]


# ---- sorted_mm helper (orientation-free fit support) ----

class TestSortedDims:
    def test_sorted_descending(self):
        r = ex("40x200x40")
        assert r.sorted_mm == [200.0, 40.0, 40.0]

    def test_sorted_two(self):
        r = ex("25x180")
        assert r.sorted_mm == [180.0, 25.0]


# ---- raw preservation (audit) ----

class TestRawPreservation:
    def test_raw_kept(self):
        r = ex("  200 x 40 x 40 mm  ")
        assert r.raw == "200 x 40 x 40 mm"
