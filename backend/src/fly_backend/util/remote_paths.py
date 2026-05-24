"""Conventional Drive paths shared across behaviors.

The session archive on Drive lives under:
  <base>/YYYY/MMM/MMM-DD/TD_<Customer>/VIDEO + FOTOS

upload_to_drive and verify_upload both build the same path; this helper exists
so the two can't drift (which previously broke verification silently).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..integrations.composio_drive import DriveClient
    from ..persistence.models import Session


async def ensure_session_subfolders(
    session: Session, drive: DriveClient
) -> tuple[str, str]:
    """Return (video_remote_id, fotos_remote_id), creating the path if absent."""
    if session.drive_folder_id is None:
        raise ValueError("session_missing_drive_folder_id")
    d = session.created_at.date()
    year_remote = await drive.ensure_subfolder(session.drive_folder_id, str(d.year))
    month_remote = await drive.ensure_subfolder(year_remote, d.strftime("%b"))
    day_remote = await drive.ensure_subfolder(month_remote, d.strftime("%b-%d"))
    customer_remote = await drive.ensure_subfolder(day_remote, f"TD_{session.customer_name}")
    video_remote = await drive.ensure_subfolder(customer_remote, "VIDEO")
    fotos_remote = await drive.ensure_subfolder(customer_remote, "FOTOS")
    return video_remote, fotos_remote
