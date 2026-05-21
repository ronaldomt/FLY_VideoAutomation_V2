from __future__ import annotations

from pathlib import Path

import pytest
import structlog

from fly_backend.behaviors.copy_media.contract import CopyMediaInput
from fly_backend.behaviors.copy_media.handler import run
from fly_backend.context import Context
from fly_backend.errors import BehaviorError
from fly_backend.integrations.composio_calendar import MockCalendarClient
from fly_backend.integrations.composio_drive import MockDriveClient
from fly_backend.integrations.ffmpeg import FakeFfmpegClient
from fly_backend.persistence.db import Database
from fly_backend.persistence.models import Session, SessionStatus
from fly_backend.settings import Settings


def _make_session(db: Database, source: Path, local: Path) -> str:
    sid = "sess-1"
    with db.session() as s:
        s.add(
            Session(
                id=sid,
                customer_name="Ana",
                drive_folder_url="https://drive.google.com/drive/folders/abc",
                drive_folder_id="abc",
                source_mount_path=str(source),
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


async def test_copies_videos_and_photos_into_buckets(ctx: Context, tmp_path: Path) -> None:
    card = tmp_path / "GOPRO"
    card.mkdir()
    (card / "GH010001.MP4").write_bytes(b"\x00" * 100)
    (card / "GOPR0001.JPG").write_bytes(b"\xff" * 50)
    (card / "ignore.txt").write_bytes(b"x")

    local = tmp_path / "TD_Ana"
    sid = _make_session(ctx.db, card, local)

    events = [e async for e in run(CopyMediaInput(session_id=sid), ctx)]
    assert events[-1].current == 2
    assert (local / "Videos" / "GH010001.MP4").exists()
    assert (local / "Fotos" / "GOPR0001.JPG").exists()
    assert not (local / "ignore.txt").exists()


async def test_idempotent_rerun(ctx: Context, tmp_path: Path) -> None:
    card = tmp_path / "GOPRO"
    card.mkdir()
    (card / "GH010001.MP4").write_bytes(b"\x00" * 100)

    local = tmp_path / "TD_Ana"
    sid = _make_session(ctx.db, card, local)

    _ = [e async for e in run(CopyMediaInput(session_id=sid), ctx)]
    mtime_first = (local / "Videos" / "GH010001.MP4").stat().st_mtime_ns
    _ = [e async for e in run(CopyMediaInput(session_id=sid), ctx)]
    mtime_second = (local / "Videos" / "GH010001.MP4").stat().st_mtime_ns
    assert mtime_first == mtime_second  # unchanged on second run


async def test_filename_collision_does_not_overwrite(ctx: Context, tmp_path: Path) -> None:
    """CLAUDE.md §3 multi-card sessions: filename collisions get _2, _3, etc."""
    card = tmp_path / "GOPRO"
    card.mkdir()
    (card / "GH010001.MP4").write_bytes(b"first")

    local = tmp_path / "TD_Ana"
    (local / "Videos").mkdir(parents=True)
    (local / "Videos" / "GH010001.MP4").write_bytes(b"pre-existing")

    sid = _make_session(ctx.db, card, local)
    _ = [e async for e in run(CopyMediaInput(session_id=sid), ctx)]

    assert (local / "Videos" / "GH010001.MP4").read_bytes() == b"pre-existing"
    assert (local / "Videos" / "GH010001_2.MP4").read_bytes() == b"first"


async def test_raises_when_card_missing(ctx: Context, tmp_path: Path) -> None:
    sid = _make_session(ctx.db, tmp_path / "missing", tmp_path / "TD_Ana")
    with pytest.raises(BehaviorError, match="card_not_mounted"):
        async for _ in run(CopyMediaInput(session_id=sid), ctx):
            pass


async def test_unknown_session_raises(ctx: Context) -> None:
    with pytest.raises(BehaviorError, match="unknown_session"):
        async for _ in run(CopyMediaInput(session_id="nope"), ctx):
            pass
