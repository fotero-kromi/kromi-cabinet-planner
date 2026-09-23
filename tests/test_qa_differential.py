"""Differential QA verification of column mappings and sidebar controls.

Crystallises the headline findings of the column-mapping and control QA campaign.
Each tested mapping or control is driven through the page's real reload path on an
enriched copy of a real customer file (deterministically augmented with duplicate
rows and, where a feature needs one, a synthetic column), and the differential
effect is asserted directly against the persisted plan in the database. AI is
bypassed by injecting an empty stored-classification map, so the deterministic
classifier and the mapped columns drive every result.

Each assertion is auto-detect-independent: a differential toggles a control while
the column mapping stays fixed across both runs, and the system-type check uses a
within-run per-row correspondence rather than a remap. So none of these tests
depends on the reload seed winning over header auto-detection.

Gated on KROMI_RAW_INPUT_XLSX (the raw consumption workbook). No ground truth is
needed: every assertion is a toggle-on vs toggle-off differential or a within-run
correspondence, not a comparison to a stored Result. No customer identifier lives
in this test; only the German source field names do.
"""

import os
import sqlite3
from io import BytesIO

import pandas as pd
import pytest

from engine.run_restore import build_seed
from tests._paths import PLANNER_PAGE

_RAW = os.environ.get("KROMI_RAW_INPUT_XLSX", "")
_HAVE_RAW = bool(_RAW and os.path.exists(_RAW))

# Real raw field names (German source headers, not customer identifiers).
_CODE = "WZIntNr"
_DESC = "WZBez"
_CONS = "Consumption Last 16 Months"
_STDSPECIAL = "WZArtID (1Standard/2Sonder)"
# Synthetic, auto-detectable columns added only when a test needs them.
_YEAR = "TestYear"
_SYSTYP = "TestSystemType"

_SHEET = "Sheet1"
_LATEST_YEAR = 2026
_N_DUPS = 12

# Every test maps the three required fields plus the real Standard/Special column,
# so the standard/special flag is consistently set and the coverage controls render.
_MAP_BASE = {"cm_code": _CODE, "cm_desc1": _DESC, "cm_cons": _CONS,
             "cm_stdspecial": _STDSPECIAL}


def _enriched_bytes(*, with_year=False, with_systyp=False, n_dups=0):
    """Raw Sheet1 plus optional synthetic columns and duplicate rows, as xlsx
    bytes. Returns (bytes, columns, n_original_rows, n_latest_year_rows).

    Duplicate rows copy the first ``n_dups`` codes at half consumption, so
    deduplication by code collapses exactly ``n_dups`` rows. TestYear cycles
    2024/2025/2026 over the originals (duplicates carry 2023, an older year that
    "keep latest year only" drops). TestSystemType cycles blank/blank/KTC/Kanban,
    so the KTC marker forces a vending machine on a quarter of the rows.
    """
    base = pd.ExcelFile(_RAW).parse(_SHEET).reset_index(drop=True)
    n = len(base)
    if with_year:
        base[_YEAR] = [(2024, 2025, _LATEST_YEAR)[i % 3] for i in range(n)]
    if with_systyp:
        base[_SYSTYP] = [("", "", "KTC", "Kanban")[i % 4] for i in range(n)]

    frames = [base]
    if n_dups > 0:
        dup = base.head(n_dups).copy()
        dup[_CONS] = pd.to_numeric(dup[_CONS], errors="coerce").fillna(0.0) / 2.0
        if with_year:
            dup[_YEAR] = 2023
        frames.append(dup)
    out = pd.concat(frames, ignore_index=True)

    n_latest = int((base[_YEAR] == _LATEST_YEAR).sum()) if with_year else 0

    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        out.to_excel(writer, index=False, sheet_name=_SHEET)
    return bio.getvalue(), list(out.columns), n, n_latest


def _drive(monkeypatch, db_path, enriched, raw_cols, mapping, controls, pending=None):
    """Drive the page's reload path once, persisting the plan to ``db_path``.

    ``mapping`` holds cm_* keys, ``controls`` holds ks_*/cov_* keys; ``pending``
    (if given) is a live technician-override map applied via the editor path. The
    reload context carries an empty classification map, so no model call happens.
    """
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("KROMI_DB_PATH", db_path)
    ui_state = {**mapping, **controls, "ks_sheet_tools": _SHEET}
    restore = build_seed(ui_state, raw_cols)
    restore["ks_hide_optional"] = False
    restore["ks_ai_colmap"] = False
    # The real Standard/Special column is present and mapped in every test, so the
    # coverage split and the special-to-KTC control render on the first pass.
    restore["_std_special_mapped"] = _STDSPECIAL in raw_cols

    at = AppTest.from_file(PLANNER_PAGE, default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": enriched, "filename": "input.xlsx",
        "customer": "TestCustomer", "site": "TestSite",
        "classifications": {}, "override_mode": "none", "override_set_id": None,
    }
    at.session_state["_pending_restore"] = restore
    if pending is not None:
        # Pre-seed the file signature so the file-change guard does not clear the
        # editor's pending map before the compute pass.
        at.session_state["_apply_set_file_sig"] = ("input.xlsx", len(enriched))
        at.session_state["_pending_overrides"] = pending
    at.run()                                    # pass 1: seed mapping + controls
    at.session_state["_force_run"] = True
    if pending is not None:
        at.session_state["_pending_overrides"] = pending
    at.run()                                    # pass 2: execute the pipeline
    assert not at.exception, f"page raised: {at.exception}"
    return at


def _count(db_path, where=""):
    sql = "SELECT COUNT(*) FROM cabinet_calculations"
    if where:
        sql += " WHERE " + where
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute(sql).fetchone()[0])
    finally:
        conn.close()


def _cabinet_type_counts(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT cabinet_type, COUNT(*) FROM cabinet_calculations "
            "GROUP BY cabinet_type"
        ).fetchall()
    finally:
        conn.close()
    return {r[0]: int(r[1]) for r in rows}


def _rows_with_code(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return pd.read_sql_query(
            "SELECT t.code, t.system_typ, c.system_category, c.cabinet_type, "
            "c.size_category, c.override_applied "
            "FROM cabinet_calculations c "
            "JOIN tool_records t ON c.tool_record_id = t.tool_record_id",
            conn,
        )
    finally:
        conn.close()


@pytest.mark.skipif(not _HAVE_RAW, reason="set KROMI_RAW_INPUT_XLSX to run")
def test_dedup_mode_collapses_duplicate_codes(monkeypatch, tmp_path):
    enriched, cols, n_orig, _ = _enriched_bytes(n_dups=_N_DUPS)
    _drive(monkeypatch, str(tmp_path / "nd.db"), enriched, cols,
           _MAP_BASE, {"ks_dedup_mode": "No deduplication"})
    n_none = _count(str(tmp_path / "nd.db"))
    _drive(monkeypatch, str(tmp_path / "bc.db"), enriched, cols,
           _MAP_BASE, {"ks_dedup_mode": "Deduplicate by Code"})
    n_code = _count(str(tmp_path / "bc.db"))
    assert n_none == n_orig + _N_DUPS          # the duplicate rows are present
    assert n_code == n_orig                    # dedup by code removes exactly them
    assert n_none - n_code == _N_DUPS


@pytest.mark.skipif(not _HAVE_RAW, reason="set KROMI_RAW_INPUT_XLSX to run")
def test_year_filter_keeps_only_latest_year(monkeypatch, tmp_path):
    enriched, cols, n_orig, n_latest = _enriched_bytes(with_year=True, n_dups=0)
    mapping = {**_MAP_BASE, "cm_year": _YEAR}
    _drive(monkeypatch, str(tmp_path / "all.db"), enriched, cols, mapping,
           {"ks_dedup_mode": "No deduplication", "ks_year_mode": "Use all rows"})
    n_all = _count(str(tmp_path / "all.db"))
    _drive(monkeypatch, str(tmp_path / "lat.db"), enriched, cols, mapping,
           {"ks_dedup_mode": "No deduplication",
            "ks_year_mode": "Keep latest year only"})
    n_lat = _count(str(tmp_path / "lat.db"))
    assert n_all == n_orig                     # all rows kept
    assert n_lat == n_latest                   # only the latest-year rows survive
    assert 0 < n_lat < n_all


@pytest.mark.skipif(not _HAVE_RAW, reason="set KROMI_RAW_INPUT_XLSX to run")
def test_system_type_column_forces_ktc(monkeypatch, tmp_path):
    enriched, cols, _, _ = _enriched_bytes(with_systyp=True, n_dups=0)
    mapping = {**_MAP_BASE, "cm_systemtyp": _SYSTYP}
    _drive(monkeypatch, str(tmp_path / "st.db"), enriched, cols, mapping, {})
    plan = _rows_with_code(str(tmp_path / "st.db"))
    forced = plan[plan["system_typ"].astype(str).str.upper() == "KTC"]
    assert len(forced) > 0                                 # the marker is present
    assert (forced["system_category"] == "KTC").all()      # every marked row is KTC


@pytest.mark.skipif(not _HAVE_RAW, reason="set KROMI_RAW_INPUT_XLSX to run")
def test_special_ktc_toggle_raises_ktc(monkeypatch, tmp_path):
    enriched, cols, _, _ = _enriched_bytes(n_dups=0)
    _drive(monkeypatch, str(tmp_path / "off.db"), enriched, cols, _MAP_BASE,
           {"ks_special_ktc": False})
    ktc_off = _count(str(tmp_path / "off.db"), "system_category = 'KTC'")
    _drive(monkeypatch, str(tmp_path / "on.db"), enriched, cols, _MAP_BASE,
           {"ks_special_ktc": True})
    ktc_on = _count(str(tmp_path / "on.db"), "system_category = 'KTC'")
    assert ktc_on > ktc_off                    # special tools forced onto vending


@pytest.mark.skipif(not _HAVE_RAW, reason="set KROMI_RAW_INPUT_XLSX to run")
def test_operational_modes_produce_distinct_compositions(monkeypatch, tmp_path):
    enriched, cols, _, _ = _enriched_bytes(n_dups=0)
    modes = {
        "standard": "Standard (best fit per tool)",
        "helix": "Helix only",
        "carousel": "Carousel only",
        "capped": "Helix + Carousel (capped)",
    }
    comp = {}
    for tag, label in modes.items():
        _drive(monkeypatch, str(tmp_path / f"{tag}.db"), enriched, cols,
               _MAP_BASE, {"ks_op_mode": label})
        ct = _cabinet_type_counts(str(tmp_path / f"{tag}.db"))
        comp[tag] = (ct.get("Helix", 0), ct.get("Carousel", 0))
    assert comp["helix"][1] == 0               # Helix-only stores nothing in a Carousel
    assert comp["carousel"][0] == 0            # Carousel-only stores nothing in a Helix
    assert len(set(comp.values())) >= 2        # the modes are not all identical


@pytest.mark.skipif(not _HAVE_RAW, reason="set KROMI_RAW_INPUT_XLSX to run")
def test_live_override_reroutes_only_the_targeted_code(monkeypatch, tmp_path):
    enriched, cols, _, _ = _enriched_bytes(n_dups=0)
    # Standard routing with the rebalancer off, so the override has no cap
    # spillover or consolidation to ripple through: only the targeted row moves.
    controls = {"ks_op_mode": "Standard (best fit per tool)", "ks_rebalancer": False}
    _drive(monkeypatch, str(tmp_path / "base.db"), enriched, cols, _MAP_BASE,
           controls)
    base = _rows_with_code(str(tmp_path / "base.db"))
    candidates = base[
        (base["system_category"] == "KTC")
        & (~base["cabinet_type"].astype(str).str.startswith("Locker"))
    ]
    assert len(candidates) > 0
    target = str(candidates.iloc[0]["code"])

    pending = {target: {"listing": "Tools", "size_category_override": "XXL"}}
    _drive(monkeypatch, str(tmp_path / "ovr.db"), enriched, cols, _MAP_BASE,
           controls, pending=pending)
    after = _rows_with_code(str(tmp_path / "ovr.db"))
    row = after[after["code"] == target].iloc[0]
    assert str(row["cabinet_type"]) == "Locker A"      # XXL routes to a locker
    assert int(row["override_applied"]) == 1           # the override is recorded

    merged = base.merge(after, on="code", suffixes=("_b", "_a"))
    changed = merged[merged["cabinet_type_b"] != merged["cabinet_type_a"]]
    assert len(changed) == 1                            # surgical: only the target moved
