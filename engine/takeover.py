"""kromi_app.engine.takeover - the takeover sheets (v34.56).

At go-live KROMI takes over the customer's stock of every article as customer
property. The takeover sheet (one per supply point, columns as in KROMI's
takeover template) tells the technicians how each article's stock splits:
whole packs go into the KTC up to the article's maximum, the rest stays at the
main stock location (HLO).

The maximum is the space the plan allocated to the article times its
packaging unit (VPE):

* Carousel: compartments x VPE.
* Helix: spirals x the places one spiral of the article's size holds x VPE.
  The plan's own ``Spiral_capacity`` is used (S 28, M 22, L 18, XL 12, by
  category when the size is unknown); a reground Helix article keeps one of
  its spirals for the reground pieces.
* Lockers, Kanban articles and articles without space in a fixed
  configuration hold nothing in the KTC: their whole stock stays at the HLO.

The stock of a row belongs to that row's supply point (with a Program mapping
every location brings its own stock). Replicate mode copies every article to
each supply point with the same stock value; there the stock is one pool that
fills the machines in supply-point order, and what is left is listed once, on
the first supply point's sheet.

Pure and Streamlit-free.
"""

from __future__ import annotations

import math
import re
from io import BytesIO
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from .cabinet_math import decide_spiral_capacity
from .export_safety import neutralize_formula_cells
from .fixed_config import STATUS_NOT_PLACED

STOCK_COL = "Stock_pcs"
CATEGORY_TEXT_COL = "ProductCategory_Text"

TAKEOVER_COLUMNS: Tuple[str, ...] = (
    "Cust. Prop. Art. Nr.", "Kunden Art. Nr.", "Bezeichnung 1", "Bezeichnung 2",
    "VPE", "im KTC", "am HLO", "Total", "Schranktyp",
)
SHEET_PREFIX = "Takeover sheet SP "
_COLUMN_WIDTHS = (16, 18, 26, 36, 7, 9, 9, 9, 12)

_KTC = "KTC"


# ---- the stock column ---------------------------------------------------------------

_STOCK_PREFERRED = ("aktuellerbestand", "istbestand", "lagerbestand", "currentstock",
                    "stockonhand", "onhand")
_STOCK_GENERIC = ("bestand", "stock")
# Min / max / safety / reorder / target levels and stock locations or values
# are never the stock on hand.
_STOCK_EXCLUDED_TOKENS = {"min", "max", "minimum", "maximum", "location", "locations",
                          "value", "wert", "safety", "reorder", "target"}
_STOCK_EXCLUDED_PARTS = ("mindest", "maximal", "sicherheit", "melde", "soll", "lagerort",
                         "bestandswert", "wert")


def _stock_candidate(header: Any) -> Optional[int]:
    """0 for a preferred stock header, 1 for a generic one, None otherwise."""
    text = str(header).lower()
    tokens = set(re.findall(r"[a-zäöüß0-9]+", text))
    if tokens & _STOCK_EXCLUDED_TOKENS:
        return None
    flat = re.sub(r"[^a-zäöüß0-9]+", "", text)
    if any(p in flat for p in _STOCK_EXCLUDED_PARTS):
        return None
    if any(p in flat for p in _STOCK_PREFERRED):
        return 0
    if any(p in flat for p in _STOCK_GENERIC):
        return 1
    return None


def guess_stock_column(df: pd.DataFrame) -> Optional[str]:
    """The column holding the customer's current stock in pieces, or None.

    Minimum, maximum, safety and reorder levels, stock locations and stock
    values are never taken, so a KDS template's Mindestbestand /
    Maximalbestand columns stay unmapped.
    """
    best: Optional[Tuple[int, int, str]] = None
    for pos, col in enumerate(df.columns):
        tier = _stock_candidate(col)
        if tier is None:
            continue
        if best is None or (tier, pos) < best[:2]:
            best = (tier, pos, col)
    return None if best is None else best[2]


# ---- per-article maximum --------------------------------------------------------------

def _num(value: Any) -> float:
    v = pd.to_numeric(value, errors="coerce")
    return float(v) if pd.notna(v) else 0.0


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "ja"}
    try:
        return bool(value) and not pd.isna(value)
    except (TypeError, ValueError):
        return bool(value)


def _in_ktc(row: Mapping[str, Any]) -> bool:
    return (_text(row.get("SystemCategory")) == _KTC
            and _text(row.get("Placement_Status")) != STATUS_NOT_PLACED)


def max_packs(row: Mapping[str, Any]) -> float:
    """Packs the plan's machine space holds for this row (0 when none)."""
    if not _in_ktc(row):
        return 0.0
    cabinet = _text(row.get("CabinetType"))
    if cabinet == "Carousel":
        return max(0.0, math.floor(_num(row.get("Carousel_stockpiles"))))
    if cabinet == "Helix":
        spirals = int(max(0.0, math.floor(_num(row.get("Spirals_needed")))))
        if spirals <= 0:
            return 0.0
        if _truthy(row.get("Regrind", False)) and spirals >= 2:
            spirals -= 1          # one spiral holds the reground pieces
        cap = _num(row.get("Spiral_capacity"))
        if cap <= 0:
            cap = float(decide_spiral_capacity(_text(row.get("SizeCategory")),
                                               _text(row.get("ProductCategory"))))
        return float(spirals) * cap
    return 0.0                    # lockers are not part of the takeover yet


def _machine_label(row: Mapping[str, Any]) -> str:
    if _text(row.get("SystemCategory")) != _KTC:
        return "Kanban"
    if _text(row.get("Placement_Status")) == STATUS_NOT_PLACED:
        return "Not placed"
    return _text(row.get("CabinetType"))


def _vpe(value: Any) -> float:
    v = _num(value)
    return v if v > 0 else 1.0


def _clean_qty(value: float) -> Any:
    value = round(float(value), 6)
    return int(value) if value.is_integer() else value


def _whole_packs(stock: float, vpe: float) -> float:
    return math.floor(stock / vpe + 1e-9) * vpe


# ---- the frames ---------------------------------------------------------------------------

def build_takeover_frames(work: pd.DataFrame, *, shared_stock: bool = False
                          ) -> List[Tuple[int, pd.DataFrame]]:
    """One takeover frame per supply point, ``[(sp, frame), ...]`` by SP.

    ``work`` is the final plan frame after the export augmentation (its
    ``Kromi_Art_No`` is the Result sheet's number; KTC rows carry the
    customer-property number). Returns ``[]`` when no stock column was
    mapped. ``shared_stock`` marks a Replicate run whose copies share one
    stock. Never mutates ``work``.
    """
    if STOCK_COL not in work.columns or len(work) == 0:
        return []
    df = work.reset_index(drop=True)
    n = len(df)
    sps = (pd.to_numeric(df["SupplyPoint"], errors="coerce").fillna(1).astype(int)
           if "SupplyPoint" in df.columns else pd.Series(1, index=df.index))
    listing = (df["Listing"].map(_text) if "Listing" in df.columns
               else pd.Series("", index=df.index))
    codes = df["Code"].map(_text) if "Code" in df.columns else pd.Series("", index=df.index)
    stock = pd.to_numeric(df[STOCK_COL], errors="coerce").fillna(0.0).clip(lower=0.0)
    numbers = (df["Kromi_Art_No"].map(_text) if "Kromi_Art_No" in df.columns
               else pd.Series("", index=df.index))
    has_cat_text = CATEGORY_TEXT_COL in df.columns
    records = df.to_dict("records")

    # Per article (listing, code): the first occurrence's number.
    first_number: Dict[Tuple[str, str], str] = {}
    # Per (sp, article): first row, summed packs and stock.
    groups: Dict[Tuple[int, Tuple[str, str]], Dict[str, Any]] = {}
    for i in range(n):
        art = (listing.iat[i], codes.iat[i])
        first_number.setdefault(art, numbers.iat[i])
        key = (int(sps.iat[i]), art)
        g = groups.get(key)
        row = records[i]
        if g is None:
            g = groups[key] = {"row": i, "packs": 0.0, "stock": 0.0,
                               "vpe": _vpe(row.get("PackUnits")),
                               "machine": _machine_label(row)}
        g["packs"] += max_packs(row)
        g["stock"] += float(stock.iat[i])

    ktc: Dict[Tuple[int, Tuple[str, str]], float] = {}
    hlo: Dict[Tuple[int, Tuple[str, str]], float] = {}
    if shared_stock:
        by_article: Dict[Tuple[str, str], List[int]] = {}
        for sp, art in groups:
            by_article.setdefault(art, []).append(sp)
        for art, sp_list in by_article.items():
            sp_list.sort()
            first = (sp_list[0], art)
            pool = groups[first]["stock"]          # the copies repeat one stock
            left = pool
            for sp in sp_list:
                g = groups[(sp, art)]
                put = min(_whole_packs(left, g["vpe"]), g["packs"] * g["vpe"])
                ktc[(sp, art)] = put
                hlo[(sp, art)] = 0.0
                left -= put
            hlo[first] = left
    else:
        for key, g in groups.items():
            put = min(_whole_packs(g["stock"], g["vpe"]), g["packs"] * g["vpe"])
            ktc[key] = put
            hlo[key] = g["stock"] - put

    out: Dict[int, List[Dict[str, Any]]] = {}
    for key in sorted(groups, key=lambda k: (k[0], groups[k]["row"])):
        sp, art = key
        g = groups[key]
        row = records[g["row"]]
        desc = _text(row.get("Description"))
        cat_text = _text(row.get(CATEGORY_TEXT_COL)) if has_cat_text else ""
        if cat_text:
            text1, text2 = cat_text, desc
        else:
            text1, text2 = desc, _text(row.get("Description_2"))
        put, rest = ktc[key], hlo[key]
        out.setdefault(sp, []).append({
            "Cust. Prop. Art. Nr.": first_number.get(art, ""),
            "Kunden Art. Nr.": art[1],
            "Bezeichnung 1": text1,
            "Bezeichnung 2": text2,
            "VPE": _clean_qty(g["vpe"]),
            "im KTC": _clean_qty(put),
            "am HLO": _clean_qty(rest),
            "Total": _clean_qty(put + rest),
            "Schranktyp": g["machine"],
        })
    return [(sp, pd.DataFrame(rows, columns=list(TAKEOVER_COLUMNS)))
            for sp, rows in sorted(out.items())]


def takeover_summary(frames: Sequence[Tuple[int, pd.DataFrame]]) -> List[Dict[str, Any]]:
    """Per supply point: articles and pieces in the KTC, at the HLO and in total."""
    rows = []
    for sp, f in frames:
        rows.append({
            "sp": int(sp), "articles": int(len(f)),
            "ktc": _clean_qty(pd.to_numeric(f["im KTC"]).sum()),
            "hlo": _clean_qty(pd.to_numeric(f["am HLO"]).sum()),
            "total": _clean_qty(pd.to_numeric(f["Total"]).sum()),
        })
    return rows


# ---- writing -----------------------------------------------------------------------------

def sheet_name(sp: int) -> str:
    return f"{SHEET_PREFIX}{int(sp)}"


def write_takeover_sheets(writer: Any, frames: Sequence[Tuple[int, pd.DataFrame]]) -> None:
    """Write one sheet per supply point onto an open openpyxl ExcelWriter."""
    from openpyxl.utils import get_column_letter

    for sp, frame in frames:
        name = sheet_name(sp)
        frame.to_excel(writer, index=False, sheet_name=name)
        ws = writer.sheets[name]
        ws.freeze_panes = "A2"
        for i, width in enumerate(_COLUMN_WIDTHS, start=1):
            ws.column_dimensions[get_column_letter(i)].width = width


def build_takeover_workbook(frames: Sequence[Tuple[int, pd.DataFrame]]) -> bytes:
    """A workbook with only the takeover sheets, for the technicians."""
    buffer_io = BytesIO()
    with pd.ExcelWriter(buffer_io, engine="openpyxl") as writer:
        write_takeover_sheets(writer, frames)
        neutralize_formula_cells(writer.book)
    buffer_io.seek(0)
    return buffer_io.getvalue()
