"""Composio SDK client factory.

Reads the API key from the OS keychain (see `fly_backend.secrets`) and
constructs a `composio.Composio` client.  All Composio-touching code goes
through here so we have one place to swap in fakes.

Notes on the model:
- `api_key` lives in the OS keychain.
- `auth_config_id` lives in `settings.composio.auth_config_id` — it's a
  non-secret reference to the auth configuration the operator created in the
  Composio dashboard (Google Super toolkit covering Calendar + Drive scopes).
- `user_id` is a stable per-install identifier, generated once and stashed
  in settings.  Composio scopes connections per user_id.

See CLAUDE.md §11 + Composio docs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import requests as _requests

from ..errors import IntegrationError, NotConfiguredError
from ..secrets import get_composio_key
from ..settings import Settings, save_settings

_COMPOSIO_V2 = "https://backend.composio.dev/api/v2"


def composio_execute(
    api_key: str,
    connection_id: str,
    entity_id: str,
    action: str,
    input_params: dict[str, Any],
    timeout: int = 60,
) -> dict[str, Any]:
    """Execute a Composio action via the v2 REST API.

    Bypasses the SDK's execute_action / check_connected_account path, which
    rejects googlesuper connections when GOOGLECALENDAR/GOOGLEDRIVE actions are
    requested. The v2 endpoint accepts the UUID-format connection_id directly.

    Raises IntegrationError on HTTP or parse failure.
    """
    app_prefix = action.split("_")[0]
    try:
        resp = _requests.post(
            f"{_COMPOSIO_V2}/actions/{action}/execute",
            headers={"x-api-key": api_key},
            json={
                "connectedAccountId": connection_id,
                "entityId": entity_id,
                "appName": app_prefix,
                "input": input_params,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except _requests.HTTPError as exc:
        raise IntegrationError(f"composio_execute_failed: {exc.response.text}") from exc
    except Exception as exc:
        raise IntegrationError(f"composio_execute_failed: {exc}") from exc


@dataclass(slots=True, frozen=True)
class ComposioConfig:
    api_key: str
    auth_config_id: str
    user_id: str
    connection_id: str | None
    toolkit: str


def ensure_user_id(settings: Settings) -> str:
    """Returns the stable per-install user_id, generating + persisting it on
    first call."""
    if settings.composio.user_id:
        return settings.composio.user_id
    settings.composio.user_id = f"fly-{uuid.uuid4().hex[:12]}"
    save_settings(settings)
    return settings.composio.user_id


def build_composio_config(settings: Settings, *, require_connection: bool = False) -> ComposioConfig:
    """Pull the runtime config together.  Raises `NotConfiguredError` if any
    prerequisite is missing — callers convert that to a 412 (see main.py)."""
    key = get_composio_key()
    if not key:
        raise NotConfiguredError("composio_api_key_missing")
    if not settings.composio.auth_config_id:
        raise NotConfiguredError("composio_auth_config_id_missing")
    if require_connection and not settings.composio.connection_id:
        raise NotConfiguredError("composio_google_not_connected")
    return ComposioConfig(
        api_key=key,
        auth_config_id=settings.composio.auth_config_id,
        user_id=ensure_user_id(settings),
        connection_id=settings.composio.connection_id,
        toolkit=settings.composio.toolkit,
    )


class ComposioClientLike(Protocol):
    """Minimal slice of the Composio SDK we depend on. Tests pass fakes."""

    def ping(self) -> None: ...  # raises IntegrationError on failure


class _RealComposioClient:
    """Thin wrapper around `composio.Composio`. Lazy import so the SDK is only
    pulled in when actually needed (tests stay fast)."""

    def __init__(self, cfg: ComposioConfig) -> None:
        self.cfg = cfg
        self._client = self._build()

    def _build(self):  # type: ignore[no-untyped-def]
        try:
            from composio import Composio
        except ImportError as exc:  # pragma: no cover
            raise IntegrationError(f"composio_sdk_missing: {exc}") from exc
        return Composio(api_key=self.cfg.api_key)

    def ping(self) -> None:
        # validate_api_key is a static method that hits /client/auth/client_info.
        # Raises ApiKeyError (subclass of Exception) on 401/403.
        try:
            from composio import Composio

            Composio.validate_api_key(self.cfg.api_key)
        except Exception as exc:
            raise IntegrationError(f"composio_ping_failed: {exc}") from exc

    @property
    def raw(self):  # type: ignore[no-untyped-def]
        return self._client


_factory: type[ComposioClientLike] = _RealComposioClient  # type: ignore[assignment]


def set_client_factory(factory: type[ComposioClientLike]) -> None:
    """Tests use this to swap in a fake. Production never calls it."""
    global _factory
    _factory = factory


def build_client(settings: Settings, *, require_connection: bool = False) -> ComposioClientLike:
    cfg = build_composio_config(settings, require_connection=require_connection)
    return _factory(cfg)  # type: ignore[call-arg]
