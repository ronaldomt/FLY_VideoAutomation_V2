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

    @app.exception_handler(NotConfiguredError)
    async def _handle_not_configured(_req: Request, exc: NotConfiguredError) -> JSONResponse:
        return JSONResponse(status_code=412, content={"error": str(exc)})

    @app.exception_handler(VerificationError)
    async def _handle_verification(_req: Request, exc: VerificationError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": str(exc)})

    @app.exception_handler(IntegrationError)
    async def _handle_integration(_req: Request, exc: IntegrationError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"error": str(exc)})

    @app.exception_handler(BehaviorError)
    async def _handle_behavior(_req: Request, exc: BehaviorError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(FlyBackendError)
    async def _handle_generic(_req: Request, exc: FlyBackendError) -> JSONResponse:
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
