"""Shared pytest fixtures.

We override the per-launch sidecar token before importing the app so tests can
hit protected endpoints deterministically.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("FLY_SIDECAR_TOKEN", "test-token")
os.environ.setdefault("FLY_WRITE_RUNTIME_FILE", "0")
os.environ.setdefault("COMPOSIO_LIVE", "0")


@pytest.fixture
def settings_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate settings/runtime files to tmp_path so tests don't leak to $HOME."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # Re-derive the module-level constants that captured Path.home() at import.
    from fly_backend import logging as logging_mod
    from fly_backend import runtime as runtime_mod
    from fly_backend import settings as settings_mod
    from fly_backend.persistence import db as db_mod

    monkeypatch.setattr(settings_mod, "SETTINGS_DIR", home / ".fly-video-automation")
    monkeypatch.setattr(
        settings_mod, "SETTINGS_FILE", home / ".fly-video-automation" / "settings.json"
    )
    monkeypatch.setattr(runtime_mod, "RUNTIME_DIR", home / ".fly-video-automation")
    monkeypatch.setattr(
        runtime_mod, "RUNTIME_FILE", home / ".fly-video-automation" / "sidecar.port"
    )
    monkeypatch.setattr(logging_mod, "LOG_DIR", home / ".fly-video-automation" / "logs")
    monkeypatch.setattr(
        db_mod, "DEFAULT_DB_PATH", home / ".fly-video-automation" / "queue.sqlite"
    )
    return home / ".fly-video-automation" / "settings.json"


@pytest.fixture
def client(settings_path: Path) -> Iterator:  # type: ignore[type-arg]
    """FastAPI TestClient with the per-launch token preset."""
    from fastapi.testclient import TestClient

    from fly_backend.main import create_app

    app = create_app()
    with TestClient(app, headers={"X-Sidecar-Token": "test-token"}) as c:
        yield c
