"""Golden capture harness for byte-identical before/after baselines.

Drives the page's full deterministic pipeline headlessly on a real raw workbook
(supplied from outside the shipped code via ``KROMI_RAW_INPUT_XLSX``) for a fixed
set of scenarios. Each scenario runs through the page's reload path into a fresh
throwaway database, and the persisted plan is dumped as three deterministic CSVs:

  pertool.csv   -- the final per-tool plan (tool_records JOIN cabinet_calculations)
  buckets.csv   -- the per-bucket cabinet summary (cabinet_plan_summary)
  grand.csv     -- the execution roll-up (engine_executions, content columns only)

A manifest records a SHA-256 per dump plus wall-clock pass timings. Capture once
before a change and once after; identical hashes prove the pipeline delivers the
same plan byte for byte. This is the verification vehicle for the run_plan
capstone and for any future golden-gated change (for example folding the content
hash into the run fingerprint).

AI never runs: the reload context carries an empty classification map, so the
deterministic classifier and the mapped columns drive every value. No customer
identifier lives in this script; only German source field names do.

Usage:
    KROMI_RAW_INPUT_XLSX=/path/to/raw.xlsx python tools/golden_capture.py OUTDIR [LABEL]

Writes OUTDIR/LABEL/<scenario>/{pertool.csv,buckets.csv,grand.csv} and
OUTDIR/LABEL/manifest.json. LABEL defaults to the current build string.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# Drives must never write remembered KTC-IDs into the repository (v34.48).
os.environ.setdefault("KROMI_FILE_PREFS_PATH", str(Path(tempfile.mkdtemp()) / "file_prefs.json"))
from engine.build_info import BUILD                     # noqa: E402
from engine.run_restore import build_seed               # noqa: E402

_SHEET = "Sheet1"

# Real raw field names (German source headers, not customer identifiers).
_MAPPING = {
    "cm_code": "WZIntNr",
    "cm_desc1": "WZBez",
    "cm_cons": "Consumption Last 16 Months",
    "cm_stdspecial": "WZArtID (1Standard/2Sonder)",
    "cm_sup": "WZLiefStamm.LWZBestellNr",
    "cm_site": "Werk",
}

# Scenario -> control overrides on top of the sidebar defaults. "default" runs the
# stock configuration; "loaded" exercises capped mode, a low Helix threshold, bulk
# routing, forced screws/accessories, a 30% buffer, and two replicated supply
# points, so the rebalancer, the carousel cap, and the replicate split all fire.
SCENARIOS: dict[str, dict] = {
    "default": {},
    "loaded": {
        "ks_op_mode": "Helix + Carousel (capped)",
        "ks_helix_threshold": 2.0,
        "ks_bulk_routing": True,
        "ks_force_screws": True,
        "ks_buffer": 30.0,
        "ks_n_sp": 2,
    },
    # The e2e harness's exact control set, so that configuration stays under
    # byte-identical protection independently of the ground-truth workbook.
    "e2e_config": {
        "ks_ktc_threshold": 1.0,
        "ks_helix_threshold": 4.0,
        "ks_consumption_months": 16,
        "ks_overfill": 1.1,
        "ks_min_carousel": 3,
        "cov_days_standard": 18,
        "cov_days_special": 18,
        "ks_reserve": 0.85,
        "ks_max_carousels": 1,
        "ks_op_mode": "Helix + Carousel (capped)",
        "ks_insert_pack": 10,
    },
}

_PERTOOL_SQL = """
SELECT t.line_no, t.code, t.listing, t.raw_consumption, t.pack_units, t.system_typ,
       c.supply_point, c.bucket_label, c.system_category, c.cabinet_type,
       c.size_category, c.product_category, c.spirals_needed, c.carousel_stockpiles,
       c.spiral_capacity, c.monthly_packs, c.target_packs, c.consumption_pcs,
       c.size_issue, c.size_issue_reason, c.override_applied, c.override_fields_json,
       c.restockable, c.restock_slots
FROM cabinet_calculations c
JOIN tool_records t ON c.tool_record_id = t.tool_record_id
ORDER BY t.line_no, t.code, c.supply_point, c.bucket_label, c.calc_id
"""

_BUCKETS_SQL = """
SELECT bucket_label, helix_cabs, carousel_cabs, locker_a, locker_b, locker_c,
       total_cabs, total_spirals, carousel_slots, ktc_count, kanban_count
FROM cabinet_plan_summary
ORDER BY bucket_label, summary_id
"""

# inputs_hash is the archive's duplicate-save key, not a plan result. Since
# v34.54 it includes the build (audit C9), so it changes with every release
# by design and is left out of the golden comparison.
_GRAND_SQL = """
SELECT rows_processed, rebalance_moves, cabinets_saved, size_issues_found,
       grand_total_cabs
FROM engine_executions
ORDER BY execution_id
"""


def _drive(raw_path: str, db_path: str, controls: dict) -> dict:
    """Drive the reload path once against ``db_path``; return pass timings."""
    from streamlit.testing.v1 import AppTest

    raw_bytes = open(raw_path, "rb").read()
    raw_cols = list(pd.ExcelFile(raw_path).parse(_SHEET).columns)

    os.environ["KROMI_DB_PATH"] = db_path
    ui_state = {**_MAPPING, **controls, "ks_sheet_tools": _SHEET}
    restore = build_seed(ui_state, raw_cols)
    restore["ks_hide_optional"] = False
    restore["ks_ai_colmap"] = False
    restore["_std_special_mapped"] = _MAPPING["cm_stdspecial"] in raw_cols

    at = AppTest.from_file("pages/1_Kromi_Planner.py", default_timeout=300)
    at.session_state["_reload_ctx"] = {
        "run_id": 1, "bytes": raw_bytes, "filename": "input.xlsx",
        "customer": "TestCustomer", "site": "TestSite",
        "classifications": {}, "override_mode": "none", "override_set_id": None,
    }
    at.session_state["_pending_restore"] = restore

    timings: dict = {}
    t0 = time.perf_counter()
    at.run()                                    # pass 1: seed mapping + controls
    timings["pass1_gate_s"] = round(time.perf_counter() - t0, 3)

    at.session_state["_force_run"] = True
    t0 = time.perf_counter()
    at.run()                                    # pass 2: execute the pipeline
    timings["pass2_run_s"] = round(time.perf_counter() - t0, 3)
    if at.exception:
        raise RuntimeError(f"page raised during the run pass: {at.exception}")

    # Pass 3 approximates a post-run interaction: a plain rerun with results
    # present. Today this replays the whole pipeline; with a cached run_plan it
    # should approach the render-only floor. The third pass on one AppTest
    # instance has a known persist-path flake, so its failure is recorded rather
    # than raised -- the timing is the point here, not the persist.
    t0 = time.perf_counter()
    try:
        at.run()
        timings["pass3_rerun_s"] = round(time.perf_counter() - t0, 3)
        timings["pass3_exception"] = str(at.exception) if at.exception else ""
    except Exception as exc:                     # noqa: BLE001 - instrument only
        timings["pass3_rerun_s"] = round(time.perf_counter() - t0, 3)
        timings["pass3_exception"] = repr(exc)
    return timings


def _dump(db_path: str, out_dir: Path) -> dict:
    """Dump the three plan tables as deterministic CSVs; return name -> sha256."""
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    hashes: dict = {}
    try:
        for name, sql in [("pertool", _PERTOOL_SQL), ("buckets", _BUCKETS_SQL),
                          ("grand", _GRAND_SQL)]:
            frame = pd.read_sql_query(sql, conn)
            path = out_dir / f"{name}.csv"
            frame.to_csv(path, index=False)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            hashes[name] = {"sha256": digest, "rows": int(len(frame))}
    finally:
        conn.close()
    return hashes


def main(argv: list[str]) -> int:
    raw = os.environ.get("KROMI_RAW_INPUT_XLSX", "")
    if not raw or not os.path.exists(raw):
        print("Set KROMI_RAW_INPUT_XLSX to the raw consumption workbook.")
        return 2
    if len(argv) < 2:
        print(__doc__)
        return 2
    out_root = Path(argv[1])
    label = argv[2] if len(argv) > 2 else BUILD
    out_dir = out_root / label
    out_dir.mkdir(parents=True, exist_ok=True)

    os.chdir(_REPO_ROOT)
    manifest: dict = {
        "label": label,
        "build": BUILD,
        "pandas": pd.__version__,
        "scenarios": {},
    }
    for scenario, controls in SCENARIOS.items():
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / f"golden_{scenario}.db")
            print(f"[{label}] driving scenario '{scenario}' ...", flush=True)
            timings = _drive(raw, db_path, controls)
            hashes = _dump(db_path, out_dir / scenario)
        manifest["scenarios"][scenario] = {"timings": timings, "dumps": hashes}
        for name, info in hashes.items():
            print(f"  {scenario}/{name}: {info['rows']} rows  sha256={info['sha256']}")
        print(f"  timings: {timings}")

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"[{label}] manifest written to {out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
