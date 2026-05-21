from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import structlog

from fly_backend.behaviors.start_session.contract import StartSessionInput
from fly_backend.behaviors.start_session.handler import (
    _sanitize_customer_name,
    run,
)
from fly_backend.context import Context
from fly_backend.errors import BehaviorError, NotConfiguredError
from fly_backend.integrations.composio_calendar import MockCalendarClient
from fly_backend.integrations.composio_drive import MockDriveClient
from fly_backend.integrations.ffmpeg import FakeFfmpegClient
from fly_backend.persistence.db import Database
from fly_backend.persistence.models import Session
from fly_backend.settings import Settings


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Context:
    # Settings must live inside tmp_path for save_settings() not to touch $HOME.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(
        "fly_backend.settings.SETTINGS_FILE",
        home / ".fly-video-automation" / "settings.json",
    )
    return Context(
        settings=Settings(local_root=str(tmp_path / "archive")),
        logger=structlog.get_logger("test"),
        calendar=MockCalendarClient(),
        drive=MockDriveClient(),
        ffmpeg=FakeFfmpegClient(),  # type: ignore[arg-type]
        db=Database.open_in_memory(),
    )


def _card_with_media(card: Path) -> None:
    card.mkdir()
    (card / "GH010001.MP4").write_bytes(b"x" * 1000)
    (card / "GOPR0001.JPG").write_bytes(b"y" * 500)


async def test_creates_local_folder_and_persists_session(
    ctx: Context, tmp_path: Path
) -> None:
    card = tmp_path / "CARD"
    _card_with_media(card)
    result = await run(
        StartSessionInput(
            customer_name="Ana Souza",
            customer_phone="+5511999990001",
            drive_folder_url="https://drive.google.com/drive/folders/1aBcDeFgHiJk",
            source_mount_path=card,
        ),
        ctx,
    )
    assert result.disk_check_ok is True
    assert result.status == "queued"
    assert result.local_folder.name == "TD_Ana Souza"
    assert (result.local_folder / "Videos").is_dir()
    assert (result.local_folder / "Fotos").is_dir()
    with ctx.db.session() as db:
        stored = db.get(Session, result.id)
        assert stored is not None
        assert stored.customer_phone == "+5511999990001"
        assert stored.drive_folder_id == "1aBcDeFgHiJk"


async def test_refuses_without_local_root(ctx: Context, tmp_path: Path) -> None:
    ctx.settings.local_root = None
    card = tmp_path / "CARD"
    _card_with_media(card)
    with pytest.raises(NotConfiguredError):
        await run(
            StartSessionInput(
                customer_name="Ana",
                drive_folder_url="https://drive.google.com/drive/folders/1aBcDeFgHiJk",
                source_mount_path=card,
            ),
            ctx,
        )


async def test_refuses_when_card_missing(ctx: Context, tmp_path: Path) -> None:
    with pytest.raises(BehaviorError, match="card_not_mounted"):
        await run(
            StartSessionInput(
                customer_name="Ana",
                drive_folder_url="https://drive.google.com/drive/folders/1aBcDeFgHiJk",
                source_mount_path=tmp_path / "nope",
            ),
            ctx,
        )


async def test_walkin_logged_when_no_phone(ctx: Context, tmp_path: Path) -> None:
    card = tmp_path / "CARD"
    _card_with_media(card)
    _ = await run(
        StartSessionInput(
            customer_name="Walk-in João",
            drive_folder_url="https://drive.google.com/drive/folders/1aBcDeFgHiJk",
            source_mount_path=card,
        ),
        ctx,
    )
    logs = Path(ctx.settings.local_root) / "_logs"  # type: ignore[arg-type]
    csv_files = list(logs.glob("walkins-*.csv"))
    assert csv_files, "expected a walkins-YYYY-MM-DD.csv to be created"
    content = csv_files[0].read_text()
    assert "Walk-in João" in content


async def test_disk_full_marks_session_failed(
    ctx: Context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end disk-full pre-check (CLAUDE.md §16): if free < required + 10%
    headroom, the session is created with status=failed and ok=False — and no
    copy phase runs. The card is left untouched."""
    card = tmp_path / "CARD"
    _card_with_media(card)

    class _FakeUsage:
        total = 100
        used = 50
        free = 50

    monkeypatch.setattr(shutil, "disk_usage", lambda _p: _FakeUsage())
    result = await run(
        StartSessionInput(
            customer_name="Ana",
            drive_folder_url="https://drive.google.com/drive/folders/1aBcDeFgHiJk",
            source_mount_path=card,
        ),
        ctx,
    )
    assert result.disk_check_ok is False
    assert result.status == "failed"
    assert result.shortfall_bytes > 0


async def test_sanitize_customer_name() -> None:
    assert _sanitize_customer_name("Ana / Souza") == "Ana  Souza"
    assert _sanitize_customer_name("") == "Walk-in"
    assert _sanitize_customer_name("../../etc/passwd") == "etcpasswd"


async def test_integration_full_pipeline(ctx: Context, tmp_path: Path) -> None:
    """Smoke integration test: orchestrator → copy → extract → upload → verify.

    Wired with mocked Composio + Fake ffmpeg. This is the contract guaranteed
    by CLAUDE.md §16: 'orchestrator has an integration test with mocked
    Composio'.
    """
    from fly_backend.behaviors.copy_media.contract import CopyMediaInput
    from fly_backend.behaviors.copy_media.handler import run as copy_run
    from fly_backend.behaviors.extract_frames.contract import ExtractFramesInput
    from fly_backend.behaviors.extract_frames.handler import run as extract_run
    from fly_backend.behaviors.upload_to_drive.contract import UploadToDriveInput
    from fly_backend.behaviors.upload_to_drive.handler import run as upload_run
    from fly_backend.behaviors.verify_upload.contract import VerifyUploadInput
    from fly_backend.behaviors.verify_upload.handler import run as verify_run

    card = tmp_path / "CARD"
    _card_with_media(card)

    session = await run(
        StartSessionInput(
            customer_name="Ana Souza",
            customer_phone="+5511999990001",
            drive_folder_url="https://drive.google.com/drive/folders/1aBcDeFgHiJk",
            source_mount_path=card,
        ),
        ctx,
    )
    assert session.disk_check_ok is True

    _ = [e async for e in copy_run(CopyMediaInput(session_id=session.id), ctx)]
    _ = [e async for e in extract_run(ExtractFramesInput(session_id=session.id), ctx)]
    _ = [e async for e in upload_run(UploadToDriveInput(session_id=session.id), ctx)]
    report = await verify_run(VerifyUploadInput(session_id=session.id), ctx)

    assert report.ok is True
    assert report.checked >= 2  # at least the MP4 + the JPG
