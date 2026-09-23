"""The run fingerprint: the value that gates cached results.

The page keeps a stored fingerprint in session state. On every rerun it recomputes
the current fingerprint from the active inputs and, if it differs from the stored
one, marks ``has_results`` invalid so the user must run the pipeline again. The
fingerprint is therefore the single definition of "what change requires a re-run".

This module holds that definition in one place so it can be unit-tested. Two rules
govern it:

* Every input that changes the produced plan MUST be a field here. A missing input
  means a control can change while a stale plan is still shown (the class of bug
  fixed in v33.71, when operational mode, the carousel cap, and the special->KTC
  toggle were added).
* The fingerprint is only ever compared for equality, so field order and the exact
  per-field coercions are part of the contract: the same inputs must always yield
  the same tuple. ``compute_run_fingerprint`` is value-faithful to the inline tuple
  it replaced (verified element-for-element against a captured golden).

Pure: no Streamlit, no I/O. The page resolves its widgets and session values into a
``FingerprintInputs`` and calls ``compute_run_fingerprint``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class FingerprintInputs:
    """Every input the run fingerprint depends on, named.

    ``columns`` is the column-mapping block in its canonical order
    (code, desc1, desc2, consumption, product, supplier, size, pack, year,
    program, site, dims, std/special, regrind, system-type); it is flattened into
    the fingerprint so the value matches the historical positional tuple.
    """

    # input source
    file_name: Optional[str]
    file_size: Optional[int]
    # SHA-256 of the uploaded bytes (I7): the content-true identity of the
    # source. Name and size alone let a content swap behind an unchanged
    # (name, size) pair keep showing a stale plan; the digest closes that hole.
    content_sha: Optional[str]
    # sheets + calculation mode
    sheet_tools: Any
    sheet_ppe: Any
    calc_mode: Any
    # column mappings (canonical order, see class docstring)
    columns: Tuple[Any, ...]
    # thresholds
    usage_threshold: float
    helix_threshold: float
    consumption_period_months: float
    optional_thresholds_active: bool
    per_class_thresholds: Mapping[str, float]
    # capacity / coverage
    insert_default_pack_units: int
    minimum_carousel_allocation: int
    coverage_days: int
    coverage_days_special: int
    helix_single_spiral_overfill_factor: float
    carousel_reserve_factor: float
    carousel_fill_ceiling: float
    # rebalancer / buffers
    enable_rebalancer: bool
    underuse_threshold_pct: float
    capacity_buffer_pct: float
    # supply points
    n_supply_points: int
    sp_mode: Any
    # feature toggles
    enable_pack_hint_extraction: bool
    enable_bulk_routing: bool
    force_screws_accessories_kanban: bool
    use_description_2: bool
    year_mode: Any
    dedup_mode: Any
    # AI
    use_ai: bool
    max_ai_items: int
    batch_size: int
    trim_ai_reason: bool
    ai_concurrency: int
    # program -> supply-point mapping
    program_to_sp_map: Optional[Mapping[Any, Any]]
    program_mapping_active: bool
    # operational mode + carousel cap + special->KTC toggle
    op_mode: Any
    max_carousels_cap: int
    special_ktc_enabled: bool
    # scope + overrides
    effective_customer: Any
    effective_site: Any
    apply_overrides: bool
    # Restocking (v34.24): the rule categories; the mapped column name rides
    # inside ``columns`` like every other mapping choice.
    restock_categories: Tuple[str, ...]
    # Fixed configuration (v34.52): (machines per supply point, headroom %,
    # move-overflow toggle). Folded into the mode-specific position, so it
    # counts only in fixed mode and every other mode keeps its fingerprint.
    fixed_config: Optional[Tuple[Any, ...]] = None


def compute_run_fingerprint(i: FingerprintInputs) -> tuple:
    """Build the fingerprint tuple that gates cached results.

    The carousel cap is folded in only in Capped mode (it has no effect otherwise,
    so including it always would force needless re-runs), the fixed
    configuration shares that position in Fixed mode, and the program map is
    folded in only when program mapping is active. Both ``per_class_thresholds`` and
    the program map are sorted so equivalent dictionaries compare equal regardless
    of insertion order.
    """
    return (
        i.file_name, i.file_size, i.content_sha,
        i.sheet_tools, i.sheet_ppe, i.calc_mode,
        *i.columns,
        float(i.usage_threshold), float(i.helix_threshold), float(i.consumption_period_months),
        bool(i.optional_thresholds_active),
        tuple(sorted((k, float(v)) for k, v in i.per_class_thresholds.items())),
        int(i.insert_default_pack_units),
        int(i.minimum_carousel_allocation), int(i.coverage_days), int(i.coverage_days_special),
        float(i.helix_single_spiral_overfill_factor), float(i.carousel_reserve_factor),
        float(i.carousel_fill_ceiling),
        bool(i.enable_rebalancer), float(i.underuse_threshold_pct),
        float(i.capacity_buffer_pct), int(i.n_supply_points), i.sp_mode,
        bool(i.enable_pack_hint_extraction), bool(i.enable_bulk_routing),
        bool(i.force_screws_accessories_kanban), bool(i.use_description_2),
        i.year_mode, i.dedup_mode, bool(i.use_ai), int(i.max_ai_items), int(i.batch_size),
        bool(i.trim_ai_reason),
        int(i.ai_concurrency),
        # The page always supplies a mapping when program mapping is active;
        # the extra None check narrows the optional for the type checker
        # without changing the emitted value for any valid input.
        (tuple(sorted(i.program_to_sp_map.items()))
         if (i.program_mapping_active and i.program_to_sp_map is not None) else None),
        i.op_mode,
        tuple(i.restock_categories or ()),
        (int(i.max_carousels_cap) if i.op_mode == "Capped"
         else (i.fixed_config if i.op_mode == "Fixed" else None)),
        bool(i.special_ktc_enabled),
        i.effective_customer, i.effective_site, bool(i.apply_overrides),
    )
