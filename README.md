# FLY Video Automation V2

Near-zero-click ingest workflow for a skydiving school: SD card / GoPro insert → local archive → frame extraction → Google Drive upload → WhatsApp share link.

> The canonical spec for this repo is [`CLAUDE.md`](./CLAUDE.md). If anything here conflicts with `CLAUDE.md`, `CLAUDE.md` wins until updated.

## Status

- Track open human-blocked items in [`BLOCKERS.md`](./BLOCKERS.md).
- Track implementation milestones in [`PROGRESS.md`](./PROGRESS.md).

## Architecture (TL;DR)

- **Tauri 2.x shell (Rust)** — disk-insert detection, tray, sidecar lifecycle.
- **Python sidecar (FastAPI)** — behavior-based business logic, SQLite job queue.
- **React frontend (Vite + TS + Tailwind + Zustand)** — page-per-context UI.

See `CLAUDE.md` §7 for the full diagram.

## Requirements

- macOS 13+ or Windows 10/11
- Python **3.11+** (via [`uv`](https://docs.astral.sh/uv/))
- Node **20+** with [`pnpm`](https://pnpm.io/)
- Rust stable (only required to build the Tauri shell)
- ffmpeg available on PATH

## Quick start (dev)

```bash
# 1. Install Python deps (uv reads backend/pyproject.toml)
cd backend && uv sync && cd ..

# 2. Install frontend deps
cd app/ui && pnpm install && cd ../..

# 3. Run everything (backend + Vite + Tauri dev)
./scripts/dev.sh
```

Backend alone: `cd backend && uv run uvicorn fly_backend.main:app --reload`
Frontend alone: `cd app/ui && pnpm dev`

## Production build (v1: unsigned, personal distribution)

```bash
./scripts/build-sidecar.sh   # PyInstaller bundle for the current OS
./scripts/package.sh         # Tauri bundle (unsigned .dmg / .msi)
```

### Installing the unsigned build

V1 is distributed personally to one workstation. Code signing is intentionally out of scope (see `CLAUDE.md` §18, §19).

**macOS:** the first launch will be blocked by Gatekeeper. Either:
- Right-click the app → **Open** → **Open** in the warning dialog, **or**
- `xattr -dr com.apple.quarantine /Applications/FLY\ Video\ Automation.app`

**Windows:** SmartScreen will warn on first launch. Click **More info** → **Run anyway**.

Signing comes back in v2 (SaaS).

## Repository layout

See `CLAUDE.md` §6. ADRs for any deviations live in `docs/decisions/`.
