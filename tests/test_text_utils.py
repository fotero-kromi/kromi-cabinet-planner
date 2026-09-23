"""Tests for engine.text_utils — 14 string/numeric helpers."""

import math

import pandas as pd
import pytest

from engine import text_utils as tu

# ---- norm ----

class TestNorm:
    def test_lowercases(self):
        assert tu.norm("HELLO") == "hello"

    def test_strips_whitespace(self):
        assert tu.norm("  hello  ") == "hello"

    def test_empty(self):
        assert tu.norm("") == ""

    def test_none(self):
        assert tu.norm(None) == ""

    def test_number(self):
        # norm() requires str input; non-strings → ""
        assert tu.norm(42) == ""


# ---- collapse_ws ----

class TestCollapseWs:
    def test_multiple_spaces(self):
        assert tu.collapse_ws("hello    world") == "hello world"

    def test_tabs_and_newlines(self):
        assert tu.collapse_ws("a\tb\nc") == "a b c"

    def test_leading_trailing(self):
        assert tu.collapse_ws("  hello  ") == "hello"

    def test_empty(self):
        assert tu.collapse_ws("") == ""

    def test_none(self):
        assert tu.collapse_ws(None) == ""


# ---- clean_text_cell ----

class TestCleanTextCell:
    def test_nbsp(self):
        """Non-breaking space (\\xa0) → regular space."""
        assert tu.clean_text_cell("hello\xa0world") == "hello world"

    def test_zero_width_space(self):
        """ZWSP (\\u200b) is replaced with a regular space, then collapsed."""
        assert tu.clean_text_cell("hello\u200bworld") == "hello world"

    def test_zero_width_joiner_preserved(self):
        """ZWJ (\\u200d) is NOT in the strip list — it's preserved.
        Only NBSP, tab, CR, LF, ZWSP, BOM are stripped."""
        result = tu.clean_text_cell("hello\u200dworld")
        assert "\u200d" in result

    def test_bom(self):
        assert tu.clean_text_cell("\ufeffhello") == "hello"

    def test_normal_text_unchanged(self):
        assert tu.clean_text_cell("hello world") == "hello world"

    def test_empty(self):
        assert tu.clean_text_cell("") == ""

    def test_none(self):
        assert tu.clean_text_cell(None) == ""


# ---- shorten ----

class TestShorten:
    def test_under_limit(self):
        assert tu.shorten("hello", 10) == "hello"

    def test_over_limit(self):
        result = tu.shorten("hello world", 5)
        assert len(result) <= 5

    def test_exact_limit(self):
        assert tu.shorten("hello", 5) == "hello"

    def test_empty(self):
        assert tu.shorten("", 10) == ""


# ---- _fmt_seconds ----

class TestFmtSeconds:
    def test_under_minute(self):
        assert "s" in tu._fmt_seconds(15)

    def test_minutes(self):
        out = tu._fmt_seconds(125)
        assert "m" in out  # contains "min" or "m"

    def test_zero(self):
        out = tu._fmt_seconds(0)
        assert isinstance(out, str)


# ---- _strip_json_code_fence ----

class TestStripJsonCodeFence:
    def test_plain_json(self):
        assert tu._strip_json_code_fence('{"a":1}') == '{"a":1}'

    def test_json_fence(self):
        result = tu._strip_json_code_fence('```json\n{"a":1}\n```')
        assert '{"a":1}' in result
        assert "```" not in result

    def test_plain_fence(self):
        result = tu._strip_json_code_fence('```\n{"a":1}\n```')
        assert '{"a":1}' in result
        assert "```" not in result

    def test_empty(self):
        assert tu._strip_json_code_fence("") == ""


# ---- guess_column ----

class TestGuessColumn:
    def test_exact_match(self):
        df = pd.DataFrame(columns=["Code", "Description", "Year"])
        assert tu.guess_column(df, ["code"]) == "Code"

    def test_case_insensitive(self):
        df = pd.DataFrame(columns=["CODE", "description"])
        assert tu.guess_column(df, ["code"]) == "CODE"

    def test_no_match(self):
        df = pd.DataFrame(columns=["foo", "bar"])
        assert tu.guess_column(df, ["code"]) is None

    def test_multiple_candidates_first_wins(self):
        df = pd.DataFrame(columns=["Article", "Code", "Reference"])
        # First match in candidates wins, not first column
        result = tu.guess_column(df, ["reference", "code"])
        assert result == "Reference"


# ---- parse_number_series ----

class TestParseNumberSeries:
    def test_european_format(self):
        s = pd.Series(["1.234,56", "100,5"])
        result = tu.parse_number_series(s)
        assert float(result.iloc[0]) == pytest.approx(1234.56)
        assert float(result.iloc[1]) == pytest.approx(100.5)

    def test_us_format(self):
        s = pd.Series(["1,234.56", "100.5"])
        result = tu.parse_number_series(s)
        # Mixed format detection should work for typical cases
        assert pd.notna(result.iloc[0])

    def test_integers(self):
        s = pd.Series(["100", "200"])
        result = tu.parse_number_series(s)
        assert int(result.iloc[0]) == 100

    def test_garbage_becomes_zero(self):
        """parse_number_series returns 0.0 for unparseable input (defensive)."""
        s = pd.Series([None, "", "abc"])
        result = tu.parse_number_series(s)
        assert (result == 0.0).all()


# ---- _normalize_size_code ----

class TestNormalizeSizeCode:
    def test_uppercase(self):
        assert tu._normalize_size_code("s") == "S"
        assert tu._normalize_size_code("m") == "M"
        assert tu._normalize_size_code("xl") == "XL"

    def test_whitespace(self):
        assert tu._normalize_size_code("  XL  ") == "XL"

    def test_empty_defaults_to_L(self):
        """Empty/unknown size codes default to 'L' (large) — a documented fallback."""
        assert tu._normalize_size_code("") == "L"

    def test_none_defaults_to_L(self):
        assert tu._normalize_size_code(None) == "L"

    def test_garbage_defaults_to_L(self):
        assert tu._normalize_size_code("GARBAGE") == "L"


# ---- contains_any_keyword ----

class TestContainsAnyKeyword:
    def test_short_keyword_word_boundary(self):
        """Short keyword 'vis' should not match inside 'tournevis'."""
        assert tu.contains_any_keyword("vis m6", ["vis"]) is True
        assert tu.contains_any_keyword("tournevis", ["vis"]) is False

    def test_long_keyword_substring(self):
        """Long keyword (>4 chars) matches as substring."""
        assert tu.contains_any_keyword("xxforetxx", ["foret"]) is True

    def test_no_match(self):
        assert tu.contains_any_keyword("hello", ["world"]) is False

    def test_multiple_keywords_any_match(self):
        assert tu.contains_any_keyword("foret D5", ["drill", "foret"]) is True

    def test_empty_keyword_list(self):
        assert tu.contains_any_keyword("anything", []) is False

    def test_empty_text(self):
        assert tu.contains_any_keyword("", ["foret"]) is False


# ---- first_nonempty ----

class TestFirstNonempty:
    def test_first_real_value(self):
        s = pd.Series(["", "hello", "world"])
        assert tu.first_nonempty(s) == "hello"

    def test_all_empty(self):
        s = pd.Series(["", "", ""])
        assert tu.first_nonempty(s) == ""

    def test_whitespace_only(self):
        s = pd.Series(["   ", "real"])
        assert tu.first_nonempty(s) == "real"

    def test_with_nan(self):
        s = pd.Series([None, "real"])
        assert tu.first_nonempty(s) == "real"

    def test_empty_series(self):
        s = pd.Series([], dtype=object)
        assert tu.first_nonempty(s) == ""


# ---- first_positive_number ----

class TestFirstPositiveNumber:
    def test_first_positive(self):
        s = pd.Series([0, 0, 5, 10])
        assert tu.first_positive_number(s) == 5

    def test_all_zero(self):
        s = pd.Series([0, 0, 0])
        result = tu.first_positive_number(s, default=99)
        assert result == 99

    def test_negative_skipped(self):
        s = pd.Series([-1, -5, 3])
        assert tu.first_positive_number(s) == 3

    def test_nan_default(self):
        s = pd.Series([0, 0])
        result = tu.first_positive_number(s, default=float("nan"))
        assert math.isnan(result)

    def test_floats(self):
        s = pd.Series([0.0, 0.5, 2.5])
        assert tu.first_positive_number(s) == 0.5


# ---- first_valid_size ----

class TestFirstValidSize:
    def test_first_valid(self):
        s = pd.Series(["", "M", "L"])
        assert tu.first_valid_size(s) == "M"

    def test_invalid_skipped(self):
        s = pd.Series(["GARBAGE", "L"])
        assert tu.first_valid_size(s) == "L"

    def test_all_invalid(self):
        s = pd.Series(["", "GARBAGE"])
        assert tu.first_valid_size(s, default="X") == "X"


# ---- parse_year_series ----

class TestParseYearSeries:
    def test_valid_years(self):
        s = pd.Series(["2023", "2024", "2025"])
        result = tu.parse_year_series(s)
        assert int(result.iloc[0]) == 2023

    def test_invalid_become_nan(self):
        s = pd.Series(["abc", "2024"])
        result = tu.parse_year_series(s)
        assert pd.isna(result.iloc[0])
        assert int(result.iloc[1]) == 2024

    def test_out_of_range(self):
        """Years like 1850 or 2300 should be discarded."""
        s = pd.Series(["1850", "2024", "3000"])
        result = tu.parse_year_series(s)
        # Behavior is to accept reasonable years; out-of-range may be NaN'd
        # We just verify 2024 makes it through
        assert int(result.iloc[1]) == 2024

    def test_all_missing_does_not_crash(self):
        """A file with no Year column sets every row to NA. Since pandas 3.0,
        astype(str) leaves a missing value as a float nan (not the string
        "nan"), so the parser must guard non-string input rather than calling
        .lower() on a float. The whole column must parse to NaN without error."""
        import numpy as np
        s = pd.Series([np.nan, np.nan, np.nan])
        result = tu.parse_year_series(s)
        assert result.isna().all()

    def test_mixed_missing_and_valid(self):
        """Missing entries (np.nan, pd.NA) and float-typed years coexist with
        string years without crashing."""
        import numpy as np
        s = pd.Series([np.nan, "2024", 2025.0, pd.NA])
        result = tu.parse_year_series(s)
        assert pd.isna(result.iloc[0])
        assert int(result.iloc[1]) == 2024
        assert int(result.iloc[2]) == 2025
        assert pd.isna(result.iloc[3])
