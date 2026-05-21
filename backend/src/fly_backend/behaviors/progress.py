"""Shared ProgressEvent for behaviors that stream (copy / extract / upload).

The HTTP layer (CLAUDE.md §10) flattens these into Server-Sent Events on
`GET /sessions/:id/events`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ProgressEvent(BaseModel):
    phase: str  # PhaseName.value
    current: int
    total: int
    message: str | None = None
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
