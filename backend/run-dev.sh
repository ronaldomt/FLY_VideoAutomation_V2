#!/usr/bin/env bash
# Dev backend launcher. Always uses port 8000 + token `dev-token`
# to match app/ui/.env.local. Kills anything already on the port.
set -euo pipefail
cd "$(dirname "$0")"
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
FLY_SIDECAR_TOKEN=dev-token \
FLY_WRITE_RUNTIME_FILE=0 \
exec uv run uvicorn fly_backend.main:app --reload --host 127.0.0.1 --port 8000
