# FLY Video Automation V2 — Project CLAUDE.md

> **Single source of truth for this repo.** If a decision is not in this file, ask before guessing. If a decision in this file conflicts with code, this file wins until updated.

---

## 0. How to use this file

You are an autonomous coding agent (Compound Engineering `/lfg` mode). Your job:

1. Read this file end-to-end **before** writing any code.
2. Initialize the repo per §6 and §13.
3. Build v1 per §3 — §12.
4. When you hit a **hard wall** (missing credentials, account creation, OAuth consent screens, signing certs, anything requiring the human owner) → **do not stop**. Write/append to `BLOCKERS.md` (see §17) and continue building everything that does not depend on the blocker.
5. End each session by updating `BLOCKERS.md` and `PROGRESS.md` (see §17).

**Rules of engagement**
- Never fabricate API responses, credentials, or test data presented as real.
- Never disable upload verification to "make it pass."
- Never auto-wipe a card by default. Hard default: OFF.
- Prefer clarity over cleverness. No premature abstraction.
- One concern per module. No mixing operations / config / setup in the UI.
- Commit after every meaningful unit of work with a clear message.
- **Token budget awareness:** monitor remaining tokens against the 5-hour session window. When **< 20% remains**, stop opening new work, run `ce-compound` to capture state, write the handoff doc per §17.5, and end cleanly. Do not start a behavior you can't finish.

---

## 1. Project identity

| Field | Value |
|---|---|
| Project name | FLY Video Automation V2 |
| Client | Skydiving school (single workstation, single Google account) |
| Owner | Ronaldo Tkotz |
| Working dir | `/Users/ronaldosmacbookpro/PROjetcts/FLY_VideoAutomation V2` |
| Repo state at start | Not a git repo — initialize with `git init` |
| Target platforms | macOS (primary dev) + Windows (must work) |
| Date format | `YYYY-MM-DD` |
| File naming | `kebab-case` |

---

## 2. Goal & success criteria

**Goal:** Inserting an SD card / GoPro should trigger a near-zero-click workflow that copies media to a structured local archive, extracts frames from videos, uploads everything to a user-pasted Google Drive folder, and produces a shareable WhatsApp link.

**Success (v1):**
- Operator's per-customer work is **≤ 3 clicks**: pick customer → paste/confirm Drive URL → confirm.
- Handles **10–30 customers/day, 50–200 GB/day** without operator babysitting.
- **Zero file loss.** Local archive is always created and complete before any upload.
- **Upload verified** (size + checksum) before any optional card wipe.
- Runs unattended once started (long uploads can finish overnight).

---

## 3. The operator workflow (the truth)

This is the canonical happy path. Build to this; deviations must be justified in code comments.

1. **Card insert detected.** The Tauri app window pops to foreground (or launches if minimized to tray).
2. **Customer picker page** loads today's events from the school's Google Calendar via Composio.
   - Rows: `HH:MM — Name — Type (HC/VIP)`.
   - Search box on top, filters by name.
   - Persistent "+ New (walk-in)" row.
   - If two customers share the same name on the same day, both rows are shown with their event time — operator disambiguates.
3. **Operator picks a customer** (or types a walk-in name).
4. **Destination page**:
   - Input: "Paste destination Google Drive folder URL".
   - Recent destinations dropdown (last 5 used).
   - Validate the URL resolves to a Drive folder ID via Composio.
5. **Ingest page** (single screen, progress-driven):
   - Create/use local folder: `<RootLocal>/TD_<Customer Name>/Videos/` and `/Fotos/`.
   - Copy MP4s from card → `Videos/`.
   - Copy any JPGs found on the card → `Fotos/`.
   - For every MP4, extract frames at the configured interval (default 1 fps) → `Fotos/`.
   - Upload everything to the pasted Drive folder, preserving the `Videos/` + `Fotos/` subfolders.
   - Verify each upload (file size + Drive `md5Checksum` vs. local hash).
6. **Done page**:
   - Drive share link copied to clipboard.
   - If a phone was parsed from the Calendar event → open `https://wa.me/<phone>?text=<url-encoded link>`.
   - Status: "✅ Done — link copied".
   - Optional button: "Wipe card now" (only enabled if (a) setting is on AND (b) upload fully verified). Always requires explicit click. Never automatic.

### Multi-card sessions
- Each card insert **re-shows the customer list**. Operator picks again — even for the same customer.
- If `TD_<Name>` exists for today → append to it. Filename collisions → append `_2`, `_3`. Never overwrite.

### Edge cases v1 must handle
- **Walk-ins**: free-text name. Logged in `<RootLocal>/_logs/walkins-YYYY-MM-DD.csv`.
- **No phone in event**: clipboard-only, no WhatsApp open. Don't error.
- **Drive failure mid-upload**: local copy is already complete. Queue persists across reboots. Resume automatically when Drive is reachable.
- **Same-card-reinsert**: detect by card volume signature; if a session already completed for this volume in the last hour, prompt "Already ingested. Re-run?".
- **Multi-customer on one card** (rare): v1 dumps everything to the chosen customer. Operator reorganizes manually in Drive. **Out of scope to auto-split.**

---

## 4. Locked decisions (do not re-litigate)

| # | Decision |
|---|---|
| 1 | Cross-platform: macOS + Windows |
| 2 | Stack: **Tauri (Rust shell) + Python sidecar + React frontend** |
| 3 | Google integration: **Composio** (Calendar read + Drive read/write) |
| 4 | Drive destination: **user pastes folder URL each session** (no auto path resolution from Calendar) |
| 5 | Local archive layout: `<RootLocal>/TD_<Customer>/Videos/` + `/Fotos/` |
| 6 | Frame extraction: ffmpeg, default 1 fps, configurable per session and globally |
| 7 | Card wipe: OFF by default; explicit per-session button; requires verified upload |
| 8 | Share: clipboard + WhatsApp Web (`wa.me`) when phone is parsed |
| 9 | Architecture: **component-based frontend + behavior-based Python backend** |
| 10 | UI: separate pages per context (no mixing operations / config / setup) |
| 11 | Design system: built in **Open Design**, then refined with **Impecable** |
| 12 | Single school Google account (tested on owner's account during build) |
| 13 | One dedicated ingest workstation |
| 14 | Calendar source: one Google Calendar; event title format observed as `Name - Phone - Age - Weight - Type(HC|VIP)`; only **Name** is guaranteed |

---

## 5. Tech stack (lock to these unless §17 records a substitution)

### Shell / window
- **Tauri 2.x** (Rust). Reasons: native disk-insert events, small bundle, code-signing path on both OSes, future-proof.
- Rust crates: `notify` (FS events), `sysinfo`, `tauri-plugin-shell`, `tauri-plugin-clipboard-manager`, `tauri-plugin-opener` (open `wa.me` link).

### Backend (sidecar)
- **Python 3.11+** (pinned in `pyproject.toml`).
- Web framework: **FastAPI** + `uvicorn` (binds to `127.0.0.1:<random-free-port>`, port written to a runtime file the frontend reads).
- Process manager: started/stopped by Tauri as a sidecar binary (PyInstaller-packed).
- Key libs:
  - `composio-core` (Google Calendar + Drive)
  - `ffmpeg-python` (frame extraction)
  - `httpx` (Drive uploads, resumable)
  - `pydantic` v2 (contracts)
  - `sqlmodel` + `sqlite` (job queue persistence)
  - `structlog` (logging)
  - `pytest` + `pytest-asyncio` (tests)

### Frontend
- **React 18 + Vite + TypeScript**.
- State: **Zustand** (simple, not Redux).
- Routing: **React Router** (page-per-context).
- HTTP: **TanStack Query** + native `fetch`.
- Styling: **Tailwind CSS** + components from Open Design / Impecable output.
- Icons: **lucide-react**.

### Tooling
- **uv** for Python dep management (faster than pip).
- **pnpm** for frontend.
- **biome** for JS lint/format.
- **ruff** + **mypy** for Python.
- **pre-commit** hooks for both.

---

## 6. Repo structure (reference — refine if you can do better)

> The structure below is a **reference**. Compound Engineering may propose and apply a better layout if it improves clarity, testability, or the path to v2 SaaS. If you deviate, document the change in `docs/decisions/0001-repo-structure.md` (one short ADR) and update this section in the same commit. Do not deviate silently.

```
.
├── CLAUDE.md                         ← this file
├── BLOCKERS.md                       ← created/updated by the agent (see §17)
├── PROGRESS.md                       ← created/updated by the agent (see §17)
├── README.md                         ← short, links to CLAUDE.md
├── .gitignore
├── .editorconfig
├── pre-commit-config.yaml
│
├── app/                              ← Tauri shell (Rust)
│   ├── src-tauri/
│   │   ├── Cargo.toml
│   │   ├── tauri.conf.json
│   │   └── src/
│   │       ├── main.rs
│   │       ├── disk_watcher.rs       ← native card-insert detection
│   │       ├── sidecar.rs            ← spawn/stop Python sidecar
│   │       └── ipc.rs                ← bridge events to frontend
│   └── ui/                           ← React app
│       ├── package.json
│       ├── vite.config.ts
│       ├── tailwind.config.ts
│       ├── src/
│       │   ├── main.tsx
│       │   ├── routes.tsx
│       │   ├── api/                  ← typed client for backend HTTP
│       │   ├── state/                ← Zustand stores
│       │   ├── pages/                ← one folder per page (§9)
│       │   ├── components/           ← shared, dumb components
│       │   └── styles/
│       └── public/
│
├── backend/                          ← Python sidecar
│   ├── pyproject.toml
│   ├── README.md
│   ├── src/fly_backend/
│   │   ├── __init__.py
│   │   ├── main.py                   ← FastAPI app entrypoint
│   │   ├── settings.py               ← config schema (§12)
│   │   ├── logging.py
│   │   ├── http/
│   │   │   └── routes.py             ← REST endpoints (§10)
│   │   ├── behaviors/                ← VERTICAL SLICES, one per use case
│   │   │   ├── detect_card/
│   │   │   ├── list_today_customers/
│   │   │   ├── start_session/
│   │   │   ├── resolve_drive_folder/
│   │   │   ├── copy_media/
│   │   │   ├── extract_frames/
│   │   │   ├── upload_to_drive/
│   │   │   ├── verify_upload/
│   │   │   ├── make_share_link/
│   │   │   └── wipe_card/
│   │   ├── integrations/
│   │   │   ├── composio_calendar.py
│   │   │   ├── composio_drive.py
│   │   │   └── ffmpeg.py
│   │   ├── persistence/
│   │   │   ├── db.py
│   │   │   └── models.py
│   │   └── util/
│   └── tests/
│       ├── unit/                     ← per-behavior tests
│       └── integration/
│
├── scripts/
│   ├── dev.sh                        ← starts backend + tauri dev together
│   ├── build-sidecar.sh              ← PyInstaller bundle for current OS
│   └── package.sh                    ← signed installer (mac/win)
│
└── docs/
    ├── design/                       ← Open Design / Impecable exports
    ├── decisions/                    ← ADRs as we deviate
    └── solutions/                    ← documented solutions (bugs, best practices, workflow patterns); YAML frontmatter indexed by module, tags, problem_type
```

---

## 7. Architecture overview

```
┌───────────────────────────────────────────────────────────┐
│ Tauri Shell (Rust)                                        │
│  ├─ Disk watcher → emits "card_inserted" Tauri event      │
│  ├─ System tray icon                                      │
│  └─ Spawns sidecar on launch, kills on exit               │
└──────────────┬──────────────────────────┬─────────────────┘
               │ Tauri events             │ HTTP (localhost)
               ▼                          ▼
┌──────────────────────────────┐  ┌───────────────────────────────┐
│ React Frontend (UI)          │  │ Python Sidecar (FastAPI)      │
│  - Page-per-context          │  │  - Behavior-based modules     │
│  - Component library         │  │  - SQLite job queue           │
│  - Zustand state             │  │  - Composio + ffmpeg          │
└──────────────┬───────────────┘  └────────────┬──────────────────┘
               │                               │
               └────────────► localhost ◄──────┘
                             :PORT
```

### Why this split

- **Rust** owns OS-native primitives (disk events, signed packaging, tray).
- **Python** owns business logic (easy ffmpeg, Composio SDK, fast iteration).
- **React** owns UX. Fully decoupled from the backend — talks via HTTP, can later be lifted as-is into a web SaaS frontend (productization track).

### Behavior-based backend, explained (refine as needed)

> The breakdown below is a **reference**. Compound Engineering may merge, split, or rename behaviors if it produces a cleaner design. Constraints that cannot be relaxed: (a) the backend stays behavior-/use-case-oriented (no class hierarchies for business logic), (b) each behavior remains independently testable, (c) integrations stay isolated in `integrations/`. Document any structural deviation in `docs/decisions/0002-behavior-layout.md`.


A "behavior" is a vertical slice = one use case = one folder under `backend/src/fly_backend/behaviors/`. Each behavior contains:

```
behaviors/<behavior_name>/
├── __init__.py
├── contract.py    ← Pydantic Input + Output models
├── handler.py     ← pure async function: run(input) -> output
└── tests.py       ← unit tests
```

Rules:
- A behavior never imports another behavior. Composition happens at the HTTP route layer or in an orchestrator behavior (e.g. `start_session`).
- Behaviors receive a `Context` object (DB, logger, integrations) — injected, not imported.
- Each behavior is independently testable and could become an API endpoint or background job.
- No class hierarchies. Use Pydantic models for data, plain async functions for logic.

This is the unit of work. When in doubt: **one new requirement = one new behavior**.

---

## 8. Backend behaviors — specs (reference list)

Each row is a behavior to implement. Inputs/outputs are Pydantic models defined in `contract.py`. **Compound Engineering may adjust this list** (merge, split, rename, add) if a cleaner decomposition emerges during implementation, under the constraints in §7. Record changes in the same ADR (`0002-behavior-layout.md`).

| Behavior | Input | Output | Notes |
|---|---|---|---|
| `detect_card` | event from Rust | `CardDetected{volume_id, mount_path, label}` | Triggered by Tauri event forwarded over HTTP webhook to backend. |
| `list_today_customers` | `date` | `list[CustomerEvent{time, name, phone?, age?, weight?, type?}]` | Calls `composio_calendar.list_events(date)`. Parser tolerant — only `name` guaranteed. |
| `start_session` | `customer_name, drive_folder_url, source_mount_path, settings` | `Session{id, local_folder}` | Orchestrator. Creates local folders, persists session in SQLite, returns session id. |
| `resolve_drive_folder` | `drive_folder_url` | `DriveFolder{id, name, path}` | Parse URL → folder id → fetch metadata via Composio. Reject if not a folder. |
| `copy_media` | `session_id` | stream of progress events | Copies MP4 → `Videos/`, JPG → `Fotos/`. Idempotent. |
| `extract_frames` | `session_id, fps` | stream of progress events | For each MP4 in `Videos/`, write JPGs to `Fotos/`. Naming: `<video-basename>_<sec>.jpg`. |
| `upload_to_drive` | `session_id` | stream of progress events | Mirror local `Videos/` + `Fotos/` under the pasted Drive folder. Resumable uploads. Parallelism cap = 4. |
| `verify_upload` | `session_id` | `VerificationReport{ok, mismatches}` | Compare file sizes + md5 checksums between local and Drive. Required before card wipe. |
| `make_share_link` | `session_id` | `ShareLink{url, phone?}` | Returns Drive folder share URL + parsed phone (if available). |
| `wipe_card` | `session_id, confirm` | `WipeResult{ok}` | Only runs if (a) `confirm=True`, (b) verification passed. Never silent. |

---

## 9. Frontend pages — specs

**Separate contexts get separate pages. Operations contexts are unified into one page** because they are a single continuous flow the operator walks through without ever leaving. Config, setup, and logs stay separate.

| Route | Page | Purpose | Key components |
|---|---|---|---|
| `/` | **Idle** | Empty state. "Insert a card to begin." Tray icon active. | Status badge, last session summary. |
| `/session/:sessionId?` | **Session** (unified operation page) | Single page that walks the operator through the four steps: **Customer → Destination → Ingest → Done**. Implemented as a stepper inside one route — the operator never navigates away mid-session. State for the active step lives in a Zustand store keyed by `sessionId`. | `SessionStepper`, `CustomerStep`, `DestinationStep`, `IngestStep`, `DoneStep`. |
| `/settings` | **Settings** | All config (§12). Separate sub-tabs for Storage, Extraction, Integrations, Card. | `SettingsForm`. |
| `/setup` | **First-run setup** | One-time onboarding: pick local root, connect Composio, set Google Calendar id. | `Wizard` (3 steps). |
| `/logs` | **Logs** | View structured logs, filter by session. Read-only. | `LogTable`. |

**Step-component rules (inside `/session`)**
- Each step is its own component file under `pages/session/steps/`. No step imports another step.
- Step transitions are driven by the Zustand store, not React Router. The URL stays on `/session/:sessionId` throughout.
- Back/forward between steps is permitted **only** before upload starts. Once `IngestStep` begins copying, the flow is forward-only until `DoneStep`.
- The `DoneStep` is also where the optional "Wipe card" button lives. Same rules as before (verified upload required; explicit click; never silent).

**Navigation rules**
- The Idle page is the only entry point for normal use. The Session page is reached automatically on card insert, or via a "New session" button.
- Settings / Setup / Logs are reached via a hamburger menu, never from inside an active session.
- No global modals that block the workflow. Use the step components.
- Loading states: skeleton screens, not spinners that block input.

---

## 10. Backend HTTP API (frontend ↔ Python)

Base URL: `http://127.0.0.1:<port>`. Port written by sidecar to `~/.fly-video-automation/sidecar.port`. Frontend reads on startup.

All requests authenticated with a per-launch shared secret written to the same file. Header: `X-Sidecar-Token`.

### Endpoints

```
GET    /health                                    → {ok: true, version}
GET    /settings                                  → Settings
PUT    /settings                                  → Settings
GET    /setup/status                              → {composio_connected, calendar_id_set, local_root_set}
POST   /setup/composio/start                      → {auth_url}
POST   /setup/composio/complete                   → {ok}

GET    /customers/today                           → CustomerEvent[]
POST   /sessions                                  → Session (body: StartSessionInput)
GET    /sessions/:id                              → Session
GET    /sessions/:id/events  (Server-Sent Events) → stream of phase progress
POST   /sessions/:id/verify                       → VerificationReport
GET    /sessions/:id/share-link                   → ShareLink
POST   /sessions/:id/wipe-card                    → WipeResult (body: {confirm: true})

POST   /cards/detected      ← called by Tauri shell when a card is inserted
GET    /cards/current                             → CardDetected | null

GET    /logs                                      → LogEntry[]   (query: session_id?, level?)
```

SSE is used for long-running phases (copy, extract, upload). Each event: `{phase, current, total, message, ts}`.

---

## 11. Composio integration

Composio is the Google bridge. Use the Python SDK.

**Required Composio actions** (minimum set):
- `GOOGLECALENDAR_FIND_EVENT` (or equivalent list-events action) — list events for a date in the school calendar.
- `GOOGLEDRIVE_FIND_FOLDER` — resolve a folder by id.
- `GOOGLEDRIVE_CREATE_FILE` (or resumable upload equivalent) — upload files.
- `GOOGLEDRIVE_CREATE_PERMISSION` — make the folder shareable, get share URL.

**Setup steps the agent CANNOT complete autonomously** (add to `BLOCKERS.md`):
1. Create a Composio account / API key — **human action**.
2. Authenticate the school's Google account through Composio's OAuth flow — **human action** (browser consent).
3. Confirm which Composio "App" / integration variant is used — **human decision**.

**What the agent CAN do now:**
- Wire the SDK behind `integrations/composio_calendar.py` and `integrations/composio_drive.py` with clean interfaces.
- Mock the integrations in tests.
- Build the `/setup/composio/start` and `/setup/composio/complete` endpoints to handle the auth flow once the user provides the API key.
- Surface a clear error in the UI when the integration is not yet authenticated.

---

## 12. Settings schema

Stored at `~/.fly-video-automation/settings.json`. Validated by Pydantic. Editable from `/settings` page.

```json
{
  "local_root": "/path/to/archive",
  "drive_recent_folders": ["https://drive.google.com/drive/folders/..."],
  "calendar_id": "primary",
  "extraction": {
    "enabled": true,
    "fps": 1.0,
    "min_interval_seconds": 0.25,
    "max_interval_seconds": 10.0,
    "output_format": "jpg",
    "jpeg_quality": 90
  },
  "ingest": {
    "video_extensions": [".mp4", ".mov"],
    "photo_extensions": [".jpg", ".jpeg"],
    "ignore_hidden": true
  },
  "upload": {
    "parallel_uploads": 4,
    "chunk_size_mb": 16,
    "max_retries": 6
  },
  "card_wipe": {
    "enabled": false,
    "require_verification": true
  },
  "whatsapp": {
    "auto_open_when_phone_present": true
  },
  "ui": {
    "auto_focus_on_card_insert": true
  },
  "composio": {
    "api_key_set": false,
    "google_connected": false
  }
}
```

Settings page has 4 sub-tabs to keep contexts separate: **Storage**, **Extraction & Ingest**, **Upload & Card**, **Integrations**.

---

## 13. Build / run / test commands

Add these to `scripts/` and document in `README.md`.

```bash
# First-time setup (mac/linux)
./scripts/setup.sh

# Dev (runs Python sidecar + Tauri + Vite together)
./scripts/dev.sh

# Backend only
cd backend && uv run uvicorn fly_backend.main:app --reload

# Frontend only
cd app/ui && pnpm dev

# Tauri dev (assumes backend is running)
cd app/src-tauri && cargo tauri dev

# Tests
cd backend && uv run pytest
cd app/ui && pnpm test

# Lint
cd backend && uv run ruff check . && uv run mypy src/
cd app/ui && pnpm biome check .

# Build production binary (unsigned — personal distribution for v1)
./scripts/build-sidecar.sh   # PyInstaller, current OS
./scripts/package.sh          # Tauri bundle (unsigned .dmg / .msi for v1; signing returns in v2)
```

---

## 14. Coding conventions

### Python
- Black-compatible formatting via `ruff format`.
- Type hints mandatory. `mypy --strict` on `backend/src/`.
- Behavior handlers: `async def run(input: Input, ctx: Context) -> Output:` — that's the signature.
- No global mutable state. Pass `Context`.
- Errors: raise typed exceptions (`BehaviorError`, `IntegrationError`, `VerificationError`). HTTP layer maps to status codes.
- Logs: `structlog`. Include `session_id` and `behavior` in every log.

### TypeScript / React
- Strict TS.
- Function components only. No class components.
- One component per file. PascalCase filename.
- Hooks at top of component, no conditional hooks.
- API calls only via `src/api/` — never inline `fetch` in a component.
- No `any`. Use generated types from the backend Pydantic schemas (export OpenAPI → generate via `openapi-typescript`).

### Rust
- Keep it tiny. Only what Tauri needs.
- No business logic in Rust beyond disk watching and sidecar management.

### Commits
- Conventional commits: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`.
- One concern per commit.
- After every behavior is implemented + tested → commit.

---

## 15. Logging, error handling, recovery

- **Logs**: JSON via `structlog`. Written to `~/.fly-video-automation/logs/YYYY-MM-DD.log` (rotating). Also exposed via `/logs` endpoint.
- **Job queue**: SQLite. Every session's phases are rows. On startup, the backend **reconciles** any session in state `queued` or `running` to `failed` with reason `interrupted_by_restart`. The operator decides whether to retry — `copy_media` is idempotent via `FileRecord` rows so retry is cheap. Auto-resume was tried and walked back: see `docs/decisions/0003-no-auto-resume.md`.
- **Idempotency**: copy + upload behaviors must be safe to re-run. Use file hashes to skip already-completed files.
- **Backoff**: exponential on Drive 429/5xx, max 6 retries, then mark phase `failed` (not the session).
- **Crash safety**: writes go to temp filenames + atomic rename. Never partial writes visible to the upload step.

---

## 16. Definition of done — v1

A v1 ship is **only** complete when ALL of the following are true:

- [ ] App launches on macOS and Windows from **unsigned local builds** (personal distribution — code signing is explicitly out of scope for v1, see §19).
- [ ] Card insertion is detected on both OSes within 3 seconds.
- [ ] Customer list loads from Composio in < 2s on a normal day.
- [ ] Full ingest of a real session (copy + extract at the configured fps + upload + verify) completes without manual intervention. **No artificial size cap.** Any session size the local disk can hold must succeed.
- [ ] **Disk-full handling**: before starting a session, the system checks free space against estimated session size; if insufficient, the operator is shown a clear, blocking notification with the exact shortfall and no copy is started. Mid-session disk-full surfaces an explicit error on the Session page (not a silent failure) and the session is marked `failed` with state preserved for retry after the operator frees space.
- [ ] Upload verification compares md5 checksums and refuses to enable the wipe button on mismatch.
- [ ] All backend behaviors have unit tests; orchestrator (`start_session`, or its equivalent if CE renamed it) has an integration test with mocked Composio.
- [ ] All frontend pages exist and are reachable; operations are unified on `/session`; no page mixes concerns.
- [ ] Settings persisted and editable from UI.
- [ ] First-run setup wizard works (with Composio auth handed off to a real account by the human).
- [ ] `BLOCKERS.md` contains zero open `BLOCKED` items that the human hasn't explicitly accepted.
- [ ] `PROGRESS.md` shows every milestone in §16 checked.

---

## 17. Blocker protocol (read this carefully)

When you cannot complete something autonomously, **do not stop the build**. Do this:

1. Append a block to `BLOCKERS.md` using this template:

```markdown
## [BLOCKED] <short title>
- **Date:** 2026-MM-DD
- **Behavior/Module:** <where it surfaced>
- **Why blocked:** <human action required: account creation / OAuth / signing cert / API key / decision>
- **What I tried:** <commands, links, attempts>
- **What I built around it:** <stub / mock / interface ready for swap-in>
- **What the human needs to do:** <numbered, concrete steps>
- **Unblocked by:** <-- human checks this when done -->
```

2. Stub the dependency behind an interface so the rest of the system compiles and tests run.
3. Mark the affected behavior(s) with a `# BLOCKED: see BLOCKERS.md` comment.
4. Continue building everything else.

When you finish a session, **also** update `PROGRESS.md`:

```markdown
# Progress

## Done
- [x] Repo scaffolding
- [x] Behavior: list_today_customers (with mocked Composio)
- ...

## In progress
- [ ] ...

## Awaiting human (see BLOCKERS.md)
- [ ] Composio API key
- [ ] Google OAuth consent for school account
- [ ] Apple Developer ID for signing
- [ ] Windows code-signing cert

## Manual tests still to run
- [ ] Real card insert on macOS (Sonoma)
- [ ] Real card insert on Windows 11
- [ ] End-to-end 10 GB session against real Composio + Drive
```

---

## 17.5. Token budget handoff protocol (5-hour session window)

Sessions run against a **5-hour token window**. To avoid a hard cutoff mid-behavior:

1. **Monitor remaining tokens continuously.** When you cross **< 20%** remaining, **stop opening new work immediately.**
2. **Run `ce-compound`** to capture learnings, decisions made, and any patterns worth preserving.
3. **Create or append `HANDOFF.md`** at the repo root with the following structure:

   ```markdown
   # Handoff — <YYYY-MM-DD HH:MM>

   ## Where I stopped
   - Last commit: <sha + message>
   - Last behavior worked on: <name + state: scaffolded / in-progress / tested>
   - Last frontend step worked on: <component + state>

   ## What is fully done (verified)
   - <list>

   ## What is in-flight (incomplete — do not assume working)
   - <file paths + what is missing>

   ## What is next (concrete first 3 actions for the next session)
   1. ...
   2. ...
   3. ...

   ## Open questions / decisions to confirm with owner
   - <list>

   ## State of BLOCKERS.md
   - Open blockers: <count>
   - New blockers added this session: <list>

   ## ce-compound output reference
   - <path to the compound doc produced this session, if any>
   ```

4. **Commit cleanly** with message `chore: handoff at <YYYY-MM-DD HH:MM>`.
5. **End the session.** Do not start a new behavior. Do not start a new frontend page. Do not start anything you cannot finish before the window closes.

The next session resumes by reading `HANDOFF.md` **first**, then `PROGRESS.md`, then `BLOCKERS.md`, then `CLAUDE.md`. The "What is next" list in `HANDOFF.md` is the first 3 actions.

---

## 18. Pre-seeded blocker list (for `BLOCKERS.md` on first run)

The agent should create `BLOCKERS.md` with these entries already populated:

1. **Composio account + API key** — owner action.
2. **Connect school's Google account in Composio** (OAuth consent) — owner action.
3. **Confirm Google Calendar ID** to read events from (default `primary` or named) — owner decision.
4. **Pick `<RootLocal>` path** on the workstation — owner decision (also collectable via first-run setup UI).

**Note on testing card-insert detection:** the owner will leave an SD card inserted on the Mac during the build window. The agent **can and should** test the card-insert detection behavior on macOS end-to-end against this real card. On Windows, detection must still be implemented and unit-tested, but real end-to-end verification on Windows hardware is an owner-action item recorded as a manual test in `PROGRESS.md` (not a blocker).

**Code signing is explicitly NOT a blocker for v1.** The owner will distribute the app personally as an unsigned local build. macOS users will bypass Gatekeeper manually; Windows users will accept the SmartScreen warning. Document this in the `README.md` install instructions. Signing returns when the app moves online as a SaaS (v2+).

---

## 19. Out of scope (v1) and v2+ roadmap

### Out of scope for v1
- Auto-splitting one card across multiple customers.
- Video editing, trimming, watermarking, transcoding.
- Customer-facing portal.
- Direct media delivery (own CDN).
- Billing or CRM.
- Auth beyond a single school Google account.
- Multi-workstation sync.
- **Code signing and notarization** (Apple Developer ID, Windows code-signing cert). Owner distributes personally as unsigned builds for v1; signing returns when the app moves online.

### v2 productization roadmap (informs v1 architecture choices)
- **Move online (SaaS).** The Python backend already speaks HTTP — lift it onto a server. Frontend already decoupled — lift it to a web app. Tauri shell becomes optional (used only for local-disk ingest as a thin agent).
- **AI auto-editing.** Pluggable post-processing pipeline; each editor is a new behavior.
- **Customer portal.** Frontend route group, separate auth scope.
- **Direct delivery infrastructure.** Replace `wa.me` with branded share pages; CDN-backed.
- **Billing + CRM.** Tenant model, per-school workspaces.

Build v1 so that none of the above requires a rewrite — only additions. Concretely: no business logic in Rust; no Composio calls outside `integrations/`; no auth assumptions baked into behaviors; settings layer is per-instance, not global.

---

## 20. Glossary

- **Session** — one customer's ingest run. Includes copy + extract + upload + verify + (optional) wipe.
- **Behavior** — one vertical-slice unit of backend logic. See §7.
- **Card** — any inserted removable media: SD, microSD via reader, GoPro mounted as mass storage.
- **TD** — prefix for local customer folder, per the school's existing convention: `TD_<Customer Name>`.
- **HC / VIP** — jump types observed in Calendar titles.

---

## 21. First action when this file is read

1. `git init` in the working directory.
2. Create the directory tree per §6 (empty files OK to start).
3. Create `BLOCKERS.md` with the pre-seeded list from §18.
4. Create `PROGRESS.md` with empty sections.
5. Commit: `chore: initial scaffolding per CLAUDE.md`.
6. Start building, behavior by behavior, page by page, in this order:
   1. Repo + tooling (pyproject, package.json, tauri.conf, scripts).
   2. Backend skeleton + `/health` + settings layer.
   3. Behaviors with mocked integrations + unit tests.
   4. Frontend pages with mocked data.
   5. Tauri shell + disk watcher.
   6. Wire real Composio behind a feature flag (`COMPOSIO_LIVE=1`); default off.
   7. End-to-end against real Drive once human unblocks credentials.

Update `PROGRESS.md` at the end of every meaningful step.
