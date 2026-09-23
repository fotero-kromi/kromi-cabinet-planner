"""kromi_app.engine.fitting — dimensional fit checking.

Given parsed package dimensions (see engine.dimensions) and the physical
compartment envelopes (see engine.constants), decide which cabinet types can
physically hold a package and recommend the smallest one that fits.

Tools are always dispensed in their packaging, so the package is the object
that must fit the compartment. Packages may be loaded in any orientation, so
fit tests are orientation-free: a package fits a rectangular compartment when
its dimensions, sorted largest-first, are each <= the compartment's dimensions
sorted the same way.

Pure module: no Streamlit, no global state, no I/O. Every result carries an
evidence/confidence tag mirroring the classifier and extractor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from .constants import (
    CAROUSEL_SLOTS,
    HELIX_COIL_CLEAR_DIAMETER_MM,
    HELIX_COIL_USABLE_LENGTH_MM,
    HELIX_MAX_PITCH_MM,
    LOCKER_BOXES,
)
from .dimensions import PackageDims, extract_package_dims

# Cabinet-type labels used across the engine.
HELIX = "Helix"
CAROUSEL = "Carousel"
LOCKER_A = "Locker A"
LOCKER_B = "Locker B"
LOCKER_C = "Locker C"

# Recommendation order — smallest / highest-throughput first. A package is
# routed to the earliest cabinet in this list that can hold it. Helix is the
# most space-efficient for small high-rotation items; Lockers are the
# fallback for large items.
RECOMMENDATION_ORDER = [HELIX, CAROUSEL, LOCKER_C, LOCKER_A, LOCKER_B]


@dataclass
class FitResult:
    """Outcome of checking a package against all cabinet types."""

    fits: dict[str, bool] = field(default_factory=dict)  # cabinet_type -> fits?
    recommended: str | None = None  # smallest fitting cabinet
    evidence: str = ""  # how it was decided
    package_sorted_mm: list[float] = field(default_factory=list)

    @property
    def fits_anywhere(self) -> bool:
        return any(self.fits.values())


def _normalize_package(pkg: PackageDims) -> list[float] | None:
    """Return a 3-element [L, W, H] (sorted descending) for fit testing.

    Packages may arrive with 1, 2, or 3 measured dimensions:
      - 3 dims: use as-is.
      - 2 dims: treat as a flat/cylinder package; the missing third dimension
        is taken equal to the SMALLER of the two (a Ø25 x 180 cylinder becomes
        25 x 25 x 180 — a square cross-section bounding the round one).
      - 1 dim: a lone diameter/size; assume a cube of that size (square
        cross-section, length equal to the dimension).
    Returns None when there are no usable dimensions.
    """
    vals = list(pkg.values_mm)
    if not vals:
        return None
    if len(vals) >= 3:
        dims = sorted(vals[:3], reverse=True)
    elif len(vals) == 2:
        a, b = sorted(vals, reverse=True)  # a >= b
        # b is the cross-section size; the bounding square cross-section is b x b.
        dims = sorted([a, b, b], reverse=True)
    else:  # len == 1
        d = vals[0]
        dims = [d, d, d]
    return dims


def _box_fits(pkg_sorted: list[float], comp_dims: list[float]) -> bool:
    """Orientation-free rectangular fit: each package dim (sorted desc) must
    be <= the corresponding compartment dim (sorted desc)."""
    p = sorted(pkg_sorted, reverse=True)
    c = sorted(comp_dims, reverse=True)
    return all(pv <= cv + 1e-9 for pv, cv in zip(p, c, strict=False))


def _fits_helix(pkg_sorted: list[float]) -> bool:
    """A package fits a Helix coil when:
    - its length (largest dim) <= usable coil length, AND
    - its cross-section (the two smaller dims) fits the clear coil ring, AND
    - its thinnest dim fits within the widest spiral pitch (feed direction).
    """
    if len(pkg_sorted) < 3:
        return False
    longest, mid, shortest = pkg_sorted[0], pkg_sorted[1], pkg_sorted[2]
    if longest > HELIX_COIL_USABLE_LENGTH_MM + 1e-9:
        return False
    # Cross-section (mid x shortest) must sit within the round clear ring.
    # Use the ring's clear diameter as the bound on BOTH cross-section dims
    # (a conservative square-in-circle bound would be stricter; we bound each
    # side by the diameter, which matches how a package rests in the coil).
    if mid > HELIX_COIL_CLEAR_DIAMETER_MM + 1e-9:
        return False
    # Feed-direction thickness must fit the widest available pitch.
    if shortest > HELIX_MAX_PITCH_MM + 1e-9:
        return False
    return True


def _fits_carousel(pkg_sorted: list[float]) -> bool:
    """Fits if the package fits EITHER carousel slot geometry.

    rect slot: simple box (87 x 68 x 195).
    pie slot : tapering wedge — conservatively bound by its widest opening
               (outer_width x height x depth). A package that fits the
               rectangular envelope of the wedge opening fits the slot.
    """
    rect = cast("dict[str, float]", CAROUSEL_SLOTS["rect"])
    rect_dims = [
        rect["outer_width_mm"],
        rect["height_mm"],
        rect["depth_mm"],
    ]
    if _box_fits(pkg_sorted, rect_dims):
        return True
    pie = cast("dict[str, float]", CAROUSEL_SLOTS["pie"])
    # Conservative wedge bound: use the wide (outer) opening as the width.
    pie_dims = [
        pie["outer_width_mm"],
        pie["height_mm"],
        pie["depth_mm"],
    ]
    return _box_fits(pkg_sorted, pie_dims)


def _fits_locker(pkg_sorted: list[float], model: str) -> bool:
    """Fits if the package fits ANY box size offered by the locker model."""
    spec = LOCKER_BOXES.get(model)
    if not spec:
        return False
    box_sizes = cast("list[dict[str, float]]", spec["box_sizes_mm"])
    for box in box_sizes:
        comp = [
            box["width_mm"],
            box["depth_mm"],
            box["height_mm"],
        ]
        if _box_fits(pkg_sorted, comp):
            return True
    return False


def check_fit(pkg: PackageDims) -> FitResult:
    """Check a package against every cabinet type and recommend the smallest
    that fits. Returns a FitResult; when the package has no usable dimensions
    the result has empty `fits` and evidence 'no-dims' (caller falls back to
    the category-size approximation)."""
    dims = _normalize_package(pkg)
    if dims is None:
        return FitResult(evidence="no-dims")

    fits = {
        HELIX: _fits_helix(dims),
        CAROUSEL: _fits_carousel(dims),
        LOCKER_C: _fits_locker(dims, LOCKER_C),
        LOCKER_A: _fits_locker(dims, LOCKER_A),
        LOCKER_B: _fits_locker(dims, LOCKER_B),
    }

    recommended = None
    for cab in RECOMMENDATION_ORDER:
        if fits.get(cab):
            recommended = cab
            break

    # Evidence carries the source confidence from the extractor plus the
    # dimension count, so downstream can tell exact fits from padded ones.
    src = pkg.evidence if pkg.evidence else "unknown"
    ev = f"fit:{src}"
    if recommended is None:
        ev = f"no-fit:{src}"

    return FitResult(
        fits=fits,
        recommended=recommended,
        evidence=ev,
        package_sorted_mm=dims,
    )


def fit_disposition(current_cabinet: str, pkg: PackageDims) -> dict:
    """Validate a package against its CURRENTLY-assigned cabinet and suggest
    a correction when it doesn't fit.

    Returns a dict:
      {
        "status": "ok" | "misfit" | "no-dims",
        "current": <cabinet or "">,
        "fits_current": bool,
        "recommended": <cabinet or None>,
        "evidence": <str>,
      }

    - "ok"      : package fits its current cabinet (no action needed).
    - "misfit"  : package does NOT fit its current cabinet; `recommended`
                  names the smallest cabinet that does (or None if nothing fits).
    - "no-dims" : no usable dimensions; caller keeps the heuristic routing.
    """
    result = check_fit(pkg)
    if result.evidence == "no-dims":
        return {
            "status": "no-dims",
            "current": current_cabinet or "",
            "fits_current": False,
            "recommended": None,
            "evidence": "no-dims",
        }

    fits_current = bool(result.fits.get(current_cabinet, False))
    status = "ok" if fits_current else "misfit"
    return {
        "status": status,
        "current": current_cabinet or "",
        "fits_current": fits_current,
        "recommended": result.recommended,
        "evidence": result.evidence,
    }


def apply_fit_check(df):
    """Advisory dimensional fit-check over a planning frame (additive).

    Reads ``CabinetType`` and ``PackageDimensions`` per row and returns a copy of
    ``df`` with four columns added:

      - ``Fit_status``       : "ok" | "misfit" | "no-dims" (blank for non-KTC rows)
      - ``Fit_recommended``  : smallest cabinet that fits, when the current one does not
      - ``Fit_evidence``     : short reason string from the geometry check
      - ``Fit_package_mm``   : the parsed package envelope, sorted, as "w x d x h"

    Only KTC rows are checked; Kanban and PPE rows are not dispensed from KTC
    cabinets and receive blank fit columns. This stage is purely advisory: it never
    changes the routing the planner computed, only annotates it. The caller decides
    whether to run it at all (today: only when a package-dimensions column was
    mapped), so the function itself makes no assumption about that.
    """
    out = df.copy()
    fit_status = []
    fit_recommended = []
    fit_evidence = []
    fit_package_mm = []
    for _, row in out.iterrows():
        # Kanban and PPE rows are not dispensed from KTC cabinets, so skip them.
        if row.get("SystemCategory") != "KTC":
            fit_status.append("")
            fit_recommended.append("")
            fit_evidence.append("")
            fit_package_mm.append("")
            continue
        pkg = extract_package_dims(row.get("PackageDimensions", ""))
        disp = fit_disposition(str(row.get("CabinetType", "")), pkg)
        fit_status.append(disp["status"])
        fit_recommended.append(disp["recommended"] or "")
        fit_evidence.append(disp["evidence"])
        fit_package_mm.append(
            " x ".join(f"{v:g}" for v in pkg.sorted_mm) if pkg.ok else ""
        )

    out["Fit_status"] = fit_status
    out["Fit_recommended"] = fit_recommended
    out["Fit_evidence"] = fit_evidence
    out["Fit_package_mm"] = fit_package_mm
    return out
