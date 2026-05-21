#!/usr/bin/env bash
# Produces an unsigned Tauri bundle (.dmg on macOS / .msi on Windows) for the
# current OS. Personal distribution only (v1) — code signing is intentionally
# out of scope; see CLAUDE.md §18 / §19.

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> 1. Building Python sidecar"
./scripts/build-sidecar.sh

echo "==> 2. Building frontend"
(cd app/ui && pnpm install --frozen-lockfile && pnpm build)

echo "==> 3. Bundling Tauri app (unsigned)"
(cd app/src-tauri && cargo tauri build)

echo
echo "==> Done. Bundles are under app/src-tauri/target/release/bundle/."
echo "    macOS Gatekeeper / Windows SmartScreen will warn on first launch."
echo "    See README.md (Installing the unsigned build)."
