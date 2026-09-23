"""A manual Helix-fit size fix wins over reused classifications (v34.57).

Since v34.53 a workbook the database already knows reuses its stored
classifications on a fresh run. The plan applied the technician's "Treat as
Helix-fit (M)" fix first and the reuse second, so the reuse put the stored
L/XL size back: the fix was listed as active but changed nothing, and
"Select all and apply" appeared to do nothing.
"""
import pandas as pd

from engine.fixed_config import FIXED_MODE, STATUS_NOT_PLACED
from engine.plan import run_plan
from tests.test_run_plan_equivalence import _boundary_frame, _params


def _row(res, code):
    w = res.work
    return w[w["Code"].astype(str) == code].iloc[0]


def test_manual_fix_beats_the_stored_size():
    df = _boundary_frame()
    p = _params(df, stored_classifications=(("T014", "XL", "holders"),),
                manual_size_fixes=(("T014", "M"),))
    row = _row(run_plan(df, pd.DataFrame(), p), "T014")
    assert row["SizeCategory"] == "M"
    assert row["SizeCategory_Source"] == "Manual (Helix-fit)"


def test_stored_size_still_applies_without_a_fix():
    df = _boundary_frame()
    p = _params(df, stored_classifications=(("T014", "XL", "holders"),))
    row = _row(run_plan(df, pd.DataFrame(), p), "T014")
    assert row["SizeCategory"] == "XL"
    assert row["SizeCategory_Source"] == "Reused from stored run"


def test_fixed_configuration_places_the_fixed_article_in_the_helix():
    """An L Carousel article that found no Carousel space moves into the Helix
    once it is asserted Helix-fit, also when the workbook is a known one."""
    df = _boundary_frame()
    df.loc[df["Code"] == "T003", "SizeCategory"] = "L"
    common = dict(op_mode=FIXED_MODE, fixed_machines=((1, 1, 1, 0, 0, 0),),
                  fixed_headroom_pct=0.0, fixed_allow_spill=True,
                  stored_classifications=(("T003", "L", "drills"),))
    # No Carousel space: every Carousel-routed article needs to move or stays out.
    import engine.fixed_config as fc
    orig = fc.usable_capacity

    def tiny(machines, headroom_pct):
        cap = orig(machines, headroom_pct)
        cap["Carousel"] = 0
        return cap
    fc.usable_capacity = tiny
    try:
        before = _row(run_plan(df, pd.DataFrame(), _params(df, **common)), "T003")
        after = _row(run_plan(df, pd.DataFrame(), _params(
            df, manual_size_fixes=(("T003", "M"),), **common)), "T003")
    finally:
        fc.usable_capacity = orig
    assert before["Placement_Status"] == STATUS_NOT_PLACED
    assert after["Placement_Status"] != STATUS_NOT_PLACED
    assert after["CabinetType"] == "Helix"
