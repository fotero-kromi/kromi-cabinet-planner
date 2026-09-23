"""Customer article numbers stay exact text (v34.50, audit C11).

A numeric code column that contains an empty cell is read by pandas as
floats, so 12345 became "12345.0" in every export, including the Customer
article No of the Article setup sheet. Codes are now written back as the
integer text when the float is integral.
"""
import math

from engine.text_utils import clean_code_cell


def test_integral_floats_lose_the_decimal_tail():
    assert clean_code_cell(12345.0) == "12345"
    assert clean_code_cell(50105904.0) == "50105904"


def test_other_values_are_cleaned_as_text():
    assert clean_code_cell(12345) == "12345"
    assert clean_code_cell("00123") == "00123"
    assert clean_code_cell(" 50105904-00243 ") == "50105904-00243"
    assert clean_code_cell(123.5) == "123.5"
    assert clean_code_cell(float("nan")) == ""
    assert clean_code_cell(None) == ""
    assert clean_code_cell(math.inf) == "inf"
