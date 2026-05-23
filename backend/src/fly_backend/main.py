"""FastAPI sidecar entrypoint.

Two run modes:
- `uvicorn fly_backend.main:app --reload` for dev (fixed port).
- `python -m fly_backend.main` (or the PyInstaller binary) — picks a random
  free port, writes runtime file, and serves until killed by Tauri.

See CLAUDE.md §5, §10.
"""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .errors import (
    BehaviorError,
    FlyBackendError,
    IntegrationError,
    NotConfiguredError,
    VerificationError,
)
from .http.auth import SidecarAuth
from .http.routes import router
from .logging import configure_logging, get_logger
from .runtime import (
    clear_runtime_file,
    find_free_port,
    generate_token,
    write_runtime_file,
)

LOG_LEVEL = os.environ.get("FLY_LOG_LEVEL", "INFO")
RUN_TOKEN = os.environ.get("FLY_SIDECAR_TOKEN", "") or generate_token()
WRITE_RUNTIME_FILE = os.environ.get("FLY_WRITE_RUNTIME_FILE", "1") != "0"

# macOS default soft limit is 256; raise it to handle concurrent ffmpeg + uploads + SSE.
try:
    import resource as _resource
    _soft, _hard = _resource.getrlimit(_resource.RLIMIT_NOFILE)
    _resource.setrlimit(_resource.RLIMIT_NOFILE, (min(_hard, 4096), _hard))
except Exception:
    pass


async def _recover_composio_connection(log: object) -> None:
    """At startup, if the API key is set but connection_id is null, query Composio
    for the most recent ACTIVE connection for this install and write it to settings.
    Runs once per process start; failures are logged and swallowed."""
    import httpx

    from .secrets import get_composio_key
    from .settings import load_settings, save_settings

    settings = load_settings()
    if not settings.composio.api_key_set or settings.composio.connection_id:
        return  # Nothing to do
    api_key = get_composio_key()
    if not api_key:
        return
    user_id = settings.composio.user_id
    if not user_id:
        return
    try:
        _V1 = "https://backend.composio.dev/api/v1"
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(
                f"{_V1}/connectedAccounts",
                headers={"x-api-key": api_key},
                params={"user_uuid": user_id, "pageSize": 50},
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
        active = [i for i in items if i.get("status") == "ACTIVE"]
        if not active:
            getattr(log, "warning", print)("composio_startup_recovery_no_active_connections")
            return
        active.sort(key=lambda i: i.get("updatedAt", ""), reverse=True)
        recovered_id = str(active[0]["id"])
        settings.composio.connection_id = recovered_id
        save_settings(settings)
        getattr(log, "info", print)("composio_startup_recovery_ok", connection_id=recovered_id)
    except Exception as exc:
        getattr(log, "warning", print)("composio_startup_recovery_failed", error=str(exc))


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging(LOG_LEVEL)
    log = get_logger("fly_backend.lifespan")
    log.info("sidecar_starting", token_set=bool(RUN_TOKEN))

    from .behaviors.detect_card.contract import DetectCardInput
    from .behaviors.detect_card.handler import run as _detect_card
    from .context import build_default_context
    from .disk_poller import set_card_callback, start_disk_poller
    from .http.routes import _set_last_card

    async def _on_card(mount: object, label: str | None) -> None:
        from pathlib import Path
        mount_path = Path(str(mount))
        payload = DetectCardInput(
            mount_path=mount_path,
            volume_id=str(mount_path),
            label=label,
        )
        ctx = build_default_context()
        detected = await _detect_card(payload, ctx)
        _set_last_card(detected.model_dump(mode="json"))

    set_card_callback(_on_card)
    poller_task = asyncio.create_task(start_disk_poller())

    # Auto-recover Composio connection_id at startup when the API key is present
    # but connection_id is null (e.g. after key rotation). This makes startup
    # self-healing without requiring a UI action from the operator.
    asyncio.create_task(_recover_composio_connection(log))

    try:
        yield
    finally:
        poller_task.cancel()
        log.info("sidecar_stopping")
        clear_runtime_file()


def create_app() -> FastAPI:
    app = FastAPI(
        title="FLY Video Automation Sidecar",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Only localhost ever talks to us, but the Tauri webview's origin is
    # tauri://localhost on macOS / https://tauri.localhost on Windows.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "tauri://localhost",
            "https://tauri.localhost",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    auth = SidecarAuth(RUN_TOKEN)

    @app.middleware("http")
    async def _auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        from fastapi import HTTPException

        try:
            auth.verify(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)

    err_log = get_logger("fly_backend.errors")

    @app.exception_handler(NotConfiguredError)
    async def _handle_not_configured(req: Request, exc: NotConfiguredError) -> JSONResponse:
        err_log.warning("not_configured", path=req.url.path, error=str(exc))
        return JSONResponse(status_code=412, content={"error": str(exc)})

    @app.exception_handler(VerificationError)
    async def _handle_verification(req: Request, exc: VerificationError) -> JSONResponse:
        err_log.warning("verification_failed", path=req.url.path, error=str(exc))
        return JSONResponse(status_code=409, content={"error": str(exc)})

    @app.exception_handler(IntegrationError)
    async def _handle_integration(req: Request, exc: IntegrationError) -> JSONResponse:
        err_log.error("integration_error", path=req.url.path, error=str(exc))
        return JSONResponse(status_code=502, content={"error": str(exc)})

    @app.exception_handler(BehaviorError)
    async def _handle_behavior(req: Request, exc: BehaviorError) -> JSONResponse:
        err_log.warning("behavior_error", path=req.url.path, error=str(exc))
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(FlyBackendError)
    async def _handle_generic(req: Request, exc: FlyBackendError) -> JSONResponse:
        err_log.error("generic_backend_error", path=req.url.path, error=str(exc))
        return JSONResponse(status_code=500, content={"error": str(exc)})

    app.include_router(router)
    return app


app = create_app()


def run() -> None:
    """Production sidecar entry — picks a free port, writes the runtime file."""
    configure_logging(LOG_LEVEL)
    log = get_logger("fly_backend.main")

    port = int(os.environ.get("FLY_SIDECAR_PORT", "0")) or find_free_port()
    if WRITE_RUNTIME_FILE:
        path = write_runtime_file(port, RUN_TOKEN)
        log.info("sidecar_runtime_file_written", path=str(path), port=port)

    def _graceful(*_args: object) -> None:
        clear_runtime_file()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _graceful)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _graceful)

    uvicorn.run(
        "fly_backend.main:app",
        host="127.0.0.1",
        port=port,
        log_level=LOG_LEVEL.lower(),
        reload=False,
    )


if __name__ == "__main__":
    run()
