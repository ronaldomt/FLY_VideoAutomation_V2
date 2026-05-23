"""Google Calendar via Composio.

Two implementations:
- `MockCalendarClient` — default. Returns deterministic synthetic events.
- `LiveCalendarClient` — wraps the Composio SDK. Active when
  `settings.composio.google_connected` is True (api_key_set + connection_id set).

The switch lives in `build_calendar_client()` so callers (Context) stay clean.
See CLAUDE.md §11.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

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




# ── title parser ─────────────────────────────────────────────────────────────

_PHONE_RE = re.compile(r"\+?\d[\d\s\-\(\)]{7,}\d")
_AGE_RE = re.compile(r"\b(\d{1,3})\s*(?:anos?|yr?s?|y\.o\.?)?\b", re.IGNORECASE)
_WEIGHT_RE = re.compile(r"\b(\d{2,3}(?:\.\d)?)\s*kg\b", re.IGNORECASE)
_TYPE_RE = re.compile(r"\b(HC|VIP)\b", re.IGNORECASE)


def _parse_title(title: str) -> tuple[str, str | None, int | None, float | None, str | None]:
    """Return (name, phone, age, weight, type) from a calendar event title.

    Title format observed: `Name - Phone - Age - Weight - Type(HC|VIP)`.
    Only `name` is guaranteed; everything else is best-effort.
    Weight is identified by 'kg' suffix so it is never confused with age.
    """
    # Split on " - " (with surrounding spaces) to preserve hyphenated names like
    # "Walk-in" or "Maria-Clara".
    parts = [p.strip() for p in title.split(" - ")]

    name = parts[0] if parts else title.strip()

    phone: str | None = None
    age: int | None = None
    weight: float | None = None
    jump_type: str | None = None

    remaining = parts[1:]
    for part in remaining:
        if phone is None:
            m = _PHONE_RE.search(part)
            if m:
                phone = re.sub(r"[\s\-\(\)]", "", m.group()).strip()
                continue

        if _TYPE_RE.search(part):
            jump_type = _TYPE_RE.search(part).group(1).upper()  # type: ignore[union-attr]
            continue

        # Weight must be checked before age: "72kg" has kg suffix
        wm = _WEIGHT_RE.search(part)
        if wm:
            weight = float(wm.group(1))
            continue

        am = _AGE_RE.search(part)
        if am:
            candidate = int(am.group(1))
            if 1 <= candidate <= 120:
                age = candidate
            continue

    return name, phone, age, weight, jump_type


def _parse_event(event: dict[str, Any]) -> CustomerEvent:
    """Convert a raw Google Calendar event dict to a CustomerEvent."""
    title = event.get("summary", "Unknown")
    start = event.get("start", {})
    dt_str: str = start.get("dateTime", "") or start.get("date", "")
    # Extract HH:MM from ISO datetime; fallback to ""
    time_str = ""
    if "T" in dt_str:
        time_str = dt_str.split("T")[1][:5]

    name, phone, age, weight, jump_type = _parse_title(title)
    return CustomerEvent(
        time=time_str,
        name=name,
        phone=phone,
        age=age,
        weight=weight,
        type=jump_type,
    )


# ── live client ──────────────────────────────────────────────────────────────


class LiveCalendarClient:
    """Real Composio-backed Google Calendar client.

    Active when `COMPOSIO_LIVE=1` env var is set and the Google connection is
    established (api_key + connection_id in settings).
    """

    def __init__(self, calendar_id: str, api_key: str, user_id: str, connection_id: str) -> None:
        self.calendar_id = calendar_id
        self.api_key = api_key
        self.user_id = user_id
        self.connection_id = connection_id

    async def list_events(self, on: date) -> list[CustomerEvent]:
        import asyncio

        return await asyncio.get_event_loop().run_in_executor(None, self._list_sync, on)

    def _list_sync(self, on: date) -> list[CustomerEvent]:  # pragma: no cover
        from .composio_client import composio_execute

        day = on.isoformat()
        result = composio_execute(
            api_key=self.api_key,
            connection_id=self.connection_id,
            entity_id=self.user_id,
            action="GOOGLECALENDAR_EVENTS_LIST",
            input_params={
                "calendarId": self.calendar_id,
                "timeMin": f"{day}T00:00:00Z",
                "timeMax": f"{day}T23:59:59Z",
                "singleEvents": True,
                "orderBy": "startTime",
                "maxResults": 100,
            },
        )
        items: list[dict[str, Any]] = (result.get("data") or {}).get("items") or []
        return [_parse_event(item) for item in items]


def build_calendar_client(settings: Settings) -> CalendarClient:
    from ..errors import NotConfiguredError
    from ..secrets import get_composio_key

    if not settings.composio.api_key_set:
        raise NotConfiguredError("composio_api_key_missing")
    if not settings.composio.connection_id:
        raise NotConfiguredError("composio_google_not_connected")
    api_key = get_composio_key()
    if not api_key:
        raise NotConfiguredError("composio_api_key_missing")
    return LiveCalendarClient(
        calendar_id=settings.calendar_id,
        api_key=api_key,
        user_id=settings.composio.user_id or "",
        connection_id=settings.composio.connection_id,
    )
