"""Per-file run preferences, remembered across sessions.

Stores a small amount of run setup (KTC-ID, customer/label) keyed on a
file identifier so that re-uploading a known catalog pre-fills the values
the user entered last time. Backed by a single JSON file; all reads and
writes are defensive so a missing or corrupt store never breaks a run.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

# Default location; override via env for tests or custom deployments.
DEFAULT_PREFS_PATH = Path(
    os.getenv("KROMI_FILE_PREFS_PATH", "runs/file_prefs.json")
)


def _prefs_path(path: Path | None = None) -> Path:
    return path if path is not None else DEFAULT_PREFS_PATH


def load_all_prefs(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return the full {file_key: {ktc_id, customer}} map, or {} on any error."""
    p = _prefs_path(path)
    try:
        with p.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def get_file_prefs(file_key: str, path: Path | None = None) -> dict[str, str]:
    """Return the saved prefs for one file key, or an empty dict."""
    if not file_key:
        return {}
    entry = load_all_prefs(path).get(file_key, {})
    return entry if isinstance(entry, dict) else {}


def save_file_prefs(file_key: str, ktc_id: str, customer: str,
                    path: Path | None = None) -> bool:
    """Persist prefs for one file key. Returns True on success.

    Existing entries for other files are preserved. A blank file_key is a
    no-op (returns False) so we never write an unkeyed blob.
    """
    if not file_key:
        return False
    p = _prefs_path(path)
    prefs = load_all_prefs(path)
    if not prefs and _is_unreadable(p):
        # v34.48: a corrupt store is kept aside instead of being overwritten,
        # so the other files' remembered KTC-IDs can still be recovered.
        try:
            p.replace(p.with_name(f"{p.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}"))
        except OSError:
            return False
    prefs[file_key] = {
        "ktc_id": str(ktc_id or "").strip(),
        "customer": str(customer or "").strip(),
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(p, prefs)
        return True
    except OSError:
        return False


def _is_unreadable(p: Path) -> bool:
    """True when ``p`` exists and has content but is not a JSON object."""
    try:
        if not p.exists() or p.stat().st_size == 0:
            return False
        with p.open(encoding="utf-8") as f:
            return not isinstance(json.load(f), dict)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return True
    except OSError:
        return False


def _atomic_write_json(p: Path, data: dict) -> None:
    """Write via a temp file in the same folder, then replace (v34.48).

    A crash or a full disk mid-write can no longer leave a truncated store.
    """
    fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def file_key_for(filename: str) -> str:
    """Normalise an uploaded filename into a stable lookup key.

    Uses the lower-cased base name without extension, so 'Catalog_W1.xlsx'
    and a re-upload of the same file resolve to the same key regardless of
    the directory it came from.
    """
    if not filename:
        return ""
    base = os.path.basename(str(filename))
    stem = os.path.splitext(base)[0]
    return stem.strip().lower()
