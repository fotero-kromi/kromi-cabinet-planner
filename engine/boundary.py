"""Deterministic boundary heuristics between preprocessing and the plan.

The page runs these passes on the planning frame after preprocessing and
column scaffolding, in this order: the ProductCategory normalize-and-classify
step, the ToolClass derivation, the insert override, the SizeCategory and
PackUnits provided/heuristic steps with the insert pack safety net, and, after
the AI stage, the final insert safety pass with the default size fill. Both
functions are pure: they copy the input frame, never touch a clock, a session,
or the environment, and are deterministic in their inputs, which is what lets
the page wrap them in a content-addressed cache. Bodies were moved verbatim
from the page; the two knobs the passes read (the pack-hint toggle and the
insert default pack size) travel as explicit parameters.
"""

from __future__ import annotations

import pandas as pd

from engine.classification import (
    classify_with_evidence,
    derive_tool_class,
    heuristic_pack_units,
    heuristic_pack_units_from_text,
    heuristic_size_category,
    is_weak_category,
    looks_like_insert_code,
    normalize_product_category,
)
from engine.constants import (
    INSERT_KEYWORDS,
    LISTING_PPE,
    LISTING_TOOLS,
    PC_VALID,
    SIZE_VALID,
    TOOL_CLASS_VALID,
)


_STEP_DRILL_WORDS = ("stufenbohrer", "step drill")


def _is_step_drill_word(raw: object) -> bool:
    """True when a provided category text names a step drill (v34.56)."""
    text = str(raw or "").strip().lower()
    return any(w in text for w in _STEP_DRILL_WORDS)


def apply_pre_ai_heuristics(df: pd.DataFrame, *, enable_pack_hint_extraction: bool,
                            insert_default_pack_units: float) -> pd.DataFrame:
    """Steps A through D of the page's boundary, verbatim, on a copy."""
    work = df.copy()
    # STEP A) ProductCategory
    pc_raw = work["ProductCategory"].astype(str).str.strip()
    pc_norm = pc_raw.apply(normalize_product_category)

    provided_pc_strong = pc_raw.ne("") & (~pc_norm.apply(is_weak_category))
    work["ProductCategory"] = pc_norm

    work.loc[provided_pc_strong, "ProductCategory_Source"] = "Provided"
    work.loc[~provided_pc_strong, "ProductCategory"] = ""
    work.loc[~provided_pc_strong, "ProductCategory_Source"] = "Default"

    pc_missing = work["ProductCategory"].astype(str).str.strip().eq("")
    if pc_missing.any():
        for idx in work[pc_missing].index:
            row = work.loc[idx]
            cat, evidence = classify_with_evidence(
                desc1=str(row.get("Description", "")),
                desc2=str(row.get("Description_2", "")),
                code=str(row.get("Code", "")),
                supplier_code=str(row.get("SupplierCode", "")),
                listing=str(row.get("Listing", LISTING_TOOLS)),
            )
            if cat and cat in PC_VALID and cat != "other":
                work.at[idx, "ProductCategory"] = cat
                work.at[idx, "ProductCategory_Source"] = "Heuristic"
                work.at[idx, "ProductCategory_Evidence"] = evidence
                work.at[idx, "ProductCategory_Confidence"] = "high"
            # else: leave blank, AI will be asked

    # Mark still-blank rows explicitly so we know where "no heuristic answer" came from
    pc_missing = work["ProductCategory"].astype(str).str.strip().eq("")
    work.loc[pc_missing, "ProductCategory_Evidence"] = "no-match"
    work.loc[pc_missing, "ProductCategory_Confidence"] = "unknown"

    # Mark Provided rows with appropriate evidence (they came from the source data)
    provided_mask = work["ProductCategory_Source"] == "Provided"
    work.loc[provided_mask & (work["ProductCategory_Evidence"] == ""), "ProductCategory_Evidence"] = "provided"
    work.loc[provided_mask & (work["ProductCategory_Confidence"] == ""), "ProductCategory_Confidence"] = "high"

    # Safety net: tag any remaining blank ProductCategory as 'other' before AI fallback
    # but only so downstream code can compare; AI will still be called on these.
    pc_still_missing = work["ProductCategory"].astype(str).str.strip().eq("")
    if pc_still_missing.any():
        work.loc[pc_still_missing, "ProductCategory"] = "other"
        work.loc[pc_still_missing, "ProductCategory_Source"] = "Default"

    # STEP A.5) ToolClass — derive from classification evidence + supplier.
    # Heuristic rows get a specific tool_class when the evidence is detailed
    # enough (iso:CNMG, supplier_pattern:seco:WS_grade, shorthand:FO, etc.).
    # Rows that fall through to AI will get tool_class from the AI response.
    for idx in work.index:
        src = work.at[idx, "ProductCategory_Source"]
        if src not in ("Heuristic", "Provided"):
            continue
        evidence = str(work.at[idx, "ProductCategory_Evidence"] or "")
        pc = str(work.at[idx, "ProductCategory"] or "")
        tc = derive_tool_class(
            evidence=evidence,
            code=str(work.at[idx, "Code"] or ""),
            supplier_field=str(work.at[idx, "SupplierCode"] or ""),
            product_category=pc,
        )
        # v34.56: a provided structure word naming a step drill (KDS
        # Bezeichnung 1 "Stufenbohrer ...") sets the step-drill class; the
        # category alone only says "drills" (KROMI code 13 instead of 14).
        if src == "Provided" and pc == "drills" and _is_step_drill_word(pc_raw.at[idx]):
            tc = "step_drill"
        if tc and tc in TOOL_CLASS_VALID:
            work.at[idx, "ToolClass"] = tc
            work.at[idx, "ToolClass_Source"] = src

    # Insert override
    for idx, row in work.iterrows():
        if str(row.get("Listing", LISTING_TOOLS)).strip().lower() == LISTING_PPE.lower():
            continue
        combined = " ".join([
            str(row.get("ProductCategory", "")),
            str(row.get("Description", "")),
            str(row.get("Description_2", "")),
            str(row.get("Code", "")),
        ]).lower()

        # Strong insert evidence: explicit keyword OR canonical ISO code
        strong_insert = False
        for kw in INSERT_KEYWORDS:
            if kw in combined:
                strong_insert = True
                break
        if not strong_insert:
            if looks_like_insert_code(" ".join([
                str(row.get("Description", "")),
                str(row.get("Description_2", "")),
                str(row.get("Code", "")),
                str(row.get("SupplierCode", "")),
            ])):
                strong_insert = True

        if strong_insert:
            if str(work.at[idx, "ProductCategory"]).strip().lower() != "inserts":
                work.at[idx, "ProductCategory"] = "inserts"
                if work.at[idx, "ProductCategory_Source"] in ("", "Default"):
                    work.at[idx, "ProductCategory_Source"] = "Heuristic"
                    work.at[idx, "ProductCategory_Evidence"] = "insert-override"
                    work.at[idx, "ProductCategory_Confidence"] = "high"

    # STEP B) SizeCategory
    size_raw = work["SizeCategory"].astype(str).str.strip()
    provided_size = size_raw.ne("") & size_raw.str.upper().isin(SIZE_VALID)

    work.loc[provided_size, "SizeCategory"] = work.loc[provided_size, "SizeCategory"].astype(str).str.upper()
    work.loc[~provided_size, "SizeCategory"] = ""

    work.loc[provided_size, "SizeCategory_Source"] = "Provided"
    work.loc[~provided_size, "SizeCategory_Source"] = "Default"

    # STEP C) PackUnits
    if "PackUnits_Evidence" not in work.columns:
        work["PackUnits_Evidence"] = ""
    if "PackUnits_Confidence" not in work.columns:
        work["PackUnits_Confidence"] = ""

    pack_valid = (~work["PackUnits"].isna()) & (work["PackUnits"] > 0)
    work.loc[pack_valid, "PackUnits_Source"] = "Provided"
    work.loc[pack_valid, "PackUnits_Evidence"] = "provided"
    work.loc[pack_valid, "PackUnits_Confidence"] = "high"
    work.loc[~pack_valid, "PackUnits_Source"] = "Default"

    pack_missing = work["PackUnits"].isna() | (work["PackUnits"] <= 0)
    if pack_missing.any():
        for idx in work[pack_missing].index:
            row = work.loc[idx]

            # first try to extract a pack size from the description text
            # when enabled. This catches "qte 50", "carton de 60", etc.
            if enable_pack_hint_extraction:
                pu_text, pu_ev = heuristic_pack_units_from_text(
                    row.get("Description", ""),
                    row.get("Description_2", ""),
                    row.get("Code", ""),
                    row.get("SupplierCode", ""),
                )
                if pu_text is not None:
                    work.at[idx, "PackUnits"] = float(pu_text)
                    work.at[idx, "PackUnits_Source"] = "Heuristic"
                    work.at[idx, "PackUnits_Evidence"] = f"text:{pu_ev}"
                    work.at[idx, "PackUnits_Confidence"] = "high"
                    continue

            # Fall back to category default
            pc = str(work.at[idx, "ProductCategory"])
            pu = heuristic_pack_units(pc)
            if pu is not None:
                work.at[idx, "PackUnits"] = float(pu)
                work.at[idx, "PackUnits_Source"] = "Heuristic"
                work.at[idx, "PackUnits_Evidence"] = f"category:{pc}"
                work.at[idx, "PackUnits_Confidence"] = "medium"

    pack_missing = work["PackUnits"].isna() | (work["PackUnits"] <= 0)
    if pack_missing.any():
        work.loc[pack_missing, "PackUnits"] = 1.0
        work.loc[pack_missing, "PackUnits_Source"] = "Default"
        work.loc[pack_missing, "PackUnits_Evidence"] = "default-1"
        work.loc[pack_missing, "PackUnits_Confidence"] = "low"

    # second safety pass for inserts
    mask_insert_pack = work["ProductCategory"].astype(str).str.lower().eq("inserts")
    if mask_insert_pack.any():
        _ins_pack = float(insert_default_pack_units)
        mask_bad_insert_pack = mask_insert_pack & (
            work["PackUnits"].isna() | (work["PackUnits"] <= 0) | (work["PackUnits"] != _ins_pack)
        )
        work.loc[mask_bad_insert_pack, "PackUnits"] = _ins_pack
        work.loc[mask_bad_insert_pack, "PackUnits_Source"] = "Heuristic"
        work.loc[mask_bad_insert_pack, "PackUnits_Evidence"] = f"insert-default-{_ins_pack:g}"
        work.loc[mask_bad_insert_pack, "PackUnits_Confidence"] = "high"

    # STEP D) SizeCategory heuristic pass
    size_missing = work["SizeCategory"].astype(str).str.strip().eq("")
    if size_missing.any():
        for idx in work[size_missing].index:
            row = work.loc[idx]
            h = heuristic_size_category(
                prod_cat=str(row.get("ProductCategory", "")),
                desc1=str(row.get("Description", "")),
                desc2=str(row.get("Description_2", "")),
            )
            if h:
                work.at[idx, "SizeCategory"] = h
                work.at[idx, "SizeCategory_Source"] = "Heuristic"
    return work


def apply_post_ai_safety(df: pd.DataFrame, *,
                         insert_default_pack_units: float) -> pd.DataFrame:
    """The final insert safety pass and default size fill, verbatim, on a copy.

    Precondition, as on the page: apply_pre_ai_heuristics ran first, so
    PackUnits is already resolved for every row (the default-1 fallback fills
    all gaps); this pass reads it as a number.
    """
    work = df.copy()
    # Final safety pass after AI:
    for idx, row in work.iterrows():
        # PPE rows are exempt from the insert auto-override
        if str(row.get("Listing", LISTING_TOOLS)).strip().lower() == LISTING_PPE.lower():
            continue
        combined = " ".join([
            str(row.get("ProductCategory", "")),
            str(row.get("Description", "")),
            str(row.get("Description_2", "")),
            str(row.get("Code", "")),
        ]).lower()
        strong_insert = any(kw in combined for kw in INSERT_KEYWORDS)
        if not strong_insert:
            if looks_like_insert_code(" ".join([
                str(row.get("Description", "")),
                str(row.get("Description_2", "")),
                str(row.get("Code", "")),
                str(row.get("SupplierCode", "")),
            ])):
                strong_insert = True
        if strong_insert:
            work.at[idx, "ProductCategory"] = "inserts"
            if str(work.at[idx, "PackUnits"]).strip() == "" or float(work.at[idx, "PackUnits"]) != float(insert_default_pack_units):
                work.at[idx, "PackUnits"] = float(insert_default_pack_units)
                work.at[idx, "PackUnits_Source"] = "Heuristic"
            if str(work.at[idx, "SizeCategory"]).strip() == "":
                work.at[idx, "SizeCategory"] = "S"
                work.at[idx, "SizeCategory_Source"] = "Heuristic"

    # Final default size if still missing
    still_missing_size = work["SizeCategory"].astype(str).str.strip().eq("")
    if still_missing_size.any():
        work.loc[still_missing_size, "SizeCategory"] = "L"
        work.loc[still_missing_size, "SizeCategory_Source"] = "Default"
    return work
