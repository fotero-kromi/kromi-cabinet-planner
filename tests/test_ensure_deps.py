"""Contracts for the dependency sync launcher step (v34.49, audit C5).

run.bat used to install requirements only when Streamlit was missing, so an
upgrade whose requirements changed (a new package, a raised security floor)
never reached a machine that already had Streamlit. tools/ensure_deps.py
reinstalls whenever requirements.txt changes (fingerprint stamp) or the
installed Streamlit is below the floor. A failed install never blocks a
working installation: the app still starts when Streamlit is importable.
"""
from tools import ensure_deps as ed


def _req(tmp_path, text="streamlit>=1.54,<2.0\npandas>=2.0,<3.0\n"):
    p = tmp_path / "requirements.txt"
    p.write_text(text, encoding="utf-8")
    return p


def test_fingerprint_ignores_comments_and_whitespace(tmp_path):
    a = ed.requirements_fingerprint(_req(tmp_path, "# c\nstreamlit>=1.54\n\npandas\n"))
    b = ed.requirements_fingerprint(_req(tmp_path, "streamlit>=1.54   \npandas  # x\n"))
    c = ed.requirements_fingerprint(_req(tmp_path, "streamlit>=1.55\npandas\n"))
    assert a == b != c


def test_needs_install_rules(tmp_path):
    req = _req(tmp_path)
    stamp = tmp_path / "stamp"
    fp = ed.requirements_fingerprint(req)
    assert ed.needs_install(req, stamp, streamlit_version="1.58.0")        # no stamp
    stamp.write_text(fp, encoding="utf-8")
    assert not ed.needs_install(req, stamp, streamlit_version="1.58.0")    # up to date
    assert ed.needs_install(req, stamp, streamlit_version=None)            # missing
    assert ed.needs_install(req, stamp, streamlit_version="1.40.0")        # below floor
    stamp.write_text("old", encoding="utf-8")
    assert ed.needs_install(req, stamp, streamlit_version="1.58.0")        # changed


def test_ensure_installs_then_stamps(tmp_path):
    req, stamp, calls = _req(tmp_path), tmp_path / "s" / "stamp", []
    rc = ed.ensure(req, stamp, streamlit_version=lambda: "1.58.0",
                   install=lambda p: calls.append(p) or 0, say=lambda m: None)
    assert rc == 0 and calls == [req]
    assert stamp.read_text(encoding="utf-8") == ed.requirements_fingerprint(req)
    calls.clear()
    assert ed.ensure(req, stamp, streamlit_version=lambda: "1.58.0",
                     install=lambda p: calls.append(p) or 0, say=lambda m: None) == 0
    assert calls == []                                   # nothing to do second time


def test_failed_install_keeps_a_working_app_startable(tmp_path):
    req, stamp, msgs = _req(tmp_path), tmp_path / "stamp", []
    rc = ed.ensure(req, stamp, streamlit_version=lambda: "1.58.0",
                   install=lambda p: 1, say=msgs.append)
    assert rc == 0 and not stamp.exists()                # retried next launch
    assert any("could not" in m.lower() for m in msgs)


def test_failed_install_without_streamlit_stops(tmp_path):
    req, stamp = _req(tmp_path), tmp_path / "stamp"
    rc = ed.ensure(req, stamp, streamlit_version=lambda: None,
                   install=lambda p: 1, say=lambda m: None)
    assert rc == 1
