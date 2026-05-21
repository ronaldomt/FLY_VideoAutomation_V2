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
from ..behaviors.copy_media.contract import CopyMediaInput
from ..behaviors.copy_media.handler import run as copy_media
from ..behaviors.detect_card.contract import DetectCardInput
from ..behaviors.detect_card.handler import run as detect_card
from ..behaviors.extract_frames.contract import ExtractFramesInput
from ..behaviors.extract_frames.handler import run as extract_frames
from ..behaviors.list_today_customers.contract import (
    ListTodayCustomersInput,
    ListTodayCustomersOutput,
)
from ..behaviors.list_today_customers.handler import run as list_today_customers
from ..behaviors.make_share_link.contract import MakeShareLinkInput, ShareLink
from ..behaviors.make_share_link.handler import run as make_share_link
from ..behaviors.start_session.contract import SessionOut, StartSessionInput
from ..behaviors.start_session.handler import run as start_session
from ..behaviors.upload_to_drive.contract import UploadToDriveInput
from ..behaviors.upload_to_drive.handler import run as upload_to_drive
from ..behaviors.verify_upload.contract import VerificationReport, VerifyUploadInput
from ..behaviors.verify_upload.handler import run as verify_upload
from ..behaviors.wipe_card.contract import WipeCardInput, WipeResult
from ..behaviors.wipe_card.handler import run as wipe_card
from ..context import build_default_context
from ..integrations.composio_client import ensure_user_id
from ..logging import get_logger
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
    }


class _CompleteOAuthBody(BaseModel):
    connection_request_id: str


@router.post("/setup/composio/start")
async def setup_composio_start() -> dict[str, str]:
    """Initiate the Composio Google OAuth flow.

    Requires api_key (keychain) + auth_config_id (settings) to already be set.
    Returns {auth_url, connection_request_id} — the frontend opens auth_url in a
    browser tab and passes connection_request_id back to /complete.
    """
    import asyncio

    log = get_logger("setup.composio")
    settings = load_settings()
    api_key = get_composio_key()
    if not api_key:
        raise HTTPException(412, detail="composio_api_key_missing")
    if not settings.composio.auth_config_id:
        raise HTTPException(412, detail="composio_auth_config_id_missing")
    user_id = ensure_user_id(settings)
    try:
        from composio import ComposioToolSet

        toolset = ComposioToolSet(api_key=api_key, entity_id=user_id)
        conn_req = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: toolset.initiate_connection(
                integration_id=settings.composio.auth_config_id,
                entity_id=user_id,
            ),
        )
    except Exception as exc:
        log.error("composio_oauth_initiate_failed", error=str(exc))
        raise HTTPException(502, detail=f"composio_oauth_initiate_failed: {exc}") from exc
    if not conn_req.redirectUrl:
        raise HTTPException(502, detail="composio_no_redirect_url")
    log.info("composio_oauth_initiated", connection_id=conn_req.connectedAccountId)
    return {
        "auth_url": conn_req.redirectUrl,
        "connection_request_id": conn_req.connectedAccountId,
    }


@router.post("/setup/composio/complete")
async def setup_composio_complete(body: _CompleteOAuthBody) -> dict[str, bool]:
    """Verify the Composio connection is ACTIVE and persist the connection_id.

    The frontend calls this after the user completes OAuth in the browser.
    Returns {ok: true} on success; 409 if the connection is not yet active.
    """
    import asyncio

    log = get_logger("setup.composio")
    settings = load_settings()
    api_key = get_composio_key()
    if not api_key:
        raise HTTPException(412, detail="composio_api_key_missing")
    user_id = ensure_user_id(settings)
    try:
        from composio import ComposioToolSet

        toolset = ComposioToolSet(api_key=api_key, entity_id=user_id)
        account = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: toolset.get_connected_account(id=body.connection_request_id),
        )
    except Exception as exc:
        log.error("composio_connection_check_failed", error=str(exc))
        raise HTTPException(502, detail=f"composio_connection_check_failed: {exc}") from exc
    if account.status != "ACTIVE":
        raise HTTPException(409, detail=f"connection_not_yet_active: {account.status}")
    settings.composio.connection_id = body.connection_request_id
    save_settings(settings)
    log.info("composio_oauth_complete", connection_id=body.connection_request_id)
    return {"ok": True}


# ── customers ────────────────────────────────────────────────────────────────

@router.get("/customers/today", response_model=ListTodayCustomersOutput)
async def customers_today(on: date | None = None) -> ListTodayCustomersOutput:
    return await list_today_customers(ListTodayCustomersInput(on=on), _ctx())


# ── cards ────────────────────────────────────────────────────────────────────

_LAST_CARD: dict[str, object] | None = None


@router.post("/cards/detected")
async def cards_detected(payload: DetectCardInput) -> dict[str, object]:
    global _LAST_CARD
    detected = await detect_card(payload, _ctx())
    _LAST_CARD = detected.model_dump(mode="json")
    return _LAST_CARD


@router.get("/cards/current")
async def cards_current() -> dict[str, object] | None:
    return _LAST_CARD


# ── sessions ─────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=SessionOut)
async def sessions_create(payload: StartSessionInput) -> SessionOut:
    return await start_session(payload, _ctx())


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
    """Drives the full ingest pipeline as a Server-Sent Events stream.

    Phase order: copy_media → extract_frames → upload_to_drive → verify_upload.
    Each ProgressEvent is encoded as JSON in the SSE `data:` field. The stream
    closes once verification completes. If the client disconnects, in-flight
    phases continue running (DB-backed; resumable from `/sessions/:id`).
    """
    ctx = _ctx()
    with ctx.db.session() as db:
        if db.get(Session, session_id) is None:
            raise HTTPException(status_code=404, detail="unknown_session")

    async def _stream() -> AsyncIterator[dict[str, str]]:
        for behavior, inp in (
            (copy_media, CopyMediaInput(session_id=session_id)),
            (extract_frames, ExtractFramesInput(session_id=session_id)),
            (upload_to_drive, UploadToDriveInput(session_id=session_id)),
        ):
            async for event in behavior(inp, ctx):  # type: ignore[arg-type]
                if await request.is_disconnected():
                    return
                yield {"event": "progress", "data": event.model_dump_json()}
        # Verification is one-shot, not a stream.
        report = await verify_upload(VerifyUploadInput(session_id=session_id), ctx)
        yield {"event": "verification", "data": report.model_dump_json()}

        # Mark the session completed/failed.
        with ctx.db.session() as db:
            sess = db.get(Session, session_id)
            if sess is not None:
                sess.status = SessionStatus.completed if report.ok else SessionStatus.failed
                if not report.ok:
                    sess.error = f"verification_failed: {len(report.mismatches)} mismatches"
                db.add(sess)
                db.commit()
        yield {
            "event": "done",
            "data": json.dumps({"ok": report.ok, "session_id": session_id}),
        }

    return EventSourceResponse(_stream())


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
