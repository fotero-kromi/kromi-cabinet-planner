#!/usr/bin/env bash
# Session start hook (v34.59): install the Python dependencies in Claude Code
# cloud sessions (a no-op when they are already satisfied). Local sessions keep
# their own environment, so this only runs when CLAUDE_CODE_REMOTE is "true".
# It never fails the session.
#
# Rewrite branch: also installs the new app's back-end dependencies and starts
# a local PostgreSQL with an empty "kromi_test" database for its tests (the
# PostgreSQL the cloud image provides; CI tests on PostgreSQL 18).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}" || exit 0

pip_install() {
  python3 -m pip install -q -r "$1" >/dev/null 2>&1 \
    || python3 -m pip install -q --break-system-packages -r "$1" >/dev/null 2>&1 \
    || echo "Dependency install failed; run: pip install -r $1"
}
pip_install requirements-dev.txt
if [ -f backend/requirements-dev.txt ]; then
  pip_install backend/requirements-dev.txt
fi

# Local PostgreSQL for the back-end tests: trust authentication, listening on
# 127.0.0.1 only, data under the postgres user's home.
PG_BIN=$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)
PG_DATA=/var/lib/postgresql/kromi-test
if [ -n "$PG_BIN" ] && id postgres >/dev/null 2>&1; then
  if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    su postgres -s /bin/bash -c \
      "$PG_BIN/initdb -D $PG_DATA -U kromi --auth=trust -E UTF8 --locale=C.UTF-8" \
      >/dev/null 2>&1 || echo "PostgreSQL initdb failed"
  fi
  if ! su postgres -s /bin/bash -c "$PG_BIN/pg_ctl -D $PG_DATA status" >/dev/null 2>&1; then
    su postgres -s /bin/bash -c \
      "$PG_BIN/pg_ctl -D $PG_DATA -l $PG_DATA/server.log -w \
       -o '-p 5432 -k /var/run/postgresql -c listen_addresses=127.0.0.1' start" \
      >/dev/null 2>&1 || echo "PostgreSQL start failed; see $PG_DATA/server.log"
  fi
  psql -h 127.0.0.1 -U kromi -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = 'kromi_test'" 2>/dev/null | grep -q 1 \
    || psql -h 127.0.0.1 -U kromi -d postgres -c "CREATE DATABASE kromi_test" >/dev/null 2>&1 \
    || echo "Could not create the kromi_test database"
fi
exit 0
