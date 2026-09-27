"""kromi_app.engine.multi_location - articles on several machines (v34.63).

A customer's location column (mapped as the Program column) assigns every
article to a vending machine. One cell may name several machines, for example
``AB-100 + AB 101``. This module reads those cells and plans such an article
in every supply point its machines map to (owner decisions D1 to D6):

* The Program mapping works per machine: every machine a cell names is mapped
  to a supply point, or to 0 ("Not planned here").
* D1 Consumption: an article listed for k machines gives each machine an equal
  share (1/k); a supply point receives the shares of the listed machines
  mapped to it. A machine that is not planned keeps its share out of the
  plan. Optionally every supply point counts the full consumption.
* D4: an article with no planned machine stops the run (never dropped
  silently); the page lists those articles.
* D5 Stock: one pool per article (Listing, Code), the stock of every source
  row that reaches the plan counted once (``Stock_Article_pcs``); the
  takeover fills the article's supply points in order from it.
* D6 Numbers: one number per article, whatever the number of supply points.
* A shared article is KTC in every supply point when it is KTC in one (owner
  decision 2026-09-27): an article is never KTC and Kanban at once.

A file without multi-machine cells gives exactly the frame it gave before
this module: no new columns and identical values.

Pure and Streamlit-free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

#: Characters that separate machines in one cell. '/' and '-' are not
#: separators: they occur inside machine and area names.
_SEPARATORS = re.compile(r"[+&;,]")
#: Letters, then optional spaces, '-' or '_', then digits: ``AB 101``.
_PREFIXED = re.compile(r"^([^\W\d_]+)[\s\-_]*(\d+)$")
_DIGITS = re.compile(r"^\d+$")

#: The value of the per-machine mapping that keeps a machine out of the plan.
NOT_PLANNED = 0
NOT_PLANNED_LABEL = "Not planned here"

#: Columns this module adds, only when a cell names several machines.
SOURCE_COL = "Location_Source"
SHARED_COL = "Location_Shared"
ARTICLE_STOCK_COL = "Stock_Article_pcs"
#: Helper columns between the expansion and the planning-base dedup.
_ROW_COL = "_Location_Row"
_ROW_STOCK_COL = "_Location_Row_Stock"
_CUT_COL = "_Location_Cut"

_STOCK_COL = "Stock_pcs"            # engine.takeover.STOCK_COL


def _collapse(text: Any) -> str:
    if text is None:
        return ""
    try:
        if pd.isna(text):
            return ""
    except (TypeError, ValueError):
        pass
    return " ".join(str(text).split())


def _prefixed(part: str) -> Optional[Tuple[str, str]]:
    m = _PREFIXED.match(part)
    return (m.group(1).upper(), m.group(2)) if m else None


def canonical_location(text: Any) -> str:
    """One machine label in its canonical spelling.

    Whitespace is collapsed; letters followed by digits (``AB 101``,
    ``ab-101``, ``AB_101``, ``AB101``) become ``AB-101``; anything else is
    kept as written. Also translates the machine keys of stored runs.
    """
    part = _collapse(text)
    pre = _prefixed(part)
    return f"{pre[0]}-{pre[1]}" if pre else part


def split_locations(text: Any) -> Tuple[str, ...]:
    """The machines one location cell names, canonical, in order of appearance.

    Separators are ``+``, ``&``, ``;`` and ``,``. A part made only of digits
    takes the letter prefix of the nearest earlier part that has one
    (``AB-100 +101`` names ``AB-100`` and ``AB-101``); without one it stays
    as it is. Empty and repeated parts are dropped. A blank cell gives ``()``.
    """
    out: List[str] = []
    prefix: Optional[str] = None
    for raw in _SEPARATORS.split(_collapse(text)):
        part = raw.strip()
        if not part:
            continue
        pre = _prefixed(part)
        if pre:
            prefix = pre[0]
            label = f"{pre[0]}-{pre[1]}"
        elif _DIGITS.match(part) and prefix is not None:
            label = f"{prefix}-{part}"
        else:
            label = part
        if label not in out:
            out.append(label)
    return tuple(out)


# ---- the machines of a file -------------------------------------------------------------

def row_machines(text: Any) -> Tuple[str, ...]:
    """The machines of one row; a blank cell is the blank machine ``""``."""
    return split_locations(text) or ("",)


def _program_series(work: pd.DataFrame) -> pd.Series:
    if "Program" in work.columns:
        return work["Program"]
    return pd.Series("", index=work.index)


def distinct_machines(work: pd.DataFrame) -> List[str]:
    """Every machine the file names, sorted, with the blank machine last.

    For a file without multi-machine cells this is the list of distinct
    programmes (in their canonical spelling).
    """
    names: set = set()
    blank = False
    for text in _program_series(work):
        parts = split_locations(text)
        if parts:
            names.update(parts)
        else:
            blank = True
    return sorted(names) + ([""] if blank else [])


def multi_machine_rows(work: pd.DataFrame) -> int:
    """How many rows name more than one machine."""
    return int(sum(len(split_locations(t)) > 1 for t in _program_series(work)))


def has_multi_machine_cells(work: pd.DataFrame) -> bool:
    return multi_machine_rows(work) > 0


def unassigned_machines(machines: Sequence[str], machine_to_sp: Mapping[str, Any]) -> List[str]:
    """Machines without a supply point or "Not planned here" chosen yet."""
    return [m for m in machines if machine_to_sp.get(m) is None]


def machine_stats(work: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Per machine: the rows naming it and its equal share of their use."""
    cons = pd.to_numeric(work.get("Consumption_pcs", 0.0), errors="coerce")
    cons = cons.fillna(0.0) if isinstance(cons, pd.Series) else pd.Series(0.0, index=work.index)
    out: Dict[str, Dict[str, float]] = {}
    for text, use in zip(_program_series(work), cons):
        parts = row_machines(text)
        for m in parts:
            s = out.setdefault(m, {"rows": 0, "consumption": 0.0})
            s["rows"] += 1
            s["consumption"] += float(use) / len(parts)
    return out


def _sp_label(sp: int) -> str:
    return NOT_PLANNED_LABEL if int(sp) == NOT_PLANNED else f"SP {int(sp)}"


def mapping_summary(work: pd.DataFrame, machine_to_sp: Mapping[str, Any], *,
                    n_supply_points: int, full_consumption: bool = False
                    ) -> List[Dict[str, Any]]:
    """Rows and consumption per supply point after the shares, for the page.

    A row counts once in every supply point it reaches. Machines without a
    choice yet are left out; a "Not planned here" line appears when a machine
    of the file is set to it.
    """
    sp_of = {m: int(v) for m, v in machine_to_sp.items() if v is not None}
    rows: Dict[int, int] = {sp: 0 for sp in range(1, int(n_supply_points) + 1)}
    use: Dict[int, float] = {sp: 0.0 for sp in rows}
    names: Dict[int, List[str]] = {sp: [] for sp in rows}
    cons = pd.to_numeric(work.get("Consumption_pcs", 0.0), errors="coerce")
    cons = cons.fillna(0.0) if isinstance(cons, pd.Series) else pd.Series(0.0, index=work.index)
    for text, total in zip(_program_series(work), cons):
        parts = row_machines(text)
        here: Dict[int, int] = {}
        for m in parts:
            if m in sp_of:
                here[sp_of[m]] = here.get(sp_of[m], 0) + 1
        for sp, n in here.items():
            rows.setdefault(sp, 0)
            use.setdefault(sp, 0.0)
            rows[sp] += 1
            full = full_consumption and sp != NOT_PLANNED
            use[sp] += float(total) if full else float(total) * n / len(parts)
    for m in distinct_machines(work):
        if m in sp_of:
            names.setdefault(sp_of[m], []).append(m or "(blank)")
    order = sorted(sp for sp in rows if sp != NOT_PLANNED) + (
        [NOT_PLANNED] if NOT_PLANNED in rows else [])
    out = []
    for sp in order:
        ms = names.get(sp, [])
        out.append({
            "Supply Point": _sp_label(sp),
            "Rows": int(rows[sp]),
            "Annual consumption": int(round(use[sp])),
            "# machines": len(ms),
            "Machines (first 5)": ", ".join(ms[:5])
            + (f" + {len(ms) - 5} more" if len(ms) > 5 else ""),
        })
    return out


# ---- the expansion --------------------------------------------------------------------------

@dataclass(frozen=True)
class ExpansionInfo:
    """What the expansion noticed, for the page and the Run_Metadata sheet."""

    multi_rows: int = 0
    shared_articles: int = 0
    not_planned_machines: Tuple[str, ...] = ()
    #: (Listing, Code) of articles none of whose machines is planned (D4).
    unplanned_articles: Tuple[Tuple[str, str], ...] = ()
    #: Rows that reach no supply point (their machines are not planned).
    dropped_rows: int = 0
    shared: Tuple[Tuple[str, str], ...] = field(default=())


def _articles(frame: pd.DataFrame) -> List[Tuple[str, str]]:
    listing = (frame["Listing"].astype(str) if "Listing" in frame.columns
               else pd.Series("", index=frame.index))
    return list(zip(listing, frame["Code"].astype(str)))


def _supply_points(values: Sequence[int], index: pd.Index) -> pd.Series:
    # The same conversion the plain Program map used, so the dtype matches.
    return pd.Series(list(values), index=index).astype("Int64").astype(int)


def _mark_shared(frame: pd.DataFrame) -> None:
    """Set the shared flag and the article stock pool, in place.

    Shared: the article (Listing, Code) sits in two or more supply points.
    The pool is the stock of every source row once; it is only kept when a
    stock column is mapped and an article is shared or a row lost a share to
    a machine that is not planned.
    """
    # Text keys (listing and code joined by a unit separator), not tuples, so
    # the grouping reads the same on every pandas version.
    arts = pd.Series(["\x1f".join(a) for a in _articles(frame)], index=frame.index)
    n_sp = frame.groupby(arts)["SupplyPoint"].transform("nunique")
    frame[SHARED_COL] = (n_sp >= 2).to_numpy()
    if _ROW_STOCK_COL not in frame.columns:
        return
    once = pd.DataFrame({"art": arts, "row": frame[_ROW_COL],
                         "stock": frame[_ROW_STOCK_COL]}).drop_duplicates("row")
    pool = once.groupby("art")["stock"].sum()
    if bool(frame[SHARED_COL].any()) or bool(frame[_CUT_COL].any()):
        frame[ARTICLE_STOCK_COL] = arts.map(pool).astype(float).to_numpy()
    elif ARTICLE_STOCK_COL in frame.columns:
        frame.drop(columns=[ARTICLE_STOCK_COL], inplace=True)


def expand_locations(work: pd.DataFrame, machine_to_sp: Mapping[str, Any], *,
                     full_consumption: bool = False) -> Tuple[pd.DataFrame, ExpansionInfo]:
    """Plan every row in each supply point its machines map to (before the dedup).

    ``machine_to_sp`` maps each machine label (``distinct_machines``) to a
    supply point, or to ``NOT_PLANNED``. Every row becomes one copy per
    planned supply point with ``SupplyPoint`` set; its consumption (and stock)
    is the share of its machines mapped there (D1), or the full consumption in
    every supply point with ``full_consumption``. Rows that reach no supply
    point are left out; ``info.unplanned_articles`` names the articles left
    without any planned machine, which must stop the run (D4).

    Only when a cell names several machines are the columns
    ``Location_Source`` (the cell text), ``Location_Shared`` (the article sits
    in two or more supply points) and, with a stock column, ``Stock_Article_pcs``
    (the article's stock pool) added; the planning-base preparation finalizes
    them after its year filter. A file without multi-machine cells gives the
    frame the plain Program map gave. A machine without a choice raises
    ``ValueError``: nothing is assigned silently (D3). Never mutates ``work``.
    """
    programs = _program_series(work)
    machines = [row_machines(t) for t in programs]
    missing = sorted({m for ms in machines for m in ms if machine_to_sp.get(m) is None})
    if missing:
        raise ValueError("No supply point chosen for machine(s): "
                         + ", ".join(repr(m) for m in missing))
    sp_of = {m: int(v) for m, v in machine_to_sp.items() if v is not None}
    planned = [sorted({sp_of[m] for m in ms} - {NOT_PLANNED}) for ms in machines]
    in_file = sorted({m for ms in machines for m in ms})
    not_planned = tuple(m for m in in_file if sp_of[m] == NOT_PLANNED)
    multi = int(sum(len(ms) > 1 for ms in machines))

    arts = _articles(work)
    reached: Dict[Tuple[str, str], bool] = {}
    for art, sps in zip(arts, planned):
        reached[art] = reached.get(art, False) or bool(sps)
    unplanned = tuple(a for a in dict.fromkeys(arts) if not reached[a])
    dropped = int(sum(not sps for sps in planned))

    if multi == 0:
        keep = [bool(sps) for sps in planned]
        out = work.copy() if all(keep) else work.loc[keep].copy()
        out["SupplyPoint"] = _supply_points(
            [sps[0] for sps in planned if sps], out.index)
        return out, ExpansionInfo(not_planned_machines=not_planned,
                                  unplanned_articles=unplanned, dropped_rows=dropped)

    positions: List[int] = []
    sps_out: List[int] = []
    shares: List[Tuple[int, int]] = []
    cut: List[bool] = []
    for pos, (ms, sps) in enumerate(zip(machines, planned)):
        lost = any(sp_of[m] == NOT_PLANNED for m in ms)
        for sp in sps:
            positions.append(pos)
            sps_out.append(sp)
            shares.append((sum(sp_of[m] == sp for m in ms), len(ms)))
            cut.append(lost)
    out = work.iloc[positions].reset_index(drop=True)
    out["SupplyPoint"] = _supply_points(sps_out, out.index)
    n_here = pd.Series([s[0] for s in shares], index=out.index, dtype=float)
    k = pd.Series([s[1] for s in shares], index=out.index, dtype=float)
    cons = pd.to_numeric(out["Consumption_pcs"], errors="coerce").fillna(0.0)
    if not full_consumption:
        out["Consumption_pcs"] = cons * n_here / k
    out[SOURCE_COL] = programs.iloc[positions].astype(str).to_numpy()
    out[_ROW_COL] = positions
    out[_CUT_COL] = cut
    if _STOCK_COL in out.columns:
        stock = pd.to_numeric(out[_STOCK_COL], errors="coerce").fillna(0.0)
        out[_ROW_STOCK_COL] = stock
        out[_STOCK_COL] = stock * n_here / k
    _mark_shared(out)
    shared = tuple(dict.fromkeys(
        a for a, s in zip(_articles(out), out[SHARED_COL]) if s))
    return out, ExpansionInfo(multi_rows=multi, shared_articles=len(shared),
                              not_planned_machines=not_planned,
                              unplanned_articles=unplanned, dropped_rows=dropped,
                              shared=shared)


def finalize_planning_rows(base: pd.DataFrame) -> pd.DataFrame:
    """After the year filter: recompute the shared flag and the stock pool on
    the rows that remain, then drop the helper columns. A frame without the
    expansion's helper columns is returned unchanged."""
    if _ROW_COL not in base.columns:
        return base
    _mark_shared(base)
    return base.drop(columns=[c for c in (_ROW_COL, _ROW_STOCK_COL, _CUT_COL)
                              if c in base.columns])


# ---- one system per article ---------------------------------------------------------------

SHARED_KTC_REASON = ("KTC: the article is KTC at another supply point "
                     "(an article on several machines is never KTC and Kanban at once)")


def harmonize_shared_system(work: pd.DataFrame, *, helix_threshold: float,
                            min_carousel_compartments: int, carousel_reserve_factor: float,
                            helix_overfill_factor: float) -> int:
    """A shared article that is KTC in one supply point is KTC in all, in place.

    Owner decision (2026-09-27): an article is never KTC and Kanban at once.
    Runs after every routing layer (threshold, overrides, system type,
    special tools, bulk routing). Each Kanban copy of an article that is KTC
    elsewhere gets a machine sized from its own share, like a System type =
    KTC row (``route_and_size_row`` with ``force_ktc``), and leaves bulk
    routing. Returns the number of copies moved; a frame without the shared
    flag is not touched.
    """
    if SHARED_COL not in work.columns or len(work) == 0:
        return 0
    from .cabinet_math import route_and_size_row

    shared = work[SHARED_COL].fillna(False).astype(bool)
    system = work["SystemCategory"].astype(str)
    arts = pd.Series(["\x1f".join(a) for a in _articles(work)], index=work.index)
    ktc_arts = set(arts[shared & (system == "KTC")])
    flip = shared & (system != "KTC") & arts.isin(ktc_arts)
    for idx in work.index[flip]:
        res = route_and_size_row(
            monthly_packs=pd.to_numeric(work.at[idx, "Monthly_packs"], errors="coerce"),
            monthly_pcs=pd.to_numeric(work.at[idx, "Monthly_pcs"], errors="coerce"),
            target_packs=pd.to_numeric(work.at[idx, "Target_packs"], errors="coerce"),
            size_cat=work.at[idx, "SizeCategory"],
            product_category=work.at[idx, "ProductCategory"],
            threshold=0.0,
            helix_threshold=float(helix_threshold),
            min_carousel_compartments=int(min_carousel_compartments),
            carousel_reserve_factor=float(carousel_reserve_factor),
            helix_overfill_factor=float(helix_overfill_factor),
            regrind=bool(work.at[idx, "Regrind"]) if "Regrind" in work.columns else False,
            force_ktc=True,
        )
        work.at[idx, "SystemCategory"] = res["SystemCategory"]
        work.at[idx, "CabinetType"] = res["CabinetType"]
        work.at[idx, "Spiral_capacity"] = (
            res["Spiral_capacity"] if res["Spiral_capacity"] is not None else pd.NA)
        work.at[idx, "Spirals_needed"] = int(res["Spirals_needed"])
        work.at[idx, "Carousel_stockpiles"] = int(res["Carousel_stockpiles"])
        if "SystemCategory_Reason" in work.columns:
            work.at[idx, "SystemCategory_Reason"] = SHARED_KTC_REASON
        if "VendMode" in work.columns:
            work.at[idx, "VendMode"] = "Vending"
        if "VendBlockReason" in work.columns:
            work.at[idx, "VendBlockReason"] = ""
    return int(flip.sum())


# ---- exports ------------------------------------------------------------------------------

MACHINES_COLUMN = "Machines (source)"
SUPPLY_POINTS_COLUMN = "Supply points"


def add_display_columns(work: pd.DataFrame) -> None:
    """The two Result-sheet columns, in place, only for multi-machine files:
    the machines the source cell named and the article's supply points
    ("SP 1, SP 2")."""
    if SOURCE_COL not in work.columns:
        return
    work[MACHINES_COLUMN] = work[SOURCE_COL]
    arts = pd.Series(_articles(work), index=work.index)
    sps = pd.to_numeric(work["SupplyPoint"], errors="coerce")
    per_article: Dict[Tuple[str, str], List[int]] = {}
    for art, sp in zip(arts, sps):
        if pd.notna(sp):
            per_article.setdefault(art, [])
            if int(sp) not in per_article[art]:
                per_article[art].append(int(sp))
    work[SUPPLY_POINTS_COLUMN] = arts.map(
        lambda a: ", ".join(f"SP {sp}" for sp in sorted(per_article.get(a, []))))


def shared_article_count(work: pd.DataFrame) -> int:
    """Articles (Listing, Code) planned in two or more supply points."""
    if SHARED_COL not in work.columns:
        return 0
    flag = work[SHARED_COL].fillna(False).astype(bool)
    return len(set(a for a, f in zip(_articles(work), flag) if f))


def multi_location_meta_rows(meta: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Run_Metadata rows of a run whose file names several machines in a cell.

    ``meta``: multi_rows, shared_articles, full_consumption and
    not_planned_machines.
    """
    machines = tuple(meta.get("not_planned_machines") or ())
    return [
        {"Key": "Rows naming several machines", "Value": int(meta.get("multi_rows", 0))},
        {"Key": "Articles in several supply points",
         "Value": int(meta.get("shared_articles", 0))},
        {"Key": "Consumption for shared articles",
         "Value": ("full in every supply point" if meta.get("full_consumption")
                   else "equal share per machine")},
        {"Key": "Machines not planned",
         "Value": ", ".join(m or "(blank)" for m in machines) if machines else "none"},
    ]
