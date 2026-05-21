"""SQLite-backed job queue models.

Every session's phases are rows. On startup, the backend resumes any session
in state `running` or `queued`. See CLAUDE.md §15.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


class SessionStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class PhaseName(StrEnum):
    copy_media = "copy_media"
    extract_frames = "extract_frames"
    upload = "upload_to_drive"
    verify = "verify_upload"
    share = "make_share_link"
    wipe = "wipe_card"


class PhaseStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


def _now() -> datetime:
    return datetime.now(UTC)


class Session(SQLModel, table=True):
    id: str = Field(primary_key=True)
    customer_name: str
    drive_folder_url: str
    drive_folder_id: str | None = None
    source_mount_path: str
    local_folder: str
    status: SessionStatus = SessionStatus.queued
    error: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Phase(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    name: PhaseName
    status: PhaseStatus = PhaseStatus.pending
    current: int = 0
    total: int = 0
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FileRecord(SQLModel, table=True):
    """One file inside a session. Used for idempotency + verification."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    relative_path: str  # e.g., "Videos/GH010001.MP4"
    size: int = 0
    md5: str | None = None
    drive_file_id: str | None = None
    uploaded: bool = False
    verified: bool = False
