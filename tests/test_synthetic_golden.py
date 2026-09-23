"""Synthetic golden gate (v34.59): the byte-identity gate in every test run.

The golden and export capture tools need a private customer workbook, so they
only ran by hand and never in CI. tools/synthetic_golden.py generates an
anonymous, deterministic catalog and drives the planner page through four
scenarios; the persisted plan tables and the exported workbook of each must
match tests/golden/synthetic_manifest.json. This is the safety net for the
page decomposition (docs/Code_Professionalization_Plan.md, step 0).

If a change is meant to alter results, regenerate the manifest with
``python tools/synthetic_golden.py --update`` and say why in the CHANGELOG.
"""
from io import BytesIO

import pandas as pd
import pytest

from tools import synthetic_golden as sg
from tools.check import find_banned_names


def test_the_catalog_is_deterministic():
    a, b = sg.build_catalog(), sg.build_catalog()
    pd.testing.assert_frame_equal(a, b)
    assert list(a.columns) == sg.COLUMNS


def test_the_catalog_is_anonymous():
    assert find_banned_names(sg.build_catalog().to_csv(index=False)) == []
    assert sg.build_catalog()["Article No"].str.startswith("SYN-").all()


def test_the_catalog_exercises_the_planner():
    df = sg.build_catalog()
    assert len(df) >= 360
    assert (df["Consumption 12 months"] == 0).mean() > 0.15        # missing consumption
    assert df["Article No"].duplicated().sum() == 8                  # repeated articles
    assert set(df["Location"]) == {"Line A", "Line B"}
    assert {"KTC", "", "KTC or Kanban", "Locker"} <= set(df["System"])
    assert (df["Category"] == "Stufenbohrer VHM").any()
    assert df["Description"].str.contains("CNMG").any()               # ISO inserts


def test_the_manifest_covers_every_scenario():
    assert set(sg.load_manifest()["scenarios"]) == set(sg.SCENARIOS)


def _book(meta_rows, value):
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        pd.DataFrame(meta_rows, columns=["Key", "Value"]).to_excel(
            w, index=False, sheet_name="Run_Metadata")
        pd.DataFrame({"Code": ["A"], "Spirals_needed": [value]}).to_excel(
            w, index=False, sheet_name="Result")
    return bio.getvalue()


def test_the_workbook_digest_ignores_only_the_environment():
    base = [["Build", "v1"], ["Timestamp (UTC)", "t1"], ["Model", "m1"], ["KTC threshold", 1]]
    other_env = [["Build", "v2"], ["Timestamp (UTC)", "t2"], ["Model", "m2"],
                 ["KTC threshold", 1]]
    other_setting = [["Build", "v1"], ["Timestamp (UTC)", "t1"], ["Model", "m1"],
                     ["KTC threshold", 2]]
    d = sg.workbook_digest(_book(base, 1))
    assert sg.workbook_digest(_book(other_env, 1)) == d
    assert sg.workbook_digest(_book(other_setting, 1)) != d
    assert sg.workbook_digest(_book(base, 2)) != d


@pytest.mark.parametrize("scenario", list(sg.SCENARIOS))
def test_the_scenario_matches_the_manifest(scenario, tmp_path):
    want = sg.load_manifest()["scenarios"][scenario]
    got = sg.run_scenario(scenario, str(tmp_path))
    changed = sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))
    assert not changed, (
        f"{scenario}: {changed} changed. If this change is intended, run "
        "'python tools/synthetic_golden.py --update' and say why in the CHANGELOG.")
