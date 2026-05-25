from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import select

from ...context import Context
from ...errors import BehaviorError
from ...persistence.models import FileRecord, Phase, PhaseName, PhaseStatus, Session
from ...util.disk import check_free_space
from ...util.hashing import md5_file
from ..progress import ProgressEvent
from .contract import ExtractFramesInput

# If free space drops below this between videos, abort the phase rather than
# let ffmpeg crash mid-write. 500 MB is a heuristic: a single 4K MP4 minute
# can emit ~50 MB of JPGs at 1 fps; 500 MB gives headroom for one more video
# of typical length while still failing fast.
_LOW_WATER_BYTES = 500_000_000


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

    # Preflight: estimate that frame output peaks at ~2x total video bytes.
    # Caller-provided estimate, so we skip the built-in 10% safety margin and
    # provide our own headroom in the multiplier.
    total_video_bytes = sum(v.stat().st_size for v in videos)
    preflight = check_free_space(local, total_video_bytes * 2, safety_pct=0.0)
    if not preflight.ok:
        _mark_phase(ctx, payload.session_id, PhaseStatus.failed, 0, total)
        raise BehaviorError(
            f"disk_full_at_extract_start: {preflight.free_bytes:,} bytes free, "
            f"need ~{preflight.required_bytes:,}"
        )

    _mark_phase(ctx, payload.session_id, PhaseStatus.running, 0, total)

    for i, video in enumerate(videos, start=1):
        if ctx.cancel_event and ctx.cancel_event.is_set():
            return
        # Re-check free space between videos: ffmpeg's per-video output is
        # hard to predict, so a low-water trip is the only safe stop.
        free_now = shutil.disk_usage(local).free
        if free_now < _LOW_WATER_BYTES:
            _mark_phase(ctx, payload.session_id, PhaseStatus.failed, i - 1, total)
            raise BehaviorError(
                f"disk_full_during_extraction: {free_now:,} bytes free, "
                f"below low-water threshold {_LOW_WATER_BYTES:,}"
            )

        log.info("extracting", video=video.name, fps=fps)
        # Write to a per-video temp dir so a partial / failed ffmpeg run
        # never leaves orphan JPGs in Fotos/. We drain ALL frames into the
        # temp dir first, then bulk-move into Fotos/ as a single atomic step
        # — partial yields followed by a crash never expose half-written
        # files alongside verified ones.
        temp_dir = fotos_dir / f".in-progress-{video.stem}"
        if temp_dir.exists():
            # Stale temp from a previous crash. Remove before reusing.
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        produced_frames: list[Path] = []
        try:
            async for frame in ctx.ffmpeg.extract_frames(
                video, temp_dir, fps, ctx.settings.extraction.jpeg_quality
            ):
                produced_frames.append(frame.frame_path)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        # Success: move every frame into Fotos/ and record it.
        try:
            for temp_path in produced_frames:
                final_path = fotos_dir / temp_path.name
                shutil.move(str(temp_path), str(final_path))
                rel_str = str(final_path.relative_to(local))
                with ctx.db.session() as db:
                    existing = db.exec(
                        select(FileRecord).where(
                            FileRecord.session_id == payload.session_id,
                            FileRecord.relative_path == rel_str,
                        )
                    ).first()
                    if existing is None:
                        size = final_path.stat().st_size
                        db.add(
                            FileRecord(
                                session_id=payload.session_id,
                                relative_path=rel_str,
                                size=size,
                                md5=md5_file(final_path) if size > 0 else None,
                            )
                        )
                        db.commit()
        finally:
            # Empty after success (all files moved). rmtree is a no-op then.
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

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
