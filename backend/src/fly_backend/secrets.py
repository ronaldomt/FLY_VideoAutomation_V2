"""OS-keychain-backed storage for credentials.

The Composio API key lives in macOS Keychain / Windows Credential Manager /
Linux Secret Service via the `keyring` library — never in `settings.json`.
The settings document only records a boolean flag indicating presence.

Tests inject a fake keyring backend via `set_backend()` to avoid touching the
real OS keychain.
"""

from __future__ import annotations

import contextlib
from typing import Final, Protocol

SERVICE_NAME: Final[str] = "fly-video-automation"
COMPOSIO_KEY_USER: Final[str] = "composio_api_key"


class KeychainBackend(Protocol):
    def get_password(self, service: str, user: str) -> str | None: ...
    def set_password(self, service: str, user: str, password: str) -> None: ...
    def delete_password(self, service: str, user: str) -> None: ...


class _RealKeyringBackend:
    def get_password(self, service: str, user: str) -> str | None:
        import keyring

        return keyring.get_password(service, user)

    def set_password(self, service: str, user: str, password: str) -> None:
        import keyring

        keyring.set_password(service, user, password)

    def delete_password(self, service: str, user: str) -> None:
        import keyring
        import keyring.errors

        with contextlib.suppress(keyring.errors.PasswordDeleteError):
            keyring.delete_password(service, user)


class InMemoryBackend:
    """Test double — keeps keys in a dict instead of touching the OS keychain."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, user: str) -> str | None:
        return self._store.get((service, user))

    def set_password(self, service: str, user: str, password: str) -> None:
        self._store[(service, user)] = password

    def delete_password(self, service: str, user: str) -> None:
        self._store.pop((service, user), None)


_backend: KeychainBackend = _RealKeyringBackend()


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
