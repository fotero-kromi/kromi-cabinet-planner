"""Pure cost and ETA estimation for the AI classification run.

Extracted from the page so the wave model and token accounting are unit-tested
rather than inferred from a live run. The page shows this estimate before a run
starts; the live ETA still recalibrates from measured token usage once the first
batch returns, so these figures are a pre-run guide, not a contract.

All rates are env-overridable and were calibrated against observed gpt-5-mini runs
with the structured classification schema (whose per-item free-text "reason" field
is the main output-token and latency driver).
"""

from __future__ import annotations

import math
import os
from typing import Dict

# Pricing assumptions (USD per 1M tokens).
PRICE_INPUT_PER_1M = float(os.getenv("PRICE_INPUT_PER_1M", "0.25"))
PRICE_OUTPUT_PER_1M = float(os.getenv("PRICE_OUTPUT_PER_1M", "2.00"))

# Per-item and per-batch token assumptions. Trimming the reason field drops the
# per-item output sharply, so it has its own (lower) figure.
EST_INPUT_TOKENS_PER_ITEM = int(os.getenv("EST_INPUT_TOKENS_PER_ITEM", "160"))
EST_OUTPUT_TOKENS_PER_ITEM = int(os.getenv("EST_OUTPUT_TOKENS_PER_ITEM", "160"))
EST_OUTPUT_TOKENS_PER_ITEM_TRIMMED = int(os.getenv("EST_OUTPUT_TOKENS_PER_ITEM_TRIMMED", "45"))
EST_INPUT_TOKENS_OVERHEAD_PER_BATCH = int(os.getenv("EST_INPUT_TOKENS_OVERHEAD_PER_BATCH", "450"))
EST_OUTPUT_TOKENS_OVERHEAD_PER_BATCH = int(os.getenv("EST_OUTPUT_TOKENS_OVERHEAD_PER_BATCH", "60"))

# A structured batch of ~20 items typically takes ~45-75 s end to end on the
# reasoning model; 65 s is a slightly conservative middle.
EST_SECONDS_PER_BATCH = float(os.getenv("EST_SECONDS_PER_BATCH", "65.0"))


def estimate_ai_run(
    n_items: int, batch_size: int, workers: int, trim_reason: bool
) -> Dict[str, float]:
    """Pre-run cost and time estimate for classifying ``n_items`` articles.

    Batches run up to ``workers`` at a time, so wall-clock time is driven by the
    number of sequential waves, ceil(batches / workers), not the raw batch count.
    Returns batches, waves, seconds, input/output token totals, and USD cost.

    Guards keep the function total for degenerate inputs the UI does not produce
    (a zero or negative batch size or worker count). For every valid input it
    reproduces the figures the page previously computed inline.
    """
    n_items = max(0, int(n_items))
    batch_size = max(1, int(batch_size))
    workers = max(1, int(workers))

    batches = math.ceil(n_items / batch_size)
    waves = math.ceil(batches / workers)
    seconds = waves * EST_SECONDS_PER_BATCH

    in_tokens = (
        batches * EST_INPUT_TOKENS_OVERHEAD_PER_BATCH
        + n_items * EST_INPUT_TOKENS_PER_ITEM
    )
    out_per_item = (
        EST_OUTPUT_TOKENS_PER_ITEM_TRIMMED if trim_reason else EST_OUTPUT_TOKENS_PER_ITEM
    )
    out_tokens = (
        batches * EST_OUTPUT_TOKENS_OVERHEAD_PER_BATCH + n_items * out_per_item
    )

    cost = (
        (in_tokens / 1_000_000) * PRICE_INPUT_PER_1M
        + (out_tokens / 1_000_000) * PRICE_OUTPUT_PER_1M
    )

    return {
        "batches": batches,
        "waves": waves,
        "seconds": seconds,
        "in_tokens": in_tokens,
        "out_tokens": out_tokens,
        "cost": cost,
    }
