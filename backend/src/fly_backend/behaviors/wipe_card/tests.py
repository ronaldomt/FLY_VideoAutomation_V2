from __future__ import annotations

from pathlib import Path

import pytest
import structlog

from fly_backend.behaviors.wipe_card.contract import WipeCardInput
from fly_backend.behaviors.wipe_card.handler import run
from fly_backend.context import Context
from fly_backend.errors import VerificationError
from fly_backend.integrations.composio_calendar import MockCalendarClient
from fly_backend.integrations.composio_drive import MockDriveClient
from fly_backend.integrations.ffmpeg import FakeFfmpegClient
from fly_backend.persistence.db import Database
from fly_backend.persistence.models import FileRecord, Session, SessionStatus
from fly_backend.settings import Settings


def _seed(db: Database, card: Path, local: Path, all_verified: bool) -> str:
    sid = "sess-1"
    card.mkdir(exist_ok=True)
    (card / "GH010001.MP4").write_bytes(b"x")
    (card / "GOPR0001.JPG").write_bytes(b"y")
    with db.session() as s:
        s.add(
            Session(
                id=sid,
                customer_name="Ana",
                drive_folder_url="https://drive.google.com/drive/folders/abc",
                drive_folder_id="abc",
                source_mount_path=str(card),
                local_folder=str(local),
                status=SessionStatus.completed,
            )
        )
        for rel in ["Videos/GH010001.MP4", "Fotos/GOPR0001.JPG"]:
            s.add(
                FileRecord(
                    session_id=sid,
                    relative_path=rel,
                    size=1,
                    uploaded=True,
                    verified=all_verified,
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


async def test_refuses_without_explicit_confirm(ctx: Context, tmp_path: Path) -> None:
    sid = _seed(ctx.db, tmp_path / "CARD", tmp_path / "TD_Ana", all_verified=True)
    ctx.settings.card_wipe.enabled = True
    result = await run(WipeCardInput(session_id=sid, confirm=False), ctx)
    assert result.ok is False
    assert result.skipped_reason == "not_confirmed"


async def test_refuses_when_setting_disabled(ctx: Context, tmp_path: Path) -> None:
    sid = _seed(ctx.db, tmp_path / "CARD", tmp_path / "TD_Ana", all_verified=True)
    ctx.settings.card_wipe.enabled = False  # explicit; matches default
    result = await run(WipeCardInput(session_id=sid, confirm=True), ctx)
    assert result.ok is False
    assert result.skipped_reason == "card_wipe_disabled_in_settings"


async def test_refuses_when_files_unverified(ctx: Context, tmp_path: Path) -> None:
    sid = _seed(ctx.db, tmp_path / "CARD", tmp_path / "TD_Ana", all_verified=False)
    ctx.settings.card_wipe.enabled = True
    with pytest.raises(VerificationError):
        await run(WipeCardInput(session_id=sid, confirm=True), ctx)


async def test_wipes_when_all_conditions_met(ctx: Context, tmp_path: Path) -> None:
    card = tmp_path / "CARD"
    sid = _seed(ctx.db, card, tmp_path / "TD_Ana", all_verified=True)
    ctx.settings.card_wipe.enabled = True
    result = await run(WipeCardInput(session_id=sid, confirm=True), ctx)
    assert result.ok is True
    assert result.deleted == 2
    assert not any(p.is_file() for p in card.rglob("*"))
