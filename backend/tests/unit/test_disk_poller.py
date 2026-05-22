"""Unit tests for the disk_poller background task.

Tests operate on _poll_once() to avoid the infinite-loop / timeout issues
that come with testing start_disk_poller() directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fly_backend.disk_poller import _poll_once, set_card_callback


@pytest.mark.asyncio
async def test_poll_fires_callback_for_new_volume(tmp_path: Path) -> None:
    calls: list[tuple[Path, str | None]] = []

    async def _cb(mount: Path, label: str | None) -> None:
        calls.append((mount, label))

    set_card_callback(_cb)

    vol = tmp_path / "CARD"
    vol.mkdir()

    from unittest.mock import patch

    async def _fake_mounts() -> set[Path]:
        return {vol}

    with patch("fly_backend.disk_poller._get_removable_mounts", _fake_mounts):
        new_seen = await _poll_once(set())  # vol not in seen → new

    assert len(calls) == 1
    assert calls[0][0] == vol
    assert calls[0][1] == vol.name
    assert new_seen == {vol}


@pytest.mark.asyncio
async def test_poll_does_not_fire_for_known_volume(tmp_path: Path) -> None:
    calls: list[Path] = []

    async def _cb(mount: Path, label: str | None) -> None:
        calls.append(mount)

    set_card_callback(_cb)

    vol = tmp_path / "EXISTING"
    vol.mkdir()

    from unittest.mock import patch

    async def _fake_mounts() -> set[Path]:
        return {vol}

    with patch("fly_backend.disk_poller._get_removable_mounts", _fake_mounts):
        await _poll_once({vol})  # vol already in seen

    assert calls == []


@pytest.mark.asyncio
async def test_poll_re_detects_after_eject(tmp_path: Path) -> None:
    calls: list[Path] = []

    async def _cb(mount: Path, label: str | None) -> None:
        calls.append(mount)

    set_card_callback(_cb)

    vol = tmp_path / "CARD"
    vol.mkdir()

    from unittest.mock import patch

    # Step 1: vol known, then ejected
    async def _mounts_empty() -> set[Path]:
        return set()

    with patch("fly_backend.disk_poller._get_removable_mounts", _mounts_empty):
        seen = await _poll_once({vol})  # vol disappears from current → seen = {}

    assert calls == []
    assert seen == set()

    # Step 2: vol re-inserted
    async def _mounts_with_vol() -> set[Path]:
        return {vol}

    with patch("fly_backend.disk_poller._get_removable_mounts", _mounts_with_vol):
        await _poll_once(seen)  # vol is new again

    assert len(calls) == 1
    assert calls[0] == vol


@pytest.mark.asyncio
async def test_poll_handles_callback_exception_gracefully(tmp_path: Path) -> None:
    async def _bad_cb(mount: Path, label: str | None) -> None:
        raise RuntimeError("boom")

    set_card_callback(_bad_cb)

    vol = tmp_path / "CARD"
    vol.mkdir()

    from unittest.mock import patch

    async def _fake_mounts() -> set[Path]:
        return {vol}

    with patch("fly_backend.disk_poller._get_removable_mounts", _fake_mounts):
        # Should not raise
        new_seen = await _poll_once(set())

    assert new_seen == {vol}  # seen is still updated despite callback error
