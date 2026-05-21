#!/usr/bin/env bash
# Bundles the Python sidecar into a single binary via PyInstaller. The
# resulting `fly-backend` (or `fly-backend.exe`) is dropped next to the Tauri
# binary so the shell can spawn it at runtime. See CLAUDE.md §13.

set -euo pipefail

cd "$(dirname "$0")/../backend"

# Resolve the entry module and bundle. We add the package as a hidden import
# because PyInstaller's static analyser misses the `from .behaviors.<name>`
# pattern.
uv run --extra dev python -m pip install --quiet pyinstaller

uv run --extra dev pyinstaller \
  --noconfirm \
  --clean \
  --name fly-backend \
  --onefile \
  --collect-submodules fly_backend \
  --paths src \
  src/fly_backend/main.py

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
echo "    Copy it next to the Tauri binary before packaging."
