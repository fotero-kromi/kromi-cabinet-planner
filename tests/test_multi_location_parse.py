"""engine/multi_location.py (v34.63): reading the machines a location cell names.

A customer's location (Program) cell may name several vending machines, for
example ``AB-100 + AB 101``. The parser splits it into canonical machine
labels; the labels are invented.
"""
import pytest

from engine.multi_location import canonical_location, split_locations


@pytest.mark.parametrize("text,expected", [
    # the spelling patterns of a real list (invented labels)
    ("AB-100 + AB 101", ("AB-100", "AB-101")),
    ("AB-100 +101", ("AB-100", "AB-101")),
    ("AB-101 + 102", ("AB-101", "AB-102")),
    ("AB-100 +101 + 102", ("AB-100", "AB-101", "AB-102")),
    # a single value is unchanged
    ("Line A", ("Line A",)),
    ("AB-100", ("AB-100",)),
    ("KTC-B", ("KTC-B",)),
    # duplicates collapse, first appearance wins the order
    ("AB-100 + AB-100", ("AB-100",)),
    ("AB-101 + AB-100 + ab 101", ("AB-101", "AB-100")),
    # leading, trailing and doubled separators
    ("+ AB-100 +", ("AB-100",)),
    (", AB-100 ;; AB-101 ,", ("AB-100", "AB-101")),
    ("+", ()),
    # blank
    ("", ()),
    ("   ", ()),
    (None, ()),
    # digits without an earlier prefix stay as they are
    ("100 + 101", ("100", "101")),
    # mixed case and the other separators
    ("ab-100 & Ab 101", ("AB-100", "AB-101")),
    ("ab_100; AB  101", ("AB-100", "AB-101")),
    ("AB100, 101", ("AB-100", "AB-101")),
    # names are kept; only whitespace collapses
    ("Line A + Line B", ("Line A", "Line B")),
    ("  Line   A  ", ("Line A",)),
    # '/' and '-' are part of a name, never a separator
    ("Hall 3/North", ("Hall 3/North",)),
    ("Cell-West + Cell-East", ("Cell-West", "Cell-East")),
    # the nearest earlier prefix is the one a bare number takes
    ("AB-100 + CD-7 + 8", ("AB-100", "CD-7", "CD-8")),
    ("AB-100 + Line A + 5", ("AB-100", "Line A", "AB-5")),
])
def test_split_locations(text, expected):
    assert split_locations(text) == expected


def test_a_number_cell_is_read_as_text():
    assert split_locations(101) == ("101",)


@pytest.mark.parametrize("text,expected", [
    ("AB 101", "AB-101"),
    ("ab-101", "AB-101"),
    ("AB_101", "AB-101"),
    ("AB101", "AB-101"),
    ("AB - 101", "AB-101"),
    ("AB-101", "AB-101"),
    ("Line A", "Line A"),
    ("  Line   A ", "Line A"),
    ("101", "101"),
    ("KTC-B", "KTC-B"),
    ("", ""),
    (None, ""),
])
def test_canonical_location(text, expected):
    assert canonical_location(text) == expected


def test_every_split_part_is_canonical():
    for text in ("AB-100 + AB 101", "ab 100 & 7", "Line A + x_9"):
        for part in split_locations(text):
            assert canonical_location(part) == part
