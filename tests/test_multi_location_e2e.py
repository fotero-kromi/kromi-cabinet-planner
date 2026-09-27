"""Articles on several machines through the planner page (v34.63).

End to end with invented data: a location cell may name several machines
("AB-100 + AB 101"); every machine gets its own supply-point dropdown with no
default, "Not planned here" keeps a machine out of the plan, an article is
planned in every supply point its machines map to, its stock is one pool
and it has one number. Machine labels are invented.
"""
import hashlib
import json
from io import BytesIO

import pandas as pd
import pytest
from openpyxl import load_workbook

from engine.run_restore import build_seed
from tests._paths import PLANNER_PAGE

FIXED_LABEL = "Fixed configuration (existing machines)"

# code, area (location), consumption over 16 months, stock, pack unit
_ROWS = [
    ("S01", "AB-100 + AB 101", 3200.0, 50, 1),
    ("S02", "AB-100 +101", 1600.0, 7, 5),
    ("S03", "ab-100 & AB 101", 4800.0, 23, 1),
    ("P04", "AB-100", 800.0, 11, 1),
    ("P05", "AB-101", 960.0, 4, 1),
    ("P06", "AB-100", 640.0, 0, 1),
    ("K07", "AB-100 + AB-101", 0.0, 30, 1),
    ("K08", "AB-101", 0.0, 6, 1),
]


def _xlsx(rows):
    df = pd.DataFrame({
        "ItemCode": [r[0] for r in rows],
        "ItemName": [f"Bohrer D{i + 3},5" for i in range(len(rows))],
        "Cons16": [r[2] for r in rows],
        "Area": [r[1] for r in rows],
        "Qty": [r[3] for r in rows],
        "Pack": [r[4] for r in rows],
    })
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Sheet1")
    return bio.getvalue(), list(df.columns)


def _unsplit(rows):
    """The same list with every article at its first machine only."""
    return [(c, "AB-100" if ("+" in a or "&" in a) else a, u, s, p) for c, a, u, s, p in rows]


class _Drive:
    """One page drive: the AppTest, the downloads and the frames run_plan saw."""

    def __init__(self, monkeypatch, tmp_path, rows, *, controls=None, name="ml"):
        import streamlit as st
        from streamlit.testing.v1 import AppTest

        import engine.plan as ep

        monkeypatch.setenv("KROMI_DB_PATH", str(tmp_path / f"{name}.db"))
        st.cache_data.clear()
        self.plans = []
        orig_plan = ep.run_plan

        def spy_plan(work, ov, params):
            self.plans.append(work.copy())
            return orig_plan(work, ov, params)
        monkeypatch.setattr(ep, "run_plan", spy_plan)

        self.downloads = {}
        orig_dl = st.download_button

        def spy_dl(*args, **kw):
            label = str(kw.get("label", args[0] if args else ""))
            data = kw.get("data", args[1] if len(args) > 1 else None)
            payload = data.getvalue() if hasattr(data, "getvalue") else data
            if isinstance(payload, (bytes, bytearray)):
                self.downloads[label] = bytes(payload)
            return orig_dl(*args, **kw)
        monkeypatch.setattr(st, "download_button", spy_dl)

        raw, cols = _xlsx(rows)
        self.cols = cols
        seed = build_seed({"cm_code": "ItemCode", "cm_desc1": "ItemName", "cm_cons": "Cons16",
                           "ks_sheet_tools": "Sheet1"}, cols)
        seed.update({"ks_hide_optional": False, "ks_ai_colmap": False,
                     "_std_special_mapped": False, "ks_n_sp": 2, **(controls or {})})
        self.at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
        self.at.session_state["_reload_ctx"] = {
            "run_id": 1, "bytes": raw, "filename": f"{name}.xlsx", "customer": "MlCustomer",
            "site": "MlSite", "classifications": {}, "override_mode": "none",
            "override_set_id": None}
        self.at.session_state["_pending_restore"] = seed
        self.at.run()
        assert not self.at.exception, self.at.exception

    def select(self, key, value):
        next(s for s in self.at.selectbox if s.key == key).select(value).run()
        assert not self.at.exception, self.at.exception
        return self

    def map_columns(self, stock=True):
        self.select("cm_program", "Area")
        self.select("cm_pack", "Pack")
        if stock:
            self.select("cm_stock", "Qty")
        return self

    def machines(self, mapping):
        for machine, sp in mapping.items():
            self.select(f"prog_sp::{machine}", sp)
        return self

    def run(self, ktc_id="150"):
        next(t for t in self.at.text_input if t.label == "KTC-ID").input(ktc_id).run()
        self.at.session_state["_force_run"] = True
        self.at.run()
        assert not self.at.exception, self.at.exception
        return self

    def export(self):
        btn = next(b for b in self.at.button if getattr(b, "key", "") == "btn_prepare_exports")
        btn.click()
        self.at.run()
        assert not self.at.exception, self.at.exception
        book = next(b for lbl, b in self.downloads.items() if "plan workbook" in lbl.lower())
        return load_workbook(BytesIO(book))

    def errors(self):
        return " ".join(str(e.value) for e in self.at.error)

    def planned(self):
        return any(str(s.value) == "Planning base summary" for s in self.at.subheader)


def _sheet(wb, name):
    rows = list(wb[name].values)
    return pd.DataFrame(rows[1:], columns=rows[0])


_FIXED = {"ks_op_mode": FIXED_LABEL, "ks_fixed_headroom": 0.0,
          "ks_fixed_helix_1": 1, "ks_fixed_carousel_1": 1,
          "ks_fixed_helix_2": 1, "ks_fixed_carousel_2": 1}


# ---- a multi-machine list in a fixed configuration -----------------------------------------

def test_shared_articles_in_a_fixed_configuration(monkeypatch, tmp_path):
    d = _Drive(monkeypatch, tmp_path, _ROWS, controls=_FIXED)
    d.map_columns().machines({"AB-100": 1, "AB-101": 2}).run()
    captions = " ".join(str(c.value) for c in d.at.caption)
    assert "4 rows name several machines" in captions
    wb = d.export()

    shared = {"S01", "S02", "S03", "K07"}
    sheets = {sp: _sheet(wb, f"Takeover sheet SP {sp}") for sp in (1, 2)}
    for sp, frame in sheets.items():
        codes = frame["Kunden Art. Nr."].astype(str)
        for code in shared:
            assert (codes == code).sum() == 1, (sp, code)
    # the stock over both sheets is the list's stock: nothing counted twice
    total = sum(pd.to_numeric(f["Total"]).sum() for f in sheets.values())
    assert total == sum(r[3] for r in _ROWS)
    for code in shared:
        line = sheets[1][sheets[1]["Kunden Art. Nr."].astype(str) == code]
        assert str(line["Hinweis"].iloc[0]) == "Bestand geteilt mit SP 2"

    result = _sheet(wb, "Result")
    assert set(result["Supply points"][result["Code"].astype(str) == "S01"]) == {"SP 1, SP 2"}
    assert set(result["Machines (source)"][result["Code"].astype(str) == "S02"]) == {"AB-100 +101"}
    meta = {row[0]: row[1] for row in list(wb["Run_Metadata"].values)[1:]}
    assert meta["Rows naming several machines"] == 4
    assert meta["Articles in several supply points"] == 4
    assert meta["Consumption for shared articles"] == "equal share per machine"
    assert meta["Machines not planned"] == "none"
    assert "Extra machines (estimate)" in list(wb["Fixed_Configuration"].values)[0]
    lines = [str(m.value) for m in d.at.markdown]
    assert any(line.startswith("SP 1: ") for line in lines)
    assert any(line.startswith("SP 2: ") for line in lines)

    # numbers: the same as the run with every article at one machine
    u = _Drive(monkeypatch, tmp_path, _unsplit(_ROWS), controls=_FIXED, name="unsplit")
    u.map_columns().machines({"AB-100": 1, "AB-101": 2}).run()
    uwb = u.export()
    pd.testing.assert_frame_equal(_sheet(wb, "Article setup"), _sheet(uwb, "Article setup"))
    want = dict(zip(_sheet(uwb, "Result")["Code"].astype(str),
                    _sheet(uwb, "Result")["Kromi_Art_No"].astype(str)))
    for code, number in zip(result["Code"].astype(str), result["Kromi_Art_No"].astype(str)):
        assert number == want[code], code


# ---- no silent default ----------------------------------------------------------------------

def test_an_unassigned_machine_blocks_the_run_until_it_is_chosen(monkeypatch, tmp_path):
    d = _Drive(monkeypatch, tmp_path, _ROWS)
    d.map_columns(stock=False)
    boxes = {s.key: s for s in d.at.selectbox if str(s.key).startswith("prog_sp::")}
    assert set(boxes) == {"prog_sp::AB-100", "prog_sp::AB-101"}
    assert all(b.value is None for b in boxes.values())          # no SP 1 default
    d.select("prog_sp::AB-100", 1).run()
    assert "unassigned" in d.errors() and "AB-101" in d.errors()
    assert not d.planned()
    d.select("prog_sp::AB-101", 2).run()
    assert "unassigned" not in d.errors()
    assert d.planned()


# ---- not planned here ------------------------------------------------------------------------

_NP_ROWS = [
    ("N01", "AB-100 + AB-102", 1600.0, 10, 1),
    ("N02", "AB-100", 800.0, 3, 1),
    ("N03", "AB-101", 800.0, 3, 1),
]


def test_a_machine_not_planned_here_keeps_its_share_out(monkeypatch, tmp_path):
    d = _Drive(monkeypatch, tmp_path, _NP_ROWS)
    d.map_columns(stock=False).machines({"AB-100": 1, "AB-101": 2, "AB-102": 0}).run()
    assert d.planned() and not d.errors()
    work = d.plans[-1]
    n01 = work[work["Code"] == "N01"]
    assert list(n01["SupplyPoint"]) == [1]
    assert float(n01["Consumption_pcs"].iloc[0]) == pytest.approx(800.0)
    captions = " ".join(str(c.value) for c in d.at.caption)
    assert "Not planned here: AB-102" in captions


def test_an_article_with_only_a_machine_not_planned_blocks_the_run(monkeypatch, tmp_path):
    rows = _NP_ROWS + [("Z99", "AB-102", 500.0, 1, 1)]
    d = _Drive(monkeypatch, tmp_path, rows)
    d.map_columns(stock=False).machines({"AB-100": 1, "AB-101": 2, "AB-102": 0}).run()
    assert "no planned machine" in d.errors() and "'Z99'" in d.errors()
    assert not d.planned()


# ---- restore --------------------------------------------------------------------------------------

def test_a_stored_run_restores_the_machine_mapping_and_the_option(monkeypatch, tmp_path):
    import db as kdb

    d = _Drive(monkeypatch, tmp_path, _NP_ROWS, name="restore")
    d.map_columns(stock=False).machines({"AB-100": 1, "AB-101": 2, "AB-102": 0})
    next(c for c in d.at.checkbox if c.key == "ks_ml_full_consumption").check().run()
    d.run()
    assert float(d.plans[-1].query("Code == 'N01'")["Consumption_pcs"].iloc[0]) == 1600.0

    conn = kdb.init_db(str(tmp_path / "restore.db"))
    run_id = conn.execute("SELECT MAX(run_id) FROM analysis_runs").fetchone()[0]
    ui = json.loads(kdb.get_run(conn, run_id)["settings_json"])["ui_state"]
    conn.close()
    assert ui["prog_sp::AB-102"] == 0 and ui["prog_sp::AB-101"] == 2
    assert ui["ks_ml_full_consumption"] is True

    import streamlit as st
    from streamlit.testing.v1 import AppTest

    st.cache_data.clear()
    raw, cols = _xlsx(_NP_ROWS)
    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": run_id, "bytes": raw, "filename": "restore.xlsx", "customer": "MlCustomer",
        "site": "MlSite", "classifications": {}, "override_mode": "none",
        "override_set_id": None}
    seed = build_seed(ui, cols)
    # Same workbook: keep the restored mapping, as Load & recompute does.
    seed.update({"ks_hide_optional": False, "ks_ai_colmap": False,
                 "_std_special_mapped": False,
                 "_mapping_file_id": ("content", hashlib.sha256(raw).hexdigest())})
    at.session_state["_pending_restore"] = seed
    at.run()
    boxes = {s.key: s.value for s in at.selectbox if str(s.key).startswith("prog_sp::")}
    assert boxes == {"prog_sp::AB-100": 1, "prog_sp::AB-101": 2, "prog_sp::AB-102": 0}
    assert next(c for c in at.checkbox if c.key == "ks_ml_full_consumption").value is True
    assert "unassigned" not in " ".join(str(e.value) for e in at.error)
