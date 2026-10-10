#!/bin/sh
# Finder container entrypoint: API + built frontend on one port.
set -e
mkdir -p "$FINDER_DATA_DIR" "$FINDER_HERMES_ROOT/profiles"
exec /opt/finder/.venv/bin/python -m uvicorn app.main:app --app-dir /opt/finder/backend \
     --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
