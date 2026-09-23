"""Demand arithmetic and the base KTC/Kanban routing decision.

These were inline in the planner page. They are the most correctness-sensitive
numbers the app produces, so they live here where they can be unit-tested.

The demand columns:

* ``Monthly_pcs``   = Consumption_pcs / consumption_period_months
* ``Monthly_packs`` = Monthly_pcs / PackUnits (a zero pack count is treated as 1)
* ``Coverage_days`` = per row when a Standard/Special column is mapped and the two
  coverage windows differ, otherwise the single coverage value
* ``Target_packs``  = Monthly_packs * Coverage_days / DAYS_PER_MONTH

The base routing decision is monthly *pieces* against a per-row threshold: KTC
when ``Monthly_pcs`` is strictly greater than the threshold, Kanban otherwise.
Override layers (screws/accessories, system type, special->KTC) are applied by
the caller after this; they are not part of the base decision.

Pure: no Streamlit, no I/O. The DataFrame functions return a new frame and do not
mutate their input.
"""

from __future__ import annotations

import pandas as pd

from engine.constants import DAYS_PER_MONTH
from engine.routing_rules import (
    classify_standard_special,
    coverage_days_for,
    threshold_for_row,
)


def monthly_pcs(consumption_pcs: float, consumption_period_months: float) -> float:
    """Monthly pieces from period consumption."""
    return consumption_pcs / consumption_period_months


def monthly_packs(monthly_pieces: float, pack_units: float) -> float:
    """Monthly packs from monthly pieces. A zero pack count is treated as 1."""
    return monthly_pieces / (pack_units if pack_units != 0 else 1)


def target_packs(monthly_pack_count: float, coverage_days: float,
                 days_per_month: float = DAYS_PER_MONTH) -> float:
    """Coverage-window-scaled sizing demand, in packs."""
    return monthly_pack_count * (coverage_days / days_per_month)


def compute_demand(
    df: pd.DataFrame,
    *,
    consumption_period_months: float,
    coverage_days: float,
    coverage_days_special: float,
    days_per_month: float = DAYS_PER_MONTH,
) -> pd.DataFrame:
    """Add ``Monthly_pcs``, ``Monthly_packs``, ``Coverage_days``, ``Target_packs``.

    Coverage is split by Standard/Special only when a ``StdSpecial`` column is
    present and the two coverage windows differ; in that case a ``Coverage_class``
    column is also added. Otherwise the single ``coverage_days`` value applies to
    every row and no ``Coverage_class`` column is produced. Requires
    ``Consumption_pcs`` and ``PackUnits``.
    """
    out = df.copy()
    out["Monthly_pcs"] = out["Consumption_pcs"] / float(consumption_period_months)
    out["Monthly_packs"] = out["Monthly_pcs"] / out["PackUnits"].replace(0, 1)

    split_coverage = ("StdSpecial" in out.columns) and (coverage_days_special != coverage_days)
    if split_coverage:
        cls = out["StdSpecial"].apply(classify_standard_special)
        out["Coverage_days"] = cls.apply(
            lambda c: coverage_days_for(c, float(coverage_days), float(coverage_days_special), True)
        )
        out["Coverage_class"] = cls.replace("", "standard")
    else:
        out["Coverage_days"] = float(coverage_days)

    out["Target_packs"] = out["Monthly_packs"] * (out["Coverage_days"] / days_per_month)
    return out


def assign_system_category(
    df: pd.DataFrame,
    *,
    usage_threshold: float,
    per_class_thresholds: dict,
    optional_thresholds_active: bool,
) -> pd.DataFrame:
    """Add ``SystemCategory`` (KTC/Kanban) and ``SystemCategory_Reason``.

    The decision is monthly *pieces* against a per-row threshold: each tool uses
    its per-class threshold when optional thresholds are active (inserts via the
    insert-detection fallback), otherwise the single standard threshold. KTC when
    ``Monthly_pcs`` is strictly greater than the threshold, Kanban otherwise.
    Requires ``Monthly_pcs`` (see :func:`compute_demand`).
    """
    out = df.copy()
    if out.empty:
        out["SystemCategory"] = pd.Series(dtype="object")
        out["SystemCategory_Reason"] = pd.Series(dtype="object")
        return out

    row_threshold = out.apply(
        lambda r: threshold_for_row(
            product_category=r.get("ProductCategory"),
            tool_class=r.get("ToolClass", ""),
            standard_threshold=float(usage_threshold),
            per_class_thresholds=per_class_thresholds,
            optional_active=bool(optional_thresholds_active),
        ),
        axis=1,
    )
    out["SystemCategory"] = (out["Monthly_pcs"] > row_threshold).map({True: "KTC", False: "Kanban"})
    out["SystemCategory_Reason"] = [
        f"Monthly_pcs {'>' if mp > thr else '<='} threshold {thr:g} pcs/mo"
        for mp, thr in zip(out["Monthly_pcs"], row_threshold)
    ]
    return out
