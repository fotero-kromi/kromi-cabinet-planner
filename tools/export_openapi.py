"""Write the new app's OpenAPI schema to frontend/openapi.json.

Usage (repository root):
    python tools/export_openapi.py

The front end's TypeScript client is generated from that file
(``npm run gen:api`` in frontend/). A back-end test fails while the file differs
from the schema the app serves, and the front-end CI job fails while the
generated client differs from the file, so the two sides cannot drift apart.
No database is needed.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "frontend" / "openapi.json"


def render(schema: dict[str, Any]) -> str:
    """The file's exact text: stable key order, LF line endings, final newline."""
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    sys.path[:0] = [str(REPO / "backend"), str(REPO)]
    # The app builds its database engine at import; nothing connects here.
    os.environ.setdefault("KROMI_DATABASE_URL", "postgresql+psycopg://unused@127.0.0.1:1/unused")
    from kromi_api.main import create_app

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with open(TARGET, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(create_app().openapi()))
    print(f"wrote {TARGET.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
