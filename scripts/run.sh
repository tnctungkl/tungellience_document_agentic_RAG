#!/usr/bin/env bash
set -euo pipefail
host="${API_HOST:-127.0.0.1}"
port="${API_PORT:-8000}"
printf 'Starting Tungelligence on http://%s:%s (local-only by default).\n' "$host" "$port"
exec python -m uvicorn app.api.main:app --host "$host" --port "$port"
