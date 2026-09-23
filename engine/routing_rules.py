"""Per-tool-family routing and sizing rules.

Two independent, optional refinements to the planner's defaults:

1. Insert KTC/Kanban threshold override
   The standard KTC/Kanban threshold applies to every
   tool. Optionally, inserts can be held to a separate, usually higher
   threshold: inserts cost far less than a drill or a mill, so a site may
   want them in the vending machine only when they move in high volume.
   When the override is off, the standard threshold runs the whole list.

2. Standard / Special on-machine coverage
   On-machine stock coverage (days) normally applies to every tool. If the
   source list carries a column marking each tool as "standard" or
   "special", coverage can be split: standard tools use the standard
   coverage, special tools use the special coverage. The marker value is
   matched against keywords in French, Polish, German, Spanish, English,
   Slovak, and Slovenian. When the column is not mapped, the single
   coverage value applies to every tool.

All functions are pure so they can be unit-tested in isolation.
"""
from __future__ import annotations

import unicodedata

# ---------------------------------------------------------------------------
# Part 1: insert threshold override
# ---------------------------------------------------------------------------
_INSERT_TOOLCLASS_HINTS = ("insert",)  # turning_insert, milling_insert, ...


def is_insert(product_category: object, tool_class: object = "") -> bool:
    """True when a row is an insert (carbide indexable insert).

    Primary signal is ProductCategory == 'inserts'; ToolClass containing
    'insert' is accepted as a fallback for rows whose category was not set.
    """
    pc = str(product_category or "").strip().lower()
    if pc == "inserts":
        return True
    tc = str(tool_class or "").strip().lower()
    return any(h in tc for h in _INSERT_TOOLCLASS_HINTS)


def ktc_threshold_for(row_is_insert: bool, standard_threshold: float,
                      insert_threshold: float, insert_override_active: bool) -> float:
    """The KTC/Kanban threshold that applies to one row.

    Inserts use `insert_threshold` only when the override is active;
    otherwise every row uses `standard_threshold`.
    """
    if insert_override_active and row_is_insert:
        return float(insert_threshold)
    return float(standard_threshold)


def threshold_for_row(
    *,
    product_category: object,
    tool_class: object,
    standard_threshold: float,
    per_class_thresholds: dict,
    optional_active: bool,
) -> float:
    """The KTC/Kanban threshold (monthly pieces) that applies to one row.

    Generalises the insert override to per-tool-class thresholds:
    - When ``optional_active`` is False, every row uses ``standard_threshold``
      (inserts included) -- the single threshold runs the whole list.
    - When ``optional_active`` is True, a row uses its tool-class threshold from
      ``per_class_thresholds`` if one is set, otherwise ``standard_threshold``.
      Inserts are resolved via :func:`is_insert` so a row whose ProductCategory
      is blank but whose ToolClass says insert still uses the insert threshold.

    ``per_class_thresholds`` is keyed by lower-case ProductCategory
    (e.g. ``{"inserts": 3.0, "drills": 5.0}``).
    """
    if not optional_active:
        return float(standard_threshold)
    if is_insert(product_category, tool_class):
        key = "inserts"
    else:
        key = str(product_category or "").strip().lower()
    val = per_class_thresholds.get(key)
    if val is None or (isinstance(val, float) and val != val):  # None or NaN
        return float(standard_threshold)
    return float(val)


_REGRIND_YES = {"yes", "y", "true", "1", "ja", "x"}


def is_regrind(value: object) -> bool:
    """True when a regrind-flag cell marks the tool as reground/resharpenable.

    The import sheet carries a YES/NO column. ``yes`` (case-insensitive, with a
    few tolerant synonyms) is True; blank, ``no``, ``0``, ``false``, ``nein``
    and anything else are False.
    """
    return str(value or "").strip().lower() in _REGRIND_YES


def parse_system_type(value: object) -> str:
    """Normalise a customer-specified storage-system cell to one of:
    ``"KTC"`` (force a vending machine; never Kanban), ``"KTC_OR_KANBAN"``
    (flexible: the monthly-pieces threshold decides), ``"LOCKER"`` (force a
    locker), or ``""`` (no constraint -> the planner's normal behaviour).

    Recognises German and English spellings. ``locker``/``schrank`` win first;
    a cell naming both KTC and Kanban is the flexible case; KTC alone is the
    forced-vending case; anything else (including blank or Kanban alone, for
    which there is no forced category) yields ``""``.
    """
    s = str(value or "").strip().lower()
    if not s:
        return ""
    if "locker" in s or "schrank" in s:
        return "LOCKER"
    has_ktc = "ktc" in s
    has_kanban = "kanban" in s
    if has_ktc and has_kanban:
        return "KTC_OR_KANBAN"
    if has_ktc:
        return "KTC"
    return ""


# ---------------------------------------------------------------------------
# Part 2: standard / special coverage
# ---------------------------------------------------------------------------
_SPECIAL_CHAR_MAP = str.maketrans({
    "\u0142": "l", "\u0141": "l",   # ł Ł  (Polish)
    "\u00df": "ss",                  # ß    (German)
    "\u0111": "d", "\u0110": "d",   # đ Đ
    "\u00f8": "o", "\u00d8": "o",   # ø Ø
})


def _fold(text: object) -> str:
    """Lower-case and strip accents so 'Spézial', 'ŠTANDARD', 'zwykły' match.

    Only None is treated as empty; numeric 0 / 0.0 must survive (they are a
    valid 'special' flag) rather than being collapsed by a truthiness test.
    """
    s = ("" if text is None else str(text)).strip().lower().translate(_SPECIAL_CHAR_MAP)
    decomposed = unicodedata.normalize("NFKD", s)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# Keyword lists are stored accent-folded (ASCII) and matched as substrings.
# SPECIAL is checked first because several "special" terms in Polish/Slovak/
# Slovenian literally contain the word "standard" (e.g. niestandardowy =
# non-standard) and would otherwise be misread as standard.
SPECIAL_KEYWORDS: tuple[str, ...] = (
    # English
    "special", "custom", "bespoke", "non-standard", "nonstandard",
    "non standard", "made to order", "made-to-order",
    # French
    "speciale", "specifique", "sur mesure", "sur-mesure", "particulier",
    "hors standard", "hors-standard",
    # German
    "sonder", "sonderwerkzeug", "sonderteil", "sonderanfertigung",
    "spezial", "speziell",
    # Spanish
    "especial", "especifico", "a medida", "no estandar",
    # Polish
    "specjalny", "specjalne", "niestandard",  # niestandardowy/-e
    "na zamowienie",
    # Slovak
    "specialny", "specialne", "zvlastny", "nestandard",  # neštandardný/-á
    "na mieru",
    # Slovenian
    "poseben", "posebni", "posebna", "specialni", "specialno", "specialen",
    "po narocilu",
)

STANDARD_KEYWORDS: tuple[str, ...] = (
    # English
    "standard", "std", "normal", "regular",
    # French
    "ordinaire", "courant",
    # German
    "regular", "serie", "serien", "serienteil", "serienwerkzeug",
    "katalog", "katalogartikel", "lagerartikel",
    # Spanish
    "estandar",
    # Polish
    "standardowy", "standardowe", "normalny", "zwykly", "katalogowy",
    # Slovak
    "standardny", "standardna", "normalny", "bezny", "katalogovy",
    # Slovenian
    "standardni", "standarden", "navadni", "obicajni", "serijski",
)

STANDARD = "standard"
SPECIAL = "special"
UNKNOWN = ""

# Exact-match binary encodings, so a site can mark the column with simple
# flags instead of words. These are matched exactly (not as substrings) so
# that, for example, "no" does not match inside "normal" and "1" does not
# match inside "12345". Polarity: 1 / yes / true = standard, 2 / no / false =
# special. Numeric cells like 1.0 / 2.0 are normalised to "1" / "2" first.
# (0 is NOT mapped: the supported numeric scheme is strictly 1 = standard,
# 2 = special. A site using any other code should rewrite the column to 1/2,
# yes/no, or standard/special before uploading.)
STANDARD_EXACT: frozenset[str] = frozenset({"1", "yes", "y", "true"})
SPECIAL_EXACT: frozenset[str] = frozenset({"2", "no", "n", "false"})


def _binary_token(folded: str) -> str:
    """Normalise a folded value to a bare integer token when it is numeric.

    '1.0' -> '1', '0.0' -> '0', '8.0' -> '8'. Non-numeric values pass through
    unchanged so the exact-match sets see 'yes'/'no'/etc. as-is.
    """
    try:
        f = float(folded)
    except (TypeError, ValueError):
        return folded
    if f == int(f):
        return str(int(f))
    return folded


def classify_standard_special(value: object) -> str:
    """Classify a marker cell as 'standard', 'special', or '' (unknown).

    Recognises three encodings: the words standard/special (in the seven
    supported languages, accent-insensitive), the binary flags 1/0, and
    yes/no. Binary flags are matched exactly; words are matched as
    substrings with SPECIAL tested first so non-standard variants that
    contain 'standard' are not mis-classified.
    """
    folded = _fold(value)
    if not folded:
        return UNKNOWN
    token = _binary_token(folded)
    if token in STANDARD_EXACT:
        return STANDARD
    if token in SPECIAL_EXACT:
        return SPECIAL
    if any(k in folded for k in SPECIAL_KEYWORDS):
        return SPECIAL
    if any(k in folded for k in STANDARD_KEYWORDS):
        return STANDARD
    return UNKNOWN


def coverage_days_for(classification: str, standard_days: float,
                      special_days: float, split_active: bool) -> float:
    """On-machine coverage (days) for one row.

    With the split active, only rows classified 'special' use
    `special_days`; 'standard' and unknown rows use `standard_days`.
    With the split inactive, every row uses `standard_days`.
    """
    if split_active and classification == SPECIAL:
        return float(special_days)
    return float(standard_days)
