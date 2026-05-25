"""HTTP endpoints. Thin layer over behaviors.

See CLAUDE.md §10 for the canonical endpoint catalog. The orchestration of
phases (copy → extract → upload → verify → share) is exposed as Server-Sent
Events on `GET /sessions/:id/events`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .. import __version__
from ..behaviors.detect_card.contract import DetectCardInput
from ..behaviors.detect_card.handler import run as detect_card
from ..behaviors.list_today_customers.contract import (
    ListTodayCustomersInput,
    ListTodayCustomersOutput,
)
from ..behaviors.list_today_customers.handler import run as list_today_customers
from ..behaviors.make_share_link.contract import MakeShareLinkInput, ShareLink
from ..behaviors.make_share_link.handler import run as make_share_link
from ..behaviors.progress import ProgressEvent
from ..behaviors.resolve_drive_folder.contract import ResolveDriveFolderInput
from ..behaviors.resolve_drive_folder.handler import run as resolve_drive_folder
from ..behaviors.start_session.contract import SessionOut, StartSessionInput
from ..behaviors.start_session.handler import run as start_session
from ..behaviors.verify_upload.contract import VerificationReport, VerifyUploadInput
from ..behaviors.verify_upload.handler import run as verify_upload
from ..behaviors.wipe_card.contract import WipeCardInput, WipeResult
from ..behaviors.wipe_card.handler import run as wipe_card
from ..context import build_default_context
from ..integrations.composio_client import ensure_user_id
from ..logging import get_logger
from ..orchestrator import orchestrator
from ..persistence.models import Phase, Session, SessionStatus
from ..secrets import get_composio_key
from ..settings import Settings, load_settings, save_settings
from . import integrations_routes

router = APIRouter()
router.include_router(integrations_routes.router)


def _ctx():  # type: ignore[no-untyped-def]
    # Built per-request so settings changes are visible without restart.
    return build_default_context()


# ── health & settings ────────────────────────────────────────────────────────

@router.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "version": __version__}


@router.get("/settings", response_model=Settings)
async def get_settings() -> Settings:
    return load_settings()


@router.put("/settings", response_model=Settings)
async def put_settings(incoming: Settings) -> Settings:
    save_settings(incoming)
    return incoming


@router.get("/setup/status")
async def setup_status() -> dict[str, bool]:
    s = load_settings()
    return {
        "composio_connected": s.composio.api_key_set and s.composio.google_connected,
        "calendar_id_set": bool(s.calendar_id),
        "local_root_set": bool(s.local_root),
        "drive_base_folder_set": bool(s.drive_base_folder_id),
    }


class _DriveBaseInput(BaseModel):
    drive_folder_url: str


@router.get("/setup/drive-base")
async def setup_drive_base_get() -> dict[str, object]:
    s = load_settings()
    return {
        "configured": bool(s.drive_base_folder_id),
        "folder_id": s.drive_base_folder_id,
        "folder_url": s.drive_base_folder_url,
        "folder_name": None,
    }


@router.post("/setup/drive-base")
async def setup_drive_base_post(body: _DriveBaseInput) -> dict[str, object]:
    ctx = _ctx()
    folder = await resolve_drive_folder(
        ResolveDriveFolderInput(drive_folder_url=body.drive_folder_url), ctx
    )
    s = load_settings()
    s.drive_base_folder_url = body.drive_folder_url.strip()
    s.drive_base_folder_id = folder.id
    save_settings(s)
    return {"ok": True, "folder_id": folder.id, "folder_name": folder.name}


class _CompleteOAuthBody(BaseModel):
    connection_request_id: str


_COMPOSIO_V3 = "https://backend.composio.dev/api/v3"


@router.post("/setup/composio/start")
async def setup_composio_start() -> dict[str, str]:
    """Initiate the Composio Google OAuth flow via the v3 API.

    The Composio SDK's initiate_connection() uses the deprecated v1 endpoint;
    POST /api/v3/connected_accounts/link accepts the ac_* auth_config_id
    that users copy from the Composio dashboard.

    Returns {auth_url, connection_request_id} — the frontend opens auth_url
    in a browser tab and passes connection_request_id back to /complete.
    """
    import httpx

    log = get_logger("setup.composio")
    settings = load_settings()
    api_key = get_composio_key()
    if not api_key:
        raise HTTPException(412, detail="composio_api_key_missing")
    if not settings.composio.auth_config_id:
        raise HTTPException(412, detail="composio_auth_config_id_missing")
    user_id = ensure_user_id(settings)
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.post(
                f"{_COMPOSIO_V3}/connected_accounts/link",
                headers={"x-api-key": api_key},
                json={"auth_config_id": settings.composio.auth_config_id, "user_id": user_id},
            )
            resp.raise_for_status()
            data: dict = resp.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        log.error("composio_oauth_initiate_failed", error=body)
        raise HTTPException(502, detail=f"composio_oauth_initiate_failed: {body}") from exc
    except Exception as exc:
        log.error("composio_oauth_initiate_failed", error=str(exc))
        raise HTTPException(502, detail=f"composio_oauth_initiate_failed: {exc}") from exc
    redirect_url = data.get("redirect_url")
    if not redirect_url:
        raise HTTPException(502, detail="composio_no_redirect_url")
    conn_id = data.get("connected_account_id", "")
    log.info("composio_oauth_initiated", connection_id=conn_id)
    return {"auth_url": redirect_url, "connection_request_id": conn_id}


@router.post("/setup/composio/complete")
async def setup_composio_complete(body: _CompleteOAuthBody) -> dict[str, bool]:
    """Verify the Composio connection is ACTIVE and persist the connection_id.

    The frontend calls this after the user completes OAuth in the browser.
    Returns {ok: true} on success; 409 if the connection is not yet active.
    """
    import httpx

    log = get_logger("setup.composio")
    settings = load_settings()
    api_key = get_composio_key()
    if not api_key:
        raise HTTPException(412, detail="composio_api_key_missing")
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(
                f"{_COMPOSIO_V3}/connected_accounts/{body.connection_request_id}",
                headers={"x-api-key": api_key},
            )
            resp.raise_for_status()
            data: dict = resp.json()
    except httpx.HTTPStatusError as exc:
        body_text = exc.response.text
        log.error("composio_connection_check_failed", error=body_text)
        raise HTTPException(502, detail=f"composio_connection_check_failed: {body_text}") from exc
    except Exception as exc:
        log.error("composio_connection_check_failed", error=str(exc))
        raise HTTPException(502, detail=f"composio_connection_check_failed: {exc}") from exc
    status = data.get("status", "")
    connection_id = body.connection_request_id

    if status != "ACTIVE":
        # The given connection may still be initializing; look for the most
        # recent ACTIVE connection for this user as a fallback (e.g. when the
        # browser completes OAuth but the returned ID had a race condition).
        try:
            user_id = ensure_user_id(settings)
            async with httpx.AsyncClient(timeout=15) as http2:
                list_resp = await http2.get(
                    f"{_COMPOSIO_V3}/connected_accounts",
                    headers={"x-api-key": api_key},
                    params={"user_id": user_id, "toolkit_slug": "googlesuper"},
                )
                list_resp.raise_for_status()
                items = list_resp.json().get("items", [])
            active = [i for i in items if i.get("status") == "ACTIVE"]
            if active:
                # Most recently updated active connection wins.
                active.sort(key=lambda i: i.get("updated_at", ""), reverse=True)
                connection_id = active[0]["id"]
                status = "ACTIVE"
        except Exception:
            pass  # Keep original status; will 409 below.

    if status != "ACTIVE":
        raise HTTPException(409, detail=f"connection_not_yet_active: {status}")

    # Resolve the v1 UUID — action execution (execute_action) uses the v1/v2
    # API which requires a UUID, not the ca_* id returned by v3.
    uuid = await _resolve_v1_uuid(api_key, settings.composio.user_id or "", connection_id)
    settings.composio.connection_id = uuid or connection_id
    save_settings(settings)
    log.info("composio_oauth_complete", connection_id=settings.composio.connection_id)
    return {"ok": True}


async def _resolve_v1_uuid(api_key: str, user_id: str, ca_id: str) -> str | None:
    """Map a v3 ca_* connected account ID to the v1 UUID needed for execute_action.

    The Composio SDK's action execution endpoints (v1/v2) require UUID-format
    connection IDs; the v3 OAuth flow returns ca_* IDs. This function fetches
    the v1 connected accounts list and returns the most recent ACTIVE UUID.
    Returns None if the lookup fails (caller falls back to the ca_* id).
    """
    import httpx

    _COMPOSIO_V1 = "https://backend.composio.dev/api/v1"
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(
                f"{_COMPOSIO_V1}/connectedAccounts",
                headers={"x-api-key": api_key},
                params={"user_uuid": user_id, "pageSize": 50},
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
        active = [i for i in items if i.get("status") == "ACTIVE"]
        if not active:
            return None
        active.sort(key=lambda i: i.get("updatedAt", ""), reverse=True)
        return str(active[0]["id"])
    except Exception:
        return None


# ── customers ────────────────────────────────────────────────────────────────

@router.get("/customers/today", response_model=ListTodayCustomersOutput)
async def customers_today(on: date | None = None) -> ListTodayCustomersOutput:
    return await list_today_customers(ListTodayCustomersInput(on=on), _ctx())


# ── cards ────────────────────────────────────────────────────────────────────

_LAST_CARD: dict[str, object] | None = None
_ALL_CARDS: dict[str, dict[str, object]] = {}  # keyed by volume_id


def _record_card(card_dict: dict[str, object], volume_id: str) -> None:
    """Update both the last-detected card and the all-cards map.

    Called from the HTTP POST /cards/detected handler AND from the in-process
    Python disk poller (main.py lifespan). Both must stay in sync so
    /cards/list returns every currently-mounted card.
    """
    global _LAST_CARD
    _LAST_CARD = card_dict
    _ALL_CARDS[volume_id] = card_dict


@router.post("/cards/detected")
async def cards_detected(payload: DetectCardInput) -> dict[str, object]:
    detected = await detect_card(payload, _ctx())
    card_dict = detected.model_dump(mode="json")
    _record_card(card_dict, str(payload.volume_id))
    return card_dict


@router.get("/cards/current")
async def cards_current() -> dict[str, object] | None:
    return _LAST_CARD


@router.get("/cards/list")
async def cards_list() -> list[dict[str, object]]:
    """Return all known cards whose mount_path still exists on disk."""
    from pathlib import Path as _Path

    return [c for c in _ALL_CARDS.values() if _Path(str(c["mount_path"])).exists()]


# ── sessions ─────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=SessionOut)
async def sessions_create(payload: StartSessionInput) -> SessionOut:
    from ..errors import ConcurrencyLimitError

    out = await start_session(payload, _ctx())
    # Spawn the detached orchestrator task. The SSE endpoint is a pure
    # observer; the work runs whether or not anyone is listening.
    # Skip when start_session failed the pre-flight check (e.g. disk_full).
    if out.status == "queued":
        try:
            await orchestrator.spawn(out.id)
        except ConcurrencyLimitError as exc:
            # Roll the new session back to failed so the DB doesn't keep an
            # orphan queued row the operator can't see. The frontend's 409
            # handler surfaces "Another session is already running."
            ctx = _ctx()
            with ctx.db.session() as db:
                sess = db.get(Session, out.id)
                if sess is not None:
                    sess.status = SessionStatus.failed
                    sess.error = "session_concurrency_limit"
                    db.add(sess)
                    db.commit()
            raise HTTPException(
                status_code=409, detail="session_concurrency_limit"
            ) from exc
    return out


@router.get("/sessions/recent")
async def sessions_recent(
    status: str | None = None, limit: int = 20
) -> list[dict[str, object]]:
    """List recent sessions, newest first. Powers the Idle page's failed
    sessions surface. ``status`` filters by SessionStatus value; ``limit`` is
    capped at 100 to keep the response cheap.
    """
    from sqlmodel import select

    cap = max(1, min(limit, 100))
    ctx = _ctx()
    with ctx.db.session() as db:
        stmt = select(Session)
        if status is not None:
            try:
                wanted = SessionStatus(status)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail=f"invalid_status: {status}"
                ) from exc
            stmt = stmt.where(Session.status == wanted)
        stmt = stmt.order_by(Session.created_at.desc()).limit(cap)  # type: ignore[attr-defined]
        rows = db.exec(stmt).all()
        return [
            {
                "id": s.id,
                "customer_name": s.customer_name,
                "status": s.status.value,
                "error": s.error,
                "created_at": s.created_at.isoformat(),
                "local_folder": s.local_folder,
            }
            for s in rows
        ]


@router.delete("/sessions/failed")
async def sessions_clear_failed(older_than_hours: int = 0) -> dict[str, int]:
    """Delete failed + cancelled sessions older than ``older_than_hours`` hours.

    Default 0 = delete all failed/cancelled regardless of age. Cascades to
    Phase and FileRecord rows for those sessions. Does NOT delete the
    associated local folders — that's a deliberately separate, scarier
    action the operator triggers from Finder.
    """
    from datetime import UTC, datetime, timedelta

    from sqlmodel import select

    from ..persistence.models import FileRecord

    ctx = _ctx()
    cutoff = datetime.now(UTC) - timedelta(hours=max(0, older_than_hours))
    terminal = (SessionStatus.failed, SessionStatus.cancelled)
    with ctx.db.session() as db:
        stmt = select(Session).where(
            Session.status.in_(terminal),  # type: ignore[attr-defined]
            Session.created_at <= cutoff,
        )
        rows = db.exec(stmt).all()
        ids = [s.id for s in rows]
        if not ids:
            return {"deleted": 0}
        # Manual cascade — SQLModel doesn't auto-cascade by default.
        for phase in db.exec(
            select(Phase).where(Phase.session_id.in_(ids))  # type: ignore[attr-defined]
        ).all():
            db.delete(phase)
        for fr in db.exec(
            select(FileRecord).where(FileRecord.session_id.in_(ids))  # type: ignore[attr-defined]
        ).all():
            db.delete(fr)
        for sess in rows:
            db.delete(sess)
        db.commit()
    return {"deleted": len(ids)}


@router.get("/sessions/{session_id}")
async def sessions_get(session_id: str) -> dict[str, object]:
    from sqlmodel import select

    ctx = _ctx()
    with ctx.db.session() as db:
        s = db.get(Session, session_id)
        if s is None:
            raise HTTPException(status_code=404, detail="unknown_session")
        phase_rows = db.exec(select(Phase).where(Phase.session_id == session_id)).all()
        return {
            "id": s.id,
            "customer_name": s.customer_name,
            "customer_phone": s.customer_phone,
            "drive_folder_url": s.drive_folder_url,
            "drive_folder_id": s.drive_folder_id,
            "source_mount_path": s.source_mount_path,
            "local_folder": s.local_folder,
            "status": s.status.value,
            "error": s.error,
            "phases": [
                {
                    "name": p.name.value,
                    "status": p.status.value,
                    "current": p.current,
                    "total": p.total,
                    "message": p.message,
                }
                for p in phase_rows
            ],
        }


@router.get("/sessions/{session_id}/events")
async def sessions_events(session_id: str, request: Request) -> EventSourceResponse:
    """Observe the ingest pipeline as a Server-Sent Events stream.

    The work itself runs in a detached orchestrator task (see
    ``fly_backend.orchestrator``). This endpoint is a **pure observer**:
    it emits a snapshot of current phase state from the DB so a reconnecting
    UI doesn't appear to rewind, then forwards live events from a per-session
    fanout queue. Disconnecting from this stream has zero effect on the
    pipeline; reconnecting does not restart it.

    Event types: ``progress`` (per phase tick), ``verification``, ``done``,
    ``cancelled``, ``pipeline_error``. See ``app/ui/src/api/client.ts``.
    """
    from sqlmodel import select

    ctx = _ctx()
    with ctx.db.session() as db:
        sess = db.get(Session, session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail="unknown_session")
        snapshot_status = sess.status
        phase_rows = db.exec(select(Phase).where(Phase.session_id == session_id)).all()
        snapshot_events = [
            ProgressEvent(
                phase=p.name.value,
                current=p.current,
                total=p.total,
                message=p.message,
            )
            for p in phase_rows
        ]

    queue = orchestrator.subscribe(session_id)

    async def _stream() -> AsyncIterator[dict[str, str]]:
        try:
            for snap in snapshot_events:
                yield {"event": "progress", "data": snap.model_dump_json()}

            # Terminal-state short-circuits: tell the UI to stop subscribing.
            if snapshot_status in {SessionStatus.completed, SessionStatus.failed}:
                yield {
                    "event": "done",
                    "data": json.dumps(
                        {
                            "ok": snapshot_status == SessionStatus.completed,
                            "session_id": session_id,
                        }
                    ),
                }
                return
            if snapshot_status == SessionStatus.cancelled:
                yield {
                    "event": "cancelled",
                    "data": json.dumps({"session_id": session_id}),
                }
                return

            if queue is None:
                # Race: orchestrator finished between the snapshot read and
                # subscribe. Re-read terminal status and emit accordingly.
                with ctx.db.session() as db:
                    sess2 = db.get(Session, session_id)
                    final_status = sess2.status if sess2 else None
                if final_status == SessionStatus.cancelled:
                    yield {
                        "event": "cancelled",
                        "data": json.dumps({"session_id": session_id}),
                    }
                elif final_status in {
                    SessionStatus.completed,
                    SessionStatus.failed,
                }:
                    yield {
                        "event": "done",
                        "data": json.dumps(
                            {
                                "ok": final_status == SessionStatus.completed,
                                "session_id": session_id,
                            }
                        ),
                    }
                return

            terminal_events = {"done", "cancelled", "pipeline_error"}
            while True:
                event = await queue.get()
                yield event
                if event["event"] in terminal_events:
                    return
        finally:
            if queue is not None:
                orchestrator.unsubscribe(session_id, queue)

    return EventSourceResponse(_stream())


@router.post("/sessions/{session_id}/cancel")
async def sessions_cancel(session_id: str) -> dict[str, bool]:
    """Signal cancellation of a running or queued session.

    Sets the orchestrator's per-session cancel event and marks the session
    cancelled in the DB. Idempotent — calling on an already-cancelled session
    returns ok=true. Returns 409 if the session is already completed/failed.
    """
    ctx = _ctx()
    with ctx.db.session() as db:
        sess = db.get(Session, session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail="unknown_session")
        if sess.status in {SessionStatus.completed, SessionStatus.failed}:
            raise HTTPException(status_code=409, detail="session_already_terminal")
        if sess.status != SessionStatus.cancelled:
            sess.status = SessionStatus.cancelled
            db.add(sess)
            db.commit()

    await orchestrator.cancel(session_id)
    return {"ok": True}


@router.post("/sessions/{session_id}/verify", response_model=VerificationReport)
async def sessions_verify(session_id: str) -> VerificationReport:
    return await verify_upload(VerifyUploadInput(session_id=session_id), _ctx())


@router.get("/sessions/{session_id}/share-link", response_model=ShareLink)
async def sessions_share_link(session_id: str) -> ShareLink:
    return await make_share_link(MakeShareLinkInput(session_id=session_id), _ctx())


@router.post("/sessions/{session_id}/wipe-card", response_model=WipeResult)
async def sessions_wipe_card(session_id: str, body: dict[str, bool]) -> WipeResult:
    confirm = bool(body.get("confirm", False))
    return await wipe_card(
        WipeCardInput(session_id=session_id, confirm=confirm), _ctx()
    )


# ── logs ─────────────────────────────────────────────────────────────────────

@router.get("/logs")
async def logs(session_id: str | None = None, level: str | None = None) -> list[dict[str, object]]:
    """Tail today's log file. Filters are applied after parse for v1."""
    from datetime import date as _date

    from ..logging import LOG_DIR

    log_path = LOG_DIR / f"{_date.today().isoformat()}.log"
    if not log_path.exists():
        return []
    out: list[dict[str, object]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if session_id and entry.get("session_id") != session_id:
            continue
        if level and entry.get("level") != level:
            continue
        out.append(entry)
    return out[-500:]  # tail
