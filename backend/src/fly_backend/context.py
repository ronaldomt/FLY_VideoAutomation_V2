"""Dependency container passed to behaviors.

A `Context` carries everything a behavior needs (settings, logger, integrations,
DB session). Behaviors NEVER import each other; composition happens here or in
HTTP routes.

See CLAUDE.md §7.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .logging import get_logger
from .settings import Settings, load_settings

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

    from .integrations.composio_calendar import CalendarClient
    from .integrations.composio_drive import DriveClient
    from .integrations.ffmpeg import FfmpegClient
    from .persistence.db import Database


@dataclass(slots=True)
class Context:
    """Injected into every behavior. Never imported by other behaviors."""

    settings: Settings
    logger: BoundLogger
    calendar: CalendarClient
    drive: DriveClient
    ffmpeg: FfmpegClient
    db: Database
    cancel_event: asyncio.Event | None = field(default=None)

    def with_bindings(self, **bindings: object) -> Context:
        """Return a shallow copy with a logger that has extra bound fields."""
        return Context(
            settings=self.settings,
            logger=self.logger.bind(**bindings),
            calendar=self.calendar,
            drive=self.drive,
            ffmpeg=self.ffmpeg,
            db=self.db,
            cancel_event=self.cancel_event,
        )


def build_default_context(settings: Settings | None = None) -> Context:
    """Wire the default Context. Composio live/mocked switch is read from env."""
    from .integrations.composio_calendar import build_calendar_client
    from .integrations.composio_drive import build_drive_client
    from .integrations.ffmpeg import FfmpegClient
    from .persistence.db import Database

    s = settings or load_settings()
    return Context(
        settings=s,
        logger=get_logger("fly_backend"),
        calendar=build_calendar_client(s),
        drive=build_drive_client(s),
        ffmpeg=FfmpegClient(),
        db=Database.open_default(),
    )
