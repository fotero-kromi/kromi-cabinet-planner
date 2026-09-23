"""OpenAI transport and the cached batch wrapper (v34.48, moved from the page).

The page consumes ``ai_classify_batch_cached(cache_key)`` exactly as before and
gets the same 5-tuple ``(result_map, input_tokens, output_tokens,
error_or_None, missing_rows)``. What changed (audit C7): only a *successful*
batch is cached. The engine raises ``AIBatchFailed`` on a final failure, the
cached inner function lets it propagate (Streamlit never caches an exception),
and this wrapper turns it back into the failure tuple. A batch that failed on
a timeout or rate limit is therefore asked again on the next run instead of
being replayed from the cache until the app restarts.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional, Tuple

import streamlit as st
from openai import OpenAI

from engine.ai_batch import AIBatchFailed, classify_batch
from engine.ai_classifier import extract_chat_usage

AI_RETRY_ATTEMPTS = 3
AI_CALL_TIMEOUT_SECONDS = float(os.getenv("AI_CALL_TIMEOUT_SECONDS", "60"))
AI_MAX_BACKOFF_SECONDS = float(os.getenv("AI_MAX_BACKOFF_SECONDS", "10"))
BATCH_SCHEMA_NAME = "cabinet_planner_batch_v25"

# Indirection so tests can run the retry loop without waiting.
_sleep = time.sleep


@st.cache_resource
def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not defined. Put it in your environment or .env file.")
    return OpenAI(api_key=api_key)


def call_openai_structured(
    client: Any,
    model: str,
    prompt: str,
    schema_name: str,
    schema: Dict[str, Any],
    timeout_s: float,
) -> Tuple[str, int, int]:
    """Call OpenAI Chat Completions with strict JSON-schema structured output."""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You return only valid JSON matching the provided schema. No prose, no markdown fences."},
            {"role": "user", "content": prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        },
        timeout=timeout_s,
    )

    if not getattr(resp, "choices", None):
        raise ValueError("OpenAI response had no choices")
    msg = resp.choices[0].message
    content = getattr(msg, "content", None) or ""
    if not content.strip():
        # Strict structured output refusal (safety) puts text in .refusal, not .content
        refusal = getattr(msg, "refusal", None)
        if refusal:
            raise ValueError(f"Model refused structured output: {refusal}")
        raise ValueError("OpenAI response content is empty")

    in_tok, out_tok = extract_chat_usage(resp)
    return content, in_tok, out_tok


@st.cache_data(show_spinner=False)
def _ai_classify_batch_success(cache_key: Tuple) -> Tuple[Dict[str, Dict[str, Any]], int, int, int]:
    """Cached on success only: a final failure raises and is never memoised."""
    model, trim_reason, cooked_items = cache_key
    client = get_openai_client()

    def _call(prompt: str, schema: Dict[str, Any]) -> Tuple[str, int, int]:
        return call_openai_structured(
            client, model, prompt, BATCH_SCHEMA_NAME, schema, AI_CALL_TIMEOUT_SECONDS)

    return classify_batch(
        cooked_items, trim_reason=trim_reason, call=_call,
        attempts=AI_RETRY_ATTEMPTS, max_backoff=AI_MAX_BACKOFF_SECONDS,
        sleep=lambda s: _sleep(s),
    )


def ai_classify_batch_cached(cache_key: Tuple) -> Tuple[Dict[str, Dict[str, Any]], int, int, Optional[str], int]:
    """Return: (result_map, input_tokens, output_tokens, error_message_or_None, missing_row_count)."""
    try:
        out, in_tok, out_tok, missing = _ai_classify_batch_success(cache_key)
    except AIBatchFailed as exc:
        return {}, 0, 0, str(exc), exc.n_missing
    return out, in_tok, out_tok, None, missing
