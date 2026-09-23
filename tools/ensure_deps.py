"""Keep the installed dependencies in step with requirements.txt (v34.49, audit C5).

Called by run.bat before the app starts. The old launcher installed
requirements only when Streamlit was missing, so a release that changed
requirements.txt (a new package, a raised security floor) never reached a
machine that already had Streamlit. This step reinstalls whenever:

* requirements.txt changed since the last successful install (a fingerprint
  of its meaningful lines is stamped in the user profile), or
* Streamlit is missing, or older than the floor declared in requirements.txt.

A failed install never blocks a working installation: if Streamlit is still
importable the app starts anyway (and the install is retried next launch).
Exit code 1 only when Streamlit is unavailable.

Usage:  python tools/ensure_deps.py
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = APP_ROOT / "requirements.txt"
DEFAULT_STAMP = Path(os.path.expanduser("~")) / ".kromi_cabinet_planner" / "deps.sha256"


def _meaningful_lines(req_path: Path) -> list[str]:
    out = []
    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(re.sub(r"\s+", "", line))
    return out


def requirements_fingerprint(req_path: Path) -> str:
    """SHA-256 of the requirement lines, ignoring comments and whitespace."""
    return hashlib.sha256("\n".join(_meaningful_lines(req_path)).encode("utf-8")).hexdigest()


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def streamlit_floor(req_path: Path) -> Optional[tuple[int, ...]]:
    for line in _meaningful_lines(req_path):
        if re.match(r"^streamlit\b", line, re.I):
            m = re.search(r">=([\d.]+)", line)
            return _version_tuple(m.group(1)) if m else None
    return None


def installed_streamlit_version() -> Optional[str]:
    try:
        from importlib.metadata import version
        return version("streamlit")
    except Exception:
        return None


def needs_install(req_path: Path, stamp_path: Path, *, streamlit_version: Optional[str]) -> bool:
    if streamlit_version is None:
        return True
    floor = streamlit_floor(req_path)
    if floor and _version_tuple(streamlit_version) < floor:
        return True
    try:
        stamped = Path(stamp_path).read_text(encoding="utf-8").strip()
    except OSError:
        return True
    return stamped != requirements_fingerprint(req_path)


def pip_install(req_path: Path) -> int:
    return subprocess.call([sys.executable, "-m", "pip", "install", "-r", str(req_path)])


def ensure(
    req_path: Path = DEFAULT_REQUIREMENTS,
    stamp_path: Path = DEFAULT_STAMP,
    *,
    streamlit_version: Callable[[], Optional[str]] = installed_streamlit_version,
    install: Callable[[Path], int] = pip_install,
    say: Callable[[str], None] = print,
) -> int:
    """Install when needed; return 0 when the app can start, 1 otherwise."""
    req_path, stamp_path = Path(req_path), Path(stamp_path)
    if not needs_install(req_path, stamp_path, streamlit_version=streamlit_version()):
        return 0
    first_run = streamlit_version() is None
    say("First-run setup: installing Python dependencies. Takes around a minute."
        if first_run else
        "Updating Python dependencies to match this version of the app.")
    rc = install(req_path)
    if rc == 0:
        try:
            stamp_path.parent.mkdir(parents=True, exist_ok=True)
            stamp_path.write_text(requirements_fingerprint(req_path), encoding="utf-8")
        except OSError:
            pass  # the install worked; it is simply repeated next launch
        return 0
    if streamlit_version() is not None:
        say("Warning: the dependency update could not be completed (see the "
            "messages above). Starting with the installed versions; the update "
            "is retried on the next launch.")
        return 0
    say("Dependency installation failed and Streamlit is not available.")
    return 1


if __name__ == "__main__":
    sys.exit(ensure())
