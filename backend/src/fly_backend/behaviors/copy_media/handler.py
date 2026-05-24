from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import select

from ...context import Context
from ...errors import BehaviorError
from ...persistence.models import FileRecord, Phase, PhaseName, PhaseStatus, Session
from ...util.hashing import md5_file
from ..progress import ProgressEvent
from .contract import CopyMediaInput


def _classify(file: Path, ctx: Context) -> str | None:
    """Return 'Videos' / 'Fotos' / None per the configured extensions."""
    suf = file.suffix.lower()
    if suf in {e.lower() for e in ctx.settings.ingest.video_extensions}:
        return "Videos"
    if suf in {e.lower() for e in ctx.settings.ingest.photo_extensions}:
        return "Fotos"
    return None


def _unique_target(target: Path) -> Path:
    """Avoid silent overwrites: append _2, _3, ... when a same-named file
    already exists (CLAUDE.md §3 multi-card sessions)."""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    i = 2
    while True:
        candidate = target.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


async def run(payload: CopyMediaInput, ctx: Context) -> AsyncIterator[ProgressEvent]:
    """Copy media from the card into the session's local archive."""
    log = ctx.logger.bind(behavior="copy_media", session_id=payload.session_id)
    with ctx.db.session() as db:
        session = db.get(Session, payload.session_id)
        if session is None:
            raise BehaviorError(f"unknown_session: {payload.session_id}")
        source = Path(session.source_mount_path)
        local_root = Path(session.local_folder)

    if not source.exists():
        raise BehaviorError(f"card_not_mounted: {source}")

    videos_dir = local_root / "Videos"
    fotos_dir = local_root / "Fotos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    fotos_dir.mkdir(parents=True, exist_ok=True)

    candidates: list[tuple[Path, str]] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        if ctx.settings.ingest.ignore_hidden and path.name.startswith("."):
            continue
        bucket = _classify(path, ctx)
        if bucket is None:
            continue
        candidates.append((path, bucket))

    total = len(candidates)
    if total == 0:
        yield ProgressEvent(
            phase=PhaseName.copy_media.value, current=0, total=0, message="no_media_on_card"
        )
        _mark_phase(ctx, payload.session_id, PhaseStatus.completed, current=0, total=0)
        return

    _mark_phase(ctx, payload.session_id, PhaseStatus.running, current=0, total=total)

    for i, (src, bucket) in enumerate(candidates, start=1):
        if ctx.cancel_event and ctx.cancel_event.is_set():
            return
        rel = Path(bucket) / src.name
        dst = _unique_target(local_root / rel)
        rel_str = str(dst.relative_to(local_root))

        with ctx.db.session() as db:
            existing = db.exec(
                select(FileRecord).where(
                    FileRecord.session_id == payload.session_id,
                    FileRecord.relative_path == rel_str,
                )
            ).first()

        if existing is None or not dst.exists():
            shutil.copy2(src, dst)
            md5 = md5_file(dst)
            with ctx.db.session() as db:
                if existing:
                    existing.size = dst.stat().st_size
                    existing.md5 = md5
                    db.add(existing)
                else:
                    db.add(
                        FileRecord(
                            session_id=payload.session_id,
                            relative_path=rel_str,
                            size=dst.stat().st_size,
                            md5=md5,
                        )
                    )
                db.commit()
        else:
            log.debug("copy_skip_existing", path=rel_str)

        yield ProgressEvent(
            phase=PhaseName.copy_media.value, current=i, total=total, message=rel_str
        )
        _mark_phase(ctx, payload.session_id, PhaseStatus.running, current=i, total=total)

    _mark_phase(ctx, payload.session_id, PhaseStatus.completed, current=total, total=total)
    log.info("copy_complete", files=total)


def _mark_phase(
    ctx: Context,
    session_id: str,
    status: PhaseStatus,
    *,
    current: int,
    total: int,
    message: str | None = None,
) -> None:
    with ctx.db.session() as db:
        existing = db.exec(
            select(Phase).where(
                Phase.session_id == session_id, Phase.name == PhaseName.copy_media
            )
        ).first()
        now = datetime.now(UTC)
        if existing is None:
            existing = Phase(
                session_id=session_id,
                name=PhaseName.copy_media,
                status=status,
                current=current,
                total=total,
                message=message,
                started_at=now if status == PhaseStatus.running else None,
            )
        else:
            existing.status = status
            existing.current = current
            existing.total = total
            existing.message = message
            if status == PhaseStatus.running and existing.started_at is None:
                existing.started_at = now
            if status in {PhaseStatus.completed, PhaseStatus.failed}:
                existing.finished_at = now
        db.add(existing)
        db.commit()
