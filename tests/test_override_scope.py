"""Override-set scope matching and updates (v34.50, audit C12).

Scope filters used SQL LIKE with the typed text wrapped in wildcards, so a
partial or wildcard customer name listed other customers' sets in the "Update
an existing set" picker, and "Update" replaced the chosen set's rows with the
newest set of the page's scope plus the edits instead of the chosen set's own
rows. Scope matching is now exact (case-insensitive), an empty string means
"no customer" exactly, and updates merge the edits onto the chosen set.
"""
import pandas as pd
import pytest

from db.override_sets import (
    list_override_sets,
    override_set_as_dataframe,
    save_override_set,
    update_override_set_with_edits,
)
from db.store import init_db
from engine.overrides import OVERRIDE_COLUMNS


@pytest.fixture
def conn(tmp_path):
    c = init_db(str(tmp_path / "s.db"))
    yield c
    c.close()


def _rows(*items):
    out = []
    for code, cat in items:
        r = {c: "" for c in OVERRIDE_COLUMNS}
        r.update({"code": code, "listing": "Tools", "product_category_override": cat})
        out.append(r)
    return pd.DataFrame(out, columns=OVERRIDE_COLUMNS)


def test_scope_filter_is_exact_not_substring(conn):
    save_override_set(conn, customer="PlantA", site="P1", overrides_df=_rows(("A", "drills")))
    save_override_set(conn, customer="PlantAB", site="P1", overrides_df=_rows(("B", "mills")))
    assert [s["customer"] for s in list_override_sets(conn, customer="planta")] == ["PlantA"]
    assert list_override_sets(conn, customer="Plant") == []
    assert list_override_sets(conn, customer="%") == []
    assert len(list_override_sets(conn)) == 2          # no filter: everything


def test_empty_string_means_no_customer_exactly(conn):
    save_override_set(conn, customer=None, site=None, overrides_df=_rows(("A", "drills")))
    save_override_set(conn, customer="PlantA", site="P1", overrides_df=_rows(("B", "mills")))
    blank = list_override_sets(conn, customer="", site="")
    assert len(blank) == 1 and blank[0]["customer"] in (None, "")


def test_update_merges_edits_onto_the_chosen_set(conn):
    old = save_override_set(conn, customer="PlantA", site="P1",
                            overrides_df=_rows(("A", "drills"), ("B", "mills")))
    save_override_set(conn, customer="PlantA", site="P1",       # newer set, other rows
                      overrides_df=_rows(("Z", "reamers")))
    n = update_override_set_with_edits(
        conn, old, edits_df=_rows(("C", "taps")),
        customer="PlantA", site="P1", reviewer_name="t", notes=None)
    codes = sorted(override_set_as_dataframe(conn, old)["code"])
    assert codes == ["A", "B", "C"] and n == 3


def test_update_edit_replaces_a_field_of_an_existing_code(conn):
    sid = save_override_set(conn, customer="PlantA", site="P1",
                            overrides_df=_rows(("A", "drills")))
    update_override_set_with_edits(conn, sid, edits_df=_rows(("A", "mills")),
                                   customer="PlantA", site="P1",
                                   reviewer_name=None, notes=None)
    df = override_set_as_dataframe(conn, sid)
    assert list(df["code"]) == ["A"]
    assert df.loc[0, "product_category_override"] == "mills"


def test_update_of_a_missing_set_changes_nothing(conn):
    assert update_override_set_with_edits(
        conn, 999, edits_df=_rows(("A", "drills")), customer="X", site="Y",
        reviewer_name=None, notes=None) == 0
