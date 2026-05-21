#!/usr/bin/env bash
# Setup script — installs Python + Node deps for the project.
# See CLAUDE.md §13.

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Python deps (uv)"
(cd backend && uv sync --extra dev)

echo "==> Frontend deps (pnpm)"
(cd app/ui && pnpm install --frozen-lockfile)

echo "==> Done. Run ./scripts/dev.sh to start the dev environment."
