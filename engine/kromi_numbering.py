"""KROMI article number assignment.

Generates 12-digit, all-numeric KROMI article numbers for a tool catalog.
The numbering logic is universal across all customers. The only value
that changes per customer is the KTC-ID, which forms the first three
digits of every number. Everything else (the code matrix, dimension
extraction, variant counter, trailing zero) is identical for everyone.

Number anatomy
--------------
KTC articles (12 chars) -- simple running counter, no dimension/description:
    [KTC-ID : 3] [fixed "10" : 2] [running counter : 4] [trailing 000 : 3]
Kanban (and unclassified) non-holder articles (12 chars):
    [KTC-ID : 3] [Kromi code : 2] [dimension : 4] [variant : 2] [trailing 0 : 1]
Kanban (and unclassified) holder articles (12 chars):
    [KTC-ID : 3] [holder code 20008 : 5] [dimension : 1] [variant : 2] [trailing 0 : 1]

KTC numbers carry the fixed code "10" at positions 3-4, which the class matrix
never emits, so a KTC number can never collide with a Kanban number. The KTC
counter is 1-based in result order and ignores tool class and dimension.

Invariants enforced for every generated number (verified by tests)
------------------------------------------------------------------
    1. exactly 12 characters
    2. all characters are digits 0-9 (no letters)
    3. ends in 0
    4. unique within the catalog

The variant field is a zero-padded running counter within each
(KTC-ID, Kromi code, dimension) group, so two physically different
articles that share the same dimension fingerprint still receive
distinct numbers. The trailing 0 is fixed by requirement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

# ---------------------------------------------------------------------------
# Universal ToolClass -> Kromi code matrix (positions 4-5, or 5-digit holder code)
# ---------------------------------------------------------------------------
# Codes follow the tooling structure logic:
#   drill 13 | step drill 14 | thread tools 15 | milling cutter 16 |
#   reamer 11 | counter 17 | insert 12 | holder 20008 | accessories 20 |
#   misc/other 19
KROMI_CODE_MATRIX: dict[str, str] = {
    # --- drills -> 13 ---
    "solid_carbide_drill": "13", "hss_drill": "13", "spiral_drill": "13",
    "nc_drill": "13", "pilot_drill": "13", "center_drill": "13",
    "core_drill": "13", "deep_hole_drill": "13", "indexable_drill": "13",
    "center_point": "13",
    # --- step drills -> 14 ---
    "step_drill": "14",
    # --- milling cutters -> 16 ---
    "solid_end_mill": "16", "face_mill": "16", "burr": "16",
    "radius_mill": "16", "ball_track_mill": "16", "disc_mill": "16",
    "form_mill": "16", "shell_mill": "16", "t_slot_mill": "16",
    "gear_cutter": "16", "saw_blade": "16",
    # --- thread tools -> 15 ---
    "tap": "15", "tap_carbide": "15", "tap_hss": "15",
    "thread_mill": "15", "thread_former": "15", "thread_roller": "15",
    "thread_hole_cutter": "15", "threading_die": "15", "threading_insert": "15",
    # --- reamers -> 11 ---
    "reamer": "11", "multi_stage_reamer": "11", "honing_reamer": "11",
    "reaming_insert": "11",
    # --- counters -> 17 ---
    "countersink": "17", "back_countersink": "17", "flat_countersink": "17",
    "step_countersink": "17",
    # --- inserts -> 12 ---
    "turning_insert": "12", "milling_insert": "12", "drilling_insert": "12",
    "grooving_insert": "12",
    # --- holders -> 20008 (5-digit special case) ---
    "hsk_holder": "20008", "abs_holder": "20008", "bmt_holder": "20008",
    "capto_holder": "20008", "km_holder": "20008", "masbt_holder": "20008",
    "mk_holder": "20008", "sk_holder": "20008", "vdi_holder": "20008",
    "varia_holder": "20008", "varilock_holder": "20008", "collet": "20008",
    "turning_holder": "20008", "milling_holder": "20008",
    "boring_holder": "20008", "drilling_holder": "20008",
    "grooving_holder": "20008", "reaming_holder": "20008",
    # --- accessories -> 20 ---
    "accessory": "20", "screw": "20", "wrench": "20",
    # --- misc / other -> 19 ---
    "abrasive_belt": "19", "abrasive_disc": "19", "cutting_disc": "19",
    "grinding_wheel": "19", "grinding_pin": "19", "flap_wheel": "19",
    "brush": "19", "boring_bar": "19", "broach": "19",
    "deburring_fork": "19", "dressing_tool": "19", "form_steel": "19",
    "honing_stone": "19", "punch_die": "19", "ppe": "19",
    "welding_consumable": "19", "other": "19",
}

DEFAULT_CODE = "19"        # fallback for empty/unmapped ToolClass (misc/other)
HOLDER_CODE = "20008"      # 5-digit holder code
TOTAL_LENGTH = 12
TRAILING = "0"             # required final digit

# --- KTC simple-counter scheme (KTC articles only) --------------------------
# A KTC article number is [KTC-ID:3]["10"][running counter:4]["000"]. The
# counter is a 1-based index in result order; it does NOT encode tool class or
# dimension. Kanban articles keep the dimension/description scheme above. The
# two never collide: the class matrix never emits "10", so positions 3-4 always
# differ between a KTC number and a Kanban number.
KTC_FIXED = "10"           # fixed segment after the KTC-ID for KTC articles
KTC_COUNTER_DIGITS = 4     # width of the KTC running counter (0001..9999)
KTC_TRAILING = "000"       # trailing zeros (keeps the required final 0)
KTC_MAX = 10 ** KTC_COUNTER_DIGITS - 1  # 9999


# Keywords that force a step-drill classification regardless of ToolClass,
# in case the upstream classifier missed it.
_STEP_DRILL_KEYWORDS = ("stufenbohrer", "stufenbohr", "stufenfräser", "step drill")


@dataclass(frozen=True)
class KromiRuleset:
    """A customer-specific KROMI numbering scheme.

    Attributes
    ----------
    name:
        Human-readable ruleset name (e.g. "KROMI").
    code_matrix:
        Maps a ToolClass string to its Kromi code. Codes are normally
        2 digits; the holder code is 5 digits.
    holder_code:
        The 5-digit code that triggers the holder anatomy.
    dim_digits_normal:
        How many dimension digits a non-holder number carries.
    dim_digits_holder:
        How many dimension digits a holder number carries.
    variant_digits:
        Width of the running variant counter (zero-padded).
    default_code:
        Code used when the ToolClass is empty or not in the matrix.
    """
    name: str
    code_matrix: dict[str, str]
    holder_code: str = HOLDER_CODE
    dim_digits_normal: int = 4
    dim_digits_holder: int = 1
    variant_digits: int = 2
    default_code: str = DEFAULT_CODE


# The single, universal ruleset. KTC-ID is supplied per call.
KROMI_RULESET = KromiRuleset(name="KROMI", code_matrix=KROMI_CODE_MATRIX)


def _digits_only(text: object) -> str:
    """Return the digit characters from text, in order of appearance."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    return "".join(re.findall(r"\d", str(text)))


def _extract_dim(description: object, n: int) -> str:
    """First n digit characters of description, zero-padded to width n."""
    digits = _digits_only(description)[:n]
    return digits.ljust(n, "0").zfill(n)


def kromi_code_for(tool_class: object, description: object,
                   ruleset: KromiRuleset = KROMI_RULESET) -> tuple[str, bool]:
    """Resolve the Kromi code for one article.

    Returns (code, is_holder). The description is checked for step-drill
    keywords first so a misclassified step drill still gets code 14.
    """
    desc_l = str(description).lower() if description is not None else ""
    if any(k in desc_l for k in _STEP_DRILL_KEYWORDS):
        return ("14", False)

    tc = str(tool_class or "").strip().lower()
    code = ruleset.code_matrix.get(tc, ruleset.default_code)
    return (code, code == ruleset.holder_code)


def build_kromi_number(ktc_id: str, tool_class: object, description: object,
                       variant: int, ruleset: KromiRuleset = KROMI_RULESET) -> str:
    """Build one 12-digit KROMI number (without uniqueness bookkeeping).

    `variant` is the 0-based running index within the article's
    (ktc_id, code, dimension) group. Raises ValueError if the variant
    exceeds what the ruleset's variant field can hold, or if the result
    is not a valid 12-digit all-numeric number ending in 0.
    """
    if not (isinstance(ktc_id, str) and ktc_id.isdigit() and len(ktc_id) == 3):
        raise ValueError(f"KTC-ID must be exactly 3 digits, got {ktc_id!r}")

    code, is_holder = kromi_code_for(tool_class, description, ruleset)
    dim_n = ruleset.dim_digits_holder if is_holder else ruleset.dim_digits_normal
    dim = _extract_dim(description, dim_n)

    variant_max = 10 ** ruleset.variant_digits - 1
    if variant > variant_max:
        raise ValueError(
            f"Variant {variant} exceeds the {ruleset.variant_digits}-digit "
            f"field (max {variant_max}) for ruleset {ruleset.name}. "
            f"Group is too large for the current number format."
        )
    variant_str = str(variant).zfill(ruleset.variant_digits)

    number = ktc_id + code + dim + variant_str + TRAILING

    # Enforce invariants
    if len(number) != TOTAL_LENGTH:
        raise ValueError(
            f"Generated number {number!r} is {len(number)} chars, "
            f"expected {TOTAL_LENGTH}. code={code} dim={dim} variant={variant_str}"
        )
    if not number.isdigit():
        raise ValueError(f"Generated number {number!r} is not all-numeric")
    if not number.endswith(TRAILING):
        raise ValueError(f"Generated number {number!r} does not end in {TRAILING}")
    return number


def build_ktc_number(ktc_id: str, counter: int) -> str:
    """Build one 12-digit KTC article number.

    Anatomy: [KTC-ID:3]["10"][counter:4]["000"]. `counter` is the 1-based
    running index of the article among KTC rows, in result order; it does not
    encode tool class or dimension. Raises ValueError on a bad KTC-ID or a
    counter outside 1..9999 (the 4-digit field cannot represent more).
    """
    if not (isinstance(ktc_id, str) and ktc_id.isdigit() and len(ktc_id) == 3):
        raise ValueError(f"KTC-ID must be exactly 3 digits, got {ktc_id!r}")
    if isinstance(counter, bool) or not isinstance(counter, int) \
            or not (1 <= counter <= KTC_MAX):
        raise ValueError(
            f"KTC counter {counter!r} is out of range 1..{KTC_MAX}; the "
            f"{KTC_COUNTER_DIGITS}-digit field cannot represent it."
        )
    number = ktc_id + KTC_FIXED + str(counter).zfill(KTC_COUNTER_DIGITS) + KTC_TRAILING

    if len(number) != TOTAL_LENGTH:
        raise ValueError(
            f"Generated KTC number {number!r} is {len(number)} chars, "
            f"expected {TOTAL_LENGTH}."
        )
    if not number.isdigit():
        raise ValueError(f"Generated KTC number {number!r} is not all-numeric")
    if not number.endswith(TRAILING):
        raise ValueError(f"Generated KTC number {number!r} does not end in {TRAILING}")
    return number


def assign_kromi_numbers(df: pd.DataFrame, ktc_id: str,
                         tool_class_col: str = "ToolClass",
                         description_col: str = "Description",
                         output_col: str = "Kromi_Art_No",
                         ruleset: KromiRuleset = KROMI_RULESET) -> pd.DataFrame:
    """Return a copy of df with a KROMI number column added.

    The number is built per the ruleset; the variant counter guarantees
    uniqueness across articles that share the same (ktc_id, code,
    dimension) fingerprint. Input columns are not modified.
    """
    out = df.copy()
    if len(out) == 0:
        out[output_col] = pd.Series(dtype="object")
        return out

    # First pass: resolve code + dimension to form the group key (everything
    # except the variant and the trailing zero).
    base_keys: list[str] = []
    for _, row in out.iterrows():
        tc = row.get(tool_class_col)
        desc = row.get(description_col)
        code, is_holder = kromi_code_for(tc, desc, ruleset)
        dim_n = ruleset.dim_digits_holder if is_holder else ruleset.dim_digits_normal
        dim = _extract_dim(desc, dim_n)
        base_keys.append(ktc_id + code + dim)

    out["_kromi_base"] = base_keys
    out["_kromi_variant"] = out.groupby("_kromi_base").cumcount()

    numbers: list[str] = []
    for (_, row), variant in zip(out.iterrows(), out["_kromi_variant"]):
        numbers.append(
            build_kromi_number(ktc_id, row.get(tool_class_col),
                               row.get(description_col), int(variant), ruleset)
        )
    out[output_col] = numbers
    out = out.drop(columns=["_kromi_base", "_kromi_variant"])
    return out


def assign_split_numbers(df: pd.DataFrame, ktc_id: str,
                         tool_class_col: str = "ToolClass",
                         description_col: str = "Description",
                         output_col: str = "Kromi_Art_No",
                         ruleset: KromiRuleset = KROMI_RULESET,
                         system_col: str = "System") -> pd.DataFrame:
    """Return a copy of df with output_col added, branching on `system_col`.

    KTC rows (System == "KTC") get the simple running-counter scheme via
    build_ktc_number, numbered 1..N in the order they appear. Every other row
    (Kanban or blank) keeps the dimension/description scheme via
    assign_kromi_numbers. The two schemes never collide: a KTC number carries
    the fixed code "10" at positions 3-4, which the class matrix never emits.
    Input columns are not modified. Raises ValueError if the legacy scheme
    overflows its variant field or the KTC counter exceeds 9999.
    """
    out = df.copy()
    if len(out) == 0:
        out[output_col] = pd.Series(dtype="object")
        return out

    if system_col in out.columns:
        system = out[system_col].astype(str).str.strip()
    else:
        system = pd.Series([""] * len(out), index=out.index)
    is_ktc = system == "KTC"

    numbers = pd.Series([pd.NA] * len(out), index=out.index, dtype="object")

    # KTC rows: running counter, 1-based, in result order.
    for counter, idx in enumerate(out.loc[is_ktc].index, start=1):
        numbers.loc[idx] = build_ktc_number(ktc_id, counter)

    # Everything else: the dimension/description (legacy) scheme.
    rest = out.loc[~is_ktc]
    if len(rest) > 0:
        numbered = assign_kromi_numbers(
            rest, ktc_id=ktc_id, tool_class_col=tool_class_col,
            description_col=description_col, output_col=output_col,
            ruleset=ruleset,
        )
        numbers.loc[numbered.index] = numbered[output_col]

    out[output_col] = numbers
    return out


def derive_system_column(df: pd.DataFrame,
                         system_category_col: str = "SystemCategory",
                         cabinet_type_col: str = "CabinetType",
                         output_col: str = "System") -> pd.DataFrame:
    """Return a copy of df with a System column = 'KTC' or 'Kanban'.

    Prefers the existing SystemCategory field (already 'KTC'/'Kanban').
    Falls back to deriving from CabinetType: any vending cabinet
    (Helix/Carousel/Locker A/B/C) is KTC; Kanban is Kanban; anything
    else is left blank.
    """
    out = df.copy()
    vending = {"Helix", "Carousel", "Locker A", "Locker B", "Locker C"}

    if system_category_col in out.columns:
        out[output_col] = out[system_category_col].apply(
            lambda v: "KTC" if str(v).strip() == "KTC"
            else ("Kanban" if str(v).strip() == "Kanban" else "")
        )
    elif cabinet_type_col in out.columns:
        def _map(ct: object) -> str:
            c = str(ct).strip()
            if c in vending:
                return "KTC"
            if c == "Kanban":
                return "Kanban"
            return ""
        out[output_col] = out[cabinet_type_col].apply(_map)
    else:
        out[output_col] = ""
    return out


def resolve_article_system(df: pd.DataFrame, default_system: str) -> pd.DataFrame:
    """Resolve each row's property system for the numbering-only mode (v34.44).

    No plan exists in that mode to decide KTC vs Kanban, so a mapped
    ``SystemTyp`` column is authoritative in BOTH directions (v34.45): a KTC
    or Locker marker forces "KTC" (both mean the article lives in a vending
    cabinet and therefore gets the predecessor/successor pair), and a cell
    naming Kanban alone forces "Kanban". Only rows the column cannot answer -
    a flexible "KTC or Kanban", a blank, or an unrecognised value - fall back
    to the caller's ``default_system`` ("KTC" or "Kanban"). Marker precedence
    matches the planner's ``parse_system_type`` (Locker beats a Kanban word in
    the same cell). Returns a copy with ``SystemCategory`` set; never mutates
    ``df``.
    """
    from .routing_rules import parse_system_type

    out = df.copy()
    default = "KTC" if str(default_system or "").strip().upper() == "KTC" else "Kanban"
    system = pd.Series(default, index=out.index, dtype=object)
    if "SystemTyp" in out.columns:
        parsed = out["SystemTyp"].map(parse_system_type)
        system = system.where(~parsed.isin(("KTC", "LOCKER")), "KTC")
        # parse_system_type returns "" for a Kanban-alone cell (the planner
        # has no forced-Kanban category), so detect that case here: the cell
        # answered, and in this mode its answer must win over the default.
        raw = out["SystemTyp"].map(lambda v: str(v).strip().lower()
                                   if v is not None and v == v else "")
        kanban_alone = (parsed == "") & raw.str.contains("kanban", regex=False)
        system = system.where(~kanban_alone, "Kanban")
    out["SystemCategory"] = system
    return out


#: Column contract of the Article setup sheet (v34.43), in display order.
ARTICLE_SETUP_COLUMNS: tuple[str, ...] = (
    "Kromi_Art_No", "Customer article No", "Description", "System",
    "Property", "Replaces", "Replaced by", "PackUnits",
)

_PROPERTY_CUSTOMER = "Customer property"
_PROPERTY_KROMI = "KROMI property"


def build_article_setup(df: pd.DataFrame, ktc_id: str,
                        tool_class_col: str = "ToolClass",
                        description_col_candidates: tuple[str, ...] = ("Description", "Description_2"),
                        ruleset: KromiRuleset = KROMI_RULESET) -> pd.DataFrame | None:
    """The Article setup sheet (v34.43): every unique KTC article twice, every
    unique Kanban article once.

    A KTC article receives two numbers describing its property lifecycle:

    * the **predecessor** (customer property) keeps today's fixed-"10" counter
      scheme, byte-identical to the number the Result sheet shows for that
      article's first row (numbering runs over the full frame exactly as
      :func:`assign_split_numbers` does, so the two sheets always agree; in a
      multi-supply-point Replicate run the sheet keeps the first occurrence's
      number, which can leave gaps in the visible counter);
    * the **successor** (KROMI property) follows the dimension/description
      scheme Kanban already uses, and its variant CONTINUES the (KTC-ID, code,
      dimension) group's counter after every dimension-scheme number the full
      frame consumed — one shared pool, so a successor can never collide with
      a Kanban number on this sheet or on the Result sheet.

    Kanban rows keep their existing Result-sheet number and appear once. The
    linkage travels in ``Replaces`` / ``Replaced by`` (the machine's
    ersetzt/ersetztDurch fields): the predecessor names its successor, the
    successor names its predecessor, Kanban rows leave both blank.

    Articles are unique by (Listing, Code), first occurrence in row order.
    Returns ``None`` when the prerequisites are missing (invalid KTC-ID, no
    ToolClass column, no description column) so the caller can omit the sheet;
    a variant-field overflow raises ``ValueError`` like the underlying number
    builder. Never mutates ``df``.
    """
    ktc = str(ktc_id or "").strip()
    if not (ktc.isdigit() and len(ktc) == 3):
        return None
    if tool_class_col not in df.columns:
        return None
    desc_col = next((c for c in description_col_candidates if c in df.columns), None)
    if desc_col is None:
        return None

    out = derive_system_column(df)
    if len(out) == 0:
        return pd.DataFrame(columns=list(ARTICLE_SETUP_COLUMNS))

    # Full-frame Result-sheet numbering: the source of every predecessor and
    # every Kanban number, and of the dimension-scheme variant occupancy.
    numbered = assign_split_numbers(
        out, ktc_id=ktc, tool_class_col=tool_class_col,
        description_col=desc_col, ruleset=ruleset,
    )

    def _base_key(row) -> str:
        code, is_holder = kromi_code_for(row.get(tool_class_col),
                                         row.get(desc_col), ruleset)
        dim_n = ruleset.dim_digits_holder if is_holder else ruleset.dim_digits_normal
        return ktc + code + _extract_dim(row.get(desc_col), dim_n)

    # Variant occupancy across the WHOLE frame (per-SP duplicates included):
    # successors start after the highest variant any Result-sheet number used.
    counts: dict[str, int] = {}
    non_ktc = numbered[numbered["System"] != "KTC"]
    for _, row in non_ktc.iterrows():
        base = _base_key(row)
        counts[base] = counts.get(base, 0) + 1

    dedup_keys = [c for c in ("Listing", "Code") if c in numbered.columns]
    unique = numbered.drop_duplicates(subset=dedup_keys, keep="first")

    rows: list[dict] = []
    for _, row in unique.iterrows():
        common = {
            "Customer article No": str(row.get("Code", "")),
            "Description": str(row.get(desc_col, "")),
            "System": str(row.get("System", "")),
            "PackUnits": row.get("PackUnits", ""),
        }
        number = str(row.get("Kromi_Art_No", ""))
        if str(row.get("System", "")) == "KTC":
            base = _base_key(row)
            variant = counts.get(base, 0)
            counts[base] = variant + 1
            successor = build_kromi_number(
                ktc, row.get(tool_class_col), row.get(desc_col), variant, ruleset,
            )
            rows.append({**common, "Property": _PROPERTY_CUSTOMER,
                         "Kromi_Art_No": number,
                         "Replaces": "", "Replaced by": successor})
            rows.append({**common, "Property": _PROPERTY_KROMI,
                         "Kromi_Art_No": successor,
                         "Replaces": number, "Replaced by": ""})
        else:
            # Kanban stock is invoiced to the customer at delivery, so it is
            # the customer's property from day one (v34.45; only the KTC
            # successor is KROMI property).
            rows.append({**common, "Property": _PROPERTY_CUSTOMER,
                         "Kromi_Art_No": number,
                         "Replaces": "", "Replaced by": ""})
    return pd.DataFrame(rows, columns=list(ARTICLE_SETUP_COLUMNS))


def order_article_setup(setup_df: pd.DataFrame,
                        code_order: "list[str] | None") -> pd.DataFrame:
    """Reorder the Article setup sheet to master-file order (v34.46).

    ``code_order`` is the source file's article codes in first-occurrence
    order (captured before the planning-base dedup sorts the frame). The
    sheet then lists one row per article in that order - the KTC predecessor
    or the Kanban number - and appends the duplicate numbers (the KTC
    successors, the only KROMI-property rows) after the last non-duplicate
    row, again in master-file order. Codes missing from ``code_order`` keep
    their relative order at the end of their block. With no order list the
    frame is returned unchanged. Never mutates ``setup_df``.
    """
    if not code_order or len(setup_df) == 0:
        return setup_df
    pos: dict[str, int] = {}
    for i, c in enumerate(code_order):
        pos.setdefault(str(c), i)
    unknown = len(pos)
    key = setup_df["Customer article No"].map(lambda c: pos.get(str(c), unknown))
    succ = (setup_df["Property"] == _PROPERTY_KROMI).astype(int)
    out = (setup_df.assign(_ord=key, _succ=succ)
           .sort_values(["_succ", "_ord"], kind="mergesort")
           .drop(columns=["_ord", "_succ"])
           .reset_index(drop=True))
    return out


def numbering_omission_reason(df: pd.DataFrame, ktc_id: str,
                              tool_class_col: str = "ToolClass",
                              description_col_candidates: tuple[str, ...] = ("Description", "Description_2"),
                              ruleset: KromiRuleset = KROMI_RULESET) -> str | None:
    """Why :func:`augment_for_export` would leave Kromi_Art_No out (v34.48).

    Returns ``None`` when numbering works, otherwise a short plain-language
    reason (invalid KTC-ID, missing ToolClass or description column, or the
    number-field overflow message). Used to report the omission with the
    export instead of dropping the numbers silently. Never mutates ``df``.
    """
    ktc = str(ktc_id or "").strip()
    if not ktc:
        return "no KTC-ID was entered (it must be exactly 3 digits)"
    if not (ktc.isdigit() and len(ktc) == 3):
        return f"the KTC-ID '{ktc}' is not exactly 3 digits"
    if tool_class_col not in df.columns:
        return f"the {tool_class_col} column is missing"
    desc_col = next((c for c in description_col_candidates if c in df.columns), None)
    if desc_col is None:
        return "no description column is mapped"
    try:
        assign_split_numbers(derive_system_column(df), ktc_id=ktc,
                             tool_class_col=tool_class_col,
                             description_col=desc_col, ruleset=ruleset)
    except ValueError as exc:
        return str(exc).strip().rstrip(".")
    return None


def augment_for_export(df: pd.DataFrame, ktc_id: str,
                       tool_class_col: str = "ToolClass",
                       description_col_candidates: tuple[str, ...] = ("Description", "Description_2"),
                       ruleset: KromiRuleset = KROMI_RULESET) -> pd.DataFrame:
    """Return a copy of df with System and (when possible) Kromi_Art_No added.

    This is the single code path used both by the live Result export and by
    the archived-run download, so the two always agree. The System column is
    always added. The Kromi_Art_No column is added only when the KTC-ID is a
    valid 3-digit string, a ToolClass column is present, and at least one of
    the candidate description columns exists. KTC rows are numbered with the
    simple running-counter scheme (no dimension/description); every other row
    keeps the dimension/description scheme. If generation raises (e.g. a Kanban
    dimension group too large for the variant field), the System column is
    still returned and Kromi_Art_No is omitted.
    """
    out = derive_system_column(df)
    ktc = str(ktc_id or "").strip()
    if not (ktc.isdigit() and len(ktc) == 3):
        return out
    if tool_class_col not in out.columns:
        return out
    desc_col = next((c for c in description_col_candidates if c in out.columns), None)
    if desc_col is None:
        return out
    try:
        out = assign_split_numbers(out, ktc_id=ktc,
                                   tool_class_col=tool_class_col,
                                   description_col=desc_col, ruleset=ruleset)
    except ValueError:
        pass
    return out
