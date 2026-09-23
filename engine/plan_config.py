"""PlanConfig: the immutable sizing-factor configuration for one planning run.

The page used to thread the two runtime sizing factors (``helix_overfill_factor``
and ``carousel_reserve_factor``) as mutable module-level globals, read both by the
factor-injecting shims and passed as arguments to the engine segments. A mismatch
between one of those reads and a segment argument was the failure mode behind the
Helix single-spiral overfill bug.

This bundles the two factors into a single frozen object, built once per run from
the UI values, so every reader sees one consistent immutable source that cannot
drift after construction. It is also the input object the cached ``run_plan`` entry
point will take.

The defaults reproduce the engine's base constants, so ``PlanConfig()`` with no
arguments is the out-of-the-box behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import (
    HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR,
    CAROUSEL_RESERVE_FACTOR,
)


@dataclass(frozen=True)
class PlanConfig:
    """Immutable per-run sizing factors.

    Attributes:
        helix_overfill_factor: a single Helix spiral holds demand up to
            ``spiral_capacity * helix_overfill_factor`` before a second spiral is
            opened. Default ``HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR`` (1.10).
        carousel_reserve_factor: the fraction of a Carousel compartment's nominal
            capacity used when sizing, leaving headroom. Default
            ``CAROUSEL_RESERVE_FACTOR`` (0.85).
    """

    helix_overfill_factor: float = HELIX_SINGLE_SPIRAL_OVERFILL_FACTOR
    carousel_reserve_factor: float = CAROUSEL_RESERVE_FACTOR
    # Fraction of a Carousel's physical slots the plan may fill before opening
    # the next cabinet; 1.0 reproduces the original full-fill behavior (v34.34).
    carousel_fill_ceiling: float = 1.0
