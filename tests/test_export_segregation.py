"""Segregation behaviour of the export shaper (v33.83).

These mirror the per-segment column dropping seen in real planner output: the
KTC sheet keeps both cabinet columns, the Kanban sheet drops both (no cabinet),
the Helix sheet drops the carousel column, and the Carousel sheet drops the helix
column. The data here is synthetic; only the structure matches production.
"""

import pandas as pd

from engine.export_shaping import user_view

# columns that survive in real output, in canonical order
_COLS = ["Listing", "Code", "Kromi_Art_No", "Description", "SupplierCode",
         "ProductCategory", "ToolClass", "SizeCategory", "PackUnits",
         "Consumption_pcs", "Monthly_pcs", "Monthly_packs", "System", "SupplyPoint",
         "CabinetType", "Spirals_needed", "Carousel_stockpiles"]


def _result_frame():
    """A small result frame: KTC items split into Helix and Carousel, plus Kanban."""
    rows = []
    # Helix KTC rows: spirals set, no carousel stockpiles
    for i in range(3):
        rows.append(dict(Listing="Tools", Code=f"H{i}", Kromi_Art_No=f"K{i}", Description="drill",
                         SupplierCode="SC", ProductCategory="drills", ToolClass="drill",
                         SizeCategory="M", PackUnits=1, Consumption_pcs=80, Monthly_pcs=5.0,
                         Monthly_packs=5.0, System="KTC", SupplyPoint=1, CabinetType="Helix",
                         Spirals_needed=2, Carousel_stockpiles=0))
    # Carousel KTC rows: stockpiles set, no spirals
    for i in range(2):
        rows.append(dict(Listing="Tools", Code=f"C{i}", Kromi_Art_No=f"K1{i}", Description="insert",
                         SupplierCode="SC", ProductCategory="inserts", ToolClass="insert",
                         SizeCategory="S", PackUnits=10, Consumption_pcs=160, Monthly_pcs=10.0,
                         Monthly_packs=1.0, System="KTC", SupplyPoint=1, CabinetType="Carousel",
                         Spirals_needed=0, Carousel_stockpiles=3))
    # Kanban rows: no cabinet, no spirals, no stockpiles
    for i in range(5):
        rows.append(dict(Listing="Tools", Code=f"B{i}", Kromi_Art_No=f"K2{i}", Description="tap",
                         SupplierCode="SC", ProductCategory="taps", ToolClass="tap",
                         SizeCategory="", PackUnits=1, Consumption_pcs=8, Monthly_pcs=0.5,
                         Monthly_packs=0.5, System="Kanban", SupplyPoint=1, CabinetType="",
                         Spirals_needed=0, Carousel_stockpiles=0))
    return pd.DataFrame(rows, columns=_COLS)


def test_ktc_segment_keeps_both_cabinet_columns():
    res = _result_frame()
    ktc = user_view(res[res["System"] == "KTC"])
    assert "Spirals_needed" in ktc.columns
    assert "Carousel_stockpiles" in ktc.columns


def test_kanban_segment_drops_both_cabinet_columns():
    res = _result_frame()
    kanban = user_view(res[res["System"] == "Kanban"])
    assert "Spirals_needed" not in kanban.columns
    assert "Carousel_stockpiles" not in kanban.columns
    # SizeCategory is blank for every Kanban row, so it drops too
    assert "SizeCategory" not in kanban.columns


def test_helix_segment_drops_carousel_keeps_spirals():
    res = _result_frame()
    helix = user_view(res[res["CabinetType"] == "Helix"])
    assert "Spirals_needed" in helix.columns
    assert "Carousel_stockpiles" not in helix.columns


def test_carousel_segment_drops_spirals_keeps_stockpiles():
    res = _result_frame()
    car = user_view(res[res["CabinetType"] == "Carousel"])
    assert "Spirals_needed" not in car.columns
    assert "Carousel_stockpiles" in car.columns


def test_segment_row_counts_are_preserved():
    res = _result_frame()
    assert len(user_view(res[res["System"] == "KTC"])) == 5
    assert len(user_view(res[res["System"] == "Kanban"])) == 5
    assert len(user_view(res[res["CabinetType"] == "Helix"])) == 3
    assert len(user_view(res[res["CabinetType"] == "Carousel"])) == 2


def test_column_count_pattern_matches_segmentation():
    # the same shape relationship seen in real output: KTC widest, Kanban narrowest
    res = _result_frame()
    n_ktc = len(user_view(res[res["System"] == "KTC"]).columns)
    n_kanban = len(user_view(res[res["System"] == "Kanban"]).columns)
    n_helix = len(user_view(res[res["CabinetType"] == "Helix"]).columns)
    n_car = len(user_view(res[res["CabinetType"] == "Carousel"]).columns)
    assert n_ktc > n_helix == n_car > n_kanban


def test_full_result_keeps_every_populated_column():
    res = _result_frame()
    full = user_view(res)
    # both cabinet columns are populated somewhere in the full frame
    assert "Spirals_needed" in full.columns and "Carousel_stockpiles" in full.columns


def test_audit_columns_never_appear_in_any_segment():
    res = _result_frame()
    res["AI_reason"] = "audit"
    res["Override_note"] = "x"
    for mask in [res["System"] == "KTC", res["System"] == "Kanban",
                 res["CabinetType"] == "Helix", res["CabinetType"] == "Carousel"]:
        cols = user_view(res[mask]).columns
        assert "AI_reason" not in cols and "Override_note" not in cols


def test_idempotent_on_already_shaped_frame():
    res = _result_frame()
    once = user_view(res)
    twice = user_view(once)
    assert list(once.columns) == list(twice.columns)
    assert len(once) == len(twice)


def test_canonical_order_preserved_in_every_segment():
    res = _result_frame()
    for mask in [res["System"] == "KTC", res["CabinetType"] == "Helix",
                 res["CabinetType"] == "Carousel"]:
        cols = list(user_view(res[mask]).columns)
        assert cols == [c for c in _COLS if c in cols]


def test_empty_segment_yields_header_only_frame():
    res = _result_frame()
    empty = user_view(res[res["System"] == "Locker"])  # no such rows
    assert len(empty) == 0
    assert list(empty.columns) == [c for c in _COLS if c in res.columns]


def test_single_row_segment_keeps_its_populated_columns():
    res = _result_frame()
    one = res[res["Code"] == "C0"]
    shaped = user_view(one)
    assert "Carousel_stockpiles" in shaped.columns
    assert "Spirals_needed" not in shaped.columns  # this single carousel row has 0 spirals
