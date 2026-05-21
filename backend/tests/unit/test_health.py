"""/health is the only unauthenticated endpoint."""

from __future__ import annotations


def test_health_returns_ok_and_version(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/health", headers={})  # no token — must still work
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["version"], str)


def test_protected_endpoint_requires_token(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/settings", headers={"X-Sidecar-Token": "wrong"})
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid_sidecar_token"}


def test_protected_endpoint_with_token(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/settings")  # client fixture preloads the correct token
    assert r.status_code == 200
    body = r.json()
    # Schema sanity-check — full coverage lives in test_settings.py.
    assert "extraction" in body
    assert body["calendar_id"] == "primary"
