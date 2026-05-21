"""Sidecar runtime state: port + per-launch shared secret.

The Rust shell reads the file written by `write_runtime_file()` to learn which
port to call and which token to send in the `X-Sidecar-Token` header. The
frontend reads the same file at startup.

See CLAUDE.md §10.
"""

from __future__ import annotations

import contextlib
import json
import secrets
import socket
from pathlib import Path
from typing import Final

RUNTIME_DIR: Final[Path] = Path.home() / ".fly-video-automation"
RUNTIME_FILE: Final[Path] = RUNTIME_DIR / "sidecar.port"


def find_free_port() -> int:
    """Bind a socket to port 0 to let the OS pick a free port, then release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def generate_token() -> str:
    """Per-launch shared secret. 32 bytes of entropy, URL-safe."""
    return secrets.token_urlsafe(32)


def write_runtime_file(port: int, token: str) -> Path:
    """Atomically write the runtime file the frontend + Rust shell read."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"port": port, "token": token}, indent=2)
    tmp = RUNTIME_FILE.with_suffix(".port.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(RUNTIME_FILE)
    # Windows / restricted FS may not honour chmod — best-effort only.
    with contextlib.suppress(OSError):
        RUNTIME_FILE.chmod(0o600)
    return RUNTIME_FILE


def clear_runtime_file() -> None:
    """Delete the runtime file. Called on graceful shutdown."""
    with contextlib.suppress(FileNotFoundError):
        RUNTIME_FILE.unlink()
