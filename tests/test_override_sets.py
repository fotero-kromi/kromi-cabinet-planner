"""Phase 4 override-set tests.

A saved set must round-trip to the engine's wide format and apply through the
real apply_overrides, so a recompute can draw overrides from the database
instead of a CSV. Also covers scope listing, latest-per-scope, and deactivation.
"""

import os

import pandas as pd
import pytest

from db import store
from db.override_sets import (
    save_override_set, get_override_set, override_set_as_dataframe,
    list_override_sets, latest_override_set, deactivate_override_set,
    delete_override_set, delete_override_set_row, update_override_set,
    format_override_set_label,
)
from engine.constants import OVERRIDE_COLUMNS
from engine.overrides import apply_overrides


@pytest.fixture()
def conn(tmp_path):
    c = store.init_db(os.path.join(str(tmp_path), "ov.db"))
    yield c
    c.close()


def _overrides_df():
    return pd.DataFrame([
        {"code": "A100", "listing": "Tools", "size_category_override": "M",
         "note": "too big for Carousel", "reviewed_by": "tester"},
        {"code": "B200", "listing": "Tools", "cabinet_type_override": "Helix"},
    ])


# --- save / read round-trip ---

def test_save_and_get_round_trip(conn):
    set_id = save_override_set(
        conn, customer="PlantA", site="P1", reviewer_name="tester",
        notes="post-review fixes", overrides_df=_overrides_df(),
    )
    got = get_override_set(conn, set_id)
    assert got["customer"] == "PlantA"
    assert got["site"] == "P1"
    assert got["reviewer_name"] == "tester"
    assert got["notes"] == "post-review fixes"

    ov = got["overrides"]
    assert list(ov.columns) == OVERRIDE_COLUMNS
    by_code = {r["code"]: r for r in ov.to_dict("records")}
    assert by_code["A100"]["size_category_override"] == "M"
    assert by_code["A100"]["note"] == "too big for Carousel"
    assert by_code["B200"]["cabinet_type_override"] == "Helix"
    # untouched fields are blank, not missing
    assert by_code["B200"]["size_category_override"] == ""


def test_blank_fields_are_not_stored(conn):
    df = pd.DataFrame([
        {"code": "A1", "listing": "Tools", "size_category_override": "M",
         "cabinet_type_override": "", "note": None, "pack_units_override": float("nan")},
    ])
    set_id = save_override_set(conn, customer="C", site="S", overrides_df=df)
    rows = conn.execute(
        "SELECT field FROM overrides WHERE set_id = ?", (set_id,)
    ).fetchall()
    fields = {r["field"] for r in rows}
    assert "size_category_override" in fields
    assert "listing" in fields
    # blanks / NaN / None skipped
    assert "cabinet_type_override" not in fields
    assert "note" not in fields
    assert "pack_units_override" not in fields


def test_empty_overrides_creates_set_with_no_rows(conn):
    set_id = save_override_set(conn, customer="C", site="S", overrides_df=pd.DataFrame())
    assert get_override_set(conn, set_id)["customer"] == "C"
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM overrides WHERE set_id = ?", (set_id,)
    ).fetchone()["n"]
    assert n == 0


# --- the critical test: a stored set applies through the real engine ---

def test_stored_set_applies_through_real_engine(conn):
    set_id = save_override_set(
        conn, customer="PlantA", site="P1", overrides_df=_overrides_df(),
    )
    ov_df = override_set_as_dataframe(conn, set_id)

    work = pd.DataFrame([
        {"Code": "A100", "Listing": "Tools", "SizeCategory": "S",
         "ProductCategory": "drills", "PackUnits": 10},
        {"Code": "B200", "Listing": "Tools", "SizeCategory": "L",
         "ProductCategory": "holders", "PackUnits": 1},
        {"Code": "Z999", "Listing": "Tools", "SizeCategory": "S",
         "ProductCategory": "other", "PackUnits": 1},
    ])
    out, stats = apply_overrides(work, ov_df)
    by_code = {r["Code"]: r for r in out.to_dict("records")}

    # A100's size override took effect through the engine's own path.
    assert by_code["A100"]["SizeCategory"] == "M"
    assert by_code["A100"]["Override_Applied"] == True  # noqa: E712
    # B200 got a cabinet-type override.
    assert by_code["B200"]["CabinetType"] == "Helix"
    assert by_code["B200"]["Override_Applied"] == True  # noqa: E712
    # An untouched tool is left alone.
    assert by_code["Z999"]["Override_Applied"] == False  # noqa: E712
    assert stats["rows_touched"] == 2


# --- scope listing / latest / deactivation ---

def test_list_override_sets_scope_and_count(conn):
    save_override_set(conn, customer="PlantA", site="P1", overrides_df=_overrides_df())
    save_override_set(conn, customer="PlantB", site="P2", overrides_df=_overrides_df())
    save_override_set(conn, customer="PlantA", site="P3", overrides_df=pd.DataFrame(
        [{"code": "X", "listing": "Tools", "size_category_override": "L"}]
    ))

    all_sets = list_override_sets(conn)
    assert len(all_sets) == 3
    # newest first
    assert all_sets[0]["created_at"] >= all_sets[-1]["created_at"]

    plant_a = list_override_sets(conn, customer="planta")
    assert len(plant_a) == 2

    # override_count is distinct tools touched
    one_tool = [s for s in all_sets if s["site"] == "P3"][0]
    assert one_tool["override_count"] == 1
    two_tool = [s for s in all_sets if s["site"] == "P1"][0]
    assert two_tool["override_count"] == 2


def test_latest_override_set_returns_newest(conn):
    first = save_override_set(conn, customer="PlantA", site="P1", overrides_df=_overrides_df())
    second = save_override_set(conn, customer="PlantA", site="P1", overrides_df=_overrides_df())
    latest = latest_override_set(conn, customer="PlantA", site="P1")
    assert latest == second
    assert latest != first
    # case-insensitive scope match
    assert latest_override_set(conn, customer="planta", site="p1") == second
    # unknown scope
    assert latest_override_set(conn, customer="Nope", site="None") is None


def test_deactivate_excludes_from_latest_and_list(conn):
    s1 = save_override_set(conn, customer="PlantA", site="P1", overrides_df=_overrides_df())
    s2 = save_override_set(conn, customer="PlantA", site="P1", overrides_df=_overrides_df())
    assert latest_override_set(conn, customer="PlantA", site="P1") == s2
    deactivate_override_set(conn, s2)
    # latest now falls back to the still-active older set
    assert latest_override_set(conn, customer="PlantA", site="P1") == s1
    # deactivated set is excluded from the active listing but visible when asked
    active = list_override_sets(conn, customer="PlantA")
    assert all(s["set_id"] != s2 for s in active)
    everything = list_override_sets(conn, customer="PlantA", active_only=False)
    assert any(s["set_id"] == s2 for s in everything)


# --- hard delete: whole sets and individual rows ---

def test_delete_override_set_removes_set_and_all_rows(conn):
    set_id = save_override_set(conn, customer="PlantA", site="P1", overrides_df=_overrides_df())
    assert len(override_set_as_dataframe(conn, set_id)) == 2
    assert delete_override_set(conn, set_id) is True
    assert get_override_set(conn, set_id) is None
    n_rows = conn.execute(
        "SELECT COUNT(*) FROM overrides WHERE set_id = ?", (set_id,)
    ).fetchone()[0]
    assert n_rows == 0


def test_delete_override_set_missing_returns_false(conn):
    assert delete_override_set(conn, 999999) is False


def test_delete_override_set_leaves_other_sets_intact(conn):
    a = save_override_set(conn, customer="PlantA", site="P1", overrides_df=_overrides_df())
    b = save_override_set(conn, customer="PlantB", site="P2", overrides_df=_overrides_df())
    assert delete_override_set(conn, a) is True
    assert get_override_set(conn, a) is None
    assert get_override_set(conn, b) is not None
    assert len(override_set_as_dataframe(conn, b)) == 2


def test_delete_override_row_removes_one_tool_only(conn):
    set_id = save_override_set(conn, customer="PlantA", site="P1", overrides_df=_overrides_df())
    n_removed = delete_override_set_row(conn, set_id, "A100")
    assert n_removed >= 1
    codes = list(override_set_as_dataframe(conn, set_id)["code"])
    assert "A100" not in codes
    assert "B200" in codes


def test_delete_override_row_missing_tool_returns_zero(conn):
    set_id = save_override_set(conn, customer="PlantA", site="P1", overrides_df=_overrides_df())
    assert delete_override_set_row(conn, set_id, "NOPE") == 0
    assert len(override_set_as_dataframe(conn, set_id)) == 2


def test_delete_override_row_strips_whitespace(conn):
    set_id = save_override_set(conn, customer="PlantA", site="P1", overrides_df=_overrides_df())
    assert delete_override_set_row(conn, set_id, "  A100  ") >= 1
    assert "A100" not in list(override_set_as_dataframe(conn, set_id)["code"])


def test_delete_last_row_leaves_empty_set_present(conn):
    set_id = save_override_set(conn, customer="PlantA", site="P1", overrides_df=_overrides_df())
    delete_override_set_row(conn, set_id, "A100")
    delete_override_set_row(conn, set_id, "B200")
    assert get_override_set(conn, set_id) is not None
    assert len(override_set_as_dataframe(conn, set_id)) == 0


# --- update in place (v33.67: no duplicate sets) ---

def _updated_df():
    """A second, different correction frame for the same scope."""
    return pd.DataFrame([
        {"code": "A100", "listing": "Tools", "size_category_override": "L",
         "note": "revised after re-review", "reviewed_by": "tester"},
        {"code": "C300", "listing": "Tools", "cabinet_type_override": "Carousel"},
    ])


def test_update_keeps_same_set_id_and_count(conn):
    """Updating a set must reuse its id and never create a second set, so the
    scope holds exactly one set instead of piling up duplicates."""
    set_id = save_override_set(
        conn, customer="PlantA", site="P1", overrides_df=_overrides_df()
    )
    before = list_override_sets(conn, customer="PlantA", site="P1")
    assert len(before) == 1

    ok = update_override_set(
        conn, set_id, customer="PlantA", site="P1",
        reviewer_name="tester", notes="round 2", overrides_df=_updated_df(),
    )
    assert ok is True

    after = list_override_sets(conn, customer="PlantA", site="P1")
    assert len(after) == 1
    assert after[0]["set_id"] == set_id


def test_update_replaces_rows(conn):
    """The old override rows are gone and the new ones are present; a code that
    was dropped from the new frame must not survive in the set."""
    set_id = save_override_set(
        conn, customer="PlantA", site="P1", overrides_df=_overrides_df()
    )
    update_override_set(
        conn, set_id, customer="PlantA", site="P1",
        reviewer_name="tester", notes=None, overrides_df=_updated_df(),
    )
    ov = override_set_as_dataframe(conn, set_id)
    by_code = {r["code"]: r for r in ov.to_dict("records")}
    assert set(by_code.keys()) == {"A100", "C300"}        # B200 dropped, C300 added
    assert by_code["A100"]["size_category_override"] == "L"   # value replaced (was M)
    assert by_code["A100"]["note"] == "revised after re-review"
    assert by_code["C300"]["cabinet_type_override"] == "Carousel"


def test_update_refreshes_metadata(conn):
    set_id = save_override_set(
        conn, customer="PlantA", site="P1", reviewer_name="orig",
        notes="first", overrides_df=_overrides_df(),
    )
    update_override_set(
        conn, set_id, customer="PlantA", site="P1",
        reviewer_name="tester", notes="second", overrides_df=_updated_df(),
    )
    got = get_override_set(conn, set_id)
    assert got["reviewer_name"] == "tester"
    assert got["notes"] == "second"


def test_update_missing_set_returns_false_and_creates_nothing(conn):
    ok = update_override_set(
        conn, 9999, customer="PlantA", site="P1",
        reviewer_name="tester", notes=None, overrides_df=_updated_df(),
    )
    assert ok is False
    assert list_override_sets(conn, customer="PlantA", site="P1") == []


def test_update_round_trips_through_apply_overrides(conn):
    """A set updated in place still reconstructs to the engine wide shape and
    applies, exactly like a freshly saved set."""
    set_id = save_override_set(
        conn, customer="PlantA", site="P1", overrides_df=_overrides_df()
    )
    update_override_set(
        conn, set_id, customer="PlantA", site="P1",
        reviewer_name="tester", notes=None, overrides_df=_updated_df(),
    )
    wide = override_set_as_dataframe(conn, set_id)
    assert list(wide.columns) == OVERRIDE_COLUMNS
    work = pd.DataFrame([
        {"Code": "A100", "Listing": "Tools", "SizeCategory": "S",
         "ProductCategory": "drills", "PackUnits": 10},
        {"Code": "C300", "Listing": "Tools", "SizeCategory": "M",
         "ProductCategory": "drills", "PackUnits": 1},
    ])
    out, _stats = apply_overrides(work, wide)
    by_code = {r["Code"]: r for r in out.to_dict("records")}
    # The updated set's corrections reached the engine: A100 resized to L,
    # C300 pinned to a Carousel.
    assert by_code["A100"]["SizeCategory"] == "L"
    assert by_code["C300"]["CabinetType"] == "Carousel"


# --- shared set-label helper (v33.70: de-duplicate the picker label) ---

def test_label_full():
    row = {"set_id": 5, "created_at": "2026-06-23T11:48:30",
           "override_count": 2, "reviewer_name": "tester"}
    assert format_override_set_label(row) == "#5 · 2026-06-23 11:48 · 2 tool(s) · tester"


def test_label_without_reviewer():
    row = {"set_id": 7, "created_at": "2026-06-23T09:00:00",
           "override_count": 1, "reviewer_name": None}
    assert format_override_set_label(row) == "#7 · 2026-06-23 09:00 · 1 tool(s)"


def test_label_handles_missing_created_at():
    # None created_at must not render the literal "None"; the date segment is
    # left blank, matching the picker's old None-guard.
    row = {"set_id": 9, "created_at": None, "override_count": 3, "reviewer_name": ""}
    assert format_override_set_label(row) == "#9 ·  · 3 tool(s)"
