"""Persistent settings (`~/.fly-video-automation/settings.json`).

Schema mirrors CLAUDE.md §12 exactly. Editable from the `/settings` page in the UI.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field, computed_field

SETTINGS_DIR: Final[Path] = Path.home() / ".fly-video-automation"
SETTINGS_FILE: Final[Path] = SETTINGS_DIR / "settings.json"


class ExtractionSettings(BaseModel):
    enabled: bool = True
    fps: float = Field(default=1.0, gt=0)
    min_interval_seconds: float = Field(default=0.25, gt=0)
    max_interval_seconds: float = Field(default=10.0, gt=0)
    output_format: str = "jpg"
    jpeg_quality: int = Field(default=90, ge=1, le=100)


class IngestSettings(BaseModel):
    video_extensions: list[str] = Field(default_factory=lambda: [".mp4", ".mov"])
    photo_extensions: list[str] = Field(default_factory=lambda: [".jpg", ".jpeg"])
    ignore_hidden: bool = True


class UploadSettings(BaseModel):
    parallel_uploads: int = Field(default=4, ge=1, le=16)
    chunk_size_mb: int = Field(default=16, ge=1, le=256)
    max_retries: int = Field(default=6, ge=0, le=20)


class CardWipeSettings(BaseModel):
    enabled: bool = False
    require_verification: bool = True


class WhatsAppSettings(BaseModel):
    auto_open_when_phone_present: bool = True


class UiSettings(BaseModel):
    auto_focus_on_card_insert: bool = True


class ComposioSettings(BaseModel):
    """Composio integration settings.

    The API key itself is NEVER stored here — it lives in the OS keychain
    (see `fly_backend.secrets`). This document only records that one has been
    set, plus the non-secret identifiers needed to reconstruct the SDK client.

    `toolkit` is locked to `google_super` for v1 (single OAuth covering
    Calendar + Drive + future Google scopes); keep the field so we can later
    support split toolkits without a settings migration.
    """

    api_key_set: bool = False
    auth_config_id: str | None = None
    connection_id: str | None = None
    user_id: str | None = None
    toolkit: str = "google_super"
    last_validated_at: str | None = None  # ISO 8601, set by /integrations/composio/ping

    @computed_field  # type: ignore[prop-decorator]
    @property
    def google_connected(self) -> bool:
        return self.api_key_set and bool(self.connection_id)


class Settings(BaseModel):
    """Top-level settings document. JSON-persisted at SETTINGS_FILE."""

    local_root: str | None = None
    drive_base_folder_url: str | None = None
    drive_base_folder_id: str | None = None
    drive_recent_folders: list[str] = Field(default_factory=list)
    calendar_id: str = "primary"
    extraction: ExtractionSettings = Field(default_factory=ExtractionSettings)
    ingest: IngestSettings = Field(default_factory=IngestSettings)
    upload: UploadSettings = Field(default_factory=UploadSettings)
    card_wipe: CardWipeSettings = Field(default_factory=CardWipeSettings)
    whatsapp: WhatsAppSettings = Field(default_factory=WhatsAppSettings)
    ui: UiSettings = Field(default_factory=UiSettings)
    composio: ComposioSettings = Field(default_factory=ComposioSettings)

    def remember_drive_folder(self, url: str, keep: int = 5) -> None:
        """Move `url` to the front of `drive_recent_folders`, dedup, cap at `keep`."""
        if url in self.drive_recent_folders:
            self.drive_recent_folders.remove(url)
        self.drive_recent_folders.insert(0, url)
        self.drive_recent_folders = self.drive_recent_folders[:keep]


def _resolve_path(path: Path | None) -> Path:
    """Resolve the active settings path. Looked up per-call so tests can swap
    `SETTINGS_FILE` via monkeypatch at runtime."""
    import fly_backend.settings as _self

    return path if path is not None else _self.SETTINGS_FILE


def load_settings(path: Path | None = None) -> Settings:
    """Read settings from disk. Returns defaults if the file does not exist."""
    p = _resolve_path(path)
    if not p.exists():
        return Settings()
    raw = p.read_text(encoding="utf-8")
    if not raw.strip():
        return Settings()
    return Settings.model_validate_json(raw)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    """Persist settings atomically (write to tmp + rename)."""
    p = _resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump_json(indent=2)
    fd, tmp_path = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=p.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, p)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_path)
        raise
