"""Tests for the AI classification schema and its reason-trim variant (v33.72)."""

from engine.ai_schema import (
    build_classification_schema,
    PRODUCT_CATEGORIES,
    TOOL_CLASSES,
    SIZE_CATEGORIES,
)


def _item(schema):
    return schema["properties"]["results"]["items"]


def test_full_schema_includes_reason():
    s = build_classification_schema(trim_reason=False)
    item = _item(s)
    assert "reason" in item["properties"]
    assert "reason" in item["required"]


def test_trimmed_schema_omits_reason_from_properties_and_required():
    s = build_classification_schema(trim_reason=True)
    item = _item(s)
    # strict mode requires every property to be in `required`, so reason must be
    # gone from BOTH, not just one.
    assert "reason" not in item["properties"]
    assert "reason" not in item["required"]


def test_classification_fields_unchanged_by_trim():
    full = _item(build_classification_schema(False))
    trim = _item(build_classification_schema(True))
    for field in ("row_id", "product_category", "tool_class", "size_category",
                  "pack_units", "confidence"):
        assert field in full["properties"]
        assert field in trim["properties"]
        assert field in full["required"]
        assert field in trim["required"]


def test_schema_is_strict_in_both_modes():
    for trim in (False, True):
        s = build_classification_schema(trim)
        item = _item(s)
        assert s["additionalProperties"] is False
        assert item["additionalProperties"] is False
        assert s["required"] == ["results"]
        # every declared property is required (strict-mode invariant)
        assert set(item["properties"].keys()) == set(item["required"])


def test_enums_match_the_classifier_contract():
    item = _item(build_classification_schema(False))
    assert item["properties"]["product_category"]["enum"] == PRODUCT_CATEGORIES
    assert item["properties"]["tool_class"]["enum"] == TOOL_CLASSES
    assert item["properties"]["size_category"]["enum"] == SIZE_CATEGORIES
    # the old 1Standard/8Sonder-style codes are not in the size enum
    assert "XXLS" in SIZE_CATEGORIES and "tap" in TOOL_CLASSES
