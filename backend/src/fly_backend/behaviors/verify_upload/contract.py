"""verify_upload — local md5 == Drive md5? Card wipe is gated on this."""

from __future__ import annotations

from pydantic import BaseModel


class VerifyUploadInput(BaseModel):
    session_id: str


class Mismatch(BaseModel):
    relative_path: str
    reason: str  # "size_mismatch" | "md5_mismatch" | "missing_on_drive"
    local_md5: str | None = None
    drive_md5: str | None = None
    local_size: int | None = None
    drive_size: int | None = None


class VerificationReport(BaseModel):
    ok: bool
    checked: int
    mismatches: list[Mismatch]
