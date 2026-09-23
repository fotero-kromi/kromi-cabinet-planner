"""Baseline measurement for the I1 run_plan capstone.

Drives the reload path on the real raw workbook exactly like the export
capture, forces one run, then times plain reruns (a widget click's script
pass) with per-stage wall clocks around the cached builders. The point is
to see where the per-click seconds actually go before touching anything.
"""
import os
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
os.environ["KROMI_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "perf.db")
# Drives must never write remembered KTC-IDs into the repository (v34.48).
os.environ.setdefault("KROMI_FILE_PREFS_PATH", str(Path(tempfile.mkdtemp()) / "file_prefs.json"))
RAW = os.environ.get("KROMI_RAW_INPUT_XLSX", "")
if not RAW:
    raise SystemExit("set KROMI_RAW_INPUT_XLSX to a raw customer workbook to run")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

st.cache_data.clear()

from engine.run_restore import build_seed  # noqa: E402

raw_bytes = open(RAW, "rb").read()
raw_cols = list(pd.ExcelFile(RAW).parse("Sheet1").columns)
ui = {"cm_code": "WZIntNr", "cm_desc1": "WZBez",
      "cm_cons": "Consumption Last 16 Months",
      "cm_stdspecial": "WZArtID (1Standard/2Sonder)",
      "ks_sheet_tools": "Sheet1"}
seed = build_seed(ui, raw_cols)
seed["ks_hide_optional"] = False
seed["ks_ai_colmap"] = False
seed["_std_special_mapped"] = True

# per-stage instrumentation: wrap the page-level cached builders after import
TIMES: dict = {}


def _timed(module, name, label):
    orig = getattr(module, name)

    def wrap(*a, **k):
        t0 = time.perf_counter()
        out = orig(*a, **k)
        TIMES.setdefault(label, []).append(time.perf_counter() - t0)
        return out

    setattr(module, name, wrap)


import engine.plan as ep  # noqa: E402

_timed(ep, "run_plan", "engine.run_plan")

from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file("pages/1_Kromi_Planner.py", default_timeout=600)
at.session_state["_reload_ctx"] = {
    "run_id": 1, "bytes": raw_bytes, "filename": "real.xlsx",
    "customer": "PerfBase", "site": "S1",
    "classifications": {}, "override_mode": "none", "override_set_id": None,
}
at.session_state["_pending_restore"] = seed

t0 = time.perf_counter()
at.run()
t_parse = time.perf_counter() - t0

at.session_state["_force_run"] = True
t0 = time.perf_counter()
at.run()
t_run = time.perf_counter() - t0
assert not at.exception, at.exception

# instrument the page module's cached wrappers now that it is imported
page_mod = None
for m in list(sys.modules.values()):
    if getattr(m, "__file__", "") and str(getattr(m, "__file__", "")).endswith("1_Kromi_Planner.py"):
        page_mod = m
        break

for fn, label in [
    ("_cached_run_plan", "page._cached_run_plan"),
    ("_cached_prepare_planning_base", "page._cached_prep"),
    ("_cached_build_result_workbook", "page._cached_workbook"),
]:
    if page_mod is not None and hasattr(page_mod, fn):
        _timed(page_mod, fn, label)

reruns = []
for i in range(3):
    TIMES.clear()
    t0 = time.perf_counter()
    at.run()
    dt = time.perf_counter() - t0
    reruns.append((dt, {k: sum(v) for k, v in TIMES.items()}))
assert not at.exception, at.exception

print(f"BASE parse_pass_s={t_parse:.3f}")
print(f"BASE run_pass_s={t_run:.3f}")
for i, (dt, stage) in enumerate(reruns, 1):
    detail = " ".join(f"{k}={v:.3f}" for k, v in sorted(stage.items()))
    print(f"BASE rerun{i}_s={dt:.3f} {detail}")
print(f"BASE rows_in_raw={len(pd.ExcelFile(RAW).parse('Sheet1'))}")
