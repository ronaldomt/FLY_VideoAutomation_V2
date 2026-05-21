# Progress

> Updated at the end of every meaningful unit of work. See `CLAUDE.md` §17.

## Done

- [x] Repo `git init` + initial scaffolding per CLAUDE.md §21
- [x] Backend skeleton: pyproject + FastAPI `/health` + settings layer
- [x] Backend behaviors with mocked integrations + unit tests
  - 10 behaviors (detect_card, list_today_customers, resolve_drive_folder,
    start_session, copy_media, extract_frames, upload_to_drive, verify_upload,
    make_share_link, wipe_card) each in `behaviors/<name>/{contract,handler,tests}.py`
  - 56 unit + integration tests pass; ruff clean
  - start_session integration test covers orchestrator → copy → extract →
    upload → verify against MockDrive + FakeFfmpeg
- [x] All §10 HTTP endpoints wired (SSE on `/sessions/:id/events`)
- [x] Frontend skeleton: Vite + React + TS + Tailwind + routing
  - React 18 + Vite + Tailwind + Zustand + TanStack Query + React Router
  - Typed sidecar HTTP client with `X-Sidecar-Token` auth
  - SSE subscriber for `/sessions/:id/events`
  - `tsc -b` clean, `vite build` succeeds, `vitest` green
- [x] Frontend pages with mocked data
  - `/` Idle, `/session/:id?` Session (stepper Customer→Destination→Ingest→Done),
    `/settings` (4 sub-tabs per §12), `/setup` wizard, `/logs` viewer
  - All pages reachable via hamburger menu; no global modals
- [x] Tauri shell + disk watcher + sidecar spawner
  - Cargo workspace, tauri.conf.json, capabilities/default.json
  - lib.rs setup hook spawns sidecar (if bundled), polls for runtime file,
    injects `window.__FLY_SIDECAR__` into the webview, and starts the disk
    watcher
  - sidecar.rs: graceful no-op in dev mode (external sidecar)
  - ipc.rs: `get_sidecar_config` Tauri command + runtime-file reader
  - disk_watcher.rs: 1s sysinfo poll over removable disks → POST
    `/cards/detected` (meets the §16 <3s SLA)
  - `cargo check` clean on macOS
  - Placeholder icons committed (real artwork is a BLOCKER)
- [x] Wire Composio behind `COMPOSIO_LIVE` feature flag
  - Mock vs Live client switch lives in `build_calendar_client` /
    `build_drive_client` based on env (`COMPOSIO_LIVE=1` + key set)
  - Live client method bodies BLOCKED until human provides Composio API key
- [x] Dev/build scripts + README install instructions
  - `scripts/setup.sh` — uv sync + pnpm install
  - `scripts/dev.sh` — backend (uvicorn :8765) + tauri dev together
  - `scripts/build-sidecar.sh` — PyInstaller bundle
  - `scripts/package.sh` — full unsigned Tauri bundle
  - README documents Gatekeeper / SmartScreen bypass for unsigned builds

## In progress

- (nothing — all scaffolded scope is in)

## Awaiting human (see BLOCKERS.md)

- [ ] Composio API key
- [ ] Google OAuth consent for school account
- [ ] Confirm Google Calendar ID
- [ ] Pick `<RootLocal>` path on the workstation
- [ ] Replace placeholder Tauri icons with real artwork

## Manual tests still to run

- [ ] Real card insert on macOS (Sonoma+) — owner leaves SD card inserted during build window so the agent can verify; final confirmation still owner-signed-off
- [ ] Real card insert on Windows 11 — owner action (workstation hardware)
- [ ] Full `cargo tauri build` on macOS (first run pulls system deps)
- [ ] Full `cargo tauri build` on Windows
- [ ] End-to-end 10 GB session against real Composio + Drive
- [ ] First-run Setup wizard against real Composio account
- [ ] WhatsApp `wa.me` link opens with correctly URL-encoded message
- [ ] Card wipe button is disabled until verification passes; explicit click required
- [ ] PyInstaller bundle of the sidecar boots on the target OS (smoke test)

## Milestone tracker (CLAUDE.md §16 Definition of Done)

- [ ] App launches on macOS and Windows from unsigned local builds
- [ ] Card insertion detected on both OSes within 3 seconds
- [ ] Customer list loads from Composio in < 2s on a normal day
- [ ] Full ingest of a real session completes without manual intervention (no artificial size cap)
- [x] Disk-full pre-check (CLAUDE.md §16) implemented in `start_session`; session marked `failed` with shortfall surfaced — integration-tested
- [x] Upload verification compares md5 checksums; wipe button disabled on mismatch
- [x] All backend behaviors have unit tests; orchestrator has integration test (mocked Composio)
- [x] All frontend pages reachable; operations unified on `/session`; no page mixes concerns
- [x] Settings persisted and editable from UI
- [x] First-run setup wizard works (against mocked integrations; real Composio behind blocker)
- [ ] `BLOCKERS.md` contains zero open items the human hasn't accepted
- [ ] `PROGRESS.md` shows every §16 milestone checked
