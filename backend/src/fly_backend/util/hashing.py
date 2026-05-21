"""md5 helpers — matches the checksum Google Drive returns in `md5Checksum`."""

from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK = 1024 * 1024  # 1 MiB


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()
