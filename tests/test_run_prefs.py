"""Tests for engine.run_prefs — per-file KTC-ID / customer memory."""
import json
from pathlib import Path

import pytest

from engine import run_prefs as rp


@pytest.fixture
def prefs_file(tmp_path):
    return tmp_path / "file_prefs.json"


class TestFileKeyFor:
    def test_strips_extension_and_path(self):
        assert rp.file_key_for("/some/dir/Catalog_W1.xlsx") == "catalog_w1"

    def test_lowercases(self):
        assert rp.file_key_for("MyCatalog.XLSX") == "mycatalog"

    def test_same_file_different_dirs_same_key(self):
        assert rp.file_key_for("a/cat.xlsx") == rp.file_key_for("b/c/cat.xlsx")

    def test_empty_returns_empty(self):
        assert rp.file_key_for("") == ""


class TestSaveLoadRoundtrip:
    def test_save_then_get(self, prefs_file):
        rp.save_file_prefs("catalog_w1", "191", "ACME Plant 1", path=prefs_file)
        got = rp.get_file_prefs("catalog_w1", path=prefs_file)
        assert got["ktc_id"] == "191"
        assert got["customer"] == "ACME Plant 1"

    def test_get_unknown_key_returns_empty(self, prefs_file):
        rp.save_file_prefs("known", "100", "X", path=prefs_file)
        assert rp.get_file_prefs("unknown", path=prefs_file) == {}

    def test_multiple_files_preserved(self, prefs_file):
        rp.save_file_prefs("file_a", "191", "A", path=prefs_file)
        rp.save_file_prefs("file_b", "315", "B", path=prefs_file)
        assert rp.get_file_prefs("file_a", path=prefs_file)["ktc_id"] == "191"
        assert rp.get_file_prefs("file_b", path=prefs_file)["ktc_id"] == "315"

    def test_overwrite_updates_only_that_key(self, prefs_file):
        rp.save_file_prefs("file_a", "191", "A", path=prefs_file)
        rp.save_file_prefs("file_b", "315", "B", path=prefs_file)
        rp.save_file_prefs("file_a", "200", "A2", path=prefs_file)
        assert rp.get_file_prefs("file_a", path=prefs_file)["ktc_id"] == "200"
        assert rp.get_file_prefs("file_a", path=prefs_file)["customer"] == "A2"
        # file_b untouched
        assert rp.get_file_prefs("file_b", path=prefs_file)["ktc_id"] == "315"

    def test_values_are_stripped(self, prefs_file):
        rp.save_file_prefs("k", "  191  ", "  ACME  ", path=prefs_file)
        got = rp.get_file_prefs("k", path=prefs_file)
        assert got["ktc_id"] == "191"
        assert got["customer"] == "ACME"


class TestDefensiveBehaviour:
    def test_missing_file_returns_empty(self, tmp_path):
        missing = tmp_path / "does_not_exist.json"
        assert rp.load_all_prefs(path=missing) == {}
        assert rp.get_file_prefs("anything", path=missing) == {}

    def test_corrupt_json_returns_empty(self, prefs_file):
        prefs_file.write_text("{ this is not valid json", encoding="utf-8")
        assert rp.load_all_prefs(path=prefs_file) == {}

    def test_non_dict_json_returns_empty(self, prefs_file):
        prefs_file.write_text("[1, 2, 3]", encoding="utf-8")
        assert rp.load_all_prefs(path=prefs_file) == {}

    def test_blank_key_save_is_noop(self, prefs_file):
        assert rp.save_file_prefs("", "191", "X", path=prefs_file) is False
        assert rp.load_all_prefs(path=prefs_file) == {}

    def test_blank_key_get_returns_empty(self, prefs_file):
        assert rp.get_file_prefs("", path=prefs_file) == {}

    def test_save_creates_parent_dir(self, tmp_path):
        nested = tmp_path / "a" / "b" / "prefs.json"
        assert rp.save_file_prefs("k", "191", "X", path=nested) is True
        assert nested.exists()
        assert rp.get_file_prefs("k", path=nested)["ktc_id"] == "191"

    def test_stored_json_is_valid_and_readable(self, prefs_file):
        rp.save_file_prefs("k", "191", "ACME", path=prefs_file)
        raw = json.loads(prefs_file.read_text(encoding="utf-8"))
        assert raw["k"]["ktc_id"] == "191"
        assert raw["k"]["customer"] == "ACME"


# ---- v34.48: atomic, corruption-safe writes (audit reliability) -------------

def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    from engine.run_prefs import save_file_prefs, get_file_prefs

    p = tmp_path / "prefs" / "file_prefs.json"
    assert save_file_prefs("cat_a", "191", "Cust A", path=p)
    assert save_file_prefs("cat_b", "150", "Cust B", path=p)
    assert get_file_prefs("cat_a", path=p)["ktc_id"] == "191"
    assert get_file_prefs("cat_b", path=p)["ktc_id"] == "150"
    leftovers = [f.name for f in p.parent.iterdir() if f.name != p.name]
    assert leftovers == []


def test_corrupt_store_is_backed_up_not_wiped(tmp_path):
    from engine.run_prefs import save_file_prefs, get_file_prefs

    p = tmp_path / "file_prefs.json"
    p.write_text('{"cat_a": {"ktc_id": "191", "cust', encoding="utf-8")  # truncated
    assert save_file_prefs("cat_b", "150", "Cust B", path=p)
    assert get_file_prefs("cat_b", path=p)["ktc_id"] == "150"
    backups = [f for f in tmp_path.iterdir() if f.name.startswith("file_prefs.json.corrupt")]
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8").startswith('{"cat_a"')
