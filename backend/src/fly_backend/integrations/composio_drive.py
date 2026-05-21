"""Google Drive via Composio.

Mock by default. `LiveDriveClient` activates when `COMPOSIO_LIVE=1` env var is
set and the Google connection is established (api_key + connection_id in settings).

Note on large files: Composio's `GOOGLEDRIVE_UPLOAD_FILE` action wraps the
standard Drive API upload and is suitable for the file sizes in scope (up to
~200 GB per session). v2 may switch to resumable chunked uploads via httpx for
better progress reporting; the `DriveClient` protocol is designed to allow that
swap without touching behaviors.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from ..errors import BehaviorError

if TYPE_CHECKING:
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
    """Real Composio-backed Google Drive client.

    All blocking Composio SDK calls are dispatched to a thread-pool executor
    so they don't block the asyncio event loop.
    """

    def __init__(self, api_key: str, user_id: str, connection_id: str) -> None:
        self.api_key = api_key
        self.user_id = user_id
        self.connection_id = connection_id

    def _toolset(self):  # type: ignore[no-untyped-def]  # pragma: no cover
        from composio import ComposioToolSet

        return ComposioToolSet(api_key=self.api_key, entity_id=self.user_id)

    def _exec(self, action: str, params: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
        ts = self._toolset()
        result: dict[str, Any] = ts.execute_action(
            action=action,
            params=params,
            connected_account_id=self.connection_id,
        )
        return result.get("data") or {}

    async def get_folder(self, folder_id: str) -> DriveFolder:  # pragma: no cover
        data = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._exec("GOOGLEDRIVE_GET_FILE_INFO", {"file_id": folder_id}),
        )
        return DriveFolder(
            id=folder_id,
            name=data.get("name", folder_id),
            path=data.get("name", folder_id),
        )

    async def ensure_subfolder(self, parent_id: str, name: str) -> str:  # pragma: no cover
        """Return id of existing subfolder named `name`, creating it if absent."""
        # Check if it already exists
        data = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._exec(
                "GOOGLEDRIVE_LIST_FILES_IN_FOLDER",
                {"folder_id": parent_id, "query": f"name='{name}' and mimeType='application/vnd.google-apps.folder'"},
            ),
        )
        files = data.get("files") or []
        for f in files:
            if f.get("name") == name:
                return str(f["id"])
        # Create it
        created = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._exec(
                "GOOGLEDRIVE_CREATE_FOLDER",
                {"name": name, "parent_folder_id": parent_id},
            ),
        )
        return str(created.get("id") or created.get("folder_id", ""))

    async def upload_file(self, parent_id: str, local: Path) -> UploadResult:  # pragma: no cover
        import hashlib

        data = local.read_bytes()
        md5 = hashlib.md5(data).hexdigest()
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._exec(
                "GOOGLEDRIVE_UPLOAD_FILE",
                {
                    "file_path": str(local),
                    "name": local.name,
                    "parent_folder_id": parent_id,
                },
            ),
        )
        file_id: str = result.get("id") or result.get("file_id", "")
        return UploadResult(
            file_id=file_id,
            name=local.name,
            size=local.stat().st_size,
            md5=md5,
        )

    async def list_files(self, folder_id: str) -> list[DriveFile]:  # pragma: no cover
        data = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._exec(
                "GOOGLEDRIVE_LIST_FILES_IN_FOLDER",
                {"folder_id": folder_id},
            ),
        )
        out = []
        for f in data.get("files") or []:
            out.append(
                DriveFile(
                    id=f.get("id", ""),
                    name=f.get("name", ""),
                    size=int(f.get("size", 0)),
                    md5=f.get("md5Checksum", ""),
                )
            )
        return out

    async def create_share_link(self, folder_id: str) -> str:  # pragma: no cover
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._exec(
                "GOOGLEDRIVE_SHARE_FILE",
                {"file_id": folder_id, "role": "reader", "type": "anyone"},
            ),
        )
        return f"https://drive.google.com/drive/folders/{folder_id}?usp=sharing"


def build_drive_client(settings: Settings) -> DriveClient:
    import os

    live = os.environ.get("COMPOSIO_LIVE", "0") == "1"
    if live and settings.composio.google_connected and settings.composio.connection_id:
        from ..secrets import get_composio_key

        api_key = get_composio_key()
        if api_key:
            return LiveDriveClient(
                api_key=api_key,
                user_id=settings.composio.user_id or "",
                connection_id=settings.composio.connection_id,
            )
    return MockDriveClient()
