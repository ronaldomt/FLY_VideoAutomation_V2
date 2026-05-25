"""Hardening tests for extract_frames: disk preflight + atomic temp dir.

These run against the in-memory DB + a fake ffmpeg, so they don't need
ffmpeg installed.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from fly_backend.behaviors.extract_frames.contract import ExtractFramesInput
from fly_backend.behaviors.extract_frames.handler import run as extract_frames
from fly_backend.context import Context
from fly_backend.errors import BehaviorError
from fly_backend.integrations.composio_drive import MockDriveClient
from fly_backend.logging import get_logger
from fly_backend.persistence.db import Database
from fly_backend.persistence.models import Session, SessionStatus
from fly_backend.settings import Settings


@dataclass(slots=True)
class _FakeFrame:
    frame_path: Path
    index: int


class _SuccessfulFfmpeg:
    """Writes 3 placeholder JPGs per video into the out_dir."""

    async def extract_frames(
        self, video: Path, out_dir: Path, fps: float, jpeg_quality: int = 90
    ) -> AsyncIterator[_FakeFrame]:
        out_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            p = out_dir / f"{video.stem}_{i:06d}.jpg"
            p.write_bytes(b"jpgdata")
            yield _FakeFrame(frame_path=p, index=i)


class _CrashingFfmpeg:
    """Writes one frame then raises — simulates ffmpeg crashing mid-video."""

    def __init__(self) -> None:
        self.calls = 0

    async def extract_frames(
        self, video: Path, out_dir: Path, fps: float, jpeg_quality: int = 90
    ) -> AsyncIterator[_FakeFrame]:
        self.calls += 1
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{video.stem}_000000.jpg"
        p.write_bytes(b"partial")
        yield _FakeFrame(frame_path=p, index=0)
        raise RuntimeError("ffmpeg_failed: simulated")


class _StubCalendar:
    async def list_events(self, on):  # type: ignore[no-untyped-def]
        return []


def _build_ctx(tmp_path: Path, ffmpeg: object) -> tuple[Context, Path]:
    db = Database.open_in_memory()
    settings = Settings()
    settings.local_root = str(tmp_path / "archive")
    settings.drive_base_folder_id = "folder_root"
    settings.extraction.enabled = True
    settings.extraction.fps = 1.0
    ctx = Context(
        settings=settings,
        logger=get_logger("test"),
        calendar=_StubCalendar(),
        drive=MockDriveClient(),
        ffmpeg=ffmpeg,  # type: ignore[arg-type]
        db=db,
    )
    return ctx, Path(settings.local_root)


def _make_session_with_videos(
    ctx: Context, local_root: Path, video_bytes_each: int, count: int
) -> tuple[str, Path]:
    sid = uuid.uuid4().hex
    local_folder = local_root / "TD_Tester"
    videos_dir = local_folder / "Videos"
    fotos_dir = local_folder / "Fotos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    fotos_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (videos_dir / f"v{i}.mp4").write_bytes(b"x" * video_bytes_each)
    with ctx.db.session() as db:
        db.add(
            Session(
                id=sid,
                customer_name="Tester",
                customer_phone=None,
                drive_folder_url="",
                drive_folder_id="folder_root",
                source_mount_path=str(local_root / "card"),
                local_folder=str(local_folder),
                status=SessionStatus.running,
            )
        )
        db.commit()
    return sid, local_folder


async def _consume(gen):  # type: ignore[no-untyped-def]
    events = []
    async for e in gen:
        events.append(e)
    return events


@pytest.mark.asyncio
async def test_preflight_aborts_when_disk_too_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, local_root = _build_ctx(tmp_path, _SuccessfulFfmpeg())
    sid, local_folder = _make_session_with_videos(ctx, local_root, 1024, 2)

    # Force check_free_space's view of free space to be ~zero.
    from fly_backend.behaviors.extract_frames import handler as handler_mod
    from fly_backend.util import disk as disk_mod

    def _fake_disk_usage(_p):  # type: ignore[no-untyped-def]
        class U:
            free = 1
            used = 0
            total = 1

        return U()

    monkeypatch.setattr(disk_mod.shutil, "disk_usage", _fake_disk_usage)
    monkeypatch.setattr(handler_mod.shutil, "disk_usage", _fake_disk_usage)

    with pytest.raises(BehaviorError) as excinfo:
        await _consume(extract_frames(ExtractFramesInput(session_id=sid), ctx))
    assert "disk_full_at_extract_start" in str(excinfo.value)
    # Fotos/ must be empty — preflight blocks before any ffmpeg call.
    assert list((local_folder / "Fotos").iterdir()) == []


@pytest.mark.asyncio
async def test_low_water_aborts_between_videos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, local_root = _build_ctx(tmp_path, _SuccessfulFfmpeg())
    sid, _local_folder = _make_session_with_videos(ctx, local_root, 1024, 3)

    # Preflight passes (lots of free). Per-video re-check drops below the
    # threshold after the first iteration.
    from fly_backend.behaviors.extract_frames import handler as handler_mod
    from fly_backend.util import disk as disk_mod

    state = {"calls": 0}

    def _fake_disk_usage(_p):  # type: ignore[no-untyped-def]
        state["calls"] += 1

        class U:
            # Big number for preflight; tiny for the loop check.
            free = 10**12 if state["calls"] <= 1 else 10
            used = 0
            total = 10**12

        return U()

    monkeypatch.setattr(disk_mod.shutil, "disk_usage", _fake_disk_usage)
    monkeypatch.setattr(handler_mod.shutil, "disk_usage", _fake_disk_usage)

    with pytest.raises(BehaviorError) as excinfo:
        await _consume(extract_frames(ExtractFramesInput(session_id=sid), ctx))
    assert "disk_full_during_extraction" in str(excinfo.value)


@pytest.mark.asyncio
async def test_atomic_temp_dir_cleans_up_on_crash(tmp_path: Path) -> None:
    """When ffmpeg raises mid-video, the .in-progress-* temp dir is removed
    and Fotos/ contains no orphan JPGs from the failed run."""
    ctx, local_root = _build_ctx(tmp_path, _CrashingFfmpeg())
    sid, local_folder = _make_session_with_videos(ctx, local_root, 1024, 1)
    fotos = local_folder / "Fotos"

    with pytest.raises(RuntimeError):
        await _consume(extract_frames(ExtractFramesInput(session_id=sid), ctx))

    # No half-written JPG should have leaked into Fotos/.
    assert list(fotos.iterdir()) == [], (
        f"Fotos/ should be empty after a failed extraction, found: "
        f"{list(fotos.iterdir())}"
    )
    # No temp dir lingering either.
    in_progress = list(fotos.glob(".in-progress-*"))
    assert in_progress == [], f"Temp dir not cleaned: {in_progress}"


@pytest.mark.asyncio
async def test_success_path_writes_final_jpgs_only(tmp_path: Path) -> None:
    """On success: Fotos/ contains the final JPGs, no .in-progress-* dirs."""
    ctx, local_root = _build_ctx(tmp_path, _SuccessfulFfmpeg())
    sid, local_folder = _make_session_with_videos(ctx, local_root, 1024, 2)
    fotos = local_folder / "Fotos"

    events = await _consume(extract_frames(ExtractFramesInput(session_id=sid), ctx))
    assert events  # at least one progress event per video
    jpgs = sorted(p.name for p in fotos.iterdir() if p.suffix == ".jpg")
    # 3 frames per video x 2 videos = 6.
    assert len(jpgs) == 6
    in_progress = list(fotos.glob(".in-progress-*"))
    assert in_progress == []
