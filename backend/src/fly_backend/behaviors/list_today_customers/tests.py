from __future__ import annotations

from datetime import date

import pytest
import structlog

from fly_backend.behaviors.list_today_customers.contract import (
    ListTodayCustomersInput,
    parse_title,
)
from fly_backend.behaviors.list_today_customers.handler import run
from fly_backend.context import Context
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


async def test_returns_mock_events(ctx: Context) -> None:
    out = await run(ListTodayCustomersInput(on=date(2026, 5, 21)), ctx)
    assert out.source == "mock"
    assert len(out.events) == 3
    assert out.events[0].name == "Ana Souza"


def test_parse_title_full_format() -> None:
    ev = parse_title("Joana Silva - +5511999990001 - 32 - 65 - HC", "09:00")
    assert ev.name == "Joana Silva"
    assert ev.phone == "+5511999990001"
    assert ev.age == 32
    assert ev.weight == 65.0
    assert ev.type == "HC"


def test_parse_title_name_only() -> None:
    ev = parse_title("Walk-in", "10:30")
    assert ev.name == "Walk-in"
    assert ev.phone is None
    assert ev.type is None


def test_parse_title_handles_kg_suffix() -> None:
    ev = parse_title("Caio - 72kg - VIP", "11:00")
    assert ev.weight == 72.0
    assert ev.type == "VIP"


def test_parse_title_handles_partial_fields() -> None:
    ev = parse_title("Maria - VIP", "12:00")
    assert ev.name == "Maria"
    assert ev.type == "VIP"
    assert ev.phone is None
