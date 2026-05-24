from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import select

from ...context import Context
from ...errors import BehaviorError
from ...persistence.models import FileRecord, Phase, PhaseName, PhaseStatus, Session
from ...util.hashing import md5_file
from ..progress import ProgressEvent
from .contract import ExtractFramesInput


async def run(payload: ExtractFramesInput, ctx: Context) -> AsyncIterator[ProgressEvent]:
    log = ctx.logger.bind(behavior="extract_frames", session_id=payload.session_id)

    with ctx.db.session() as db:
        session = db.get(Session, payload.session_id)
        if session is None:
            raise BehaviorError(f"unknown_session: {payload.session_id}")
        local = Path(session.local_folder)

    if not ctx.settings.extraction.enabled:
        yield ProgressEvent(
            phase=PhaseName.extract_frames.value, current=0, total=0, message="extraction_disabled"
        )
        _mark_phase(ctx, payload.session_id, PhaseStatus.skipped, 0, 0)
        return

    fps = _clamp_fps(payload.fps or ctx.settings.extraction.fps, ctx)
    videos_dir = local / "Videos"
    fotos_dir = local / "Fotos"
    fotos_dir.mkdir(parents=True, exist_ok=True)

    videos = sorted(videos_dir.glob("*")) if videos_dir.exists() else []
    videos = [v for v in videos if v.is_file()]
    total = len(videos)

    if total == 0:
        yield ProgressEvent(
            phase=PhaseName.extract_frames.value, current=0, total=0, message="no_videos"
        )
        _mark_phase(ctx, payload.session_id, PhaseStatus.completed, 0, 0)
        return

    _mark_phase(ctx, payload.session_id, PhaseStatus.running, 0, total)

    for i, video in enumerate(videos, start=1):
        if ctx.cancel_event and ctx.cancel_event.is_set():
            return
        log.info("extracting", video=video.name, fps=fps)
        async for frame in ctx.ffmpeg.extract_frames(
            video, fotos_dir, fps, ctx.settings.extraction.jpeg_quality
        ):
            rel_str = str(frame.frame_path.relative_to(local))
            with ctx.db.session() as db:
                existing = db.exec(
                    select(FileRecord).where(
                        FileRecord.session_id == payload.session_id,
                        FileRecord.relative_path == rel_str,
                    )
                ).first()
                if existing is None:
                    size = frame.frame_path.stat().st_size
                    db.add(
                        FileRecord(
                            session_id=payload.session_id,
                            relative_path=rel_str,
                            size=size,
                            md5=md5_file(frame.frame_path) if size > 0 else None,
                        )
                    )
                    db.commit()
        yield ProgressEvent(
            phase=PhaseName.extract_frames.value,
            current=i,
            total=total,
            message=video.name,
        )
        _mark_phase(ctx, payload.session_id, PhaseStatus.running, i, total)

    _mark_phase(ctx, payload.session_id, PhaseStatus.completed, total, total)


def _clamp_fps(fps: float, ctx: Context) -> float:
    lo = ctx.settings.extraction.min_interval_seconds
    hi = ctx.settings.extraction.max_interval_seconds
    # min_interval_seconds means the FASTEST we'll sample; convert to fps cap.
    # If fastest=0.25s between frames, that's 4 fps max. If slowest=10s, that's 0.1 fps min.
    max_fps = 1.0 / lo if lo > 0 else fps
    min_fps = 1.0 / hi if hi > 0 else fps
    return max(min_fps, min(max_fps, fps))


def _mark_phase(
    ctx: Context, session_id: str, status: PhaseStatus, current: int, total: int
) -> None:
    with ctx.db.session() as db:
        existing = db.exec(
            select(Phase).where(
                Phase.session_id == session_id, Phase.name == PhaseName.extract_frames
            )
        ).first()
        now = datetime.now(UTC)
        if existing is None:
            existing = Phase(
                session_id=session_id,
                name=PhaseName.extract_frames,
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
            if status in {PhaseStatus.completed, PhaseStatus.failed, PhaseStatus.skipped}:
                existing.finished_at = now
        db.add(existing)
        db.commit()
