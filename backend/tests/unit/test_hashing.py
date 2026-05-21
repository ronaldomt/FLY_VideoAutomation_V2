"""md5 chunked hashing matches single-shot hashlib."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fly_backend.util.hashing import md5_file


def test_md5_file_matches_hashlib(tmp_path: Path) -> None:
    data = b"a" * (2 * 1024 * 1024 + 13)  # > one chunk
    p = tmp_path / "blob.bin"
    p.write_bytes(data)
    assert md5_file(p) == hashlib.md5(data).hexdigest()


def test_md5_file_empty(tmp_path: Path) -> None:
    p = tmp_path / "empty.bin"
    p.write_bytes(b"")
    assert md5_file(p) == "d41d8cd98f00b204e9800998ecf8427e"
