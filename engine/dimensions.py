"""kromi_app.engine.dimensions — package dimension extraction.

Parses package dimensions (width / depth / height, in millimetres) from the
free-text size column some customers provide. Tools are always dispensed in
their packaging, so the package is the physical object that must fit a
compartment; these parsed dimensions feed the optional dimensional fit-check.

Pure module: no Streamlit, no global state, no I/O. Every result carries an
evidence tag describing how it was parsed, mirroring the classifier's
evidence-field pattern.

Supported input formats (case-insensitive, European or US decimals):
    "200x40x40"            -> (200, 40, 40)
    "200 x 40 x 40 mm"     -> (200, 40, 40)
    "200×40×40"            -> (200, 40, 40)   (unicode multiplication sign)
    "L200 B40 H40"         -> (200, 40, 40)   (labelled)
    "200*40*40"            -> (200, 40, 40)
    "Ø25 x 180"            -> diameter 25, length 180 (2-D cylinder)
    "25/180"               -> (25, 180)
    "150,5 x 40,5"         -> (150.5, 40.5)   (comma decimals)
    "12 cm x 4 cm"         -> (120, 40)       (cm converted to mm)
    "200"                  -> single value
    ""                     -> nothing parseable
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Units we understand, mapped to a mm multiplier.
_UNIT_TO_MM = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimetre": 1.0,
    "cm": 10.0,
    "centimeter": 10.0,
    "centimetre": 10.0,
    "m": 1000.0,
    "meter": 1000.0,
    "metre": 1000.0,
}

# Reasonable bounds (mm) for a tool package. Anything outside is treated as a
# parse error rather than a real measurement — guards against catalog noise
# like article numbers or prices landing in the size column.
_MIN_DIM_MM = 1.0
_MAX_DIM_MM = 3000.0

# Multiplication separators between dimensions: x, X, *, ×, ⋅, the word "by".
_SEP = r"[x×*⋅]"

# A single number: optional thousands separator handled by cleanup; accepts
# comma OR dot as the decimal mark.
_NUM = r"\d+(?:[.,]\d+)?"


@dataclass
class PackageDims:
    """Parsed package dimensions, all in millimetres (sorted descending in
    `sorted_mm` for orientation-independent fit checks)."""

    values_mm: list[float] = field(default_factory=list)
    is_diameter: bool = False  # True when a Ø/diameter token was seen
    evidence: str = "no-match"  # how it was parsed
    raw: str = ""  # original input (for audit)

    @property
    def count(self) -> int:
        return len(self.values_mm)

    @property
    def sorted_mm(self) -> list[float]:
        """Dimensions sorted largest-first — used for orientation-free fit."""
        return sorted(self.values_mm, reverse=True)

    @property
    def ok(self) -> bool:
        return self.count > 0


def _to_mm(num_str: str, unit: str | None) -> float | None:
    """Convert a numeric token (+ optional unit) to millimetres.

    Disambiguates the comma: a comma followed by exactly three digits is read
    as a thousands separator (1,234 -> 1234); a comma followed by one or two
    digits is a decimal mark (40,5 -> 40.5). This matches how European catalog
    data is typically written and avoids reading a 1234 mm package as 1.2 mm.
    """
    s = num_str.strip()
    # Thousands separator: comma (or dot) + exactly 3 trailing digits, no more.
    if re.fullmatch(r"\d{1,3},\d{3}", s):
        s = s.replace(",", "")  # 1,234 -> 1234
    elif re.fullmatch(r"\d{1,3}\.\d{3}", s):
        s = s.replace(".", "")  # 1.234 -> 1234 (European thousands)
    else:
        s = s.replace(",", ".")  # decimal comma -> dot
    try:
        val = float(s)
    except (ValueError, TypeError):
        return None
    if unit:
        mult = _UNIT_TO_MM.get(unit.strip().lower())
        if mult is None:
            return None
        val *= mult
    if val < _MIN_DIM_MM or val > _MAX_DIM_MM:
        return None
    return round(val, 2)


def _trailing_unit(text: str) -> str | None:
    """Find a single unit token that applies to the whole expression
    (e.g. trailing 'mm' in '200 x 40 x 40 mm')."""
    m = re.search(rf"({'|'.join(_UNIT_TO_MM)})\b", text.lower())
    return m.group(1) if m else None


def extract_package_dims(value) -> PackageDims:
    """Parse package dimensions from a single cell value.

    Returns a PackageDims. When nothing parseable is found, the result has
    count == 0 and evidence == "no-match"; callers fall back to the
    category-size approximation for that row.
    """
    if value is None:
        return PackageDims(raw="")
    raw = str(value).strip()
    if not raw:
        return PackageDims(raw="")

    text = raw

    # Detect a diameter marker (Ø, ⌀, "dia", "d=", "d ").
    is_diameter = bool(
        re.search(r"[Ø⌀]", text)
        or re.search(r"\bdia\b", text, re.IGNORECASE)
        or re.search(r"\bd\s*[=:]\s*\d", text, re.IGNORECASE)
    )

    # A single unit applying to the whole expression (trailing mm/cm/m).
    overall_unit = _trailing_unit(text)

    # --- Strategy 1: explicit N x N (x N) chains -------------------------
    # Each number may carry its own unit immediately after it.
    chain = re.findall(
        rf"({_NUM})\s*({'|'.join(_UNIT_TO_MM)})?\s*(?:{_SEP})",
        text,
        re.IGNORECASE,
    )
    # The chain regex captures every number that is FOLLOWED by a separator;
    # the final number has no trailing separator, so grab it separately.
    if chain:
        # Build the full sequence by splitting on separators.
        parts = re.split(_SEP, text, flags=re.IGNORECASE)
        vals: list[float] = []
        for part in parts:
            mnum = re.search(rf"({_NUM})\s*({'|'.join(_UNIT_TO_MM)})?", part, re.IGNORECASE)
            if not mnum:
                continue
            unit = mnum.group(2) or overall_unit
            mm = _to_mm(mnum.group(1), unit)
            if mm is not None:
                vals.append(mm)
        if len(vals) >= 2:
            ev = f"parsed:{len(vals)}d" + (":diameter" if is_diameter else "")
            return PackageDims(values_mm=vals, is_diameter=is_diameter, evidence=ev, raw=raw)

    # --- Strategy 2: labelled dims (L.. B.. H.. / W.. D.. H..) ------------
    labelled = re.findall(
        rf"\b([lbhwdtxyz])\s*[=:]?\s*({_NUM})\s*({'|'.join(_UNIT_TO_MM)})?",
        text,
        re.IGNORECASE,
    )
    if len(labelled) >= 2:
        vals = []
        for _label, num, unit in labelled:
            mm = _to_mm(num, unit or overall_unit)
            if mm is not None:
                vals.append(mm)
        if len(vals) >= 2:
            ev = f"parsed:{len(vals)}d:labelled" + (":diameter" if is_diameter else "")
            return PackageDims(values_mm=vals, is_diameter=is_diameter, evidence=ev, raw=raw)

    # --- Strategy 3: slash-separated (25/180) ----------------------------
    if "/" in text:
        slash_vals = []
        for part in text.split("/"):
            mnum = re.search(rf"({_NUM})\s*({'|'.join(_UNIT_TO_MM)})?", part, re.IGNORECASE)
            if mnum:
                mm = _to_mm(mnum.group(1), mnum.group(2) or overall_unit)
                if mm is not None:
                    slash_vals.append(mm)
        if len(slash_vals) >= 2:
            ev = f"parsed:{len(slash_vals)}d:slash" + (":diameter" if is_diameter else "")
            return PackageDims(values_mm=slash_vals, is_diameter=is_diameter, evidence=ev, raw=raw)

    # --- Strategy 4: single value ----------------------------------------
    single = re.search(rf"({_NUM})\s*({'|'.join(_UNIT_TO_MM)})?", text, re.IGNORECASE)
    if single:
        mm = _to_mm(single.group(1), single.group(2) or overall_unit)
        if mm is not None:
            ev = "parsed:1d" + (":diameter" if is_diameter else "")
            return PackageDims(values_mm=[mm], is_diameter=is_diameter, evidence=ev, raw=raw)

    return PackageDims(raw=raw)
