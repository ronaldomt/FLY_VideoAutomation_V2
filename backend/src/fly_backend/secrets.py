"""Credential storage for the Python sidecar.

Stores the Composio API key in ``~/.fly-video-automation/secrets.json``
(mode 0600 on Unix). The settings document only records a boolean flag
indicating presence.

We previously used the OS keychain via ``keyring``, but on macOS that
caused an unrecoverable prompt loop with the bundled (unsigned, PyInstaller
``--onefile``) sidecar: each launch extracts Python to a fresh tempdir, so
macOS Keychain can never bind an "Always Allow" decision to a stable
identity. The file-based store sidesteps the issue entirely on a
single-user workstation. Tests still inject a fake backend via
``set_backend()``.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Final, Protocol

SERVICE_NAME: Final[str] = "fly-video-automation"
COMPOSIO_KEY_USER: Final[str] = "composio_api_key"

_RUNTIME_DIR_NAME: Final[str] = ".fly-video-automation"
_SECRETS_FILE_NAME: Final[str] = "secrets.json"


def _secrets_path() -> Path:
    home = Path(os.path.expanduser("~"))
    runtime_dir = home / _RUNTIME_DIR_NAME
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir / _SECRETS_FILE_NAME


def _key(service: str, user: str) -> str:
    return f"{service}::{user}"


class KeychainBackend(Protocol):
    def get_password(self, service: str, user: str) -> str | None: ...
    def set_password(self, service: str, user: str, password: str) -> None: ...
    def delete_password(self, service: str, user: str) -> None: ...


class _FileBackend:
    """JSON file at ``~/.fly-video-automation/secrets.json`` (mode 0600)."""

    def _load(self) -> dict[str, str]:
        path = _secrets_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, str]) -> None:
        path = _secrets_path()
        path.write_text(json.dumps(data, indent=2))
        # Owner-only read/write. No-op on Windows; harmless.
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def get_password(self, service: str, user: str) -> str | None:
        return self._load().get(_key(service, user))

    def set_password(self, service: str, user: str, password: str) -> None:
        data = self._load()
        data[_key(service, user)] = password
        self._save(data)

    def delete_password(self, service: str, user: str) -> None:
        data = self._load()
        if data.pop(_key(service, user), None) is not None:
            self._save(data)


class InMemoryBackend:
    """Test double — keeps keys in a dict instead of touching disk."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, user: str) -> str | None:
        return self._store.get((service, user))

    def set_password(self, service: str, user: str, password: str) -> None:
        self._store[(service, user)] = password

    def delete_password(self, service: str, user: str) -> None:
        self._store.pop((service, user), None)


_backend: KeychainBackend = _FileBackend()


def set_backend(backend: KeychainBackend) -> None:
    """Used by tests + the conftest to redirect away from the real keychain."""
    global _backend
    _backend = backend


def get_composio_key() -> str | None:
    return _backend.get_password(SERVICE_NAME, COMPOSIO_KEY_USER)


def set_composio_key(key: str) -> None:
    if not key or not key.strip():
        raise ValueError("composio_api_key_empty")
    _backend.set_password(SERVICE_NAME, COMPOSIO_KEY_USER, key.strip())


def clear_composio_key() -> None:
    _backend.delete_password(SERVICE_NAME, COMPOSIO_KEY_USER)
