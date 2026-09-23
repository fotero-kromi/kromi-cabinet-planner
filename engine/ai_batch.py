"""One AI classification batch: payload, retries, response validation (v34.48).

Moved out of the page so it is testable with a fake transport and so a final
failure is *raised* rather than returned: the page caches successful batches
with ``st.cache_data``, and Streamlit never caches an exception, so a batch
that failed on a timeout or rate limit is asked again on the next run instead
of being replayed from the cache for the life of the process (audit C7).

The payload, prompt, schema and validation rules are unchanged from the page
version: the prompt is pinned byte-for-byte by tests/test_ai_prompt.py, the
schema by engine/ai_schema.py, and every model answer is still normalised
against the allowed category, tool-class, size and pack-unit values.
"""
from __future__ import annotations

import json
import random
import time
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from .ai_classifier import build_classification_prompt
from .ai_schema import build_classification_schema
from .classification_tables import PC_VALID, TOOL_CLASS_VALID
from .text_utils import _normalize_size_code, _strip_json_code_fence

#: ``call(prompt, schema) -> (content, input_tokens, output_tokens)``
Transport = Callable[[str, Dict[str, Any]], Tuple[str, int, int]]

REASON_MAX_CHARS = 200


class AIBatchFailed(Exception):
    """Every attempt for one batch failed; carries the rows left unclassified."""

    def __init__(self, message: str, n_missing: int):
        super().__init__(message)
        self.n_missing = int(n_missing)


def build_batch_payload(cooked_items: Iterable[tuple]) -> list[Dict[str, Any]]:
    """The per-item payload the model classifies (same fields and order as ever)."""
    payload = []
    for t in cooked_items:
        (row_id, code, prod_cat, desc1, desc2, supplier_code,
         current_pack_units, current_size_category, listing) = t
        payload.append({
            "row_id": row_id,
            "listing": listing,
            "code": code,
            "product_category_current": prod_cat,
            "description": desc1,
            "description_2": desc2,
            "supplier_code": supplier_code,
            "pack_units_current": current_pack_units,
            "size_category_current": current_size_category,
        })
    return payload


def parse_batch_results(content: str) -> Dict[str, Dict[str, Any]]:
    """Validate one model response into ``{row_id: fields}``.

    Raises ``ValueError`` (or ``json.JSONDecodeError``) when the response is
    not the expected JSON object; soft fields are normalised, never trusted.
    """
    data = json.loads(_strip_json_code_fence(content))
    if not isinstance(data, dict) or "results" not in data:
        raise ValueError("AI response missing 'results' field")

    out: Dict[str, Dict[str, Any]] = {}
    for r in data.get("results", []):
        if not isinstance(r, dict):
            continue
        rid = str(r.get("row_id", ""))
        if rid == "":
            continue

        pc = str(r.get("product_category", "other"))
        if pc not in PC_VALID:
            pc = "other"

        tc = str(r.get("tool_class", "")).strip().lower()
        if tc and tc not in TOOL_CLASS_VALID:
            tc = "other"

        sc = _normalize_size_code(r.get("size_category"))

        pu = r.get("pack_units", None)
        if pu is not None:
            try:
                pu = int(pu)
                if pu not in (1, 10):
                    pu = None
            except Exception:
                pu = None

        conf = str(r.get("confidence", "")).strip().lower()
        if conf not in ("high", "medium", "low"):
            conf = "medium"
        reason = str(r.get("reason", "")).strip()
        if len(reason) > REASON_MAX_CHARS:
            reason = reason[:REASON_MAX_CHARS - 3] + "..."

        out[rid] = {
            "product_category": pc,
            "tool_class": tc,
            "size_category": sc,
            "pack_units": pu,
            "confidence": conf,
            "reason": reason,
        }
    return out


def classify_batch(
    cooked_items: Tuple[tuple, ...],
    *,
    trim_reason: bool,
    call: Transport,
    attempts: int,
    max_backoff: float,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
) -> Tuple[Dict[str, Dict[str, Any]], int, int, int]:
    """Classify one batch; return ``(result_map, in_tokens, out_tokens, missing)``.

    Retries up to ``attempts`` times with capped exponential backoff and
    jitter. A response with zero usable rows for a non-empty batch counts as a
    failed attempt. After the last failed attempt raises ``AIBatchFailed``
    carrying the number of rows left unclassified.
    """
    payload = build_batch_payload(cooked_items)
    expected = {str(it["row_id"]) for it in payload}
    prompt = build_classification_prompt(payload)
    schema = build_classification_schema(trim_reason)

    last_error: Optional[str] = None
    for attempt in range(int(attempts)):
        try:
            content, in_tok, out_tok = call(prompt, schema)
            out = parse_batch_results(content)
            if expected and not (set(out) & expected):
                raise ValueError("AI response contained none of the batch rows")
            missing = len(expected - set(out))
            return out, int(in_tok or 0), int(out_tok or 0), missing
        except Exception as e:  # any transport or parse error is retryable
            last_error = f"{type(e).__name__}: {str(e)[:300]}"
            if attempt < int(attempts) - 1:
                sleep(min(2 ** attempt + jitter(0.0, 0.5), max_backoff))

    raise AIBatchFailed(
        f"failed after {int(attempts)} attempts: {last_error}", len(expected))
