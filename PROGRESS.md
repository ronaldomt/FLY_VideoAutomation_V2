# Progress

> Updated at the end of every meaningful unit of work. See `CLAUDE.md` §17.

## Done

- [x] Repo `git init` + initial scaffolding per CLAUDE.md §21

## In progress

- [ ] Backend skeleton: pyproject + FastAPI `/health` + settings layer
- [ ] Backend behaviors with mocked integrations + unit tests
- [ ] Frontend skeleton: Vite + React + TS + Tailwind + routing
- [ ] Frontend pages with mocked data
- [ ] Tauri shell + disk watcher + sidecar spawner
- [ ] Wire Composio behind `COMPOSIO_LIVE` feature flag
- [ ] Dev/build scripts + README install instructions

## Awaiting human (see BLOCKERS.md)

- [ ] Composio API key
- [ ] Google OAuth consent for school account
- [ ] Confirm Google Calendar ID
- [ ] Pick `<RootLocal>` path on the workstation

## Manual tests still to run

- [ ] Real card insert on macOS (Sonoma+) — owner leaves SD card inserted during build window so the agent can verify; final confirmation still owner-signed-off
- [ ] Real card insert on Windows 11 — owner action (workstation hardware)
- [ ] End-to-end 10 GB session against real Composio + Drive
- [ ] First-run Setup wizard against real Composio account
- [ ] Whatsapp `wa.me` link opens with correctly URL-encoded message
- [ ] Card wipe button is disabled until verification passes; explicit click required

## Milestone tracker (CLAUDE.md §16 Definition of Done)

- [ ] App launches on macOS and Windows from unsigned local builds
- [ ] Card insertion detected on both OSes within 3 seconds
- [ ] Customer list loads from Composio in < 2s on a normal day
- [ ] Full ingest of a real session completes without manual intervention (no artificial size cap)
- [ ] Disk-full pre-check + mid-session disk-full surfaces explicit error; session marked `failed` with state preserved
- [ ] Upload verification compares md5 checksums; wipe button disabled on mismatch
- [ ] All backend behaviors have unit tests; orchestrator has integration test (mocked Composio)
- [ ] All frontend pages reachable; operations unified on `/session`; no page mixes concerns
- [ ] Settings persisted and editable from UI
- [ ] First-run setup wizard works
- [ ] `BLOCKERS.md` contains zero open items the human hasn't accepted
- [ ] `PROGRESS.md` shows every §16 milestone checked
