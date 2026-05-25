"""Detached orchestrator for the ingest pipeline.

Per CLAUDE.md §15: every session runs as a background ``asyncio.Task`` whose
lifecycle is independent of any HTTP client. SSE subscribers observe
``ProgressEvent``s fanned out from the task. Disconnects do not stop work;
reconnects do not restart it.

Public surface (used by ``http/routes.py`` and ``main.py``):

- ``orchestrator.spawn(session_id)`` — idempotent; starts the pipeline task.
- ``orchestrator.subscribe(session_id)`` — returns an ``asyncio.Queue`` that
  receives every event published for this session, or ``None`` if no task is
  running (caller handles "already terminal" via DB snapshot).
- ``orchestrator.unsubscribe(session_id, queue)`` — drop a subscriber.
- ``orchestrator.cancel(session_id)`` — set the per-session cancel event.
- ``orchestrator.is_running(session_id)`` / ``wait(session_id)`` — introspection.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Callable
from typing import Final

from .behaviors.copy_media.contract import CopyMediaInput
from .behaviors.copy_media.handler import run as copy_media
from .behaviors.extract_frames.contract import ExtractFramesInput
from .behaviors.extract_frames.handler import run as extract_frames
from .behaviors.upload_to_drive.contract import UploadToDriveInput
from .behaviors.upload_to_drive.handler import run as upload_to_drive
from .behaviors.verify_upload.contract import VerifyUploadInput
from .behaviors.verify_upload.handler import run as verify_upload
from .context import Context, build_default_context
from .errors import ConcurrencyLimitError
from .logging import get_logger
from .persistence.models import Session, SessionStatus
from .settings import load_settings

# Per-subscriber queue cap. Drop-oldest on overflow; DB Phase rows are the
# source of truth for progress, so a lagging UI catches up on the next event.
_QUEUE_MAX: Final[int] = 1000

_ContextFactory = Callable[[], Context]


class _SessionState:
    __slots__ = ("cancel_event", "subscribers", "task")

    def __init__(self, task: asyncio.Task[None], cancel_event: asyncio.Event) -> None:
        self.task = task
        self.subscribers: list[asyncio.Queue[dict[str, str]]] = []
        self.cancel_event = cancel_event


class Orchestrator:
    """Process-wide registry of in-flight ingest pipelines."""

    def __init__(self, context_factory: _ContextFactory = build_default_context) -> None:
        self._context_factory = context_factory
        self._states: dict[str, _SessionState] = {}
        self._lock = asyncio.Lock()
        self._log = get_logger("fly_backend.orchestrator")

    def set_context_factory(self, factory: _ContextFactory) -> None:
        """Used by tests to inject a Context backed by in-memory DB / mocks."""
        self._context_factory = factory

    async def spawn(self, session_id: str) -> asyncio.Task[None]:
        """Start the pipeline for ``session_id`` if not already running.

        Idempotent: a second call while the task is alive returns the same task.
        Raises ``ConcurrencyLimitError`` when another distinct session is
        already alive and ``settings.session_concurrency`` would be exceeded.
        """
        async with self._lock:
            state = self._states.get(session_id)
            if state is not None and not state.task.done():
                return state.task
            alive_others = [
                sid
                for sid, st in self._states.items()
                if sid != session_id and not st.task.done()
            ]
            cap = max(1, load_settings().session_concurrency)
            if len(alive_others) >= cap:
                raise ConcurrencyLimitError(
                    f"session_concurrency_limit: {len(alive_others)} in flight, "
                    f"cap={cap}, alive={alive_others}"
                )
            cancel_event = asyncio.Event()
            task = asyncio.create_task(
                self._run(session_id, cancel_event), name=f"ingest:{session_id}"
            )
            self._states[session_id] = _SessionState(task, cancel_event)
            return task

    def subscribe(self, session_id: str) -> asyncio.Queue[dict[str, str]] | None:
        state = self._states.get(session_id)
        if state is None or state.task.done():
            return None
        q: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=_QUEUE_MAX)
        state.subscribers.append(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue[dict[str, str]]) -> None:
        state = self._states.get(session_id)
        if state is None:
            return
        with contextlib.suppress(ValueError):
            state.subscribers.remove(q)

    async def cancel(self, session_id: str) -> None:
        state = self._states.get(session_id)
        if state is None or state.task.done():
            return
        state.cancel_event.set()

    def is_running(self, session_id: str) -> bool:
        state = self._states.get(session_id)
        return state is not None and not state.task.done()

    async def wait(self, session_id: str) -> None:
        """For tests / shutdown: block until the orchestrator task finishes."""
        state = self._states.get(session_id)
        if state is None:
            return
        with contextlib.suppress(asyncio.CancelledError):
            await state.task

    async def reconcile_pending(self) -> list[str]:
        """Mark every session left in queued/running as ``failed``.

        Called from the FastAPI lifespan on startup. We deliberately do NOT
        respawn these sessions — see ``docs/decisions/0003-no-auto-resume.md``.
        The V1 operator model is "one operator, one card per session"; auto
        resume causes accumulated stale rows from earlier broken versions of
        the code to all spawn in parallel on the next boot, hosing the local
        disk before the operator can react. ``copy_media`` is idempotent via
        ``FileRecord`` rows, so the operator can cheaply retry a failed
        session by inserting the same card and picking the customer again.

        Returns the list of reconciled session IDs for logging.
        """
        from sqlmodel import select

        from .persistence.models import Session, SessionStatus

        ctx = self._context_factory()
        reconciled: list[str] = []
        with ctx.db.session() as db:
            rows = db.exec(
                select(Session).where(
                    Session.status.in_(  # type: ignore[attr-defined]
                        [SessionStatus.queued, SessionStatus.running]
                    )
                )
            ).all()
            for s in rows:
                s.status = SessionStatus.failed
                if not s.error:
                    s.error = "interrupted_by_restart"
                db.add(s)
                reconciled.append(s.id)
            if reconciled:
                db.commit()
        return reconciled

    def _publish(self, session_id: str, event_name: str, data: str) -> None:
        state = self._states.get(session_id)
        if state is None:
            return
        payload = {"event": event_name, "data": data}
        for q in list(state.subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    _ = q.get_nowait()
                    q.put_nowait(payload)
                    self._log.warning(
                        "subscriber_queue_overflow_dropped_oldest",
                        session_id=session_id,
                    )
                except Exception:
                    pass

    async def _run(self, session_id: str, cancel_event: asyncio.Event) -> None:
        log = self._log.bind(session_id=session_id)
        log.info("orchestrator_started")
        base = self._context_factory()
        ctx = Context(
            settings=base.settings,
            logger=base.logger,
            calendar=base.calendar,
            drive=base.drive,
            ffmpeg=base.ffmpeg,
            db=base.db,
            cancel_event=cancel_event,
        )

        with ctx.db.session() as db:
            sess = db.get(Session, session_id)
            if sess is None:
                log.error("session_not_found_for_orchestrator")
                self._finalize(session_id)
                return
            if sess.status == SessionStatus.queued:
                sess.status = SessionStatus.running
                db.add(sess)
                db.commit()

        try:
            for behavior, inp in (
                (copy_media, CopyMediaInput(session_id=session_id)),
                (extract_frames, ExtractFramesInput(session_id=session_id)),
                (upload_to_drive, UploadToDriveInput(session_id=session_id)),
            ):
                async for event in behavior(inp, ctx):  # type: ignore[arg-type]
                    if cancel_event.is_set():
                        break
                    self._publish(session_id, "progress", event.model_dump_json())
                if cancel_event.is_set():
                    self._mark_session_cancelled(ctx, session_id)
                    self._publish(
                        session_id,
                        "cancelled",
                        json.dumps({"session_id": session_id}),
                    )
                    log.info("orchestrator_cancelled")
                    return

            report = await verify_upload(VerifyUploadInput(session_id=session_id), ctx)
            self._publish(session_id, "verification", report.model_dump_json())

            with ctx.db.session() as db:
                sess = db.get(Session, session_id)
                if sess is not None:
                    sess.status = (
                        SessionStatus.completed if report.ok else SessionStatus.failed
                    )
                    if not report.ok:
                        sess.error = (
                            f"verification_failed: {len(report.mismatches)} mismatches"
                        )
                    db.add(sess)
                    db.commit()

            self._publish(
                session_id,
                "done",
                json.dumps({"ok": report.ok, "session_id": session_id}),
            )
            log.info("orchestrator_completed", ok=report.ok)
        except asyncio.CancelledError:
            log.warning("orchestrator_task_cancelled")
            raise
        except Exception as exc:
            log.error("orchestrator_failed", error=str(exc))
            with ctx.db.session() as db:
                sess = db.get(Session, session_id)
                if sess is not None and sess.status not in {
                    SessionStatus.completed,
                    SessionStatus.cancelled,
                }:
                    sess.status = SessionStatus.failed
                    sess.error = str(exc)
                    db.add(sess)
                    db.commit()
            self._publish(
                session_id,
                "pipeline_error",
                json.dumps({"message": str(exc), "session_id": session_id}),
            )
        finally:
            self._finalize(session_id)

    def _mark_session_cancelled(self, ctx: Context, session_id: str) -> None:
        with ctx.db.session() as db:
            sess = db.get(Session, session_id)
            if sess is not None and sess.status not in {
                SessionStatus.completed,
                SessionStatus.failed,
            }:
                sess.status = SessionStatus.cancelled
                db.add(sess)
                db.commit()

    def _finalize(self, session_id: str) -> None:
        state = self._states.pop(session_id, None)
        if state is not None:
            state.subscribers.clear()


orchestrator = Orchestrator()
