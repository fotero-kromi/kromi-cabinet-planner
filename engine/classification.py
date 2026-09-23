"""kromi_app.engine.classification — product category + tool class heuristics.

This is the largest engine module (19 functions). It owns:

* Hard insert detection (ISO code recognizer + keyword fallback)
* PPE detection
* Product-category normalization and the main keyword-based classifier
* French SAP-shorthand classifier (FO/FR/AL/ME for Foret/Fraise/Alésoir/Meule)
* Supplier-code patterns (Seco WNW, Iscar IC, Sandvik 5300/etc.)
* Supplier-specialty soft fallback (Guhring/Mapal/etc.)
* ToolClass derivation from classification evidence
* The main evidence-tracking classifier (classify_with_evidence)
* Size-category and pack-units heuristics
* Bulk-consumable family detection

All functions are pure: no streamlit, no I/O, no global state. They depend on
constants (already in engine.constants) and text utilities (engine.text_utils).
"""

from __future__ import annotations

import re

import pandas as pd

from .kds_structure_words import KDS_STRUCTURE_CATEGORY
from .constants import (
    ACCESSORY_KEYWORDS,
    BORING_BAR_KEYWORDS,
    BROACH_KEYWORDS,
    BRUSH_KEYWORDS,
    CENTER_POINT_KEYWORDS,
    COUNTERBORE_KEYWORDS,
    DRILL_KEYWORDS,
    DRILL_SHORTHAND_FR,
    FORM_STEEL_KEYWORDS,
    GEAR_CUTTING_KEYWORDS,
    GRINDING_SHORTHAND_FR,
    GRINDING_TOOL_KEYWORDS,
    HOLDER_KEYWORDS,
    HONING_TOOL_KEYWORDS,
    INSERT_KEYWORDS,
    LISTING_PPE,
    LISTING_TOOLS,
    MILL_KEYWORDS,
    MILL_SHORTHAND_FR,
    PACK_HINT_PATTERNS,
    PC_VALID,
    PPE_KEYWORDS,
    PUNCHING_KEYWORDS,
    REAMER_KEYWORDS,
    REAMER_SHORTHAND_FR,
    SCREW_KEYWORDS,
    SUPPLIER_CODE_PATTERNS,
    SUPPLIER_SPECIALTY,
    # Kromi-aligned keyword lists
    TAP_KEYWORDS,
    THREAD_DIE_KEYWORDS,
    THREAD_MILL_KEYWORDS,
    TOOL_HOLDER_KEYWORDS,
    TOOLCLASS_FROM_PRODUCT_CATEGORY,
    TOOL_CLASS_VALID,
    WELDING_KEYWORDS,
)
from .text_utils import (
    collapse_ws,
    contains_any_keyword,
    norm,
    _normalize_size_code,
)


def looks_like_insert_code(text: str) -> bool:
    """Detect an ISO-style cutting-insert shape code."""
    t = collapse_ws(str(text or "")).upper()
    pattern = (
        r"\b(?:"
        # Standard turning inserts
        r"CCMT|CNMG|CNMM|CNMA|CNGA|CNMX|"
        r"DCGT|DNMG|DNMM|DNMA|DNGA|"
        r"VNMG|VCGT|VBMT|"
        r"TCMT|TNMG|TNMM|TNGG|TPGN|TPKN|"
        r"SCMT|SNMG|SNMM|SPGN|SPMR|"
        r"WNMG|WNMM|WNMA|WNMX|WNGA|"
        # Drilling inserts
        r"APKT|ADKT|ANCX|ANKX|AOMT|AXMT|"
        # Boring inserts
        r"RCMT|RCGT|RNGN|RNMG|"
        # Milling inserts
        r"SPGT|SPGX|SPMX|SPMA|"
        r"LNMT|LNHT|LCMF|LCGN|LCGA|LCMT|LCGT|"
        r"OEMT|OFKT|OFMT|OFCX|"
        r"XOMX|XOEX|XOMT|XPMT|"
        r"QPMT|QPHM|"
        # Specialty
        r"TCKT|WXCU|WPC|HNGX|HNHN"
        r")\b"
    )
    return bool(re.search(pattern, t))


def is_insert_text(*parts: str) -> bool:
    joined = " ".join(collapse_ws(str(p or "")) for p in parts).lower()
    if not joined:
        return False
    if looks_like_insert_code(joined):
        return True
    return contains_any_keyword(joined, INSERT_KEYWORDS)


def is_ppe_text(*parts: str) -> bool:
    """Return True if any PPE keyword appears in the combined text.
    Only meaningful when the row is in the PPE listing — we never consult
    this on Tools rows, so tool descriptions can never get mistagged as PPE."""
    joined = " ".join(collapse_ws(str(p or "")) for p in parts).lower()
    if not joined:
        return False
    return contains_any_keyword(joined, PPE_KEYWORDS)


def normalize_product_category(raw: str) -> str:
    x = norm(raw)
    if not x:
        return ""

    # Canonical names are identity (v34.18): a mapped category column carrying
    # the canonical English names must keep them as provided values instead of
    # falling through the freeform synonym matcher to 'other'.
    if x in PC_VALID:
        return x

    # KDS structure-code words are exact matches against the official list
    # (v34.47): a mapped ProductCategory column carrying the KDS template's
    # Bezeichnung 1 values resolves from the customer's own taxonomy before
    # any keyword guessing. Checked ahead of the keyword blocks so compound
    # words ("Capto Aufsteck-Fräsdorn", "HSK63 Spannzangen") can never be
    # misread by a substring.
    _kds = KDS_STRUCTURE_CATEGORY.get(x)
    if _kds is not None:
        return _kds

    # INSERT MUST WIN over drilling/milling wording
    if is_insert_text(x):
        return "inserts"

    # Compound German thread-tool words must be checked BEFORE the generic
    # drill/mill match: "Gewindebohrer" contains "bohrer" and "Gewindefräser"
    # contains "fräser", so without this precedence they would be misread as
    # drills/mills. This mirrors the precedence in classify_with_evidence and
    # does not affect real drill compounds like "Stufenbohrer"/"Kernbohrer",
    # which are not in the thread keyword lists.
    if contains_any_keyword(x, THREAD_MILL_KEYWORDS):
        return "thread_mills"
    if contains_any_keyword(x, TAP_KEYWORDS):
        return "taps"
    if contains_any_keyword(x, THREAD_DIE_KEYWORDS):
        return "thread_dies"

    if contains_any_keyword(x, BORING_BAR_KEYWORDS):
        return "boring_bars"
    if contains_any_keyword(x, DRILL_KEYWORDS):
        return "drills"
    if contains_any_keyword(x, MILL_KEYWORDS):
        return "mills"
    if contains_any_keyword(x, REAMER_KEYWORDS):
        return "reamers"
    if contains_any_keyword(x, HOLDER_KEYWORDS):
        return "holders"
    if contains_any_keyword(x, SCREW_KEYWORDS):
        return "screws"
    if contains_any_keyword(x, ACCESSORY_KEYWORDS):
        return "accessories"
    if contains_any_keyword(x, PPE_KEYWORDS):
        return "ppe"

    return "other"


def first_valid_product_category(series: pd.Series, default=""):
    for v in series:
        s = normalize_product_category(v)
        if s in PC_VALID and s not in ("", "other"):
            return s
    return default


def first_valid_product_category_text(series: pd.Series, default=""):
    """Like :func:`first_valid_product_category`, but returns the provided text
    itself (v34.56). The planning base keeps a mapped category column's own
    words (a KDS structure word such as "Stufenbohrer VHM"), so the boundary
    heuristics, which normalize it, still see what the customer wrote."""
    for v in series:
        s = normalize_product_category(v)
        if s in PC_VALID and s not in ("", "other"):
            return str(v).strip()
    return default


def is_weak_category(pc: str) -> bool:
    pc = (pc or "").strip().lower()
    return pc in ("", "other")


# Deterministic rules
def heuristic_product_category(desc1: str, desc2: str, code: str, supplier_code: str) -> str | None:
    # INSERT MUST WIN over drilling/milling wording
    if is_insert_text(desc1, desc2, code, supplier_code):
        return "inserts"

    d = (collapse_ws(desc1) + " " + collapse_ws(desc2)).lower()

    if contains_any_keyword(d, BORING_BAR_KEYWORDS):
        return "boring_bars"
    if contains_any_keyword(d, DRILL_KEYWORDS):
        return "drills"
    if contains_any_keyword(d, MILL_KEYWORDS):
        return "mills"
    if contains_any_keyword(d, REAMER_KEYWORDS):
        return "reamers"
    if contains_any_keyword(d, HOLDER_KEYWORDS):
        return "holders"
    if contains_any_keyword(d, SCREW_KEYWORDS):
        return "screws"
    if contains_any_keyword(d, ACCESSORY_KEYWORDS):
        return "accessories"

    return None


def _kw_matches(text: str, keyword: str) -> bool:
    """Centralized keyword match: word-boundary for short keywords (≤4 chars)
    to avoid 'vis' matching inside 'Tournevis' and similar compound-word traps."""
    if not keyword:
        return False
    if len(keyword) <= 4:
        return bool(re.search(rf"\b{re.escape(keyword)}\b", text))
    return keyword in text


def _shorthand_matches(raw_text: str, shorthand: str) -> bool:
    """Match a French SAP-catalog shorthand (FO, FR, AL, ME) against the RAW
    uppercase description. Used for cryptic descriptions like 'FO DAG D3,27'
    where FO means Foret (drill). Lowercasing the text loses the signal —
    lowercased 'fo' would match inside 'format', 'before', 'info'.

    Match requires:
    - Token in uppercase exactly as given
    - At start of string OR preceded by whitespace / dot
    - Followed by whitespace, dot, or end-of-string

    Examples that MATCH: 'FO DAG D3,27', 'FO.CW Ø2.55', 'AL 1T D8H7'
    Examples that DON'T: 'Format', 'Foret', 'aluminum', 'metal'
    """
    if not raw_text or not shorthand:
        return False
    # Build the pattern: (start|whitespace|dot) + SHORTHAND + (whitespace|dot|end)
    pattern = rf"(?:^|[\s.]){re.escape(shorthand)}(?=[\s.]|$)"
    return bool(re.search(pattern, raw_text))


def _supplier_brand_matches(supplier_field: str, brand_substring: str) -> bool:
    """Case-insensitive substring match on the supplier field. Handles short
    names ('seco', 'Iscar') and long corporate names ('SECO TOOLS FRANCE',
    'KENNAMETAL FRANCE'). Empty supplier always returns False."""
    if not supplier_field or not brand_substring:
        return False
    return brand_substring.lower() in supplier_field.lower()


def _check_supplier_code_pattern(code: str, supplier_field: str) -> tuple[str, str] | None:
    """Run the code through SUPPLIER_CODE_PATTERNS. Returns (category, evidence)
    on the first match, or None if no pattern fires. Both the supplier brand
    AND the code shape must match — supplier alone is never enough.

    Note: ToolClass is derivable from the evidence tag via derive_tool_class().
    We return only (category, evidence) here to keep the function signature stable
    for existing callers; tool_class is looked up separately at the call site."""
    code_upper = (code or "").strip().upper()
    if not code_upper or not supplier_field:
        return None
    for brand, pattern, category, _tool_class, evidence in SUPPLIER_CODE_PATTERNS:
        if not _supplier_brand_matches(supplier_field, brand):
            continue
        if re.search(pattern, code_upper):
            return category, f"supplier_pattern:{evidence}"
    return None


def _check_supplier_specialty(supplier_field: str) -> tuple[str, str] | None:
    """Soft fallback: supplier-specialty hints. Only consulted when no other
    classification succeeded. Returns (category, evidence) for known specialty
    suppliers (Guhring=drills, Mapal=reamers, etc.)."""
    if not supplier_field:
        return None
    sup_lower = supplier_field.lower()
    for brand, payload in SUPPLIER_SPECIALTY.items():
        if brand in sup_lower:
            category, _tool_class, evidence = payload
            return category, f"supplier_specialty:{evidence}"
    return None


def derive_tool_class(
    evidence: str,
    code: str,
    supplier_field: str,
    product_category: str,
) -> str:
    """Derive a ToolClass from the classification evidence + supplier + code.

    The evidence string encodes how the row was classified (e.g. 'iso:CNMG',
    'supplier_pattern:seco:WS_grade', 'shorthand:FO', 'keyword:foret').
    From that plus the supplier and the product_category, we pick the most
    specific ToolClass we can. Returns 'other' if we can't be more specific
    than the product_category.

    This function is pure — it doesn't read any state, so it's testable in
    isolation.
    """
    if not evidence or not isinstance(evidence, str):
        return "other"

    ev_lower = evidence.lower()

    # 1) ISO insert codes — most are turning, some are milling/drilling
    if ev_lower.startswith("iso:"):
        iso_code = evidence.split(":", 1)[1].strip()
        # Milling-specific ISO prefixes
        if iso_code in (
            "APKT",
            "ADKT",
            "ANCX",
            "ANKX",
            "AOMT",
            "AXMT",
            "SPGT",
            "SPGX",
            "SPMX",
            "SPMA",
            "LNMT",
            "LNHT",
            "LCMF",
            "LCGN",
            "LCGA",
            "LCMT",
            "LCGT",
            "OEMT",
            "OFKT",
            "OFMT",
            "OFCX",
            "XOMX",
            "XOEX",
            "XOMT",
            "XPMT",
            "QPMT",
            "QPHM",
        ):
            return "milling_insert"
        # Drilling inserts
        if iso_code in ("WCMX", "WOMT", "WPMT"):
            return "drilling_insert"
        # Default: turning insert (CNMG, TNMG, WNMG, SNMG, etc.)
        return "turning_insert"

    # 2) Supplier pattern — look up the original 5-tuple to get tool_class
    if ev_lower.startswith("supplier_pattern:"):
        evidence_tag = evidence.split(":", 1)[1]  # e.g. "seco:WS_grade"
        for _brand, _pattern, _cat, tool_class, ev_in_tuple in SUPPLIER_CODE_PATTERNS:
            if ev_in_tuple == evidence_tag:
                return tool_class
        # Fallback: derive from product_category
        return TOOLCLASS_FROM_PRODUCT_CATEGORY.get(product_category, "other")

    # 3) Supplier specialty — look up the specialty entry
    if ev_lower.startswith("supplier_specialty:"):
        evidence_tag = evidence.split(":", 1)[1]
        for _brand, payload in SUPPLIER_SPECIALTY.items():
            _cat, tool_class, ev_in_tuple = payload
            if ev_in_tuple == evidence_tag:
                return tool_class
        return TOOLCLASS_FROM_PRODUCT_CATEGORY.get(product_category, "other")

    # 4) French shorthand — FO=drills, FR=mills, AL=reamers, ME=grinding
    if ev_lower.startswith("shorthand:"):
        sh = evidence.split(":", 1)[1].upper()
        if sh == "FO":
            return "solid_carbide_drill"  # most FO in French catalogs are carbide drills
        if sh == "FR":
            return "solid_end_mill"
        if sh == "AL":
            return "reamer"
        if sh == "ME":
            return "grinding_wheel"

    # 5) Generic keyword — derive from product_category, with L2 detail where
    # the specific keyword reveals a more granular ToolClass.
    if ev_lower.startswith("keyword:"):
        keyword = evidence.split(":", 1)[1].strip().lower()

        # ---- L2 detail for drills ----
        # Kromi L2 keywords map to specific drill subclasses
        DRILL_L2_MAP = {
            "spiralbohrer": "spiral_drill",
            "vhm-bohrer": "solid_carbide_drill",
            "bohrkrone": "core_drill",
            "bohrfräser": "core_drill",  # hole cutter — Kromi: drill family
            "bohrfraeser": "core_drill",
            "bohrreibahle": "spiral_drill",  # drill-reamer hybrid, drill side dominates
            "bohrsenker": "step_drill",  # drill-countersink hybrid
        }
        if keyword in DRILL_L2_MAP:
            return DRILL_L2_MAP[keyword]

        # ---- L2 detail for mills ----
        MILL_L2_MAP = {
            "frässtift": "burr",
            "fraesstift": "burr",
            "kreissägeblatt": "saw_blade",
            "kreissaegeblatt": "saw_blade",
            "wälzfräser": "form_mill",  # gear hob — treated as form mill in mills L1
            "waelzfraeser": "form_mill",
            "endmill": "solid_end_mill",
        }
        if keyword in MILL_L2_MAP:
            return MILL_L2_MAP[keyword]

        # ---- L2 detail for taps ----
        if keyword in ("gewindebohrer", "tap", "taraud", "macho de roscar", "závitník"):
            return "tap"
        if keyword in (
            "gewindeformer",
            "thread former",
            "tvarovací závitník",
            "macho de laminacion",
            "thread molder",
            "mouleur de filets",
            "závitník tvářecí",
        ):
            return "thread_former"

        # ---- L2 detail for thread mills ----
        if keyword in (
            "gewindebohrfräser",
            "gewindebohrfraeser",
            "thread hole cutter",
            "závitová vrtací fréza",
        ):
            return "thread_hole_cutter"
        if "gewindefräser" in keyword or "thread mill" in keyword or "thread cutter" in keyword:
            return "thread_mill"

        # ---- L2 detail for counterbores ----
        COUNTERBORE_L2_MAP = {
            "kegelsenker": "countersink",
            "flachsenker": "flat_countersink",
            "rückwärtssenker": "back_countersink",
            "rueckwaertssenker": "back_countersink",
            "stufensenker": "step_countersink",
            "entgratgabel": "deburring_fork",
            "deburring fork": "deburring_fork",
        }
        if keyword in COUNTERBORE_L2_MAP:
            return COUNTERBORE_L2_MAP[keyword]

        # ---- L2 detail for tool_holders ----
        # The keyword IS the interface code (hsk50, sk40, vdi30, etc.)
        if keyword.startswith("hsk"):
            return "hsk_holder"
        if keyword.startswith("sk") and len(keyword) <= 5:  # sk30/sk40/sk45/sk50, not "skala"
            return "sk_holder"
        if keyword.startswith("vdi"):
            return "vdi_holder"
        if keyword == "capto":
            return "capto_holder"
        if keyword.startswith("abs"):
            return "abs_holder"
        if keyword.startswith("masbt"):
            return "masbt_holder"
        if keyword == "bmt45":
            return "bmt_holder"
        if keyword == "varilock":
            return "varilock_holder"
        if keyword == "varia":
            return "varia_holder"
        if keyword == "km":
            return "km_holder"
        if keyword in ("morse", "cône morse", "cone morse"):
            return "mk_holder"

        # ---- L2 detail for grinding_tools ----
        GRINDING_L2_MAP = {
            "schleifscheibe": "grinding_wheel",
            "grinding wheel": "grinding_wheel",
            "schleifstift": "grinding_pin",
            "grinding pin": "grinding_pin",
            "honstein": "honing_stone",
            "honing stone": "honing_stone",
            "abrichter": "dressing_tool",
            "dressing tool": "dressing_tool",
            "trennscheibe": "cutting_disc",
            "cutting disc": "cutting_disc",
            "cutting disk": "cutting_disc",
            "schleifband": "abrasive_belt",
            "schleiffächer": "flap_wheel",
            "flap wheel": "flap_wheel",
        }
        if keyword in GRINDING_L2_MAP:
            return GRINDING_L2_MAP[keyword]

        # Default: fall through to PC-based mapping
        return TOOLCLASS_FROM_PRODUCT_CATEGORY.get(product_category, "other")

    # 6) Provided / override / AI — these have their own tool_class fields
    # populated upstream. If we got here, no specific tool_class was provided.
    return TOOLCLASS_FROM_PRODUCT_CATEGORY.get(product_category, "other")


def classify_with_evidence(
    desc1: str, desc2: str, code: str, supplier_code: str, listing: str
) -> tuple[str | None, str]:
    """Evidence-tracking classifier ."""
    d_joined = (
        collapse_ws(desc1)
        + " "
        + collapse_ws(desc2)
        + " "
        + collapse_ws(code)
        + " "
        + collapse_ws(supplier_code)
    ).lower()

    # 1) Hard insert detection — ISO code takes evidence priority over keyword
    # because ISO codes are more specific evidence than a generic "insert" word.
    if looks_like_insert_code(" ".join([desc1, desc2, code, supplier_code])):
        t = " ".join(str(x or "") for x in [desc1, desc2, code, supplier_code]).upper()
        for iso in [
            # Standard turning inserts
            "CCMT",
            "CNMG",
            "CNMM",
            "CNMA",
            "CNGA",
            "CNMX",
            "DCGT",
            "DNMG",
            "DNMM",
            "DNMA",
            "DNGA",
            "VNMG",
            "VCGT",
            "VBMT",
            "TCMT",
            "TNMG",
            "TNMM",
            "TNGG",
            "TPGN",
            "TPKN",
            "SCMT",
            "SNMG",
            "SNMM",
            "SPGN",
            "SPMR",
            "WNMG",
            "WNMM",
            "WNMA",
            "WNMX",
            "WNGA",
            # Drilling inserts
            "APKT",
            "ADKT",
            "ANCX",
            "ANKX",
            "AOMT",
            "AXMT",
            # Boring inserts
            "RCMT",
            "RCGT",
            "RNGN",
            "RNMG",
            # Milling inserts (ISO-style)
            "SPGT",
            "SPGX",
            "SPMX",
            "SPMA",
            "LNMT",
            "LNHT",
            "LCMF",
            "LCGN",
            "LCGA",
            "LCMT",
            "LCGT",
            "OEMT",
            "OFKT",
            "OFMT",
            "OFCX",
            "XOMX",
            "XOEX",
            "XOMT",
            "XPMT",
            "QPMT",
            "QPHM",
            # Specialty
            "TCKT",
            "TPKN",
            "WXCU",
            "WPC",
            "HNGX",
            "HNHN",
        ]:
            if re.search(rf"\b{iso}\b", t):
                return "inserts", f"iso:{iso}"
    # Fall through if no ISO match — try keyword
    for ins_kw in INSERT_KEYWORDS:
        if _kw_matches(d_joined, ins_kw):
            return "inserts", f"keyword:{ins_kw}"

    # French SAP-shorthand check on Tools-listing rows only. French aerospace
    # catalogs use 2-letter codes (FO, FR, AL, ME) at the start of cryptic
    # descriptions like 'FO DAG D3,27 Z2 CARB'. The AI can't reliably infer
    # these without the rest of the text being explicit; the heuristic below
    # catches them deterministically.
    if str(listing).strip().lower() == LISTING_TOOLS.lower():
        raw = " ".join(str(x or "") for x in [desc1, desc2]).strip().upper()
        for sh in DRILL_SHORTHAND_FR:
            if _shorthand_matches(raw, sh):
                return "drills", f"shorthand:{sh}"
        for sh in MILL_SHORTHAND_FR:
            if _shorthand_matches(raw, sh):
                return "mills", f"shorthand:{sh}"
        for sh in REAMER_SHORTHAND_FR:
            if _shorthand_matches(raw, sh):
                return "reamers", f"shorthand:{sh}"
        for sh in GRINDING_SHORTHAND_FR:
            if _shorthand_matches(raw, sh):
                return "accessories", f"shorthand:{sh}"

        # Supplier-specific code patterns. Both supplier brand AND code shape
        # must match — supplier alone is never enough. Catches Seco WNW08HD,
        # Iscar IC8250, Sandvik 5322-425-04, etc. without needing AI.
        pattern_hit = _check_supplier_code_pattern(code, supplier_code)
        if pattern_hit:
            return pattern_hit

    # 2) PPE listing bias — if a PPE keyword matches, lock to ppe
    if str(listing).strip().lower() == LISTING_PPE.lower():
        for ppe_kw in PPE_KEYWORDS:
            if _kw_matches(d_joined, ppe_kw):
                return "ppe", f"keyword:{ppe_kw}"

    # 3) Tool categories, in precedence order
    def _find_kw(kws: list[str]) -> str | None:
        for kw in kws:
            if _kw_matches(d_joined, kw):
                return kw
        return None

    # Kromi-aligned categories must be checked BEFORE the generic
    # drill/mill/holder sweep, because compound German words (Gewindebohrer,
    # Gewindefräser, Kegelsenker, etc.) would otherwise substring-match the
    # parent category. The fix is precedence, not stricter matching — that
    # would break compound DRILL words like "Stufenbohrer", "Kernbohrer".

    # Tool holders (Werkzeugaufnahme) — fixed engineering codes, no overlap
    kw: str | None = _find_kw(TOOL_HOLDER_KEYWORDS)
    if kw:
        return "tool_holders", f"keyword:{kw}"

    # Taps (Gewindebohrer) — MUST come before drills to prevent substring match
    kw = _find_kw(TAP_KEYWORDS)
    if kw:
        return "taps", f"keyword:{kw}"

    # Thread mills (Gewindefräser, Gewindebohrfräser) — MUST come before mills
    kw = _find_kw(THREAD_MILL_KEYWORDS)
    if kw:
        return "thread_mills", f"keyword:{kw}"

    # Thread dies (Schneideisen, Gewinderoller)
    kw = _find_kw(THREAD_DIE_KEYWORDS)
    if kw:
        return "thread_dies", f"keyword:{kw}"

    # Counterbores (Senker)
    kw = _find_kw(COUNTERBORE_KEYWORDS)
    if kw:
        return "counterbores", f"keyword:{kw}"

    # Grinding tools (Schleifkörper) — distinct from accessories
    kw = _find_kw(GRINDING_TOOL_KEYWORDS)
    if kw:
        return "grinding_tools", f"keyword:{kw}"

    # Center points (Zentrierspitzen)
    kw = _find_kw(CENTER_POINT_KEYWORDS)
    if kw:
        return "center_points", f"keyword:{kw}"

    # Smaller Kromi L1 families
    kw = _find_kw(BROACH_KEYWORDS)
    if kw:
        return "broaches", f"keyword:{kw}"
    kw = _find_kw(GEAR_CUTTING_KEYWORDS)
    if kw:
        return "gear_cutting", f"keyword:{kw}"
    kw = _find_kw(HONING_TOOL_KEYWORDS)
    if kw:
        return "honing_tools", f"keyword:{kw}"
    kw = _find_kw(BRUSH_KEYWORDS)
    if kw:
        return "brushes", f"keyword:{kw}"
    kw = _find_kw(WELDING_KEYWORDS)
    if kw:
        return "welding", f"keyword:{kw}"
    kw = _find_kw(PUNCHING_KEYWORDS)
    if kw:
        return "punching", f"keyword:{kw}"
    kw = _find_kw(FORM_STEEL_KEYWORDS)
    if kw:
        return "form_steel", f"keyword:{kw}"

    # ---- Original keyword sweep (lower precedence than the categories above) ----
    kw = _find_kw(BORING_BAR_KEYWORDS)
    if kw:
        return "boring_bars", f"keyword:{kw}"
    kw = _find_kw(DRILL_KEYWORDS)
    if kw:
        return "drills", f"keyword:{kw}"
    kw = _find_kw(MILL_KEYWORDS)
    if kw:
        return "mills", f"keyword:{kw}"
    kw = _find_kw(REAMER_KEYWORDS)
    if kw:
        return "reamers", f"keyword:{kw}"
    kw = _find_kw(HOLDER_KEYWORDS)
    if kw:
        return "holders", f"keyword:{kw}"
    kw = _find_kw(SCREW_KEYWORDS)
    if kw:
        return "screws", f"keyword:{kw}"
    kw = _find_kw(ACCESSORY_KEYWORDS)
    if kw:
        return "accessories", f"keyword:{kw}"

    # 4) PPE keyword on Tools listing — still recognize (data contamination)
    if str(listing).strip().lower() == LISTING_TOOLS.lower():
        for ppe_kw in PPE_KEYWORDS:
            if _kw_matches(d_joined, ppe_kw):
                return "ppe", f"keyword:{ppe_kw}"

    # 5) Supplier-specialty soft fallback (Tools only). Last chance before
    # punting to AI. Catches drill-specialists (Guhring, Tivoly, Botek),
    # reamer-specialists (Mapal), abrasive-specialists (Asahi Diamond) when
    # descriptions are too minimal for keyword matching.
    if str(listing).strip().lower() == LISTING_TOOLS.lower():
        specialty_hit = _check_supplier_specialty(supplier_code)
        if specialty_hit:
            return specialty_hit

    # 6) Unknown — fall through to AI. NO FALLBACK TO ppe.
    return None, "no-match"


def heuristic_product_category_with_listing(
    desc1: str, desc2: str, code: str, supplier_code: str, listing: str
) -> str | None:
    """Legacy wrapper — preserved for any external callers. The main
    pipeline uses ``classify_with_evidence`` directly."""
    cat, _evidence = classify_with_evidence(desc1, desc2, code, supplier_code, listing)
    return cat


_INCH_MARK = r'(?:"|″|\'\'|inch\b|inches\b)'


def parse_inch_diameter_mm(text: str) -> float | None:
    """Best-effort extraction of an inch diameter from a tool description, in mm.

    Conservative on purpose: it only fires on an explicit inch mark (", inch,
    inches) or on a characteristic *sub-inch* decimal token with 3-4 decimal
    places (e.g. ".370", "0.2502") — the way cutting-tool diameters are written
    in inch-based catalogs. It deliberately does NOT interpret plain millimetre
    values (which the caller handles first) or one-decimal numbers, so it won't
    misread an "8 mm" or a quantity as inches. Returns the largest dimension
    found (the governing size), converted to millimetres, or None.
    """
    if not text:
        return None
    t = str(text).lower()
    values_in: list[float] = []

    # Fractional inch with an explicit mark: 1/4", 3/8 inch
    for fm in re.finditer(rf"(\d{{1,2}})\s*/\s*(\d{{1,2}})\s*{_INCH_MARK}", t):
        den = int(fm.group(2))
        if den:
            values_in.append(int(fm.group(1)) / den)

    # Decimal or whole inch with an explicit mark: 0.5", .370 inch, 2"
    # The (?<![\d./]) guard stops it from grabbing a fraction's denominator (the
    # "4" in 1/4") or part of a larger number.
    for dm in re.finditer(rf"(?<![\d./])(\d*\.\d+|\d+)\s*{_INCH_MARK}", t):
        try:
            values_in.append(float(dm.group(1)))
        except ValueError:
            pass

    # Bare sub-inch decimal tokens (3-4 decimals) — characteristic of inch tooling
    for bm in re.finditer(r"(?<![\d.])(0?\.\d{3,4})(?!\d)", t):
        try:
            values_in.append(float(bm.group(1)))
        except ValueError:
            pass

    if not values_in:
        return None
    return max(values_in) * 25.4


def heuristic_size_category(prod_cat: str, desc1: str, desc2: str) -> str | None:
    pc = norm(prod_cat)
    d = (collapse_ws(desc1) + " " + collapse_ws(desc2)).lower()

    if pc == "inserts":
        return "S"
    if pc == "screws":
        return "S"
    # boring_bars are long tools, but size them by the measured dimension when
    # the description carries one (a Ø1.4 x 40 mm bar is small, not XL). They
    # fall through to the diameter parser below; the XL default is applied only
    # when no dimension can be read (an unspecified boring bar is assumed large).

    # PPE: size by PPE sub-type
    if pc == "ppe":
        if contains_any_keyword(
            d, ["earplug", "ear plug", "earmuff", "bouchon", "ohrstöpsel", "ohrstopsel", "tapone"]
        ):
            return "S"
        if contains_any_keyword(
            d, ["goggle", "goggles", "safety glass", "lunette", "brille", "gafa", "óculos"]
        ):
            return "S"
        if contains_any_keyword(
            d, ["mask", "masque", "maske", "mascarilla", "máscara", "respirator", "respirateur"]
        ):
            return "S"
        if contains_any_keyword(d, ["glove", "gant", "handschuh", "guante", "luva"]):
            return "S"
        if contains_any_keyword(
            d,
            [
                "safety boot",
                "safety shoe",
                "chaussure de securite",
                "chaussure de sécurité",
                "sicherheitsschuh",
                "bota de seguridad",
                "zapato de seguridad",
            ],
        ):
            return "XL"
        if contains_any_keyword(d, ["helmet", "hard hat", "casque", "helm", "casco", "capacete"]):
            return "XL"
        if contains_any_keyword(
            d, ["coverall", "overall", "combinaison", "traje de proteccion", "schutzanzug"]
        ):
            return "XXL"
        # Unknown PPE: medium default
        return "M"

    if "locker a" in d:
        return "XXL"
    if "locker b" in d:
        return "XXLS"
    if "locker c" in d:
        return "XLS"

    diam = None
    # Diameter parsing for metric catalogs. European descriptions use comma
    # decimals and leading zeros ("Ø 02,40mm" = 2.40 mm, "Ø 16,00" = 16 mm) and
    # usually put a space after the Ø symbol. Three bugs used to make tiny
    # drills read as XL:
    #   * the Ø branch had no separator, so "Ø 2,40" missed and fell through;
    #   * the decimal group captured only ONE digit, so the mm fallback grabbed
    #     the fractional part ("02,40mm" -> "40mm" -> 40 mm);
    #   * a bare "d" matched deep-hole notation ("6xD 130°" -> 130 mm).
    # The marker now allows a separator and an explicit "d=" only, and the
    # number captures 1-3 decimal places so the full value is read.
    _num = r"(\d{1,3}(?:[.,]\d{1,3})?)"
    m = re.search(r"(?:ø|⌀|dia\.?|diam\.?|(?<![x0-9])d\s*=?)\s*" + _num, d)
    if not m:
        # Fallback: first "<number> mm" — capture the FULL decimal number so
        # "02,40mm" reads as 2.40, not 40.
        m = re.search(_num + r"\s*mm\b", d)
    if m:
        try:
            diam = float(m.group(1).replace(",", "."))
        except Exception:
            diam = None

    if diam is None:
        # No millimetre diameter found — try an inch-based diameter (inch catalogs).
        inch_mm = parse_inch_diameter_mm(d)
        if inch_mm is not None:
            diam = inch_mm

    if diam is not None:
        if diam <= 6:
            return "S"
        if diam <= 12:
            return "M"
        if diam <= 25:
            return "L"
        if diam <= 40:
            return "XL"
        return "XL"

    # No measurable dimension: an unspecified boring bar is assumed to be a long,
    # large tool and defaults to XL (other categories defer to the AI pass).
    if pc == "boring_bars":
        return "XL"

    return None


def heuristic_pack_units(prod_cat: str) -> int | None:
    pc = norm(prod_cat)
    if pc == "inserts":
        return 10
    if pc in {
        "drills",
        "mills",
        "reamers",
        "holders",
        "screws",
        "accessories",
        "boring_bars",
        "ppe",
    }:
        return 1
    return None


def heuristic_pack_units_from_text(*parts: str) -> tuple[int | None, str]:
    """Extract a pack size from description text using multilingual patterns (qte/carton/par/boite etc."""
    txt = " ".join(collapse_ws(str(p or "")) for p in parts).lower()
    # Normalize some typographic quirks before regex
    txt = txt.replace("qté", "qte")
    # Insert spaces between letters and digits to catch "qte50" -> "qte 50"
    txt = re.sub(r"([a-z])(\d)", r"\1 \2", txt)
    txt = re.sub(r"(\d)([a-z])", r"\1 \2", txt)

    for pat, label in PACK_HINT_PATTERNS:
        m = re.search(pat, txt)
        if m:
            try:
                q = int(m.group(1))
            except Exception:
                q = 0
            if 1 < q <= 10000:
                return q, label
    return None, ""


def detect_item_family(desc1: str, desc2: str, code: str = "", supplier_code: str = "") -> str:
    """Detect which bulk-consumable family a row belongs to (for the optional bulk-routing feature)."""
    d = norm(
        " ".join([str(desc1 or ""), str(desc2 or ""), str(code or ""), str(supplier_code or "")])
    )

    if any(
        k in d
        for k in [
            "disque",
            "disq ",
            "abrasif",
            "abra ",
            "abranet",
            "beartex",
            "velcro",
            "grain",
            "grains",
            "quart de tour",
            "scotch brite",
            "s brite",
            "multi tr",
            "trizact",
            "lamelle",
        ]
    ):
        return "abrasive_discs"

    if any(
        k in d
        for k in [
            "godet",
            "gobelet",
            "pot ",
            "pots ",
            "couvercle",
            "preparation peint",
            "préparation peint",
            "peinture",
            "tamis",
            "mélange",
            "melange",
        ]
    ):
        return "paint_consumables"

    if any(
        k in d
        for k in [
            "etiquette",
            "étiquette",
            "label",
            "adhesif",
            "adhésif",
            "ruban",
            "bande ptfe",
            "ptfe",
        ]
    ):
        return "tapes_labels"

    if any(
        k in d
        for k in [
            "toile coton",
            "chiffon",
            "essuie",
            "essuyage",
            "wipe",
            "wipes",
            "tampon",
            "tampons",
        ]
    ):
        return "cloth_wipes"

    if any(
        k in d
        for k in [
            "mastic",
            "rtv",
            "sealant",
            "joint silicone",
            "adhesive sealant",
        ]
    ):
        return "adhesives_sealants"

    if any(
        k in d
        for k in [
            "sur chaussure",
            "sur-chaussure",
            "surchaussure",
            "charlotte",
            "combinaison jetable",
            "blouson jetable",
        ]
    ):
        return "disposable_ppe"

    if any(k in d for k in ["cartouche filtre", "filtre p3", "respirator cartridge"]):
        return "respirator_filters"

    return "other"


def merge_classification_results(work, batch_idx, result_map, *, model, timestamp_utc):
    """Merge one batch of AI classification results into ``work`` in place.

    For each row index in ``batch_idx`` this looks up ``result_map[str(idx)]`` and
    applies the AI's product category, size, and pack-unit answers, but only where
    the existing value is weak or empty, so confident heuristic results are never
    overwritten. Rules, in order:

      - Product category: replaced only when the current category is weak or its
        confidence is unknown/low. Listing corrects the answer (a Tools row can't
        become PPE; a PPE row collapses non-PPE answers to ppe unless they are
        accessories/screws/other). The category must be in PC_VALID. On accept it
        also sets source/model/timestamp/evidence, the AI confidence (clamped,
        with 'other' forced low), an optional one-line reason, a ToolClass subclass
        when the heuristic left it blank, and a heuristic pack-unit when the
        current pack source is Default or Heuristic.
      - Size category: filled only when currently blank, from the normalised AI
        size code, with source/model/timestamp.
      - Pack units: when the AI returns 1 or 10 and it differs from the current
        value, it overrides with source/model/timestamp.

    ``model`` and ``timestamp_utc`` are recorded on every field the batch writes.
    The function mutates ``work`` and returns it. It makes no model call and has no
    Streamlit dependency; the caller runs the batches and owns the timestamp.
    """
    for idx in batch_idx:
        rid = str(idx)
        rec = result_map.get(rid)
        if not rec:
            continue

        current_pc = str(work.at[idx, "ProductCategory"]).strip()
        row_listing = str(work.at[idx, "Listing"]).strip().lower() if "Listing" in work.columns else LISTING_TOOLS.lower()
        current_conf = str(work.at[idx, "ProductCategory_Confidence"]).strip()
        if is_weak_category(current_pc) or current_conf in ("unknown", "low"):
            pc = rec.get("product_category", "other")
            if row_listing == LISTING_PPE.lower() and pc not in ("ppe", "other"):
                if pc not in ("accessories", "screws", "other"):
                    pc = "ppe"
            if row_listing == LISTING_TOOLS.lower() and pc == "ppe":
                pc = "other"
            if pc in PC_VALID:
                work.at[idx, "ProductCategory"] = pc
                work.at[idx, "ProductCategory_Source"] = "AI"
                work.at[idx, "ProductCategory_AI_Model"] = model
                work.at[idx, "ProductCategory_AI_TimestampUTC"] = timestamp_utc
                work.at[idx, "ProductCategory_Evidence"] = f"ai:{pc}"
                # Prefer AI-reported confidence over hardcoded heuristic.
                # AI confidence is "high"/"medium"/"low"; defaults to "medium" if absent.
                ai_conf = str(rec.get("confidence", "medium")).strip().lower()
                if ai_conf not in ("high", "medium", "low"):
                    ai_conf = "medium"
                # 'other' is always low-confidence regardless of what AI claims
                if pc == "other":
                    ai_conf = "low"
                work.at[idx, "ProductCategory_Confidence"] = ai_conf
                # Capture the AI's one-sentence rationale for the Technician Review panel
                ai_reason = str(rec.get("reason", "")).strip()
                if ai_reason:
                    work.at[idx, "ProductCategory_Reason"] = ai_reason

                # ToolClass: AI gives us a subclass when it can
                ai_tc = str(rec.get("tool_class", "")).strip().lower()
                if ai_tc and ai_tc in TOOL_CLASS_VALID:
                    # Only fill if heuristic didn't already; AI may disagree on subclass
                    current_tc = str(work.at[idx, "ToolClass"] or "").strip()
                    if not current_tc:
                        work.at[idx, "ToolClass"] = ai_tc
                        work.at[idx, "ToolClass_Source"] = "AI"

                if work.at[idx, "PackUnits_Source"] in ("Default", "Heuristic"):
                    pu_h = heuristic_pack_units(pc)
                    if pu_h is not None and (work.at[idx, "PackUnits"] != float(pu_h)):
                        work.at[idx, "PackUnits"] = float(pu_h)
                        work.at[idx, "PackUnits_Source"] = "Heuristic"

        if str(work.at[idx, "SizeCategory"]).strip() == "":
            sc = _normalize_size_code(rec.get("size_category"))
            work.at[idx, "SizeCategory"] = sc
            work.at[idx, "SizeCategory_Source"] = "AI"
            work.at[idx, "SizeCategory_AI_Model"] = model
            work.at[idx, "SizeCategory_AI_TimestampUTC"] = timestamp_utc

        pu = rec.get("pack_units", None)
        if pu in (1, 10):
            current_pu = int(float(work.at[idx, "PackUnits"]))
            if current_pu != pu:
                work.at[idx, "PackUnits"] = float(pu)
                work.at[idx, "PackUnits_Source"] = "AI"
                work.at[idx, "PackUnits_AI_Model"] = model
                work.at[idx, "PackUnits_AI_TimestampUTC"] = timestamp_utc
    return work


def apply_stored_classifications(
    df,
    lookup,
    *,
    code_col: str = "Code",
    size_col: str = "SizeCategory",
    product_col: str = "ProductCategory",
):
    """Fill size and product category on a frame from a stored lookup, matched
    by code. Returns (frame, hits, misses): the updated copy, the codes that were
    found, and the codes with no stored classification.

    Matching is by code only, so the frame's rows may be in any order and may add
    or drop rows relative to the run the classifications came from. A model is
    never consulted; a missed code is left untouched and reported.

    This is the pure core of the recompute path's classification reuse. It lives
    in the engine because the planning pipeline applies it as one of its stages;
    ``db.classification_reuse`` re-exports it unchanged, so the database module's
    public API is intact and the database read (``classifications_by_code``) stays
    where the database is.
    """
    df = df.copy()
    hits: list[str] = []
    misses = []
    if code_col not in df.columns:
        return df, hits, [""] * len(df)
    for idx in df.index:
        code = str(df.at[idx, code_col])
        rec = lookup.get(code)
        if rec is None:
            misses.append(code)
            continue
        hits.append(code)
        if rec.get("size_category") is not None:
            df.at[idx, size_col] = rec["size_category"]
        if rec.get("product_category") is not None:
            df.at[idx, product_col] = rec["product_category"]
    return df, hits, misses
