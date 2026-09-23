"""Dependency floor contracts (v34.49, audit C5).

Streamlit below 1.54 carries CVE-2026-33682 (unauthenticated Windows SSRF that
leaks the NTLM hash) and the app already needs features far newer than the
old 1.32 floor. openai gets an upper bound so a new major cannot arrive
untested, and defusedxml hardens openpyxl's XML parsing of uploaded files.
"""
import re
from importlib.metadata import version

from tests._paths import REPO


def _req():
    lines = (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return [ln.split("#")[0].strip() for ln in lines if ln.split("#")[0].strip()]


def _spec(name):
    for ln in _req():
        if re.match(rf"^{re.escape(name)}\b", ln, re.I):
            return ln
    return None


def _v(s):
    return tuple(int(x) for x in re.findall(r"\d+", s)[:3])


def test_streamlit_floor_excludes_known_vulnerable_releases():
    spec = _spec("streamlit")
    floor = re.search(r">=\s*([\d.]+)", spec).group(1)
    assert _v(floor) >= (1, 54)
    assert "<2.0" in spec.replace(" ", "")


def test_installed_streamlit_satisfies_the_floor():
    assert _v(version("streamlit")) >= (1, 54)


def test_openai_has_an_upper_bound():
    assert "<" in (_spec("openai") or "")


def test_defusedxml_is_declared():
    assert _spec("defusedxml") is not None
