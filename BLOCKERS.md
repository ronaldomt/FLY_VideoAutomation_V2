# Blockers

This file lists items that require **human action** before the build can proceed end-to-end. The agent works around blockers (stubs / mocks) and continues building everything else. See `CLAUDE.md` §17 for protocol.

Status legend:
- `[BLOCKED]` — waiting on the human owner
- `[UNBLOCKED]` — resolved; left here for history

---

## [BLOCKED] Composio account + API key

- **Date:** 2026-05-21
- **Behavior/Module:** `backend/src/fly_backend/integrations/composio_calendar.py`, `composio_drive.py`
- **Why blocked:** Human owner must create a Composio account and generate an API key. The agent cannot complete account signup.
- **What I tried:** Wired the integration interfaces behind a `COMPOSIO_LIVE` feature flag, defaulting OFF. Mocked integrations used in tests.
- **What I built around it:** `integrations/composio_*.py` with clean interfaces (`list_events(date)`, `get_folder(folder_id)`, `upload_file(...)`, `create_share_permission(...)`). Mocked implementations registered when `COMPOSIO_LIVE=0`.
- **What the human needs to do:**
  1. Sign up at https://app.composio.dev/
  2. Create an API key.
  3. Provide the API key during first-run setup (Setup wizard → Integrations) OR set `COMPOSIO_API_KEY` env var.
- **Unblocked by:** <!-- human checks this when done -->

## [BLOCKED] Connect school's Google account in Composio (OAuth consent)

- **Date:** 2026-05-21
- **Behavior/Module:** `behaviors/list_today_customers`, `resolve_drive_folder`, `upload_to_drive`, `make_share_link`
- **Why blocked:** Google OAuth consent must be granted interactively by the school's account owner in a browser. Cannot be automated.
- **What I tried:** Built `/setup/composio/start` endpoint that returns a Composio-issued auth URL and `/setup/composio/complete` to finalize once the redirect callback fires.
- **What I built around it:** Setup wizard step that opens the auth URL in the default browser and polls `/setup/status`. Real OAuth path is dormant until the API key blocker is resolved.
- **What the human needs to do:**
  1. After Composio API key is set, run the first-run Setup wizard.
  2. Click **Connect Google** → complete consent in the browser using the school's Google account.
  3. Confirm the connection by returning to the app.
- **Unblocked by:** <!-- human checks this when done -->

## [BLOCKED] Confirm Google Calendar ID

- **Date:** 2026-05-21
- **Behavior/Module:** `behaviors/list_today_customers`
- **Why blocked:** The school may use the primary calendar or a named one. Owner decision needed.
- **What I tried:** Defaulted `calendar_id` to `primary` in `settings.json` schema (§12). Setup wizard step exposes a dropdown populated from `GOOGLECALENDAR_LIST_CALENDARS` once Composio is connected.
- **What I built around it:** Behavior reads `calendar_id` from settings; works with any value the user picks.
- **What the human needs to do:**
  1. Decide whether the school's bookings live on `primary` or a named calendar.
  2. Select it in the Setup wizard.
- **Unblocked by:** <!-- human checks this when done -->

## [BLOCKED] Pick `<RootLocal>` path on the workstation

- **Date:** 2026-05-21
- **Behavior/Module:** `behaviors/start_session`, `behaviors/copy_media`
- **Why blocked:** Owner must choose where local archives live (probably a large external drive on the workstation).
- **What I tried:** First-run Setup wizard has a "Choose archive folder" step using the OS file picker.
- **What I built around it:** Behaviors read `local_root` from settings and refuse to start a session if unset.
- **What the human needs to do:**
  1. Run the Setup wizard on the workstation.
  2. Pick the desired root path (e.g., `/Volumes/FLY_Archive`).
- **Unblocked by:** <!-- human checks this when done -->

---

## [BLOCKED] Replace placeholder Tauri icons with real artwork

- **Date:** 2026-05-21
- **Behavior/Module:** `app/src-tauri/icons/`
- **Why blocked:** v1 ships with **placeholder** PNG/ICNS/ICO icons (1-colour 32/128/256 px). They satisfy `tauri-build`'s validators so the app compiles, but they're not production artwork.
- **What I tried:** Generated valid-but-trivial PNG/ICO/ICNS files so the Tauri build doesn't fail on missing icons.
- **What I built around it:** Nothing else depends on the icon visual.
- **What the human needs to do:**
  1. Provide the FLY brand mark (or commission one).
  2. Replace the 5 files under `app/src-tauri/icons/` (32×32, 128×128, 128×128@2x, `icon.icns`, `icon.ico`).
  3. Optionally generate them with `cargo tauri icon path/to/source.png` once the source is ready.
- **Unblocked by:** <!-- human checks this when done -->

## Notes (not blockers)

- **Card-insert detection — macOS end-to-end test:** owner will leave an SD card inserted during the build window. The agent CAN and SHOULD verify detection on macOS end-to-end. (See `PROGRESS.md` → Manual tests.)
- **Card-insert detection — Windows end-to-end test:** implemented + unit-tested. Real end-to-end verification on Windows hardware is a **manual test** (see `PROGRESS.md`), not a blocker.
- **Code signing (Apple Developer ID + Windows code-signing cert):** explicitly **out of scope** for v1 per `CLAUDE.md` §18 and §19. Owner distributes personally as unsigned local builds. NOT a blocker.
