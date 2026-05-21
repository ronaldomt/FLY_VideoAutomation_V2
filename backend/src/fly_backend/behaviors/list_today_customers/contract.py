"""list_today_customers — calendar → customer picker rows.

The Calendar event title convention observed is:
    `Name - Phone - Age - Weight - Type(HC|VIP)`
Only `name` is guaranteed; the parser is tolerant (CLAUDE.md §4 decision 14).
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel

from ...integrations.composio_calendar import CustomerEvent


class ListTodayCustomersInput(BaseModel):
    on: date | None = None


class ListTodayCustomersOutput(BaseModel):
    events: list[CustomerEvent]
    calendar_id: str
    source: str  # "live" | "mock"

    model_config = {"arbitrary_types_allowed": True}


_DIGITS_RE = re.compile(r"^\+?[\d\s\-()]{7,}$")


def parse_title(title: str, time_str: str) -> CustomerEvent:
    """Best-effort parse of a calendar event title.

    Format: `Name - Phone - Age - Weight - Type`. Anything past `Name` is optional;
    if a field doesn't parse cleanly, it's dropped silently.
    """
    parts = [p.strip() for p in title.split(" - ")]
    name = parts[0] if parts else title.strip()
    phone: str | None = None
    age: int | None = None
    weight: float | None = None
    type_: str | None = None

    for field in parts[1:]:
        if phone is None and _DIGITS_RE.match(field):
            phone = field
            continue
        if field.upper() in {"HC", "VIP"}:
            type_ = field.upper()
            continue
        has_kg = "kg" in field.lower()
        try:
            n = float(field.lower().replace(",", ".").replace("kg", "").strip())
        except ValueError:
            continue
        # Explicit "kg" suffix always wins as weight.
        if has_kg and 20 <= n <= 300:
            weight = n
            continue
        if age is None and n.is_integer() and 5 <= n <= 110:
            age = int(n)
        elif weight is None and 20 <= n <= 300:
            weight = n

    return CustomerEvent(time=time_str, name=name, phone=phone, age=age, weight=weight, type=type_)
