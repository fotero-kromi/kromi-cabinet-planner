"""Canonical category names must survive normalization (v34.18).

normalize_product_category is a synonym matcher for freeform text, but a
mapped category column carrying the canonical English names fed those names
through the same matcher, and anything the keyword lists did not cover folded
to 'other'. A provided 'mills' then lost its Provided status, was re-derived
by the description classifier, and, where the description was thin, was sent
to the AI stage for an answer the file already gave. Canonical names now map
to themselves before any keyword logic runs; freeform synonyms behave as
before.
"""

import pytest

from engine.classification import normalize_product_category
from engine.constants import PC_VALID


@pytest.mark.parametrize("name", sorted(PC_VALID))
def test_canonical_names_are_identity(name):
    assert normalize_product_category(name) == name
    assert normalize_product_category(name.upper()) == name
    assert normalize_product_category(f"  {name.title()}  ") == name


def test_freeform_synonyms_still_match():
    assert normalize_product_category("Wendeplatte CNMG") == "inserts"
    assert normalize_product_category("Gewindebohrer M8") == "taps"
