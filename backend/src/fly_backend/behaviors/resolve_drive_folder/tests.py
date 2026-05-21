from __future__ import annotations

import pytest
import structlog

from fly_backend.behaviors.resolve_drive_folder.contract import ResolveDriveFolderInput
from fly_backend.behaviors.resolve_drive_folder.handler import run
from fly_backend.context import Context
from fly_backend.errors import BehaviorError
from fly_backend.integrations.composio_calendar import MockCalendarClient
from fly_backend.integrations.composio_drive import MockDriveClient
from fly_backend.integrations.ffmpeg import FakeFfmpegClient
from fly_backend.persistence.db import Database
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


async def test_resolves_full_url(ctx: Context) -> None:
    out = await run(
        ResolveDriveFolderInput(
            drive_folder_url="https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoP"
        ),
        ctx,
    )
    assert out.id == "1aBcDeFgHiJkLmNoP"
    assert out.name.startswith("Mock Folder")


async def test_rejects_garbage(ctx: Context) -> None:
    with pytest.raises(BehaviorError):
        await run(ResolveDriveFolderInput(drive_folder_url="not-a-url"), ctx)
