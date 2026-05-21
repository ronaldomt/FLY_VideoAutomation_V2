from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import select

from ...context import Context
from ...errors import BehaviorError
from ...persistence.models import FileRecord, Phase, PhaseName, PhaseStatus, Session
from ..progress import ProgressEvent
from .contract import UploadToDriveInput


async def run(payload: UploadToDriveInput, ctx: Context) -> AsyncIterator[ProgressEvent]:
    log = ctx.logger.bind(behavior="upload_to_drive", session_id=payload.session_id)

    with ctx.db.session() as db:
        session = db.get(Session, payload.session_id)
        if session is None:
            raise BehaviorError(f"unknown_session: {payload.session_id}")
        if session.drive_folder_id is None:
            raise BehaviorError("session_missing_drive_folder_id")
        local_root = Path(session.local_folder)
        parent_id = session.drive_folder_id

    # Ensure Videos/ + Fotos/ subfolders exist on Drive.
    videos_remote = await ctx.drive.ensure_subfolder(parent_id, "Videos")
    fotos_remote = await ctx.drive.ensure_subfolder(parent_id, "Fotos")
    bucket_map = {"Videos": videos_remote, "Fotos": fotos_remote}

    with ctx.db.session() as db:
        records = db.exec(
            select(FileRecord).where(FileRecord.session_id == payload.session_id)
        ).all()

    to_upload = [r for r in records if not r.uploaded]
    total = len(to_upload)
    if total == 0:
        yield ProgressEvent(
            phase=PhaseName.upload.value, current=0, total=0, message="nothing_to_upload"
        )
        _mark_phase(ctx, payload.session_id, PhaseStatus.completed, 0, 0)
        return

    _mark_phase(ctx, payload.session_id, PhaseStatus.running, 0, total)

    cap = max(1, ctx.settings.upload.parallel_uploads)
    semaphore = asyncio.Semaphore(cap)
    completed = 0
    queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()

    async def _upload_one(record: FileRecord) -> None:
        nonlocal completed
        bucket = record.relative_path.split("/", 1)[0]
        remote_parent = bucket_map.get(bucket)
        if remote_parent is None:
            raise BehaviorError(f"unknown_bucket_in_record: {record.relative_path}")
        local_path = local_root / record.relative_path
        if not local_path.exists():
            raise BehaviorError(f"missing_local_file: {record.relative_path}")
        async with semaphore:
            result = await ctx.drive.upload_file(remote_parent, local_path)
        with ctx.db.session() as db:
            row = db.get(FileRecord, record.id)
            if row is not None:
                row.drive_file_id = result.file_id
                row.uploaded = True
                if row.md5 is None:
                    row.md5 = result.md5
                row.size = result.size or row.size
                db.add(row)
                db.commit()
        completed += 1
        await queue.put(
            ProgressEvent(
                phase=PhaseName.upload.value,
                current=completed,
                total=total,
                message=record.relative_path,
            )
        )

    tasks = [asyncio.create_task(_upload_one(r)) for r in to_upload]

    async def _drain() -> None:
        await asyncio.gather(*tasks)
        await queue.put(_SENTINEL)

    drainer = asyncio.create_task(_drain())

    try:
        while True:
            event = await queue.get()
            if event is _SENTINEL:
                break
            yield event
            _mark_phase(
                ctx, payload.session_id, PhaseStatus.running, event.current, event.total
            )
    finally:
        await drainer

    _mark_phase(ctx, payload.session_id, PhaseStatus.completed, total, total)
    log.info("upload_complete", files=total)


class _Sentinel:
    pass


_SENTINEL = _Sentinel()  # type: ignore[assignment]


def _mark_phase(
    ctx: Context, session_id: str, status: PhaseStatus, current: int, total: int
) -> None:
    with ctx.db.session() as db:
        existing = db.exec(
            select(Phase).where(
                Phase.session_id == session_id, Phase.name == PhaseName.upload
            )
        ).first()
        now = datetime.now(UTC)
        if existing is None:
            existing = Phase(
                session_id=session_id,
                name=PhaseName.upload,
                status=status,
                current=current,
                total=total,
                started_at=now if status == PhaseStatus.running else None,
            )
        else:
            existing.status = status
            existing.current = current
            existing.total = total
            if status == PhaseStatus.running and existing.started_at is None:
                existing.started_at = now
            if status in {PhaseStatus.completed, PhaseStatus.failed}:
                existing.finished_at = now
        db.add(existing)
        db.commit()
