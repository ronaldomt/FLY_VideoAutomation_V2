# Plan: Stop session zombification, cap concurrency, fail loud on disk pressure

## Context

Yesterday's commit (`a4f4b5d`) correctly decoupled the ingest pipeline
from the SSE stream. It introduced a different, worse failure mode:
**mass auto-resume of accumulated zombie sessions**.

Operator-visible symptoms reproduced today (2026-05-25):

- The dev backend boots, logs `"resumed_pending_sessions"` with **8
  session IDs**, then runs all 8 orchestrators in parallel against the
  same local folder (`~/Desktop/TD_FLY/TD_Marina Ped`).
- Each one copies 2 files in ~3-10s, then starts `extract_frames`.
- All 8 ffmpeg processes write JPGs to the same `Fotos/` directory.
- The disk fills (it was already at 100% capacity, 1.8 GB free on
  460 GB volume). ffmpeg crashes mid-write with `errno 28`.
- The .app UI still points at one of the zombie session IDs and shows
  `stream_error: connection failed` + `Copying media 2/2` indefinitely.
- Dev frontend at `localhost:5173` shows "Sidecar unreachable" — a
  separate config mismatch.

`sqlite3 ~/.fly-video-automation/queue.sqlite` shows the lifetime damage
the broken architecture accumulated before yesterday's fix: **1 cancelled,
3 completed, 20 failed**. Most failures are `disk_full`, `ffmpeg_failed`
(disk full mid-extraction), and `verification_failed: 113 mismatches`.
Most "running" rows from the old SSE-driven design never got marked
terminal when the SSE connection dropped — they sat as live landmines
for `resume_pending()` to step on.

This blocks the V1 success criteria in CLAUDE.md §2 ("Handles 10–30
customers/day, 50–200 GB/day without operator babysitting") and §16
("Zero file loss", "Disk-full handling: blocking notification with exact
shortfall, no copy started"). Today, sessions can be silently lost,
the disk can be hosed by zombies, and the operator gets a generic
"stream_error" with no actionable signal.

## Root causes

| # | Cause | Why it bites |
|---|---|---|
| 1 | `orchestrator.resume_pending()` blindly spawns every `queued`/`running` session at startup. | Stale rows from earlier broken versions of the code persist forever. One restart = 8 parallel orchestrators. |
| 2 | No concurrency cap on `orchestrator.spawn()`. | The CLAUDE.md scope explicitly says "one session at a time per the V1 scope" — but the code permits N parallel sessions, with no per-session isolation of the `Fotos/` directory or ffmpeg processes. |
| 3 | `extract_frames` has no disk-space preflight. The check in `start_session.handler.py:42-49` only runs at session creation, with a 1.5× headroom estimate that gets stale by the time the session resumes hours/days later. | ffmpeg fails with cryptic `errno 28` after writing corrupt half-files. The session enters `failed` only after partial writes pollute `Fotos/`. |
| 4 | Dev frontend has no `.env.local`. `app/ui/src/api/config.ts:21` defaults to `http://127.0.0.1:8765`, but `backend/run-dev.sh` binds to `:8000`. | "Sidecar unreachable" in dev — easy to mistake for a backend bug. |

(2), (3), and (4) are all real problems independent of (1). The "fix it
for real" plan is to address all four — they reinforce each other in
exactly the failure mode the operator sees.

## Approach

Five pieces, smallest possible scope each:

1. **Replace `resume_pending()` with `reconcile_pending()`.** At startup,
   mark every session left in `queued`/`running` as `failed` with reason
   `interrupted_by_restart`. **Do not auto-respawn.** The V1 operator
   model is "one operator, one card per session"; if a session didn't
   finish, the operator decides whether to retry — they don't expect the
   sidecar to silently pick up old work behind their back. This is a
   deliberate retreat from CLAUDE.md §15's "resume any session in state
   running or queued" because that spec line was written before we
   understood how badly stale state accumulates without a cap. Documented
   as ADR `docs/decisions/0003-no-auto-resume.md`.

2. **Cap concurrent orchestrator tasks at 1.** `orchestrator.spawn()`
   rejects new requests when any other task is already alive, surfacing
   a `409 session_concurrency_limit` from the POST `/sessions` route.
   The frontend handles 409 by surfacing "Another session is already
   running — finish or cancel it first." Configurable
   (`settings.session_concurrency = 1`) so v2 can bump it without code
   changes.

3. **Disk-space preflight in `extract_frames` and `upload_to_drive`,
   plus continuous checking inside the extract loop.**
   - At phase start: `check_free_space(local_root, estimate)` against
     a conservative estimate (`2× total video bytes` for extract;
     `0 + 5% headroom` for upload — upload doesn't write locally but a
     buffer is still smart).
   - Inside the extract loop, between videos: re-check free space.
     If below a low-water mark (e.g., 500 MB), abort the phase with
     `BehaviorError("disk_full_during_extraction: {free} free")`.
   - The orchestrator catches and marks the session `failed` with that
     reason. No corrupt JPGs left behind (see piece 4).

4. **Atomic JPG writes for `extract_frames`.** ffmpeg writes to a
   temp subdirectory `Fotos/.in-progress-<video-basename>/`; on success,
   `os.rename` the directory to `Fotos/` (or move files individually
   into `Fotos/`). On failure or cancel, delete the temp directory.
   No partial JPGs ever land alongside verified ones. This makes
   re-extraction after a `disk_full` failure idempotent (the operator
   frees space and retries — `extract_frames` finds no orphan JPGs to
   trip over).

5. **Frontend Idle page lists recent failed sessions + a "Clear all
   failed" button.** Today, when something fails, the operator has no
   surface to see what happened or to clean up the DB row. The new
   list shows: customer name, when, error reason (one-liner mapped
   from internal code → operator-readable). "Clear all failed"
   discards the DB rows (does NOT delete local folders — that's a
   separate, scarier action). One-line summary on Idle: "3 failed
   sessions awaiting cleanup."

6. **Dev frontend env fix.** Create
   `app/ui/.env.example` documenting the variables, and either (a) check
   in `app/ui/.env.local` (gitignored elsewhere — must check)
   pointing at `http://127.0.0.1:8000` + `dev-token`, OR (b) change the
   default in `config.ts` to `8000` to match `run-dev.sh`. Option (b)
   is simpler and works out of the box for any dev — recommended.

## Critical files

### Backend

- `backend/src/fly_backend/orchestrator.py`
  - Replace `resume_pending()` body with `reconcile_pending()`: open a
    DB session, find sessions in `(queued, running)`, set
    `status = failed`, `error = "interrupted_by_restart"`, commit.
    Return the list of reconciled IDs for logging.
  - In `spawn()`: before creating a task, check the registry for any
    other alive task. If found, raise `ConcurrencyLimitError`
    (new error type in `errors.py`). Keep the idempotency-for-same-id
    branch intact.

- `backend/src/fly_backend/main.py`
  - Rename the lifespan call from `orchestrator.resume_pending()` to
    `orchestrator.reconcile_pending()`. Update the log message from
    `"resumed_pending_sessions"` to `"reconciled_orphaned_sessions"`.

- `backend/src/fly_backend/errors.py`
  - New exception `ConcurrencyLimitError(BehaviorError)`.

- `backend/src/fly_backend/http/routes.py`
  - In `sessions_create`: catch `ConcurrencyLimitError`, return
    `HTTPException(409, detail="session_concurrency_limit")`.

- `backend/src/fly_backend/behaviors/extract_frames/handler.py`
  - At top, after the early-out checks, compute `total_video_bytes` and
    call `check_free_space(local, total_video_bytes * 2)`. If `not ok`,
    raise `BehaviorError(f"disk_full_at_extract_start: free={free}, needed={needed}")`.
  - In the per-video loop, between videos, re-check
    `shutil.disk_usage(local).free`; if under a low-water threshold
    (500 MB), raise `BehaviorError("disk_full_during_extraction")`.
  - Wrap the call to `ctx.ffmpeg.extract_frames(...)` so each video
    writes into a temp dir; on success, move files into `Fotos/`; on
    exception, `shutil.rmtree(temp_dir, ignore_errors=True)`.

- `backend/src/fly_backend/behaviors/upload_to_drive/handler.py`
  - Add a minimal preflight: refresh the cached Drive folder ID
    (`drive.get_folder(drive_folder_id)`); if it raises, mark phase
    `failed` cleanly with reason `drive_folder_not_found`.

- `backend/src/fly_backend/http/routes.py`
  - New `GET /sessions/recent?status=failed&limit=20` returning a list
    of recent sessions for the Idle page.
  - New `DELETE /sessions/failed` returning `{deleted: N}` — removes
    all `failed` and `cancelled` rows older than 1 day (configurable
    via query param `older_than_hours`). Cascades to the `Phase` and
    `FileRecord` rows via the foreign keys.

- `backend/src/fly_backend/settings.py`
  - Add `session_concurrency: int = 1` to the top-level `Settings`.

### Frontend

- `app/ui/src/api/config.ts:21`
  - Change `DEFAULT_URL` from `http://127.0.0.1:8765` to
    `http://127.0.0.1:8000`. Add a comment noting this matches
    `backend/run-dev.sh`.

- `app/ui/.env.example` (new)
  - Document `VITE_SIDECAR_URL` and `VITE_SIDECAR_TOKEN` so future devs
    can override.

- `app/ui/src/api/client.ts`
  - Add `recentSessions: (status?: string) => GET /sessions/recent?...`
    and `clearFailedSessions: () => DELETE /sessions/failed`.

- `app/ui/src/pages/idle/IdlePage.tsx`
  - Fetch `/sessions/recent?status=failed` on mount.
  - Render a `FailedSessionsCard` with customer name, time, and a
    short error label per row. Include a "Clear all failed" button
    that calls `clearFailedSessions()` and refetches.

- `app/ui/src/pages/session/steps/CustomerStep.tsx`
  - On `createSession` 409 response, surface "Another session is still
    running. Cancel it or wait for it to finish." Don't auto-transition
    to the Ingest step.

- `app/ui/src/pages/session/steps/IngestStep.tsx`
  - Map common backend error reasons to operator-friendly text in the
    `pipeline_error` handler:
    - `disk_full_at_extract_start` / `disk_full_during_extraction` →
      "Disk is full — free space on the archive drive and retry."
    - `drive_folder_not_found` → "Drive folder is missing — re-paste the
      URL in Settings → Destination."
    - `interrupted_by_restart` → "This session was interrupted by a
      backend restart. Discard it and create a new one."

### Settings / docs

- `docs/decisions/0003-no-auto-resume.md` (new) — short ADR explaining
  why CLAUDE.md §15's resume-on-restart line is being walked back.
- Update `CLAUDE.md §15` ("Logging, error handling, recovery"): change
  the resume sentence to: *"On startup, the backend reconciles any
  session in state `queued` or `running` to `failed` with reason
  `interrupted_by_restart`. The operator decides whether to retry — copy
  is idempotent via `FileRecord` rows so retry is cheap."*

## Implementation units (suggested order)

| # | Unit | Why this order |
|---|---|---|
| 1 | Reconcile-on-restart (orchestrator + main.py + ADR) | Stops the bleeding immediately. After this, restarting the backend no longer spawns zombies. |
| 2 | Concurrency cap (orchestrator + routes + errors) | Even with reconcile, two cards inserted in quick succession could create two sessions; we want hard isolation. |
| 3 | Disk preflight in extract_frames + low-water check + atomic temp dir | Closes the actual failure mode the operator hit. ffmpeg can no longer corrupt files. |
| 4 | Drive preflight in upload_to_drive | Mirrors (3) for the next phase. |
| 5 | `/sessions/recent` + `/sessions/failed` endpoints + frontend Idle list + Clear button | Makes the state visible. Operator can clean up without sqlite3. |
| 6 | Dev env config fix (`DEFAULT_URL` + `.env.example`) | Unblocks dev iteration; tiny patch. |

Units 1–3 are the critical path. 4–6 are quick wins that should land in
the same PR if scope allows.

## Test scenarios

- `backend/tests/unit/test_orchestrator.py` (update existing):
  - `reconcile_pending()` flips queued+running rows to failed with the
    correct reason. Completed/cancelled/failed rows untouched.
  - `spawn()` rejects when another task is alive, raising
    `ConcurrencyLimitError`.
  - `spawn()` still idempotent for the same session_id.

- `backend/tests/unit/test_extract_frames_preflight.py` (new):
  - Preflight raises `BehaviorError("disk_full_at_extract_start")`
    when `check_free_space` reports not-ok. Use `monkeypatch` to
    stub `shutil.disk_usage`.
  - In-loop low-water check raises after the first video if the stub
    drops below threshold.
  - Atomic temp dir: on simulated ffmpeg failure, the temp dir is
    removed and `Fotos/` contains no partial JPGs.

- `backend/tests/unit/test_routes_recent_and_clear.py` (new):
  - `GET /sessions/recent?status=failed&limit=5` returns the 5 most
    recent failed sessions in descending `created_at` order.
  - `DELETE /sessions/failed?older_than_hours=24` removes only failed
    rows older than 24h, leaves recent failures and any non-failed.
  - Cascades remove orphan `Phase` and `FileRecord` rows.

- `app/ui/src/pages/idle/IdlePage.test.tsx` (new):
  - Renders the failed-sessions card with one row per failure.
  - "Clear all failed" calls the API and refetches.

- `app/ui/src/pages/session/steps/CustomerStep.test.tsx` (update or
  new):
  - On a 409 response from `createSession`, shows the "Another session
    is still running" message and does NOT transition to ingest.

## Verification (manual, end-to-end)

1. **Clean up the broken state first** (do this once, outside the
   automated migration):
   ```
   sqlite3 ~/.fly-video-automation/queue.sqlite "UPDATE session SET status='failed', error='cleaned_up_2026_05_25' WHERE status IN ('queued','running');"
   ```
   Then free disk space on the archive drive until at least 50 GB
   are available, OR point `local_root` at a different volume.
2. Run `./backend/run-dev.sh`. The backend log should report
   `reconciled_orphaned_sessions: []` (because we just cleaned them).
   It should NOT log any `orchestrator_started` events at boot.
3. Run `cd app/ui && pnpm dev`. Open `localhost:5173`. The status
   should show "Connected" (or the green equivalent), not "Sidecar
   unreachable".
4. Insert a real GoPro card. Create a session. Confirm copy → extract
   → upload → verify → done. Confirm `Fotos/` contains only the final
   JPGs (no `.in-progress-*` debris).
5. While a session is running, try to create a second session from the
   UI. Expect a "Another session is still running" message; the second
   session is NOT created in the DB.
6. Force a disk-full scenario: copy a large dummy file onto the
   archive drive until <500 MB free; start a new session. Expect the
   session to fail cleanly at extract start with the disk-full
   message; no partial JPGs anywhere; the orchestrator log shows
   `disk_full_at_extract_start`.
7. Restart the backend mid-session. Expect the in-flight session to
   be reconciled to `failed` with reason `interrupted_by_restart`.
   The Idle page should list it under "Failed sessions" with that
   reason. "Clear all failed" removes it.

## What stays untouched

- The orchestrator's core fanout-queue + subscriber architecture from
  yesterday's commit. That's correct.
- `copy_media` — already idempotent via `FileRecord` rows.
- `verify_upload` — unchanged.
- The SSE event protocol (`progress` / `verification` / `done` /
  `cancelled` / `pipeline_error`). Wire format preserved so existing
  client handlers keep working.

## Risks and second-order effects

- **Operator data loss perception.** Reconciling instead of resuming
  means a long upload that was 80% done before a restart is "lost"
  from the operator's perspective, even though `copy_media` and
  uploaded files are still on disk + Drive. Mitigation: the failed
  session is listed on the Idle page with its error; the operator can
  read it. Future v2: a "Resume this session" button on the failed
  row that calls `orchestrator.spawn(id)` explicitly — opt-in resume
  instead of opt-out.
- **Concurrency cap=1 is restrictive.** Some operators may hot-swap
  cards while a previous upload is still finishing. v1 scope says
  this is fine; v2 may want N>1. Settings-controlled.
- **Disk low-water threshold is a heuristic.** 500 MB may not be
  enough headroom for a single 4K video's frame extraction. The
  preflight estimate (2× video bytes) is more conservative but
  ffmpeg's actual output varies with content. Mitigation: log the
  free-space delta after each video so we can refine the heuristic
  with real numbers.
- **The frontend Idle list grows over time.** Bound the API to the
  most recent 50; provide a separate `/logs` view for historical
  digging (already exists in `app/ui/src/pages/logs/` per the routes).
- **Walking back CLAUDE.md §15 is a design change.** Worth a brief
  conversation with yourself / future-you before shipping; the ADR
  records the rationale. The spec line was written before zombie
  accumulation was a known failure mode.

## Out of scope

- Replacing SQLite with a real job queue. Single workstation, fine.
- Multi-session parallelism (v2).
- Automatic local-folder cleanup when sessions are deleted.
- An operator UI for editing the source mount path of a failed
  session before retry. (v2: probably a "Retry from card" affordance
  on each failed row that re-prompts for the card.)

## Sources

- Conversation log including the dev backend output showing 8 parallel
  `orchestrator_started` events at `2026-05-25T17:47:37` through
  `17:48:20`, followed by 7 `orchestrator_failed: ffmpeg_failed` events
  at `17:48:32` with `No space left on device`.
- `sqlite3 ~/.fly-video-automation/queue.sqlite` snapshot showing
  1 cancelled, 3 completed, 20 failed sessions, with recurring
  `disk_full`, `ffmpeg_failed (disk_full)`, and
  `verification_failed: 113 mismatches`.
- `df -h ~/Desktop` showing 460 GB volume at 100% capacity (1.8 GB free).
- Yesterday's plan + commit `a4f4b5d` ("fix(ingest): detach pipeline
  from SSE so disconnects don't restart copy"), which is correct but
  introduced the auto-resume regression.
- `backend/src/fly_backend/util/disk.py` (`check_free_space`,
  `estimate_card_size`) — the preflight machinery already exists, this
  plan just calls it from more phases.
