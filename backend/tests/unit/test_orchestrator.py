"""End-to-end tests for the detached orchestrator (CLAUDE.md §15).

These exercise the lifecycle: spawn → publish → cancel → finalize. The
pipeline runs against an empty card directory so every behavior completes
cleanly without needing real ffmpeg / Composio (the Drive client is mocked).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from fly_backend.context import Context
from fly_backend.integrations.composio_calendar import CustomerEvent
from fly_backend.integrations.composio_drive import MockDriveClient
from fly_backend.integrations.ffmpeg import FfmpegClient
from fly_backend.logging import get_logger
from fly_backend.orchestrator import Orchestrator, orchestrator
from fly_backend.persistence.db import Database
from fly_backend.persistence.models import Session, SessionStatus
from fly_backend.settings import Settings


class _StubCalendarClient:
    """Implements the CalendarClient protocol (`list_events`). The orchestrator
    never touches it — only list_today_customers does — so an empty stub is
    fine for these tests."""

    async def list_events(self, on: date) -> list[CustomerEvent]:
        return []


def _build_test_context(tmp_path: Path) -> tuple[Context, Database]:
    """Build a fully-stubbed Context anchored on tmp_path.

    Extraction is disabled so we don't need a real ffmpeg binary. The card
    directory is empty so copy_media + upload_to_drive + verify_upload all
    complete with zero files and the pipeline reaches `done` quickly.
    """
    db = Database.open_in_memory()
    settings = Settings()
    settings.local_root = str(tmp_path / "archive")
    settings.drive_base_folder_id = "folder_root"
    settings.drive_base_folder_url = "https://drive.google.com/drive/folders/folder_root"
    settings.extraction.enabled = False  # skip ffmpeg
    settings.composio.api_key_set = True
    settings.composio.connection_id = "test_conn"
    ctx = Context(
        settings=settings,
        logger=get_logger("test"),
        calendar=_StubCalendarClient(),
        drive=MockDriveClient(),
        ffmpeg=FfmpegClient(),
        db=db,
    )
    return ctx, db


def _make_session(ctx: Context, source: Path, customer: str = "Tester") -> str:
    """Insert a Session row directly so tests don't depend on start_session."""
    sid = uuid.uuid4().hex
    local_folder = Path(ctx.settings.local_root) / f"TD_{customer}"
    (local_folder / "Videos").mkdir(parents=True, exist_ok=True)
    (local_folder / "Fotos").mkdir(parents=True, exist_ok=True)
    with ctx.db.session() as db:
        db.add(
            Session(
                id=sid,
                customer_name=customer,
                customer_phone=None,
                drive_folder_url=ctx.settings.drive_base_folder_url or "",
                drive_folder_id=ctx.settings.drive_base_folder_id,
                source_mount_path=str(source),
                local_folder=str(local_folder),
                status=SessionStatus.queued,
            )
        )
        db.commit()
    return sid


@pytest.fixture
def empty_card(tmp_path: Path) -> Path:
    card = tmp_path / "card"
    card.mkdir()
    return card


@pytest.fixture
def orch(tmp_path: Path, empty_card: Path) -> Iterator[tuple[Orchestrator, Context]]:
    ctx, _db = _build_test_context(tmp_path)
    o = Orchestrator(context_factory=lambda: ctx)
    yield o, ctx


@pytest.mark.asyncio
async def test_spawn_is_idempotent(orch: tuple[Orchestrator, Context], empty_card: Path) -> None:
    o, ctx = orch
    sid = _make_session(ctx, empty_card)
    t1 = await o.spawn(sid)
    t2 = await o.spawn(sid)
    assert t1 is t2
    await o.wait(sid)


@pytest.mark.asyncio
async def test_pipeline_runs_to_completion_without_a_subscriber(
    orch: tuple[Orchestrator, Context], empty_card: Path
) -> None:
    """The work must finish whether or not anyone is listening — that's the
    whole point of detaching from SSE."""
    o, ctx = orch
    sid = _make_session(ctx, empty_card)
    await o.spawn(sid)
    await o.wait(sid)

    with ctx.db.session() as db:
        sess = db.get(Session, sid)
        assert sess is not None
        assert sess.status == SessionStatus.completed


@pytest.mark.asyncio
async def test_subscriber_receives_done(
    orch: tuple[Orchestrator, Context], empty_card: Path
) -> None:
    o, ctx = orch
    sid = _make_session(ctx, empty_card)
    await o.spawn(sid)
    q = o.subscribe(sid)
    assert q is not None

    seen: list[str] = []
    try:
        while True:
            event = await asyncio.wait_for(q.get(), timeout=5.0)
            seen.append(event["event"])
            if event["event"] in {"done", "cancelled", "pipeline_error"}:
                break
    finally:
        o.unsubscribe(sid, q)

    assert "done" in seen
    # verification should arrive before done.
    assert seen.index("verification") < seen.index("done")


@pytest.mark.asyncio
async def test_subscriber_disconnect_does_not_cancel_task(
    orch: tuple[Orchestrator, Context], empty_card: Path
) -> None:
    o, ctx = orch
    sid = _make_session(ctx, empty_card)
    await o.spawn(sid)
    q = o.subscribe(sid)
    assert q is not None
    # Drop the subscriber immediately.
    o.unsubscribe(sid, q)
    # Task continues to completion regardless.
    await o.wait(sid)
    with ctx.db.session() as db:
        sess = db.get(Session, sid)
        assert sess is not None
        assert sess.status == SessionStatus.completed


@pytest.mark.asyncio
async def test_multiple_subscribers_get_identical_streams(
    orch: tuple[Orchestrator, Context], empty_card: Path
) -> None:
    o, ctx = orch
    sid = _make_session(ctx, empty_card)
    await o.spawn(sid)
    a = o.subscribe(sid)
    b = o.subscribe(sid)
    assert a is not None and b is not None

    async def drain(q: asyncio.Queue[dict[str, str]]) -> list[str]:
        out: list[str] = []
        while True:
            ev = await asyncio.wait_for(q.get(), timeout=5.0)
            out.append(ev["event"])
            if ev["event"] in {"done", "cancelled", "pipeline_error"}:
                return out

    seen_a, seen_b = await asyncio.gather(drain(a), drain(b))
    o.unsubscribe(sid, a)
    o.unsubscribe(sid, b)
    assert seen_a == seen_b


@pytest.mark.asyncio
async def test_cancel_marks_session_cancelled(
    orch: tuple[Orchestrator, Context], empty_card: Path
) -> None:
    """A cancel signal must flip the session row to cancelled. We pre-set the
    cancel event between ``spawn`` (sync return) and the next ``await`` so
    cooperative scheduling guarantees ``_run`` sees it from the first iteration —
    avoiding wall-clock races inside the test."""
    o, ctx = orch
    sid = _make_session(ctx, empty_card)
    await o.spawn(sid)
    # No await between spawn return and the next line — _run cannot have started
    # yet under asyncio's cooperative scheduling.
    o._states[sid].cancel_event.set()
    await o.wait(sid)

    with ctx.db.session() as db:
        sess = db.get(Session, sid)
        assert sess is not None
        assert sess.status == SessionStatus.cancelled


@pytest.mark.asyncio
async def test_cancel_publishes_cancelled_to_live_subscriber(
    orch: tuple[Orchestrator, Context], empty_card: Path
) -> None:
    """Subscribers connected at cancel time should receive the ``cancelled``
    event."""
    o, ctx = orch
    sid = _make_session(ctx, empty_card)
    await o.spawn(sid)
    q = o.subscribe(sid)
    assert q is not None
    o._states[sid].cancel_event.set()

    seen: list[str] = []
    try:
        while True:
            event = await asyncio.wait_for(q.get(), timeout=5.0)
            seen.append(event["event"])
            if event["event"] in {"done", "cancelled", "pipeline_error"}:
                break
    finally:
        o.unsubscribe(sid, q)

    assert seen[-1] == "cancelled"


@pytest.mark.asyncio
async def test_module_singleton_is_usable(empty_card: Path, tmp_path: Path) -> None:
    """The shared module-level singleton can be redirected at a test context."""
    ctx, _db = _build_test_context(tmp_path)
    sid = _make_session(ctx, empty_card)

    original = orchestrator._context_factory
    orchestrator.set_context_factory(lambda: ctx)
    try:
        await orchestrator.spawn(sid)
        await orchestrator.wait(sid)
    finally:
        orchestrator.set_context_factory(original)

    with ctx.db.session() as db:
        sess = db.get(Session, sid)
        assert sess is not None
        assert sess.status == SessionStatus.completed


@pytest.mark.asyncio
async def test_resume_pending_relaunches_queued_sessions(
    tmp_path: Path, empty_card: Path
) -> None:
    """Sessions left in queued/running state by a previous process should be
    picked up by ``resume_pending()`` (CLAUDE.md §15)."""
    ctx, _db = _build_test_context(tmp_path)
    queued_sid = _make_session(ctx, empty_card, customer="Queued")
    # Manually flip a second one to "running" to simulate a crash mid-pipeline.
    running_sid = _make_session(ctx, empty_card, customer="Running")
    with ctx.db.session() as db:
        sess = db.get(Session, running_sid)
        assert sess is not None
        sess.status = SessionStatus.running
        db.add(sess)
        db.commit()
    # A completed session must NOT be resumed.
    done_sid = _make_session(ctx, empty_card, customer="Done")
    with ctx.db.session() as db:
        sess = db.get(Session, done_sid)
        assert sess is not None
        sess.status = SessionStatus.completed
        db.add(sess)
        db.commit()

    o = Orchestrator(context_factory=lambda: ctx)
    resumed = await o.resume_pending()
    assert set(resumed) == {queued_sid, running_sid}

    await o.wait(queued_sid)
    await o.wait(running_sid)
    with ctx.db.session() as db:
        for sid in (queued_sid, running_sid):
            sess = db.get(Session, sid)
            assert sess is not None
            assert sess.status == SessionStatus.completed
        # Untouched.
        done = db.get(Session, done_sid)
        assert done is not None
        assert done.status == SessionStatus.completed


@pytest.mark.asyncio
async def test_subscribe_returns_none_when_session_already_done(
    orch: tuple[Orchestrator, Context], empty_card: Path
) -> None:
    """A late subscriber should not block; the route handler reads the DB
    snapshot + terminal status instead. ``subscribe()`` returns None to signal
    that fast-path."""
    o, ctx = orch
    sid = _make_session(ctx, empty_card)
    await o.spawn(sid)
    await o.wait(sid)
    assert o.subscribe(sid) is None
    assert not o.is_running(sid)
