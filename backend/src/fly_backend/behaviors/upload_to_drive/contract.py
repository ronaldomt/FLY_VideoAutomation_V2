"""upload_to_drive — local Videos/ + Fotos/ → Drive folder.

Idempotent: uploaded files (`uploaded=True`) are skipped on rerun. Parallelism
cap from settings (CLAUDE.md §12). Exponential backoff is delegated to the
Drive client.
"""

from __future__ import annotations

from pydantic import BaseModel


class UploadToDriveInput(BaseModel):
    session_id: str
