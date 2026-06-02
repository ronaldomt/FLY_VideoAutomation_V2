#!/usr/bin/env bash
# Bundles the Python sidecar into a single binary via PyInstaller. The
# resulting `fly-backend` (or `fly-backend.exe`) is dropped next to the Tauri
# binary so the shell can spawn it at runtime. See CLAUDE.md §13.

set -euo pipefail

cd "$(dirname "$0")/../backend"

# Resolve the entry module and bundle. We add the package as a hidden import
# because PyInstaller's static analyser misses the `from .behaviors.<name>`
# pattern.
uv pip install --quiet pyinstaller

uv run --extra dev pyinstaller \
  --noconfirm \
  --clean \
  --name fly-backend \
  --onefile \
  --collect-submodules fly_backend \
  --collect-submodules composio \
  --collect-submodules uvicorn \
  --collect-submodules fastapi \
  --paths src \
  launcher.py

OUTPUT_DIR="dist"
BIN_NAME="fly-backend"
if [[ "${OS:-}" == "Windows_NT" ]]; then
  BIN_NAME="fly-backend.exe"
fi

if [[ ! -f "$OUTPUT_DIR/$BIN_NAME" ]]; then
  echo "PyInstaller did not produce $OUTPUT_DIR/$BIN_NAME" >&2
  exit 1
fi

echo "==> Built $OUTPUT_DIR/$BIN_NAME"

# Tauri externalBin expects the file named with a target-triple suffix.
# Tauri strips the suffix when bundling into the .app / .msi so the Rust
# shell finds `fly-backend` (no suffix) next to itself at runtime.
HOST_TRIPLE=$(rustc -vV | sed -n 's/^host: //p')
if [[ -z "$HOST_TRIPLE" ]]; then
  echo "Could not determine host triple from rustc -vV" >&2
  exit 1
fi
TAURI_BIN_DIR="../app/src-tauri/binaries"
mkdir -p "$TAURI_BIN_DIR"
if [[ "${OS:-}" == "Windows_NT" ]]; then
  TARGET_NAME="fly-backend-${HOST_TRIPLE}.exe"
else
  TARGET_NAME="fly-backend-${HOST_TRIPLE}"
fi
cp "$OUTPUT_DIR/$BIN_NAME" "$TAURI_BIN_DIR/$TARGET_NAME"
echo "==> Staged sidecar at $TAURI_BIN_DIR/$TARGET_NAME for Tauri externalBin"
