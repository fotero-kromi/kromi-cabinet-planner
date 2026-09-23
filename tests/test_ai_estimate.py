"""Tests for the pure AI cost/ETA estimation extracted from the page (v33.79)."""

import math

from engine.ai_estimate import (
    estimate_ai_run,
    PRICE_INPUT_PER_1M,
    PRICE_OUTPUT_PER_1M,
    EST_INPUT_TOKENS_PER_ITEM,
    EST_OUTPUT_TOKENS_PER_ITEM,
    EST_OUTPUT_TOKENS_PER_ITEM_TRIMMED,
    EST_INPUT_TOKENS_OVERHEAD_PER_BATCH,
    EST_OUTPUT_TOKENS_OVERHEAD_PER_BATCH,
    EST_SECONDS_PER_BATCH,
)


def test_batches_round_up():
    assert estimate_ai_run(100, 20, 1, False)["batches"] == 5
    assert estimate_ai_run(101, 20, 1, False)["batches"] == 6   # ceil, not floor
    assert estimate_ai_run(19, 20, 1, False)["batches"] == 1
    assert estimate_ai_run(20, 20, 1, False)["batches"] == 1


def test_wave_model_scales_with_workers():
    # 5 batches across N workers -> ceil(5 / N) waves
    assert estimate_ai_run(100, 20, 1, False)["waves"] == 5
    assert estimate_ai_run(100, 20, 2, False)["waves"] == 3   # ceil(5/2)
    assert estimate_ai_run(100, 20, 5, False)["waves"] == 1
    assert estimate_ai_run(100, 20, 10, False)["waves"] == 1  # more workers than batches


def test_seconds_follow_waves_not_batches():
    r = estimate_ai_run(100, 20, 5, False)
    # 5 batches but 1 wave with 5 workers -> one batch-time, not five
    assert r["seconds"] == 1 * EST_SECONDS_PER_BATCH
    assert estimate_ai_run(100, 20, 1, False)["seconds"] == 5 * EST_SECONDS_PER_BATCH


def test_token_accounting():
    r = estimate_ai_run(100, 20, 1, False)
    batches = 5
    assert r["in_tokens"] == batches * EST_INPUT_TOKENS_OVERHEAD_PER_BATCH + 100 * EST_INPUT_TOKENS_PER_ITEM
    assert r["out_tokens"] == batches * EST_OUTPUT_TOKENS_OVERHEAD_PER_BATCH + 100 * EST_OUTPUT_TOKENS_PER_ITEM


def test_trim_lowers_output_tokens_and_cost():
    full = estimate_ai_run(100, 20, 1, False)
    trim = estimate_ai_run(100, 20, 1, True)
    assert trim["out_tokens"] < full["out_tokens"]
    assert trim["cost"] < full["cost"]
    # input side and timing are unaffected by trimming
    assert trim["in_tokens"] == full["in_tokens"]
    assert trim["seconds"] == full["seconds"]
    # the per-item delta is exactly the trimmed-vs-full output figure, times items
    delta = (EST_OUTPUT_TOKENS_PER_ITEM - EST_OUTPUT_TOKENS_PER_ITEM_TRIMMED) * 100
    assert full["out_tokens"] - trim["out_tokens"] == delta


def test_cost_formula():
    r = estimate_ai_run(100, 20, 1, False)
    expected = (r["in_tokens"] / 1_000_000) * PRICE_INPUT_PER_1M + \
        (r["out_tokens"] / 1_000_000) * PRICE_OUTPUT_PER_1M
    assert r["cost"] == expected


def test_matches_original_inline_formula():
    # Behaviour-preservation pin: recompute exactly as the page did inline and
    # require equality, so the extraction cannot silently drift.
    for n, bs, workers, trim in [(57, 20, 3, False), (200, 25, 4, True), (1, 20, 1, False)]:
        batches = math.ceil(n / int(bs))
        waves = math.ceil(batches / max(1, int(workers)))
        est_seconds = waves * EST_SECONDS_PER_BATCH
        est_in = batches * EST_INPUT_TOKENS_OVERHEAD_PER_BATCH + n * EST_INPUT_TOKENS_PER_ITEM
        per_item = EST_OUTPUT_TOKENS_PER_ITEM_TRIMMED if trim else EST_OUTPUT_TOKENS_PER_ITEM
        est_out = batches * EST_OUTPUT_TOKENS_OVERHEAD_PER_BATCH + n * per_item
        est_cost = (est_in / 1_000_000) * PRICE_INPUT_PER_1M + (est_out / 1_000_000) * PRICE_OUTPUT_PER_1M
        r = estimate_ai_run(n, bs, workers, trim)
        assert r["batches"] == batches
        assert r["waves"] == waves
        assert r["seconds"] == est_seconds
        assert r["in_tokens"] == est_in
        assert r["out_tokens"] == est_out
        assert r["cost"] == est_cost


def test_zero_items_is_all_zero():
    r = estimate_ai_run(0, 20, 5, False)
    assert r["batches"] == 0 and r["waves"] == 0 and r["seconds"] == 0
    assert r["in_tokens"] == 0 and r["out_tokens"] == 0 and r["cost"] == 0


def test_degenerate_inputs_do_not_crash():
    # The UI never produces these, but the pure function must stay total.
    assert estimate_ai_run(50, 0, 0, False)["batches"] >= 1
    assert estimate_ai_run(-5, 20, 1, False)["batches"] == 0
