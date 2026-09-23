"""Tests for engine.build_info — the single source of truth for the build id."""

from __future__ import annotations

import re

from engine import build_info


def test_build_constant_present_and_well_formed():
    assert isinstance(build_info.BUILD, str) and build_info.BUILD
    # vMAJOR or vMAJOR.MINOR[.PATCH]
    assert re.fullmatch(r"v\d+(?:\.\d+){0,2}", build_info.BUILD), build_info.BUILD


def test_build_stamp_format():
    assert build_info.build_stamp() == f"Build {build_info.BUILD}"


def test_single_source_of_truth():
    """No source file may hard-code a literal 'v33', 'v34', etc.; the build label
    must come from engine.build_info so two outputs can't disagree on what
    build produced them. (Tests are exempt.)"""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    bad = []
    pat = re.compile(r'"v3[0-9]"|"v4[0-9]"')
    for path in list(root.glob("*.py")) + list((root / "pages").glob("*.py")) + list((root / "engine").glob("*.py")):
        if path.name in {"build_info.py"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pat.search(text):
            bad.append(str(path.relative_to(root)))
    assert not bad, f"hard-coded build labels found in {bad}; import from engine.build_info instead"
