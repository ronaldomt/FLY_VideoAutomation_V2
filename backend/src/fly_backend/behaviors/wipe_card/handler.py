from __future__ import annotations

import contextlib
from pathlib import Path

from sqlmodel import select

from ...context import Context
from ...errors import BehaviorError, VerificationError
from ...persistence.models import FileRecord, Session
from .contract import WipeCardInput, WipeResult


async def run(payload: WipeCardInput, ctx: Context) -> WipeResult:
    log = ctx.logger.bind(behavior="wipe_card", session_id=payload.session_id)
    if not payload.confirm:
        return WipeResult(ok=False, deleted=0, skipped_reason="not_confirmed")
    if not ctx.settings.card_wipe.enabled:
        return WipeResult(ok=False, deleted=0, skipped_reason="card_wipe_disabled_in_settings")

    with ctx.db.session() as db:
        session = db.get(Session, payload.session_id)
        if session is None:
            raise BehaviorError(f"unknown_session: {payload.session_id}")
        records = db.exec(
            select(FileRecord).where(FileRecord.session_id == payload.session_id)
        ).all()

    if ctx.settings.card_wipe.require_verification:
        unverified = [r for r in records if not r.verified]
        if unverified:
            raise VerificationError(
                f"refusing_wipe_unverified_files: {len(unverified)} of {len(records)}"
            )

    source = Path(session.source_mount_path)
    if not source.exists():
        raise BehaviorError(f"card_not_mounted: {source}")

    # Only delete what the OS sees as files; never touch directories at the root.
    deleted = 0
    for p in sorted(source.rglob("*"), key=lambda x: -len(str(x))):
        if p.is_file():
            try:
                p.unlink()
                deleted += 1
            except OSError as exc:
                log.warning("wipe_unlink_failed", path=str(p), error=str(exc))
        elif p.is_dir():
            # Best-effort — only rmdir if empty.
            with contextlib.suppress(OSError):
                p.rmdir()
    log.info("wipe_complete", deleted=deleted)
    return WipeResult(ok=True, deleted=deleted)
