"""detect_card handler. See contract.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import select

from ...context import Context
from ...persistence.models import Session, SessionStatus
from .contract import CardDetected, DetectCardInput


async def run(payload: DetectCardInput, ctx: Context) -> CardDetected:
    log = ctx.logger.bind(behavior="detect_card", volume_id=payload.volume_id)
    log.info("card_detected", mount_path=str(payload.mount_path), label=payload.label)

    now = datetime.now(UTC)
    threshold = now - timedelta(hours=1)
    already = False
    with ctx.db.session() as db:
        stmt = select(Session).where(
            Session.source_mount_path == str(payload.mount_path),
            Session.status == SessionStatus.completed,
            Session.updated_at >= threshold,
        )
        already = db.exec(stmt).first() is not None
    return CardDetected(
        mount_path=payload.mount_path,
        volume_id=payload.volume_id,
        label=payload.label,
        detected_at=now,
        already_ingested_within_hour=already,
    )
