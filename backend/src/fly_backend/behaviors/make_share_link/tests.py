from __future__ import annotations

from pathlib import Path

import pytest
import structlog

from fly_backend.behaviors.make_share_link.contract import MakeShareLinkInput
from fly_backend.behaviors.make_share_link.handler import _to_wa_me_number, run
from fly_backend.context import Context
from fly_backend.integrations.composio_calendar import MockCalendarClient
from fly_backend.integrations.composio_drive import MockDriveClient
from fly_backend.integrations.ffmpeg import FakeFfmpegClient
from fly_backend.persistence.db import Database
from fly_backend.persistence.models import Session, SessionStatus
from fly_backend.settings import Settings


def _seed(db: Database, local: Path, phone: str | None = None) -> str:
    sid = "sess-1"
    with db.session() as s:
        sess = Session(
            id=sid,
            customer_name="Ana",
            drive_folder_url="https://drive.google.com/drive/folders/abc",
            drive_folder_id="abc",
            source_mount_path=str(local / "src"),
            local_folder=str(local),
            status=SessionStatus.completed,
        )
        if phone is not None:
            sess.customer_phone = phone
        s.add(sess)
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


async def test_returns_url_without_phone(ctx: Context, tmp_path: Path) -> None:
    sid = _seed(ctx.db, tmp_path / "TD_Ana")
    result = await run(MakeShareLinkInput(session_id=sid), ctx)
    assert result.url.startswith("https://drive.google.com/drive/folders/abc")
    assert result.whatsapp_url is None


def test_wa_me_strips_non_digits() -> None:
    assert _to_wa_me_number("+55 11 99999-0001") == "5511999990001"
    assert _to_wa_me_number("(11) 99999-0002") == "11999990002"
