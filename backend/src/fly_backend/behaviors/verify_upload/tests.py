from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import structlog

from fly_backend.behaviors.upload_to_drive.contract import UploadToDriveInput
from fly_backend.behaviors.upload_to_drive.handler import run as upload_run
from fly_backend.behaviors.verify_upload.contract import VerifyUploadInput
from fly_backend.behaviors.verify_upload.handler import run
from fly_backend.context import Context
from fly_backend.integrations.composio_calendar import MockCalendarClient
from fly_backend.integrations.composio_drive import MockDriveClient
from fly_backend.integrations.ffmpeg import FakeFfmpegClient
from fly_backend.persistence.db import Database
from fly_backend.persistence.models import FileRecord, Session, SessionStatus
from fly_backend.settings import Settings


def _seed_with_uploaded_files(db: Database, local: Path) -> str:
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
        for rel in ["Videos/A.MP4", "Fotos/A_001.jpg"]:
            full = local / rel
            full.parent.mkdir(parents=True, exist_ok=True)
            payload = b"data-" + rel.encode()
            full.write_bytes(payload)
            s.add(
                FileRecord(
                    session_id=sid,
                    relative_path=rel,
                    size=full.stat().st_size,
                    md5=hashlib.md5(payload).hexdigest(),
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


async def test_verifies_clean_upload(ctx: Context, tmp_path: Path) -> None:
    local = tmp_path / "TD_Ana"
    sid = _seed_with_uploaded_files(ctx.db, local)
    # Upload first so MockDrive has the files.
    _ = [e async for e in upload_run(UploadToDriveInput(session_id=sid), ctx)]
    report = await run(VerifyUploadInput(session_id=sid), ctx)
    assert report.ok is True
    assert report.checked == 2
    assert report.mismatches == []


async def test_detects_size_mismatch(ctx: Context, tmp_path: Path) -> None:
    local = tmp_path / "TD_Ana"
    sid = _seed_with_uploaded_files(ctx.db, local)
    _ = [e async for e in upload_run(UploadToDriveInput(session_id=sid), ctx)]

    # Tamper with the local file post-upload — make sure the size differs too.
    (local / "Videos" / "A.MP4").write_bytes(b"completely different content of different length")
    # Clear stored md5 so the handler recomputes from disk.
    with ctx.db.session() as s:
        from sqlmodel import select

        for row in s.exec(select(FileRecord).where(FileRecord.session_id == sid)).all():
            if row.relative_path == "Videos/A.MP4":
                row.md5 = None
                s.add(row)
        s.commit()
    report = await run(VerifyUploadInput(session_id=sid), ctx)
    assert report.ok is False
    assert any(m.reason == "size_mismatch" for m in report.mismatches)


async def test_missing_on_drive_reported(ctx: Context, tmp_path: Path) -> None:
    """File recorded locally but never uploaded — should surface as missing_on_drive."""
    local = tmp_path / "TD_Ana"
    sid = _seed_with_uploaded_files(ctx.db, local)
    # Don't run upload_run. Verification should flag everything as missing_on_drive.
    report = await run(VerifyUploadInput(session_id=sid), ctx)
    assert report.ok is False
    assert all(m.reason == "missing_on_drive" for m in report.mismatches)
