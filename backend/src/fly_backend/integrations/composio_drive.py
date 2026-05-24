"""Google Drive via Composio (correct action names + v3 upload flow).

Action mapping verified 2026-05-24 against /api/v3/tools/<action> schema:
  GOOGLEDRIVE_GET_FILE_INFO       → NOT FOUND
    Replaced: validate via GOOGLEDRIVE_LIST_FILES (`q` query)
  GOOGLEDRIVE_LIST_FILES_IN_FOLDER→ NOT FOUND
    Replaced: GOOGLEDRIVE_LIST_FILES (query param is `q`, NOT `query`)
  GOOGLEDRIVE_CREATE_FOLDER       → EXISTS; params are `folder_name` + `parent_id`
                                    (NOT `parent_folder_id` — that one is silently
                                    ignored, causing folders to land at Drive root)
  GOOGLEDRIVE_UPLOAD_FILE         → EXISTS but requires v3 presigned URL flow
    Flow: POST /api/v3/files/upload/request → PUT presigned_url → execute with s3key
    Folder target param: `folder_to_upload_to`
  GOOGLEDRIVE_SHARE_FILE          → NOT FOUND
    Replaced: URL construction only (folder creator controls sharing in My Drive)
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import requests as _requests

from ..errors import BehaviorError, IntegrationError

if TYPE_CHECKING:
    from ..settings import Settings

_FOLDER_ID_RE = re.compile(r"(?:/folders/|[?&]id=)([A-Za-z0-9_\-]{10,})")
_COMPOSIO_V2 = "https://backend.composio.dev/api/v2"
_COMPOSIO_V3 = "https://backend.composio.dev/api/v3"


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
    """Real Google Drive client via Composio.

    Uses the v2 execute endpoint for metadata operations and the v3 presigned
    upload flow for file uploads (Composio's v1 upload API was removed).
    """

    def __init__(self, api_key: str, user_id: str, connection_id: str) -> None:
        self.api_key = api_key
        self.user_id = user_id
        self.connection_id = connection_id

    # ── Composio action execution (v2) ──────────────────────────────────────

    def _exec(self, action: str, params: dict[str, Any], timeout: int = 60) -> dict[str, Any]:  # pragma: no cover
        from .composio_client import composio_execute

        result = composio_execute(
            api_key=self.api_key,
            connection_id=self.connection_id,
            entity_id=self.user_id,
            action=action,
            input_params=params,
            timeout=timeout,
        )
        return result.get("data") or {}

    # ── OAuth token (for direct Drive API uploads) ───────────────────────────

    def _get_oauth_token(self) -> str | None:  # pragma: no cover
        """Try to get the real Google OAuth token from the Composio SDK.

        Returns None if the token is unavailable or masked ("REDACTED").
        Falls back gracefully — callers should use the Composio R2 path when None.
        """
        try:
            from composio import Composio as _Composio

            client = _Composio(api_key=self.api_key)
            account = client.connected_accounts.get(self.connection_id)
            token = account.connectionParams.access_token
            if token and token != "REDACTED":
                return token
        except Exception:
            pass
        return None

    # ── Direct Drive API resumable upload ────────────────────────────────────

    def _upload_direct(  # pragma: no cover
        self, local: Path, parent_folder_id: str, token: str
    ) -> str:
        """Upload directly to Google Drive via the resumable upload API.

        Avoids the Composio R2 hop (local → R2 → Drive) so the file is only
        uploaded once (local → Drive). ~2-3× faster for large files.
        Returns the Drive file_id.
        """
        data = local.read_bytes()
        mime = _guess_mime(local.name)
        upload_timeout = max(120, len(data) // (256 * 1024))

        # Initiate the resumable session
        try:
            init_resp = _requests.post(
                "https://www.googleapis.com/upload/drive/v3/files",
                params={"uploadType": "resumable"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Upload-Content-Type": mime,
                    "X-Upload-Content-Length": str(len(data)),
                },
                json={
                    "name": local.name,
                    "parents": [parent_folder_id],
                },
                timeout=15,
            )
            init_resp.raise_for_status()
        except _requests.HTTPError as exc:
            raise IntegrationError(f"drive_resumable_init_failed: {exc.response.text}") from exc

        upload_url: str = init_resp.headers["Location"]

        # Upload the file content
        try:
            up_resp = _requests.put(
                upload_url,
                data=data,
                headers={"Content-Type": mime},
                timeout=upload_timeout,
            )
            up_resp.raise_for_status()
        except _requests.HTTPError as exc:
            raise IntegrationError(f"drive_resumable_upload_failed: {exc.response.text}") from exc

        file_id: str = up_resp.json().get("id", "")
        if not file_id:
            raise IntegrationError(f"drive_resumable_no_file_id: {up_resp.text}")
        return file_id

    # ── File upload (direct if token available, Composio R2 otherwise) ───────

    def _upload_via_composio(  # pragma: no cover
        self, local: Path, parent_folder_id: str
    ) -> str:
        """Upload a local file to Drive.

        Tries direct Google Drive resumable upload first (faster — single hop).
        Falls back to Composio's v3 presigned URL flow if OAuth token is unavailable.
        Returns the Drive file_id.
        """
        data = local.read_bytes()
        md5 = hashlib.md5(data).hexdigest()
        mime = _guess_mime(local.name)

        # Step 1: Request a presigned upload URL from Composio v3
        try:
            resp1 = _requests.post(
                f"{_COMPOSIO_V3}/files/upload/request",
                headers={"x-api-key": self.api_key},
                json={
                    "md5": md5,
                    "toolkit_slug": "googlesuper",
                    "tool_slug": "GOOGLEDRIVE_UPLOAD_FILE",
                    "filename": local.name,
                    "mimetype": mime,
                },
                timeout=15,
            )
            resp1.raise_for_status()
        except _requests.HTTPError as exc:
            raise IntegrationError(f"composio_upload_request_failed: {exc.response.text}") from exc
        upload_meta = resp1.json()
        s3key: str = upload_meta["key"]
        presigned_url: str = upload_meta["new_presigned_url"]

        # Step 2: PUT file content to the presigned URL (Cloudflare R2)
        try:
            resp2 = _requests.put(
                presigned_url,
                data=data,
                headers={"Content-Type": mime},
                timeout=max(120, len(data) // (256 * 1024)),  # ~1s per 256KB
            )
            resp2.raise_for_status()
        except _requests.HTTPError as exc:
            raise IntegrationError(f"composio_s3_upload_failed: {exc.response.text}") from exc

        # Step 3: Execute Drive upload action with the s3key.
        # The correct folder parameter is `folder_to_upload_to` (confirmed from Composio schema).
        # Large video files can take >60s for Composio's R2→Drive transfer; use 300s.
        result = self._exec(
            "GOOGLEDRIVE_UPLOAD_FILE",
            {
                "file_to_upload": {"name": local.name, "mimetype": mime, "s3key": s3key},
                "folder_to_upload_to": parent_folder_id,
            },
            timeout=300,
        )
        # v2 execute API may return the response either unwrapped {"id": ...}
        # or wrapped {"data": {"id": ...}, "successful": true}
        file_id: str = str(
            result.get("id") or (result.get("data") or {}).get("id") or ""
        )
        if not file_id:
            raise IntegrationError(f"composio_upload_no_file_id: {result}")
        return file_id

    # ── DriveClient interface ────────────────────────────────────────────────

    async def get_folder(self, folder_id: str) -> DriveFolder:  # pragma: no cover
        """Validate folder exists and return its metadata.

        Uses LIST_FILES (with the correct `q` param) to confirm access. Returns
        folder_id as the name — Composio has no reliable ID→name action and the
        user already knows what folder they pasted.
        """
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._exec(
                "GOOGLEDRIVE_LIST_FILES",
                {"q": f"'{folder_id}' in parents and trashed=false"},
            ),
        )
        return DriveFolder(id=folder_id, name=folder_id, path=folder_id)

    async def ensure_subfolder(self, parent_id: str, name: str) -> str:  # pragma: no cover
        """Return id of existing subfolder named `name`, creating it if absent."""
        if not parent_id:
            raise IntegrationError("ensure_subfolder: parent_id is empty")
        # Search for an existing subfolder under parent_id matching the name.
        # The query param is `q` (not `query`); Composio silently ignores misspelled params.
        data = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._exec(
                "GOOGLEDRIVE_LIST_FILES",
                {
                    "q": (
                        f"'{parent_id}' in parents"
                        f" and name='{_escape_query_literal(name)}'"
                        f" and mimeType='application/vnd.google-apps.folder'"
                        f" and trashed=false"
                    ),
                    "fields": "files(id,name,parents)",
                    "pageSize": 100,
                },
            ),
        )
        # Defensive client-side filter: only accept a hit whose parents include parent_id.
        for f in data.get("files") or []:
            if f.get("name") != name:
                continue
            parents = f.get("parents") or []
            if not parents or parent_id in parents:
                return str(f["id"])
        # Create — the correct nest param is `parent_id`, not `parent_folder_id`.
        created = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._exec(
                "GOOGLEDRIVE_CREATE_FOLDER",
                {"folder_name": name, "parent_id": parent_id},
            ),
        )
        folder_id = str(created.get("id") or "")
        if not folder_id:
            raise IntegrationError(
                f"GOOGLEDRIVE_CREATE_FOLDER returned no id for '{name}' "
                f"under parent '{parent_id}' — response: {created}"
            )
        return folder_id

    async def upload_file(self, parent_id: str, local: Path) -> UploadResult:  # pragma: no cover
        data = local.read_bytes()
        md5 = hashlib.md5(data).hexdigest()
        file_id = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._upload_via_composio(local, parent_id)
        )
        return UploadResult(file_id=file_id, name=local.name, size=len(data), md5=md5)

    async def list_files(self, folder_id: str) -> list[DriveFile]:  # pragma: no cover
        data = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._exec(
                "GOOGLEDRIVE_LIST_FILES",
                {
                    "q": f"'{folder_id}' in parents and trashed=false",
                    "fields": "files(id,name,size,md5Checksum,parents)",
                    "pageSize": 1000,
                },
            ),
        )
        out = []
        for f in data.get("files") or []:
            # Defensive: only include files whose parents include folder_id when
            # the response carries parents. Some Composio responses strip it; in
            # that case we trust the `q` filter we just sent.
            parents = f.get("parents")
            if parents and folder_id not in parents:
                continue
            out.append(
                DriveFile(
                    id=f.get("id", ""),
                    name=f.get("name", ""),
                    size=int(f.get("size") or 0),
                    md5=f.get("md5Checksum", ""),
                )
            )
        return out

    async def create_share_link(self, folder_id: str) -> str:  # pragma: no cover
        """Return the sharing URL for the folder.

        In My Drive (non-Shared Drive), the folder's creator controls sharing.
        The operator pastes a shareable URL, so it's already accessible.
        """
        return f"https://drive.google.com/drive/folders/{folder_id}?usp=sharing"


def _guess_mime(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }.get(ext, "application/octet-stream")


def _escape_query_literal(value: str) -> str:
    """Escape a Drive query string literal (backslash + single quote)."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def build_drive_client(settings: "Settings") -> DriveClient:
    from ..errors import NotConfiguredError
    from ..secrets import get_composio_key

    if not settings.composio.api_key_set:
        raise NotConfiguredError("composio_api_key_missing")
    if not settings.composio.connection_id:
        raise NotConfiguredError("composio_google_not_connected")
    api_key = get_composio_key()
    if not api_key:
        raise NotConfiguredError("composio_api_key_missing")
    return LiveDriveClient(
        api_key=api_key,
        user_id=settings.composio.user_id or "",
        connection_id=settings.composio.connection_id,
    )
