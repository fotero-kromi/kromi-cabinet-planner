"""Parity harness for the restock-segment vectorization (v34.38, audit P2).

The reference below is the row-wise implementation frozen verbatim at the
moment of the change; the live vectorized segment must produce identical
frames and identical info counters on randomized adversarial inputs. This
freezes today's semantics as the specification rather than mirroring the
live code.
"""

from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd

from engine.plan import run_restock_segment

_RESTOCK_CABINETS = ("Helix", "Carousel", "Locker A", "Locker B", "Locker C")


def _reference_segment(
    df: pd.DataFrame, *, restock_categories: Tuple[str, ...], op_mode: str = ""
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Decide per-row restockability and reserve the buffer compartments (v34.24).

    Runs after overrides and the operational mode, so it sees the final
    routing: an override that moved a flagged item to Kanban has already done
    so, and the buffer is dropped with it. Source precedence: a mapped
    yes/no value (Provided) beats the category rule (Rule) beats the default
    of not restockable. Restocking is a vending concept, so only KTC rows in
    a cabinet carry a buffer; coil cabinets cannot restock, so a Helix item
    buffers in a Carousel while Carousel and Locker items buffer in their own
    class. The Helix operational mode is incompatible with restocking and
    makes the segment inert. Returns a new frame; never mutates ``df``.
    """
    from engine.preprocessing import normalize_restock_flag

    out = df.copy()
    out["Restockable"] = False
    out["Restockable_Source"] = ""
    out["Restock_target"] = ""
    out["Restock_slots"] = 0
    info: Dict[str, Any] = {
        "provided_true": 0, "rule_true": 0, "override_true": 0, "unknown_values": 0,
        "flagged_kanban": 0, "slots_carousel": 0,
        "slots_lockerA": 0, "slots_lockerB": 0, "slots_lockerC": 0,
        "inert_mode": False,
    }
    if str(op_mode) == "Helix":
        info["inert_mode"] = True
        return out, info

    has_ov = "Restocking_Override" in out.columns
    has_col = "Restocking" in out.columns
    cats = {str(c).strip().lower() for c in (restock_categories or ()) if str(c).strip()}
    if not has_col and not cats and not has_ov:
        return out, info

    for idx in out.index:
        source = ""
        flag = False
        if has_ov:
            raw_ov = out.at[idx, "Restocking_Override"]
            if raw_ov is not None and pd.notna(raw_ov) and str(raw_ov).strip() != "":
                norm_ov = normalize_restock_flag(raw_ov)
                if norm_ov is None:
                    info["unknown_values"] += 1
                else:
                    flag, source = bool(norm_ov), "Override"
        if not source and has_col:
            raw = out.at[idx, "Restocking"]
            if raw is not None and pd.notna(raw) and str(raw).strip() != "":
                norm = normalize_restock_flag(raw)
                if norm is None:
                    info["unknown_values"] += 1
                    norm = False
                flag, source = bool(norm), "Provided"
        if not source and cats:
            pc = str(out.at[idx, "ProductCategory"] if "ProductCategory" in out.columns else "")
            if pc.strip().lower() in cats:
                flag, source = True, "Rule"
        if source:
            # The source is the audit trail of the decision, recorded even for
            # a file-answered "no": it distinguishes "the file said no" from
            # "nothing said anything".
            out.at[idx, "Restockable_Source"] = source
        if not flag:
            continue
        out.at[idx, "Restockable"] = True
        info[{"Provided": "provided_true", "Rule": "rule_true",
              "Override": "override_true"}[source]] += 1

        system = str(out.at[idx, "SystemCategory"] if "SystemCategory" in out.columns else "")
        cabinet = str(out.at[idx, "CabinetType"] if "CabinetType" in out.columns else "")
        if system != "KTC" or cabinet not in _RESTOCK_CABINETS:
            if system == "Kanban":
                info["flagged_kanban"] += 1
            continue
        target = "Carousel" if cabinet in ("Helix", "Carousel") else cabinet
        out.at[idx, "Restock_target"] = target
        out.at[idx, "Restock_slots"] = 1
        if target == "Carousel":
            info["slots_carousel"] += 1
        else:
            info["slots_locker" + target[-1]] += 1
    return out, info




def _random_frame(rng, n):
    ov_pool = ["yes", "no", "ja", "nein", "TRUE", "0", "maybe", "", "  ", None, np.nan, "y", "x"]
    prov_pool = ov_pool + [True, False, 1, 0, 1.0, 0.0,
                           np.float64(1.0), np.bool_(False)]
    cats = ["inserts", "mills", "drills", "other", "", None]
    systems = ["KTC", "Kanban", "KTC", "KTC"]
    cabinets = ["Helix", "Carousel", "Locker A", "Locker B", "Locker C", "Kanban", ""]
    df = pd.DataFrame({
        "SystemCategory": rng.choice(systems, n),
        "CabinetType": rng.choice(cabinets, n),
        "ProductCategory": rng.choice(cats, n),
    })
    if rng.random() < 0.85:
        df["Restocking"] = rng.choice(np.array(prov_pool, dtype=object), n)
    if rng.random() < 0.85:
        df["Restocking_Override"] = rng.choice(np.array(ov_pool, dtype=object), n)
    return df


def test_vectorized_segment_matches_the_frozen_reference():
    rng = np.random.default_rng(20260712)
    for trial in range(300):
        n = int(rng.integers(0, 40))
        df = _random_frame(rng, n)
        cats = tuple(rng.choice(["inserts", "mills", "drills"],
                                size=int(rng.integers(0, 3)), replace=False))
        mode = str(rng.choice(["", "Standard", "Helix", "Capped", "Carousel"]))
        ref_out, ref_info = _reference_segment(df, restock_categories=cats, op_mode=mode)
        new_out, new_info = run_restock_segment(df, restock_categories=cats, op_mode=mode)
        assert new_info == ref_info, f"trial {trial}: info diverged: {new_info} != {ref_info}"
        pd.testing.assert_frame_equal(
            new_out.sort_index(axis=1), ref_out.sort_index(axis=1),
            check_dtype=True,
        )
