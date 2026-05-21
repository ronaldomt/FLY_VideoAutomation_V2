"""resolve_drive_folder — parse a Drive folder URL → DriveFolder."""

from __future__ import annotations

from pydantic import BaseModel


class ResolveDriveFolderInput(BaseModel):
    drive_folder_url: str


class ResolveDriveFolderOutput(BaseModel):
    id: str
    name: str
    path: str
