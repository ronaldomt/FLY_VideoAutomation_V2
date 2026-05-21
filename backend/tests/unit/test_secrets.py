"""Keychain helpers.

These tests run against the in-memory backend installed by `conftest._isolate_keychain`
— the real OS keychain is never touched."""

from __future__ import annotations

import pytest

from fly_backend.secrets import (
    clear_composio_key,
    get_composio_key,
    set_composio_key,
)


def test_set_then_get_round_trip() -> None:
    assert get_composio_key() is None
    set_composio_key("ck_live_example_1234567890")
    assert get_composio_key() == "ck_live_example_1234567890"


def test_set_strips_whitespace() -> None:
    set_composio_key("   ck_padded   ")
    assert get_composio_key() == "ck_padded"


def test_rejects_empty_key() -> None:
    with pytest.raises(ValueError, match="composio_api_key_empty"):
        set_composio_key("")
    with pytest.raises(ValueError, match="composio_api_key_empty"):
        set_composio_key("   ")


def test_clear_is_idempotent_when_absent() -> None:
    # No key set — must not raise.
    clear_composio_key()
    assert get_composio_key() is None


def test_clear_removes_existing_key() -> None:
    set_composio_key("ck_to_be_wiped")
    clear_composio_key()
    assert get_composio_key() is None
