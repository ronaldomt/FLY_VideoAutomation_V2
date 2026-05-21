from __future__ import annotations

from datetime import date as _date

from ...context import Context
from ...integrations.composio_calendar import LiveCalendarClient
from .contract import ListTodayCustomersInput, ListTodayCustomersOutput


async def run(
    payload: ListTodayCustomersInput, ctx: Context
) -> ListTodayCustomersOutput:
    log = ctx.logger.bind(behavior="list_today_customers")
    on = payload.on or _date.today()
    events = await ctx.calendar.list_events(on)
    source = "live" if isinstance(ctx.calendar, LiveCalendarClient) else "mock"
    log.info(
        "customers_listed", on=on.isoformat(), source=source, count=len(events)
    )
    return ListTodayCustomersOutput(
        events=events, calendar_id=ctx.settings.calendar_id, source=source
    )
