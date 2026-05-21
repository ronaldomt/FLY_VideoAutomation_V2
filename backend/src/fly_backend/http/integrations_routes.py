"""Integration management endpoints (Composio key + auth-config + ping).

Owns the contract surface that the Settings UI hits. Separated from
`http/routes.py` so the per-service plumbing stays grouped.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..errors import IntegrationError, NotConfiguredError
from ..integrations.composio_client import build_client
from ..logging import get_logger
from ..secrets import clear_composio_key, get_composio_key, set_composio_key
from ..settings import load_settings, save_settings

router = APIRouter(prefix="/integrations/composio", tags=["integrations"])


class ComposioKeyInput(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)
    auth_config_id: str = Field(min_length=4, max_length=128)


class ComposioStatus(BaseModel):
    api_key_set: bool
    auth_config_id: str | None
    user_id: str | None
    connection_id: str | None
    google_connected: bool
    toolkit: str
    last_validated_at: str | None


def _status_from_settings() -> ComposioStatus:
    s = load_settings()
    return ComposioStatus(
        api_key_set=s.composio.api_key_set,
        auth_config_id=s.composio.auth_config_id,
        user_id=s.composio.user_id,
        connection_id=s.composio.connection_id,
        google_connected=s.composio.google_connected,
        toolkit=s.composio.toolkit,
        last_validated_at=s.composio.last_validated_at,
    )


@router.get("/status", response_model=ComposioStatus)
async def get_status() -> ComposioStatus:
    """Cheap read of the persisted integration state. No external calls."""
    return _status_from_settings()


@router.put("/key", response_model=ComposioStatus)
async def put_key(payload: ComposioKeyInput) -> ComposioStatus:
    """Store the Composio API key in the OS keychain and the (non-secret)
    auth_config_id in settings.

    **Side effects** (per CLAUDE.md §17 — user decision: re-auth on every key
    change):
    - clears any existing `connection_id` so the Google OAuth flow re-runs.
    - clears `last_validated_at` so the UI shows the validation is stale.
    """
    log = get_logger("integrations.composio")
    settings = load_settings()
    set_composio_key(payload.api_key)
    settings.composio.api_key_set = True
    settings.composio.auth_config_id = payload.auth_config_id
    settings.composio.connection_id = None
    settings.composio.last_validated_at = None
    save_settings(settings)
    log.info("composio_key_set", auth_config_id=payload.auth_config_id)
    return _status_from_settings()


@router.delete("/key", response_model=ComposioStatus)
async def delete_key() -> ComposioStatus:
    """Wipe the key from the keychain and reset connection state."""
    log = get_logger("integrations.composio")
    clear_composio_key()
    settings = load_settings()
    settings.composio.api_key_set = False
    settings.composio.connection_id = None
    settings.composio.last_validated_at = None
    save_settings(settings)
    log.info("composio_key_cleared")
    return _status_from_settings()


class PingResult(BaseModel):
    ok: bool
    validated_at: str
    detail: str | None = None


@router.post("/ping", response_model=PingResult)
async def ping() -> PingResult:
    """Make a real Composio API call to validate the key + auth_config.

    Used by the Settings UI after Save and by the Setup wizard before kicking
    off the OAuth flow. Persists `last_validated_at` on success.
    """
    log = get_logger("integrations.composio")
    settings = load_settings()
    if not get_composio_key():
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="composio_api_key_missing",
        )
    try:
        client = build_client(settings)
        client.ping()
    except NotConfiguredError as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    except IntegrationError as exc:
        log.warning("composio_ping_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    now = datetime.now(UTC).isoformat()
    settings.composio.last_validated_at = now
    save_settings(settings)
    log.info("composio_ping_ok")
    return PingResult(ok=True, validated_at=now)
