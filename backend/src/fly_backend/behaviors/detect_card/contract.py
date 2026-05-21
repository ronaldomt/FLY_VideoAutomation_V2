"""detect_card — Tauri tells us a card just appeared.

The Rust shell debounces native FS events and POSTs to `/cards/detected`.
This behavior persists the most recent insertion so the frontend can recover
state on reload (and so we can implement the "already ingested in the last
hour" re-insert check in CLAUDE.md §3 edge cases).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class DetectCardInput(BaseModel):
    mount_path: Path
    volume_id: str = Field(description="OS-stable identifier (UUID on macOS, volume serial on Windows).")
    label: str | None = None


class CardDetected(BaseModel):
    mount_path: Path
    volume_id: str
    label: str | None
    detected_at: datetime
    already_ingested_within_hour: bool = False
