"""The front end's client is generated from ``frontend/openapi.json``; that
file must be exactly the schema the app serves, or the two sides drift apart.
After an API change: ``python tools/export_openapi.py``, then in ``frontend/``
``npm run gen:api``."""
import json
from pathlib import Path

from kromi_api.main import create_app
from tools import export_openapi

REPO = Path(__file__).resolve().parents[2]
FILE = REPO / "frontend" / "openapi.json"


def test_the_committed_schema_is_the_served_schema():
    assert FILE.is_file(), "run: python tools/export_openapi.py"
    committed = json.loads(FILE.read_text(encoding="utf-8"))
    assert committed == create_app().openapi(), "stale: run python tools/export_openapi.py"


def test_the_export_is_stable_text():
    # Same bytes on every platform and run, so the file never shows spurious diffs.
    assert FILE.read_text(encoding="utf-8") == export_openapi.render(create_app().openapi())


def test_the_schema_does_not_change_with_each_build():
    # The build is reported by /health; putting it into the schema would make
    # every release on main a stale-schema failure after the merge.
    from engine.build_info import BUILD

    assert create_app().openapi()["info"]["version"] != BUILD
