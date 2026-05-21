"""Tests for POST /setup/composio/start and POST /setup/composio/complete.

All Composio SDK calls are mocked — no real account or network needed.
Uses the shared `client` fixture (conftest) which injects the sidecar token and
isolates settings to a tmp_path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fly_backend.secrets import set_composio_key
from fly_backend.settings import Settings, save_settings

# ── helpers ──────────────────────────────────────────────────────────────────

def _fake_connection_request(
    redirect_url: str | None = "https://composio.dev/oauth?state=xyz",
    connection_id: str = "conn_abc",
) -> MagicMock:
    m = MagicMock()
    m.redirectUrl = redirect_url
    m.connectedAccountId = connection_id
    return m


def _fake_account(status: str = "ACTIVE") -> MagicMock:
    m = MagicMock()
    m.status = status
    return m


def _seed_full_config(settings_path: Path) -> None:
    """Put a valid API key in keychain + auth_config_id + user_id in settings."""
    set_composio_key("ck_live_test_key_1234567890")
    s = Settings()
    s.composio.api_key_set = True
    s.composio.auth_config_id = "ac_test_1234"
    s.composio.user_id = "fly-abcdef123456"
    save_settings(s)


# ── /setup/composio/start ────────────────────────────────────────────────────

def test_start_requires_api_key(client, settings_path: Path) -> None:
    # Keychain empty, no api_key_set
    r = client.post("/setup/composio/start")
    assert r.status_code == 412
    assert "composio_api_key_missing" in r.json()["detail"]


def test_start_requires_auth_config_id(client, settings_path: Path) -> None:
    set_composio_key("ck_live_test_key_1234567890")
    s = Settings()
    s.composio.api_key_set = True
    # auth_config_id is NOT set
    save_settings(s)

    r = client.post("/setup/composio/start")
    assert r.status_code == 412
    assert "composio_auth_config_id_missing" in r.json()["detail"]


def test_start_returns_auth_url(client, settings_path: Path) -> None:
    _seed_full_config(settings_path)
    fake_req = _fake_connection_request(
        redirect_url="https://composio.dev/oauth?state=xyz",
        connection_id="conn_123",
    )
    mock_ts = MagicMock()
    mock_ts.initiate_connection.return_value = fake_req

    with patch("composio.ComposioToolSet", return_value=mock_ts):
        r = client.post("/setup/composio/start")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["auth_url"] == "https://composio.dev/oauth?state=xyz"
    assert body["connection_request_id"] == "conn_123"


def test_start_raises_502_when_sdk_fails(client, settings_path: Path) -> None:
    _seed_full_config(settings_path)
    mock_ts = MagicMock()
    mock_ts.initiate_connection.side_effect = RuntimeError("composio down")

    with patch("composio.ComposioToolSet", return_value=mock_ts):
        r = client.post("/setup/composio/start")

    assert r.status_code == 502
    assert "composio_oauth_initiate_failed" in r.json()["detail"]


def test_start_raises_502_when_no_redirect_url(client, settings_path: Path) -> None:
    _seed_full_config(settings_path)
    fake_req = _fake_connection_request(redirect_url=None)
    mock_ts = MagicMock()
    mock_ts.initiate_connection.return_value = fake_req

    with patch("composio.ComposioToolSet", return_value=mock_ts):
        r = client.post("/setup/composio/start")

    assert r.status_code == 502
    assert "composio_no_redirect_url" in r.json()["detail"]


# ── /setup/composio/complete ─────────────────────────────────────────────────

def test_complete_stores_connection_id(client, settings_path: Path) -> None:
    _seed_full_config(settings_path)
    mock_ts = MagicMock()
    mock_ts.get_connected_account.return_value = _fake_account("ACTIVE")

    with patch("composio.ComposioToolSet", return_value=mock_ts):
        r = client.post(
            "/setup/composio/complete",
            json={"connection_request_id": "conn_stored_123"},
        )

    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    from fly_backend.settings import load_settings

    s = load_settings()
    assert s.composio.connection_id == "conn_stored_123"
    assert s.composio.google_connected is True


def test_complete_rejects_inactive_connection(client, settings_path: Path) -> None:
    _seed_full_config(settings_path)
    mock_ts = MagicMock()
    mock_ts.get_connected_account.return_value = _fake_account("INITIATED")

    with patch("composio.ComposioToolSet", return_value=mock_ts):
        r = client.post(
            "/setup/composio/complete",
            json={"connection_request_id": "conn_pending"},
        )

    assert r.status_code == 409
    assert "connection_not_yet_active" in r.json()["detail"]


def test_complete_raises_502_when_sdk_fails(client, settings_path: Path) -> None:
    _seed_full_config(settings_path)
    mock_ts = MagicMock()
    mock_ts.get_connected_account.side_effect = RuntimeError("network error")

    with patch("composio.ComposioToolSet", return_value=mock_ts):
        r = client.post(
            "/setup/composio/complete",
            json={"connection_request_id": "conn_fail"},
        )

    assert r.status_code == 502
    assert "composio_connection_check_failed" in r.json()["detail"]


def test_complete_requires_api_key(client, settings_path: Path) -> None:
    # No key set in this settings_path
    r = client.post("/setup/composio/complete", json={"connection_request_id": "conn_x"})
    assert r.status_code == 412
    assert "composio_api_key_missing" in r.json()["detail"]
