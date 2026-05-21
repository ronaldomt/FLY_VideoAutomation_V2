"""Google Drive via Composio.

Mock by default. Live client wired in Task #7. See CLAUDE.md §11.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..errors import BehaviorError
from ..settings import Settings

_FOLDER_ID_RE = re.compile(r"(?:/folders/|[?&]id=)([A-Za-z0-9_\-]{10,})")


def parse_folder_id(url_or_id: str) -> str:
    """Extract a Google Drive folder id from a URL or a bare id."""
    if not url_or_id:
        raise BehaviorError("empty_drive_folder_url")
    m = _FOLDER_ID_RE.search(url_or_id)
    if m:
        return m.group(1)
    bare = url_or_id.strip()
    if re.fullmatch(r"[A-Za-z0-9_\-]{10,}", bare):
        return bare
    raise BehaviorError(f"could_not_parse_drive_folder_id: {url_or_id!r}")


@dataclass(slots=True)
class DriveFolder:
    id: str
    name: str
    path: str  # human-readable breadcrumb, best-effort


@dataclass(slots=True)
class DriveFile:
    id: str
    name: str
    size: int
    md5: str


@dataclass(slots=True)
class UploadResult:
    file_id: str
    name: str
    size: int
    md5: str


class DriveClient(Protocol):
    async def get_folder(self, folder_id: str) -> DriveFolder: ...
    async def ensure_subfolder(self, parent_id: str, name: str) -> str: ...
    async def upload_file(self, parent_id: str, local: Path) -> UploadResult: ...
    async def list_files(self, folder_id: str) -> list[DriveFile]: ...
    async def create_share_link(self, folder_id: str) -> str: ...


class MockDriveClient:
    """In-memory implementation; lets the UI + behavior tests run offline."""

    def __init__(self) -> None:
        self.folders: dict[str, DriveFolder] = {}
        self.uploads: dict[str, list[UploadResult]] = {}
        self._next_id = 1

    def _new_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}_{self._next_id}"

    async def get_folder(self, folder_id: str) -> DriveFolder:
        folder = self.folders.get(folder_id) or DriveFolder(
            id=folder_id, name=f"Mock Folder {folder_id[:6]}", path="/Mock"
        )
        self.folders[folder_id] = folder
        return folder

    async def ensure_subfolder(self, parent_id: str, name: str) -> str:
        sub_id = f"{parent_id}__{name}"
        self.folders[sub_id] = DriveFolder(id=sub_id, name=name, path=f"/Mock/{name}")
        return sub_id

    async def upload_file(self, parent_id: str, local: Path) -> UploadResult:
        import hashlib

        data = local.read_bytes() if local.exists() else b""
        md5 = hashlib.md5(data).hexdigest()
        result = UploadResult(
            file_id=self._new_id("file"), name=local.name, size=len(data), md5=md5
        )
        self.uploads.setdefault(parent_id, []).append(result)
        return result

    async def list_files(self, folder_id: str) -> list[DriveFile]:
        return [
            DriveFile(id=r.file_id, name=r.name, size=r.size, md5=r.md5)
            for r in self.uploads.get(folder_id, [])
        ]

    async def create_share_link(self, folder_id: str) -> str:
        return f"https://drive.google.com/drive/folders/{folder_id}?usp=sharing"


class LiveDriveClient:
    """Real Composio-backed client. Wired in Task #7."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def get_folder(self, folder_id: str) -> DriveFolder:  # pragma: no cover
        raise NotImplementedError("LiveDriveClient lands in Task #7")

    async def ensure_subfolder(self, parent_id: str, name: str) -> str:  # pragma: no cover
        raise NotImplementedError

    async def upload_file(self, parent_id: str, local: Path) -> UploadResult:  # pragma: no cover
        raise NotImplementedError

    async def list_files(self, folder_id: str) -> list[DriveFile]:  # pragma: no cover
        raise NotImplementedError

    async def create_share_link(self, folder_id: str) -> str:  # pragma: no cover
        raise NotImplementedError


def build_drive_client(settings: Settings) -> DriveClient:
    live = os.environ.get("COMPOSIO_LIVE", "0") == "1"
    if live and settings.composio.api_key_set:
        return LiveDriveClient(api_key=os.environ.get("COMPOSIO_API_KEY", ""))
    return MockDriveClient()
