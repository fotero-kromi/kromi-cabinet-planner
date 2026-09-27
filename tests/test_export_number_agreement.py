"""Every sheet shows the Result sheet's KROMI number (v34.64).

The Result sheet numbers the whole plan once: the KTC running counter and the
Kanban dimension variants run over every row. Helix_only, Carousel_only,
Not_placed and Bulk_Routed used to number only their own rows, so the counter
started again at 1 and an article could show another article's number there.
Every sheet now takes its rows, numbers included, from the one numbering of
the whole plan.
"""
from io import BytesIO

import pandas as pd
import pytest
from openpyxl import load_workbook

from engine.fixed_config import FIXED_MODE
from engine.plan import run_plan
from engine.takeover import SHEET_PREFIX, STOCK_COL
from engine.workbook import build_result_workbook
from tests.test_run_plan_equivalence import _boundary_frame, _params

KEYS = ["Listing", "Code", "SupplyPoint"]

#: Tool classes for the 14 rows of the boundary frame (T001..T014).
_TOOL_CLASSES = [
    "solid_end_mill", "turning_insert", "solid_carbide_drill", "hsk_holder", "tap",
    "reamer", "screw", "wrench", "abrasive_disc", "solid_end_mill", "turning_insert",
    "solid_carbide_drill", "solid_end_mill", "boring_bar",
]


def _frame(stock=False):
    df = _boundary_frame()
    df["ToolClass"] = _TOOL_CLASSES
    if stock:
        df[STOCK_COL] = [float(i * 13 % 40) for i in range(len(df))]
    return df


def _bulk_frame():
    # A grinding wheel on the shelf (Kanban, T006) and an abrasive disc routed
    # to bulk (T009) share the dimension group 19-1250, so the disc takes the
    # second variant on the Result sheet.
    df = _frame()
    df.loc[5, ["Description", "ToolClass"]] = ["Grinding wheel 125mm", "grinding_wheel"]
    df.loc[8, ["Description", "ToolClass"]] = ["Disque abrasif 125mm", "abrasive_disc"]
    return df


#: name: (frame, plan settings, the sheets this plan must reach)
REGIMES = {
    "machines": (_frame, dict(helix_threshold=30.0, enable_rebalancer=False),
                 {"Helix_only", "Carousel_only"}),
    "replicate": (_frame, dict(n_supply_points=2, sp_mode="replicate",
                               helix_threshold=30.0, enable_rebalancer=False),
                  {"Helix_only", "Carousel_only"}),
    "partition": (_frame, dict(n_supply_points=2, sp_mode="partition",
                               helix_threshold=30.0, enable_rebalancer=False),
                  {"Helix_only", "Carousel_only"}),
    "fixed": (_frame, dict(op_mode=FIXED_MODE, fixed_machines=((1, 1, 0, 0, 0, 0),),
                           fixed_headroom_pct=90.0, fixed_allow_spill=False),
              {"Helix_only", "Not_placed"}),
    "bulk": (_bulk_frame, dict(enable_bulk_routing=True), {"Bulk_Routed"}),
}


def _plan(df, **kw):
    return run_plan(df, pd.DataFrame(), _params(df, **kw))


def _build(res, *, bulk):
    empty = pd.DataFrame()
    ov = {"rows_touched": 0, "unmatched_overrides": [], "invalid_overrides": [],
          "applied_overrides": []}
    raw, problems, _p, _c, notes = build_result_workbook(
        work=res.work, df_summary=empty, df_audit=empty, df_bucket_compare=empty,
        presentation_compact_df=empty, presentation_detail_df=empty,
        dist_cat_rows=empty, dist_cat_vol=empty, dist_cabtype=empty,
        dist_system=empty, include_planogram=False, include_technical=True,
        ktc_id="191", apply_overrides_ui=False, enable_bulk_routing=bulk,
        multiple_listings=False, consumption_period_months=16.0,
        content_key="t", _df_run_meta=empty, _bucket_plans=res.bucket_plans,
        _listings_arg=None, _listings_in_data=["Tools"], _base_info=None,
        _vend_stats=res.vend_stats, _override_stats=ov,
    )
    return load_workbook(BytesIO(raw)), problems, notes


def _frames(wb):
    out = {}
    for ws in wb.worksheets:
        rows = list(ws.values)
        if rows:
            out[ws.title] = pd.DataFrame(rows[1:], columns=rows[0])
    return out


def _numbered(frames):
    """The row sheets that carry a KROMI number, Result and Article setup aside."""
    return {name: f for name, f in frames.items()
            if "Kromi_Art_No" in f.columns and name not in ("Result", "Article setup")}


def _first_number_by_code(result):
    return result.drop_duplicates("Code").set_index("Code")["Kromi_Art_No"]


@pytest.mark.parametrize("regime", sorted(REGIMES))
def test_every_sheet_shows_the_result_number(regime):
    make, settings, reached = REGIMES[regime]
    res = _plan(make(), **settings)
    wb, problems, _notes = _build(res, bulk=bool(settings.get("enable_bulk_routing")))
    assert problems == [], problems
    frames = _frames(wb)
    result = frames["Result"]
    assert not result.duplicated(KEYS).any()
    sheets = _numbered(frames)
    # The plan reaches the sheets it is meant to test, with rows on them.
    assert all(len(sheets.get(name, ())) > 0 for name in reached), sorted(sheets)
    ref = result.set_index(KEYS)["Kromi_Art_No"]
    wrong = {}
    for name, frame in sheets.items():
        got = frame.set_index(KEYS)["Kromi_Art_No"]
        bad = [f"{code} SP {sp}: {num}, Result {ref.get((lst, code, sp))}"
               for (lst, code, sp), num in got.items() if ref.get((lst, code, sp)) != num]
        if bad:
            wrong[name] = bad
    assert wrong == {}


def test_the_article_setup_and_the_takeover_sheet_show_the_result_number():
    res = _plan(_frame(stock=True), helix_threshold=30.0, enable_rebalancer=False)
    wb, problems, _notes = _build(res, bulk=False)
    assert problems == [], problems
    frames = _frames(wb)
    first = _first_number_by_code(frames["Result"])
    setup = frames["Article setup"]
    own = setup[setup["Property"] == "Customer property"]
    assert len(own) == len(first)
    assert {c: n for c, n in zip(own["Customer article No"], own["Kromi_Art_No"])} \
        == first.to_dict()
    takeover = [f for name, f in frames.items() if name.startswith(SHEET_PREFIX)]
    assert takeover
    for sheet in takeover:
        assert list(sheet["Cust. Prop. Art. Nr."]) \
            == [first[c] for c in sheet["Kunden Art. Nr."]]


def _overflow_frame():
    # 110 Kanban rows in the dimension group 19-1250: the two-digit variant
    # field holds 100, so the plan cannot be numbered. 50 of them are routed
    # to bulk; that subset alone would fit.
    base = _boundary_frame().iloc[[13]]          # T014: two pieces, Kanban
    rows = []
    for i in range(110):
        row = base.copy()
        bulk = i >= 60
        row["Code"] = f"G{i:03d}"
        row["SupplierCode"] = f"S{i:03d}"
        row["Description"] = "Disque abrasif 125mm" if bulk else "Grinding wheel 125mm"
        row["ToolClass"] = "abrasive_disc" if bulk else "grinding_wheel"
        row["ProductCategory"] = "abrasives"
        rows.append(row)
    return pd.concat(rows, ignore_index=True)


def test_a_plan_that_cannot_be_numbered_shows_no_number_on_any_sheet():
    res = _plan(_overflow_frame(), enable_bulk_routing=True)
    assert res.vend_stats["routed_rows"] == 50
    wb, _problems, notes = _build(res, bulk=True)
    frames = _frames(wb)
    assert "Bulk_Routed" in frames and len(frames["Bulk_Routed"]) == 50
    assert "KROMI article numbers were not generated" in notes
    assert [n for n, f in frames.items() if "Kromi_Art_No" in f.columns] == []
    assert "Article setup" not in frames
