"""Tests for engine.run_restore — the pure helper that turns a stored run's
captured widget snapshot back into a session_state seed for a recompute.

No Streamlit here: the helper takes a plain mapping of widget values and the
columns present in the file being recomputed, and returns the dict the page
writes into session_state (once) so the controls and the column mapping match
the original run.
"""
import json

import pytest

from engine import run_restore as rr


# --- build_seed: column-mapping validation ----------------------------------

def test_valid_mapping_column_is_kept():
    ui = {"cm_size": "KTC Size"}
    seed = rr.build_seed(ui, available_columns=["Code", "KTC Size", "Bez"])
    assert seed["cm_size"] == "KTC Size"


def test_mapping_column_absent_from_file_is_dropped():
    # Column from a different file must not seed the selectbox (it would not be
    # a valid option); dropping it lets auto-detect run instead.
    ui = {"cm_size": "GoneColumn"}
    seed = rr.build_seed(ui, available_columns=["Code", "Bez"])
    assert "cm_size" not in seed


def test_optional_unmapped_field_keeps_the_sentinel():
    ui = {"cm_prod": rr.NOT_AVAIL}
    seed = rr.build_seed(ui, available_columns=["Code", "Bez"])
    assert seed["cm_prod"] == rr.NOT_AVAIL


def test_optional_none_becomes_sentinel():
    ui = {"cm_year": None}
    seed = rr.build_seed(ui, available_columns=["Code", "Bez"])
    assert seed["cm_year"] == rr.NOT_AVAIL


def test_required_mapping_field_dropped_when_column_absent():
    # A required field (Code) seeded with a missing column must be dropped, not
    # set to the sentinel (the required selectbox has no sentinel option).
    ui = {"cm_code": "GoneCode"}
    seed = rr.build_seed(ui, available_columns=["WZIntNr", "Bez"])
    assert "cm_code" not in seed


def test_required_mapping_field_kept_when_present():
    ui = {"cm_code": "WZIntNr", "cm_desc1": "WZBez", "cm_cons": "Consumption"}
    cols = ["WZIntNr", "WZBez", "Consumption"]
    seed = rr.build_seed(ui, available_columns=cols)
    assert seed["cm_code"] == "WZIntNr"
    assert seed["cm_desc1"] == "WZBez"
    assert seed["cm_cons"] == "Consumption"


# --- build_seed: control passthrough ----------------------------------------

def test_control_values_pass_through():
    ui = {
        "ks_ktc_threshold": 1.0,
        "ks_reserve": 0.85,
        "ks_buffer": 15.0,
        "ks_op_mode": "Helix + Carousel (capped)",
        "ks_max_carousels": 2,
        "ks_rebalancer": True,
    }
    seed = rr.build_seed(ui, available_columns=["Code"])
    for k, v in ui.items():
        assert seed[k] == v


def test_none_control_is_dropped():
    ui = {"ks_reserve": None, "ks_buffer": 15.0}
    seed = rr.build_seed(ui, available_columns=["Code"])
    assert "ks_reserve" not in seed
    assert seed["ks_buffer"] == 15.0


def test_unknown_keys_are_ignored():
    ui = {"some_other_key": 1, "ks_reserve": 0.85}
    seed = rr.build_seed(ui, available_columns=["Code"])
    assert "some_other_key" not in seed
    assert seed["ks_reserve"] == 0.85


def test_empty_inputs_are_safe():
    assert rr.build_seed(None, None) == {}
    assert rr.build_seed({}, []) == {}


# --- capture_ui_state --------------------------------------------------------

def test_capture_snapshots_only_known_keys():
    state = {
        "ks_reserve": 0.85,
        "cm_code": "WZIntNr",
        "irrelevant_widget": "x",
        "_internal_flag": True,
    }
    snap = rr.capture_ui_state(state)
    assert snap == {"ks_reserve": 0.85, "cm_code": "WZIntNr"}


def test_capture_skips_missing_and_nonscalar():
    state = {"ks_buffer": 10.0, "cm_size": ["not", "scalar"]}
    snap = rr.capture_ui_state(state)
    assert snap == {"ks_buffer": 10.0}  # the list value is skipped


def test_capture_is_json_safe_and_round_trips():
    state = {
        "ks_ktc_threshold": 1.0,
        "ks_op_mode": "Standard (best fit per tool)",
        "ks_rebalancer": True,
        "cm_code": "WZIntNr",
        "cm_prod": rr.NOT_AVAIL,
    }
    snap = rr.capture_ui_state(state)
    restored = json.loads(json.dumps(snap))  # survives DB round-trip
    seed = rr.build_seed(restored, available_columns=["WZIntNr", "Bez"])
    assert seed["cm_code"] == "WZIntNr"
    assert seed["cm_prod"] == rr.NOT_AVAIL
    assert seed["ks_op_mode"] == "Standard (best fit per tool)"
    assert seed["ks_rebalancer"] is True


def test_mapping_and_control_key_sets_are_disjoint():
    assert set(rr.MAPPING_KEYS).isdisjoint(set(rr.CONTROL_KEYS))


def test_required_mapping_keys_are_a_subset_of_mapping_keys():
    assert set(rr.REQUIRED_MAPPING_KEYS).issubset(set(rr.MAPPING_KEYS))


# --- DB round-trip: capture -> settings_json -> get_run -> build_seed --------

def test_ui_state_survives_db_round_trip(tmp_path):
    """The captured snapshot must persist through insert_run/get_run on the
    real settings_json column and rebuild the same seed on the far side."""
    import db

    conn = db.init_db(str(tmp_path / "rt.db"))
    file_id = db.upsert_file(
        conn,
        sha256="deadbeef" * 8,
        original_filename="stored_run.xlsx",
        content=b"xlsx-bytes-placeholder",
        byte_size=21,
    )

    # A snapshot as the page would capture it from session_state.
    captured = rr.capture_ui_state({
        "ks_ktc_threshold": 1.0,
        "ks_reserve": 0.85,
        "ks_buffer": 15.0,
        "ks_min_carousel": 3,
        "ks_op_mode": "Helix + Carousel (capped)",
        "ks_max_carousels": 1,
        "cov_days_standard": 20,
        "cov_days_special": 30,
        "cm_code": "WZIntNr",
        "cm_desc1": "WZBez",
        "cm_cons": "Consumption Last 16 Months",
        "cm_sup": "Lieferant",
        "cm_prod": rr.NOT_AVAIL,
    })
    run_id = db.insert_run(
        conn,
        file_id=file_id,
        build_version="v33.55",
        settings_json=json.dumps({"ui_state": captured}, ensure_ascii=False),
    )

    row = db.get_run(conn, run_id)
    assert row is not None
    stored_ui = json.loads(row["settings_json"])["ui_state"]

    file_cols = [
        "WZIntNr", "WZBez", "Consumption Last 16 Months", "Lieferant", "Werk",
    ]
    seed = rr.build_seed(stored_ui, available_columns=file_cols)

    # Controls restored verbatim.
    assert seed["ks_reserve"] == 0.85
    assert seed["ks_op_mode"] == "Helix + Carousel (capped)"
    assert seed["ks_max_carousels"] == 1
    assert seed["cov_days_special"] == 30
    # Required + present optional mapping restored to the stored columns.
    assert seed["cm_code"] == "WZIntNr"
    assert seed["cm_desc1"] == "WZBez"
    assert seed["cm_cons"] == "Consumption Last 16 Months"
    assert seed["cm_sup"] == "Lieferant"
    # Optional field that was unmapped stays the sentinel.
    assert seed["cm_prod"] == rr.NOT_AVAIL
    conn.close()


# --- build_seed: read-failure resilience (v33.56) ---------------------------
# When the stored workbook's columns cannot be read (empty available_columns),
# the mapping must be KEPT rather than dropped. Dropping it caused a recompute
# to collapse Code and Description onto the first column for files whose German
# headers auto-detect to nothing, producing a spurious column-mapping conflict.

def test_build_seed_keeps_required_mapping_when_columns_unreadable():
    ui = {
        "cm_code": "WZIntNr", "cm_desc1": "WZBez", "cm_cons": "Consumption",
        "ks_ktc_threshold": 0.6,
    }
    seed = rr.build_seed(ui, available_columns=[])
    assert seed["cm_code"] == "WZIntNr"
    assert seed["cm_desc1"] == "WZBez"
    assert seed["cm_cons"] == "Consumption"
    assert seed["ks_ktc_threshold"] == 0.6


def test_build_seed_keeps_optional_mapping_when_columns_unreadable():
    seed = rr.build_seed({"cm_size": "KTC Size"}, available_columns=[])
    assert seed["cm_size"] == "KTC Size"


def test_build_seed_none_columns_keeps_mapping():
    # available_columns=None is also "unknown", not "no columns exist".
    seed = rr.build_seed({"cm_code": "WZIntNr", "cm_desc1": "WZBez", "cm_cons": "X"},
                         available_columns=None)
    assert seed["cm_code"] == "WZIntNr"
    assert seed["cm_desc1"] == "WZBez"


def test_build_seed_still_drops_required_when_columns_known_and_absent():
    # When columns ARE readable and the stored column is no longer present, drop it
    # so auto-detect can run (unchanged behaviour).
    ui = {"cm_code": "Code", "cm_desc1": "GoneColumn", "cm_cons": "Consumption"}
    seed = rr.build_seed(ui, available_columns=["Code", "Consumption"])
    assert seed["cm_code"] == "Code"
    assert "cm_desc1" not in seed
    assert seed["cm_cons"] == "Consumption"
