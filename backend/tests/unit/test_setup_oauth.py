"""Tests for POST /setup/composio/start and POST /setup/composio/complete.

All external HTTP calls (Composio v3 API) are mocked — no real network needed.
Uses the shared `client` fixture (conftest) which injects the sidecar token and
isolates settings to a tmp_path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fly_backend.secrets import set_composio_key
from fly_backend.settings import Settings, save_settings

# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_httpx_client(post_json: dict | None = None, get_json: dict | None = None,
                        post_status: int = 201, get_status: int = 200,
                        post_raises: Exception | None = None,
                        get_raises: Exception | None = None):
    """Build an async context-manager mock for httpx.AsyncClient."""
    import httpx

    mock_client = AsyncMock()

    if post_raises:
        mock_client.post = AsyncMock(side_effect=post_raises)
    else:
        post_resp = MagicMock()
        post_resp.json.return_value = post_json or {}
        post_resp.raise_for_status = MagicMock()
        if post_status >= 400:
            post_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error", request=MagicMock(), response=MagicMock(text=str(post_json))
            )
        mock_client.post = AsyncMock(return_value=post_resp)

    if get_raises:
        mock_client.get = AsyncMock(side_effect=get_raises)
    else:
        get_resp = MagicMock()
        get_resp.json.return_value = get_json or {}
        get_resp.raise_for_status = MagicMock()
        if get_status >= 400:
            get_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error", request=MagicMock(), response=MagicMock(text=str(get_json))
            )
        mock_client.get = AsyncMock(return_value=get_resp)

    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


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
    r = client.post("/setup/composio/start")
    assert r.status_code == 412
    assert "composio_api_key_missing" in r.json()["detail"]


def test_start_requires_auth_config_id(client, settings_path: Path) -> None:
    set_composio_key("ck_live_test_key_1234567890")
    s = Settings()
    s.composio.api_key_set = True
    # auth_config_id NOT set
    save_settings(s)

    r = client.post("/setup/composio/start")
    assert r.status_code == 412
    assert "composio_auth_config_id_missing" in r.json()["detail"]


def test_start_returns_auth_url(client, settings_path: Path) -> None:
    _seed_full_config(settings_path)
    mock_http = _mock_httpx_client(
        post_json={"redirect_url": "https://connect.composio.dev/link/lk_abc", "connected_account_id": "ca_conn_123"},
    )
    with patch("httpx.AsyncClient", return_value=mock_http):
        r = client.post("/setup/composio/start")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["auth_url"] == "https://connect.composio.dev/link/lk_abc"
    assert body["connection_request_id"] == "ca_conn_123"


def test_start_raises_502_when_api_fails(client, settings_path: Path) -> None:
    import httpx
    _seed_full_config(settings_path)
    mock_http = _mock_httpx_client(
        post_raises=httpx.HTTPStatusError(
            "bad request",
            request=MagicMock(),
            response=MagicMock(text='{"error":"Auth config not found"}'),
        )
    )
    with patch("httpx.AsyncClient", return_value=mock_http):
        r = client.post("/setup/composio/start")

    assert r.status_code == 502
    assert "composio_oauth_initiate_failed" in r.json()["detail"]


def test_start_raises_502_when_no_redirect_url(client, settings_path: Path) -> None:
    _seed_full_config(settings_path)
    mock_http = _mock_httpx_client(post_json={"connected_account_id": "ca_conn_456"})
    with patch("httpx.AsyncClient", return_value=mock_http):
        r = client.post("/setup/composio/start")

    assert r.status_code == 502
    assert "composio_no_redirect_url" in r.json()["detail"]


def test_start_raises_502_on_network_error(client, settings_path: Path) -> None:
    import httpx
    _seed_full_config(settings_path)
    mock_http = _mock_httpx_client(post_raises=httpx.ConnectError("timeout"))
    with patch("httpx.AsyncClient", return_value=mock_http):
        r = client.post("/setup/composio/start")

    assert r.status_code == 502
    assert "composio_oauth_initiate_failed" in r.json()["detail"]


# ── /setup/composio/complete ─────────────────────────────────────────────────

def test_complete_stores_connection_id(client, settings_path: Path) -> None:
    _seed_full_config(settings_path)
    mock_http = _mock_httpx_client(get_json={"status": "ACTIVE", "id": "ca_conn_stored_123"})

    with patch("httpx.AsyncClient", return_value=mock_http):
        r = client.post(
            "/setup/composio/complete",
            json={"connection_request_id": "ca_conn_stored_123"},
        )

    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    from fly_backend.settings import load_settings
    s = load_settings()
    assert s.composio.connection_id == "ca_conn_stored_123"
    assert s.composio.google_connected is True


def test_complete_rejects_inactive_connection(client, settings_path: Path) -> None:
    _seed_full_config(settings_path)
    mock_http = _mock_httpx_client(get_json={"status": "INITIALIZING"})

    with patch("httpx.AsyncClient", return_value=mock_http):
        r = client.post(
            "/setup/composio/complete",
            json={"connection_request_id": "ca_conn_pending"},
        )

    assert r.status_code == 409
    assert "connection_not_yet_active" in r.json()["detail"]


def test_complete_raises_502_when_api_fails(client, settings_path: Path) -> None:
    import httpx
    _seed_full_config(settings_path)
    mock_http = _mock_httpx_client(
        get_raises=httpx.ConnectError("network error")
    )

    with patch("httpx.AsyncClient", return_value=mock_http):
        r = client.post(
            "/setup/composio/complete",
            json={"connection_request_id": "ca_conn_fail"},
        )

    assert r.status_code == 502
    assert "composio_connection_check_failed" in r.json()["detail"]


def test_complete_requires_api_key(client, settings_path: Path) -> None:
    # No key set in this settings_path
    r = client.post("/setup/composio/complete", json={"connection_request_id": "ca_conn_x"})
    assert r.status_code == 412
    assert "composio_api_key_missing" in r.json()["detail"]
