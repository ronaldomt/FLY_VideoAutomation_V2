"""HTTP surface for Composio key management.

Covers the side-effect contracts the Settings UI relies on:
- PUT /integrations/composio/key persists key in keychain + auth_config_id in
  settings, and clears connection_id (re-auth on rotation per the design
  decision).
- DELETE /integrations/composio/key wipes both the keychain and the settings
  flags.
- POST /integrations/composio/ping calls the SDK; failures don't persist
  `last_validated_at`.
"""

from __future__ import annotations

from typing import Any

import pytest

from fly_backend.errors import IntegrationError
from fly_backend.integrations import composio_client as cc
from fly_backend.secrets import get_composio_key
from fly_backend.settings import load_settings, save_settings


@pytest.fixture
def good_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Composio client factory that always succeeds. Avoids the real SDK."""

    class _Good:
        def __init__(self, _cfg: cc.ComposioConfig) -> None:
            pass

        def ping(self) -> None:
            return None

    monkeypatch.setattr(cc, "_factory", _Good)
    return _Good


@pytest.fixture
def bad_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    class _Bad:
        def __init__(self, _cfg: cc.ComposioConfig) -> None:
            pass

        def ping(self) -> None:
            raise IntegrationError("composio_ping_failed: 401 invalid_api_key")

    monkeypatch.setattr(cc, "_factory", _Bad)
    return _Bad


def test_status_starts_empty(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/integrations/composio/status")
    assert r.status_code == 200
    body = r.json()
    assert body["api_key_set"] is False
    assert body["auth_config_id"] is None
    assert body["google_connected"] is False


def test_put_key_persists_to_keychain_and_settings(client) -> None:  # type: ignore[no-untyped-def]
    r = client.put(
        "/integrations/composio/key",
        json={"api_key": "ck_test_1234567890", "auth_config_id": "ac_abcd1234"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["api_key_set"] is True
    assert body["auth_config_id"] == "ac_abcd1234"
    assert body["last_validated_at"] is None  # ping not called yet
    # Side effects:
    assert get_composio_key() == "ck_test_1234567890"
    on_disk = load_settings()
    assert on_disk.composio.api_key_set is True
    assert on_disk.composio.auth_config_id == "ac_abcd1234"


def test_put_key_rejects_short_key(client) -> None:  # type: ignore[no-untyped-def]
    r = client.put(
        "/integrations/composio/key",
        json={"api_key": "short", "auth_config_id": "ac_abcd1234"},
    )
    assert r.status_code == 422


def test_put_key_resets_connection_on_rotation(client) -> None:  # type: ignore[no-untyped-def]
    """Per the design decision: re-auth on every key change."""
    # Seed an existing connection.
    s = load_settings()
    s.composio.api_key_set = True
    s.composio.connection_id = "conn_old_123"
    s.composio.last_validated_at = "2026-05-21T12:00:00+00:00"
    save_settings(s)

    r = client.put(
        "/integrations/composio/key",
        json={"api_key": "ck_new_1234567890", "auth_config_id": "ac_new"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["connection_id"] is None
    assert body["google_connected"] is False
    assert body["last_validated_at"] is None


def test_delete_key_wipes_everything(client) -> None:  # type: ignore[no-untyped-def]
    # Set first.
    client.put(
        "/integrations/composio/key",
        json={"api_key": "ck_to_wipe_1234", "auth_config_id": "ac_x"},
    )
    r = client.delete("/integrations/composio/key")
    assert r.status_code == 200
    body = r.json()
    assert body["api_key_set"] is False
    assert body["connection_id"] is None
    assert get_composio_key() is None


def test_ping_without_key_returns_412(client) -> None:  # type: ignore[no-untyped-def]
    r = client.post("/integrations/composio/ping")
    assert r.status_code == 412
    assert r.json() == {"detail": "composio_api_key_missing"}


def test_ping_without_auth_config_returns_412(client, good_client) -> None:  # type: ignore[no-untyped-def]
    # Key present, auth_config_id not.
    from fly_backend.secrets import set_composio_key

    set_composio_key("ck_present_1234")
    s = load_settings()
    s.composio.api_key_set = True
    s.composio.auth_config_id = None
    save_settings(s)

    r = client.post("/integrations/composio/ping")
    assert r.status_code == 412
    assert r.json()["detail"] == "composio_auth_config_id_missing"


def test_ping_success_persists_validated_at(client, good_client) -> None:  # type: ignore[no-untyped-def]
    client.put(
        "/integrations/composio/key",
        json={"api_key": "ck_good_1234567890", "auth_config_id": "ac_good"},
    )
    r = client.post("/integrations/composio/ping")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["validated_at"]
    # last_validated_at now present in status.
    status_body = client.get("/integrations/composio/status").json()
    assert status_body["last_validated_at"] == body["validated_at"]


def test_ping_failure_does_not_persist_validated_at(client, bad_client) -> None:  # type: ignore[no-untyped-def]
    client.put(
        "/integrations/composio/key",
        json={"api_key": "ck_bad_1234567890", "auth_config_id": "ac_bad"},
    )
    r = client.post("/integrations/composio/ping")
    assert r.status_code == 502
    assert "composio_ping_failed" in r.json()["detail"]
    # Nothing persisted.
    on_disk = load_settings()
    assert on_disk.composio.last_validated_at is None
