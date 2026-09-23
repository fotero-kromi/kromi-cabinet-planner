"""tools/check.py (v34.59): the single quality gate for local work, cloud sessions and CI.

The customer-name scan stores the names only as salted digests, so no file in
the repository has to spell them. These tests use invented words.
"""
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from tools import check

_GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
        "-c", "commit.gpgsign=false"]


def _folded(*words):
    return {check.name_digest(w) for w in words}


def test_the_digests_are_sha256():
    for digest in check.BANNED_FOLDED_DIGESTS | check.BANNED_EXACT_DIGESTS:
        assert len(digest) == 64 and int(digest, 16) >= 0
    assert len(check.BANNED_FOLDED_DIGESTS) >= 17


def test_words_pairs_and_capitals_are_found():
    text = "Zorblax, the QUINT-vell and ZAP but not zap or zorblaxes."
    found = check.find_banned_names(text, folded=_folded("zorblax", "quint vell"),
                                    exact={check.name_digest("ZAP", exact=True)})
    assert found == ["QUINT vell", "ZAP", "Zorblax"]


def test_accents_are_folded():
    assert check.find_banned_names("Café Noir", folded=_folded("cafe")) == ["Café"]


def test_a_clean_text_has_no_names():
    assert check.find_banned_names("Helix spirals and Carousel compartments") == []


def test_the_scan_reads_inside_workbooks(tmp_path):
    book = tmp_path / "list.xlsx"
    pd.DataFrame({"Customer": ["Zorblax GmbH"]}).to_excel(book, index=False)
    assert check.find_banned_names(check._text_of(book), folded=_folded("zorblax")) == ["Zorblax"]


def test_the_repository_has_no_customer_names():
    hits = check.scan_names()
    assert not hits, f"customer names in: {sorted(hits)}"


def test_the_wording_scan_flags_filler_words_and_the_em_dash():
    lines = [("a.py", "x = 1  # plain"), ("b.md", "a seam" + "less flow"),
             ("c.md", "one — two"), ("d.md", "ACTU" + "ALLY")]
    assert [item.split(":")[0] for item in check.scan_wording(lines)] == ["b.md", "c.md", "d.md"]


@pytest.mark.skipif(subprocess.run(["git", "--version"], capture_output=True).returncode,
                    reason="git not installed")
def test_added_lines_cover_edits_and_new_files(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one\n")
    subprocess.run(_GIT + ["add", "."], cwd=tmp_path, check=True)
    subprocess.run(_GIT + ["commit", "-q", "-m", "base"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one\ntwo\n")
    (tmp_path / "b.txt").write_text("three\n")
    assert sorted(check.added_lines("main", root=tmp_path)) == [("a.txt", "two"),
                                                                 ("b.txt", "three")]


def test_without_git_the_release_list_is_scanned(tmp_path):
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / "x.py").write_text("A = 1\n")
    (tmp_path / "Home.py").write_text("\n")
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "state.json").write_text("{}")
    assert check.project_files(tmp_path) == ["Home.py", "engine/x.py"]


def test_the_customer_file_types_stay_out_of_git():
    ignored = Path(check.ROOT, ".gitignore").read_text().splitlines()
    for pattern in ("*.xlsx", "*.xls", "*.xlsm", "*.csv"):
        assert pattern in ignored
