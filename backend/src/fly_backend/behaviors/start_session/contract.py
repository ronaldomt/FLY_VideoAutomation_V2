"""start_session — orchestrator that creates the local folder, validates the
Drive destination, runs the disk-full pre-check, and persists the new session
row. Subsequent phases (copy / extract / upload / verify) are kicked off from
the HTTP layer once the session exists.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class SessionOverrides(BaseModel):
    """Per-session overrides on top of global settings."""

    fps: float | None = Field(default=None, gt=0)
    extraction_enabled: bool | None = None


class StartSessionInput(BaseModel):
    customer_name: str = Field(min_length=1, max_length=200)
    customer_phone: str | None = None
    drive_folder_url: str
    source_mount_path: Path
    overrides: SessionOverrides = Field(default_factory=SessionOverrides)


class SessionOut(BaseModel):
    id: str
    customer_name: str
    customer_phone: str | None
    drive_folder_id: str
    drive_folder_url: str
    drive_folder_name: str
    source_mount_path: Path
    local_folder: Path
    status: str
    disk_check_ok: bool
    estimated_card_bytes: int
    free_bytes: int
    shortfall_bytes: int
