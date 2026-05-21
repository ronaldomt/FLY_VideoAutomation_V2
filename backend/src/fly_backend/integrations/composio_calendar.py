"""Google Calendar via Composio.

Two implementations:
- `MockCalendarClient` — default. Returns deterministic synthetic events.
- `LiveCalendarClient` — wraps the Composio SDK. Activated when
  `COMPOSIO_LIVE=1` and an API key is configured.

The switch lives in `build_calendar_client()` so callers (Context) stay clean.
See CLAUDE.md §11.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from ..settings import Settings


@dataclass(slots=True)
class CustomerEvent:
    """One row in the operator's customer picker.

    Only `name` is guaranteed by the school's calendar convention. Other fields
    are best-effort parsed from titles like `Name - Phone - Age - Weight - Type`.
    """

    time: str  # HH:MM in local time
    name: str
    phone: str | None = None
    age: int | None = None
    weight: float | None = None
    type: str | None = None  # "HC" | "VIP" | None


class CalendarClient(Protocol):
    async def list_events(self, on: date) -> list[CustomerEvent]: ...


class MockCalendarClient:
    """Returns a small, stable list so the UI is always testable offline."""

    async def list_events(self, on: date) -> list[CustomerEvent]:
        return [
            CustomerEvent(time="09:00", name="Ana Souza", phone="+5511999990001", type="HC"),
            CustomerEvent(time="09:30", name="Bruno Lima", phone="+5511999990002", type="VIP"),
            CustomerEvent(time="10:00", name="Carla Mendes"),
        ]


class LiveCalendarClient:
    """Real Composio-backed client. Wired in Task #7 (COMPOSIO_LIVE)."""

    def __init__(self, calendar_id: str, api_key: str) -> None:
        self.calendar_id = calendar_id
        self.api_key = api_key

    async def list_events(self, on: date) -> list[CustomerEvent]:  # pragma: no cover
        # BLOCKED: see BLOCKERS.md (Composio API key + Google OAuth).
        raise NotImplementedError("LiveCalendarClient lands in Task #7")


def build_calendar_client(settings: Settings) -> CalendarClient:
    live = os.environ.get("COMPOSIO_LIVE", "0") == "1"
    if live and settings.composio.api_key_set:
        return LiveCalendarClient(
            calendar_id=settings.calendar_id,
            api_key=os.environ.get("COMPOSIO_API_KEY", ""),
        )
    return MockCalendarClient()
