"""JSON schema for the AI classification batch call.

This is pure data, kept out of the page so the schema and its reason-trim
variant can be unit-tested. The schema is ``strict``, which means every property
must also be listed in ``required`` and ``additionalProperties`` is False;
trimming the free-text ``reason`` therefore drops it from BOTH ``properties`` and
``required``. Removing the reason is the AI pipeline's main speed and cost lever,
because the reason is the bulk of the per-item output tokens.

The enums here must stay in lockstep with the heuristic classifier's categories;
they are the contract the model is held to.
"""

from __future__ import annotations

from typing import Any, Dict, List

PRODUCT_CATEGORIES: List[str] = [
    "inserts", "drills", "mills", "reamers", "holders",
    "screws", "accessories", "boring_bars", "ppe", "other",
]

TOOL_CLASSES: List[str] = [
    "turning_insert", "milling_insert", "drilling_insert",
    "solid_carbide_drill", "indexable_drill", "hss_drill", "tap",
    "solid_end_mill", "shell_mill", "face_mill", "thread_mill",
    "reamer", "boring_bar",
    "turning_holder", "milling_holder", "collet",
    "screw", "wrench", "abrasive_disc", "abrasive_belt", "grinding_wheel",
    "accessory", "ppe", "other",
]

SIZE_CATEGORIES: List[str] = ["S", "M", "L", "XL", "XXL", "XXLS", "XLS"]

# Item fields that are always present, in their required order. ``reason`` is
# appended only when reasons are not trimmed.
_BASE_REQUIRED: List[str] = [
    "row_id", "product_category", "tool_class", "size_category",
    "pack_units", "confidence",
]


def build_classification_schema(trim_reason: bool = False) -> Dict[str, Any]:
    """Return the strict JSON schema for one classification batch.

    When ``trim_reason`` is True the per-item ``reason`` field is omitted from
    both the properties and the required list, so the model is not asked to
    explain each classification and the response is much smaller. The category,
    class, size, pack, and confidence fields are unchanged either way, so the
    classification itself is unaffected.
    """
    item_properties: Dict[str, Any] = {
        "row_id": {"type": "string"},
        "product_category": {"type": "string", "enum": list(PRODUCT_CATEGORIES)},
        "tool_class": {"type": "string", "enum": list(TOOL_CLASSES)},
        "size_category": {"type": "string", "enum": list(SIZE_CATEGORIES)},
        "pack_units": {"type": ["integer", "null"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    }
    required = list(_BASE_REQUIRED)
    if not trim_reason:
        item_properties["reason"] = {"type": "string"}
        required = required + ["reason"]

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": item_properties,
                    "required": required,
                },
            }
        },
        "required": ["results"],
    }
