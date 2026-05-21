"""Unit tests for the Google Calendar event title parser."""

from __future__ import annotations

import pytest

from fly_backend.integrations.composio_calendar import _parse_event, _parse_title


@pytest.mark.parametrize(
    "title, expected_name, expected_phone, expected_age, expected_weight, expected_type",
    [
        # Full happy-path
        ("Ana Souza - +5511999990001 - 25 - 60kg - HC", "Ana Souza", "+5511999990001", 25, 60.0, "HC"),
        ("Bruno Lima - +5511999990002 - 30 - 80.5kg - VIP", "Bruno Lima", "+5511999990002", 30, 80.5, "VIP"),
        # Name only
        ("Carla Mendes", "Carla Mendes", None, None, None, None),
        # Name + phone only
        ("Diego Torres - +5544999991234", "Diego Torres", "+5544999991234", None, None, None),
        # Type case-insensitive
        ("Eva Lima - 22 - 55kg - vip", "Eva Lima", None, 22, 55.0, "VIP"),
        # Weight not confused as age (72kg)
        ("Fabio Costa - 72kg - HC", "Fabio Costa", None, None, 72.0, "HC"),
        # Age and weight in non-standard order
        ("Gabi Ramos - 90kg - 28 anos - VIP", "Gabi Ramos", None, 28, 90.0, "VIP"),
        # No type
        ("Hugo Silva - +5511988880000 - 35 - 75kg", "Hugo Silva", "+5511988880000", 35, 75.0, None),
    ],
)
def test_parse_title(
    title: str,
    expected_name: str,
    expected_phone: str | None,
    expected_age: int | None,
    expected_weight: float | None,
    expected_type: str | None,
) -> None:
    name, phone, age, weight, jump_type = _parse_title(title)
    assert name == expected_name
    assert phone == expected_phone
    assert age == expected_age
    assert weight == expected_weight
    assert jump_type == expected_type


def test_parse_event_extracts_time() -> None:
    event = {
        "summary": "Ana Souza - +5511999990001 - 25 - 60kg - HC",
        "start": {"dateTime": "2026-05-21T09:30:00-03:00"},
    }
    ce = _parse_event(event)
    assert ce.time == "09:30"
    assert ce.name == "Ana Souza"
    assert ce.phone == "+5511999990001"
    assert ce.age == 25
    assert ce.weight == 60.0
    assert ce.type == "HC"


def test_parse_event_handles_all_day() -> None:
    event = {"summary": "Walk-in", "start": {"date": "2026-05-21"}}
    ce = _parse_event(event)
    assert ce.time == ""
    assert ce.name == "Walk-in"


def test_parse_event_missing_summary() -> None:
    event = {"start": {"dateTime": "2026-05-21T10:00:00Z"}}
    ce = _parse_event(event)
    assert ce.name == "Unknown"
