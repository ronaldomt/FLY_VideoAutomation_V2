"""HTTP endpoints. Thin layer over behaviors.

See CLAUDE.md §10 for the full endpoint catalog. v0 ships /health + /settings;
behavior-backed routes are wired as behaviors land.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, status

from .. import __version__
from ..errors import NotConfiguredError
from ..settings import Settings, load_settings, save_settings

if TYPE_CHECKING:
    pass

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "version": __version__}


@router.get("/settings", response_model=Settings)
async def get_settings() -> Settings:
    return load_settings()


@router.put("/settings", response_model=Settings)
async def put_settings(incoming: Settings) -> Settings:
    save_settings(incoming)
    return incoming


@router.get("/setup/status")
async def setup_status() -> dict[str, bool]:
    s = load_settings()
    return {
        "composio_connected": s.composio.api_key_set and s.composio.google_connected,
        "calendar_id_set": bool(s.calendar_id),
        "local_root_set": bool(s.local_root),
    }


# Stub: real OAuth handoff lands once the Composio integration is wired (Task #7).
@router.post("/setup/composio/start")
async def setup_composio_start() -> dict[str, str]:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="composio_not_yet_wired",
    )


@router.post("/setup/composio/complete")
async def setup_composio_complete() -> dict[str, bool]:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="composio_not_yet_wired",
    )


@router.get("/customers/today")
async def customers_today() -> list[dict[str, object]]:
    # Wired in Task #3 once list_today_customers behavior lands.
    s = load_settings()
    if not s.composio.api_key_set:
        raise NotConfiguredError("composio_api_key_missing")
    return []
