# ADR 0003 — No auto-resume of orphaned sessions on sidecar startup

- **Date:** 2026-05-25
- **Status:** Accepted
- **Supersedes (partially):** CLAUDE.md §15 (the "resume any session in
  state running or queued" sentence)

## Context

CLAUDE.md §15 originally said:

> *Job queue: SQLite. Every session's phases are rows. On startup, the
> backend resumes any session in state `running` or `queued`.*

That line was written before the orchestrator existed as a detached
asyncio task. It assumed sessions would always be cleanly written to a
terminal state when they finished, and that any session left
`running`/`queued` represented honest unfinished work the sidecar
should pick back up.

In practice — once the orchestrator was decoupled from the SSE generator
in commit `a4f4b5d` and `resume_pending()` was added per spec — the
first boot of the new sidecar found **8 sessions** still marked
`running` from earlier broken versions of the code (where the
SSE-driven pipeline dropped the session mid-flight without marking it
terminal). All 8 spawned in parallel, all targeting the same local
folder, all extracting frames in parallel. The disk (already at 100%
capacity on the operator's workstation) was hosed in under a minute.

The pattern is structural, not a one-off: any time the sidecar process
dies during a session, the row is left as a landmine for the next boot.
There is no garbage-collection layer between "the process crashed" and
"resume on next boot."

## Decision

On startup, the sidecar **reconciles** orphaned sessions: every session
in `queued` or `running` is flipped to `failed` with reason
`interrupted_by_restart`. The orchestrator does NOT spawn any
background task for them.

## Rationale

1. **V1 operator model is one operator, one card per session.** The
   operator initiates each session deliberately; they don't expect
   background work to materialize from a previous run.
2. **`copy_media` is already idempotent** via `FileRecord` rows. Retry
   is cheap: insert the same card, pick the same customer, the copy
   phase skips already-completed files.
3. **Auto-resume failure mode is silent and catastrophic.** Disk
   exhaustion from N parallel zombies is far worse than the operator
   being told "this session was interrupted, click Retry."
4. **Concurrency cap (ADR 0004 / implementation companion)** caps live
   sessions at 1 anyway. Reviving N stale sessions in parallel
   contradicts that cap.

## Consequences

- Long uploads interrupted by a sidecar crash require an explicit
  retry. The bytes are already on disk (and partially on Drive via
  resumable uploads), so the operator only loses time, not data.
- CLAUDE.md §15 needs updating — done in the same commit as this ADR.
- Future v2: an explicit per-session "Resume" button on each failed
  row in the Idle page (opt-in resume instead of opt-out) is a clean
  way to bring back the spec's original intent without the
  zombie-pileup risk.

## Operational note

The Idle page surfaces failed sessions with their reason
(`interrupted_by_restart` is one of the friendly-mapped messages), and
includes a "Clear all failed" button that removes the DB rows older
than 1 day. Local folders are NOT deleted by Clear — that's a
deliberately separate, scarier action.
