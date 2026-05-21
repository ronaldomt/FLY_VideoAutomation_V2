"""Runtime file writer + free-port picker."""

from __future__ import annotations

import json
import socket
from pathlib import Path

from fly_backend.runtime import (
    find_free_port,
    generate_token,
    write_runtime_file,
)


def test_find_free_port_returns_usable_port(settings_path: Path) -> None:
    port = find_free_port()
    assert 1024 < port < 65536
    # And we should be able to bind to it (briefly).
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_generate_token_is_url_safe_and_long(settings_path: Path) -> None:
    t = generate_token()
    assert len(t) >= 40
    # URL-safe base64 alphabet only.
    assert all(c.isalnum() or c in "-_" for c in t)


def test_write_runtime_file_writes_atomically(settings_path: Path) -> None:
    from fly_backend.runtime import RUNTIME_FILE

    write_runtime_file(54321, "secret")
    assert RUNTIME_FILE.exists()
    body = json.loads(RUNTIME_FILE.read_text())
    assert body == {"port": 54321, "token": "secret"}
