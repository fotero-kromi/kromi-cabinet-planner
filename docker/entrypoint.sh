#!/bin/sh
# Start of the app container: bring the database schema up to date, then serve
# the app (API and front end) on port 8080. compose.yaml publishes that port
# on 127.0.0.1 only, so the app is reachable from this PC alone.
set -e
cd /app/backend
alembic upgrade head
cd /app
exec python -m uvicorn --app-dir backend kromi_api.main:app \
    --host 0.0.0.0 --port 8080
