#!/usr/bin/env bash
# Session start hook (v34.59): install the Python dependencies in Claude Code
# cloud sessions (a no-op when they are already satisfied). Local sessions keep
# their own environment, so this only runs when CLAUDE_CODE_REMOTE is "true".
# It never fails the session.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}" || exit 0
python3 -m pip install -q -r requirements-dev.txt >/dev/null 2>&1 \
  || python3 -m pip install -q --break-system-packages -r requirements-dev.txt >/dev/null 2>&1 \
  || echo "Dependency install failed; run: pip install -r requirements-dev.txt"
exit 0
