#!/usr/bin/env bash
# Runs backend (FastAPI) + frontend (Vite) + Tauri dev shell side-by-side.
# Backend port is fixed at 8765 for dev so the frontend doesn't need to read
# the runtime file. See CLAUDE.md §13.

set -euo pipefail

cd "$(dirname "$0")/.."

DEV_TOKEN="${FLY_SIDECAR_TOKEN:-dev-token}"
DEV_PORT="${FLY_SIDECAR_PORT:-8765}"

cleanup() {
  echo
  echo "==> Stopping dev processes…"
  kill "${BACKEND_PID:-0}" "${FRONTEND_PID:-0}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> Starting backend on :$DEV_PORT (token=$DEV_TOKEN, no runtime file)"
(
  cd backend
  FLY_SIDECAR_TOKEN="$DEV_TOKEN" \
  FLY_WRITE_RUNTIME_FILE=0 \
  uv run uvicorn fly_backend.main:app --reload --host 127.0.0.1 --port "$DEV_PORT"
) &
BACKEND_PID=$!

# Give uvicorn a moment to bind.
sleep 1

if [[ "${SKIP_TAURI:-0}" == "1" ]]; then
  echo "==> SKIP_TAURI=1 — starting Vite only"
  (cd app/ui && VITE_SIDECAR_URL="http://127.0.0.1:$DEV_PORT" VITE_SIDECAR_TOKEN="$DEV_TOKEN" pnpm dev) &
  FRONTEND_PID=$!
  wait "$FRONTEND_PID"
else
  echo "==> Starting Tauri dev (it will boot the Vite frontend automatically)"
  cd app/src-tauri
  VITE_SIDECAR_URL="http://127.0.0.1:$DEV_PORT" \
  VITE_SIDECAR_TOKEN="$DEV_TOKEN" \
  cargo tauri dev
fi
