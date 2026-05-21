from __future__ import annotations

from pathlib import Path

import pytest
import structlog

from fly_backend.behaviors.extract_frames.contract import ExtractFramesInput
from fly_backend.behaviors.extract_frames.handler import run
from fly_backend.context import Context
from fly_backend.integrations.composio_calendar import MockCalendarClient
from fly_backend.integrations.composio_drive import MockDriveClient
from fly_backend.integrations.ffmpeg import FakeFfmpegClient
from fly_backend.persistence.db import Database
from fly_backend.persistence.models import Session, SessionStatus
from fly_backend.settings import Settings


def _make_session(db: Database, local: Path) -> str:
    sid = "sess-1"
    with db.session() as s:
        s.add(
            Session(
                id=sid,
                customer_name="Ana",
                drive_folder_url="https://drive.google.com/drive/folders/abc",
                drive_folder_id="abc",
                source_mount_path=str(local / "src"),
                local_folder=str(local),
                status=SessionStatus.running,
            )
        )
        s.commit()
    return sid


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    return Context(
        settings=Settings(local_root=str(tmp_path / "archive")),
        logger=structlog.get_logger("test"),
        calendar=MockCalendarClient(),
        drive=MockDriveClient(),
        ffmpeg=FakeFfmpegClient(),  # type: ignore[arg-type]
        db=Database.open_in_memory(),
    )


async def test_extracts_frames_from_each_video(ctx: Context, tmp_path: Path) -> None:
    local = tmp_path / "TD_Ana"
    (local / "Videos").mkdir(parents=True)
    (local / "Videos" / "GH010001.MP4").write_bytes(b"x")
    (local / "Videos" / "GH010002.MP4").write_bytes(b"y")

    sid = _make_session(ctx.db, local)
    events = [e async for e in run(ExtractFramesInput(session_id=sid), ctx)]
    # Two videos, three fake frames each → 6 JPGs in Fotos/.
    jpgs = list((local / "Fotos").glob("*.jpg"))
    assert len(jpgs) == 6
    assert events[-1].total == 2


async def test_extraction_disabled_setting(ctx: Context, tmp_path: Path) -> None:
    ctx.settings.extraction.enabled = False
    local = tmp_path / "TD_Ana"
    (local / "Videos").mkdir(parents=True)
    (local / "Videos" / "X.MP4").write_bytes(b"x")
    sid = _make_session(ctx.db, local)
    events = [e async for e in run(ExtractFramesInput(session_id=sid), ctx)]
    assert events[0].message == "extraction_disabled"
    assert not (local / "Fotos").exists() or not any((local / "Fotos").iterdir())


async def test_no_videos_completes_cleanly(ctx: Context, tmp_path: Path) -> None:
    local = tmp_path / "TD_Ana"
    local.mkdir()
    sid = _make_session(ctx.db, local)
    events = [e async for e in run(ExtractFramesInput(session_id=sid), ctx)]
    assert events[0].message == "no_videos"
