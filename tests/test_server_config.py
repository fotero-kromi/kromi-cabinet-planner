"""Contracts for the shipped Streamlit server configuration (v34.48, audit C2/S4).

Streamlit binds to every network interface by default, which exposed every
stored customer run, the override sets and the owner's OpenAI key to anyone on
the same network, without a login. The app is a per-user desktop tool, so the
shipped configuration binds to the local machine only and keeps error details
(stack traces, file paths) out of the browser. Sharing on the network stays
possible, but only as an explicit launch option (see README).
"""

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

CONFIG = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"


def _cfg():
    with CONFIG.open("rb") as f:
        return tomllib.load(f)


def test_server_binds_to_the_local_machine_only():
    cfg = _cfg()
    assert cfg["server"]["address"] == "localhost"
    # The browser opens the same alias the server is bound to.
    assert cfg["browser"]["serverAddress"] == "localhost"


def test_error_details_stay_out_of_the_browser():
    # "none" hides the message, type and stack trace; the legacy value
    # `false` is read by Streamlit as "stacktrace".
    assert _cfg()["client"]["showErrorDetails"] == "none"


def test_existing_settings_are_kept():
    cfg = _cfg()
    assert cfg["server"]["maxUploadSize"] == 200
    assert cfg["client"]["toolbarMode"] == "viewer"
    assert cfg["client"]["showSidebarNavigation"] is False
    assert cfg["browser"]["gatherUsageStats"] is False
    assert cfg["theme"]["primaryColor"] == "#006C52"
