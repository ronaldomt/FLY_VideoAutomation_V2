from __future__ import annotations

from pathlib import Path

import pytest
import structlog

from fly_backend.behaviors.upload_to_drive.contract import UploadToDriveInput
from fly_backend.behaviors.upload_to_drive.handler import run
from fly_backend.context import Context
from fly_backend.integrations.composio_calendar import MockCalendarClient
from fly_backend.integrations.composio_drive import MockDriveClient
from fly_backend.integrations.ffmpeg import FakeFfmpegClient
from fly_backend.persistence.db import Database
from fly_backend.persistence.models import FileRecord, Session, SessionStatus
from fly_backend.settings import Settings


def _seed(db: Database, local: Path) -> tuple[str, MockDriveClient]:
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
        for rel in ["Videos/A.MP4", "Videos/B.MP4", "Fotos/A_001.jpg"]:
            full = local / rel
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(b"data-" + rel.encode())
            s.add(
                FileRecord(
                    session_id=sid,
                    relative_path=rel,
                    size=full.stat().st_size,
                )
            )
        s.commit()
    return sid, MockDriveClient()


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


async def test_uploads_all_files_and_marks_them(ctx: Context, tmp_path: Path) -> None:
    local = tmp_path / "TD_Ana"
    sid, _ = _seed(ctx.db, local)

    events = [e async for e in run(UploadToDriveInput(session_id=sid), ctx)]
    # 3 uploads (any order due to parallelism, but final event has current==total).
    assert events[-1].total == 3
    with ctx.db.session() as db:
        from sqlmodel import select

        rows = db.exec(select(FileRecord).where(FileRecord.session_id == sid)).all()
    assert all(r.uploaded for r in rows)


async def test_idempotent_skips_already_uploaded(ctx: Context, tmp_path: Path) -> None:
    local = tmp_path / "TD_Ana"
    sid, _ = _seed(ctx.db, local)
    _ = [e async for e in run(UploadToDriveInput(session_id=sid), ctx)]
    second = [e async for e in run(UploadToDriveInput(session_id=sid), ctx)]
    assert second[0].message == "nothing_to_upload"
