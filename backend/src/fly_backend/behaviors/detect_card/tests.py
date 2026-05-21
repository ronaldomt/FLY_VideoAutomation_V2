from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import structlog

from fly_backend.behaviors.detect_card.contract import DetectCardInput
from fly_backend.behaviors.detect_card.handler import run
from fly_backend.context import Context
from fly_backend.integrations.composio_calendar import MockCalendarClient
from fly_backend.integrations.composio_drive import MockDriveClient
from fly_backend.integrations.ffmpeg import FakeFfmpegClient
from fly_backend.persistence.db import Database
from fly_backend.persistence.models import Session, SessionStatus
from fly_backend.settings import Settings


@pytest.fixture
def ctx() -> Context:
    return Context(
        settings=Settings(),
        logger=structlog.get_logger("test"),
        calendar=MockCalendarClient(),
        drive=MockDriveClient(),
        ffmpeg=FakeFfmpegClient(),  # type: ignore[arg-type]
        db=Database.open_in_memory(),
    )


async def test_records_card_detection(ctx: Context) -> None:
    result = await run(
        DetectCardInput(mount_path=Path("/Volumes/GOPRO"), volume_id="vol-123", label="GOPRO"),
        ctx,
    )
    assert result.volume_id == "vol-123"
    assert result.label == "GOPRO"
    assert result.already_ingested_within_hour is False


async def test_flags_recent_ingest(ctx: Context) -> None:
    now = datetime.now(UTC)
    with ctx.db.session() as db:
        db.add(
            Session(
                id="s1",
                customer_name="Ana",
                drive_folder_url="https://drive.google.com/drive/folders/abc",
                drive_folder_id="abc",
                source_mount_path="/Volumes/GOPRO",
                local_folder="/tmp/TD_Ana",
                status=SessionStatus.completed,
                created_at=now - timedelta(minutes=10),
                updated_at=now - timedelta(minutes=10),
            )
        )
        db.commit()

    result = await run(
        DetectCardInput(mount_path=Path("/Volumes/GOPRO"), volume_id="vol-123"),
        ctx,
    )
    assert result.already_ingested_within_hour is True
