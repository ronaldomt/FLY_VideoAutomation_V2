"""Disk free-space check. See CLAUDE.md §16."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from fly_backend.util.disk import check_free_space, estimate_card_size


def test_check_free_space_ok_when_large_dest(tmp_path: Path) -> None:
    result = check_free_space(tmp_path, required_bytes=1)
    assert result.ok is True
    assert result.shortfall_bytes == 0


def test_check_free_space_fails_when_required_exceeds_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeUsage:
        total = 100
        used = 50
        free = 50

    monkeypatch.setattr(shutil, "disk_usage", lambda _p: FakeUsage())  # type: ignore[arg-type]
    result = check_free_space(tmp_path, required_bytes=1000)
    assert result.ok is False
    assert result.shortfall_bytes > 0


def test_estimate_card_size_sums_matching_files(tmp_path: Path) -> None:
    (tmp_path / "DCIM").mkdir()
    (tmp_path / "DCIM" / "a.MP4").write_bytes(b"x" * 100)
    (tmp_path / "DCIM" / "b.jpg").write_bytes(b"y" * 50)
    (tmp_path / "DCIM" / "ignore.txt").write_bytes(b"z" * 10)
    total = estimate_card_size(tmp_path, [".mp4", ".mov"], [".jpg", ".jpeg"])
    assert total == 150
