"""Disk-space pre-checks. See CLAUDE.md §16 (Definition of Done)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class DiskCheck:
    ok: bool
    free_bytes: int
    required_bytes: int
    shortfall_bytes: int


def check_free_space(destination: Path, required_bytes: int, safety_pct: float = 0.10) -> DiskCheck:
    """Compare free space on `destination`'s volume to `required_bytes`.

    `safety_pct` reserves headroom (default 10%) on top of the estimate. The
    caller is responsible for surfacing `DiskCheck.ok == False` to the operator
    before any bytes are copied.
    """
    destination.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(destination)
    needed = int(required_bytes * (1 + safety_pct))
    shortfall = max(0, needed - usage.free)
    return DiskCheck(
        ok=usage.free >= needed,
        free_bytes=usage.free,
        required_bytes=needed,
        shortfall_bytes=shortfall,
    )


def estimate_card_size(mount_path: Path, video_exts: list[str], photo_exts: list[str]) -> int:
    """Sum sizes of files matching the configured extensions. Estimate only —
    frame-extraction output is added separately by the caller."""
    total = 0
    if not mount_path.exists():
        return 0
    exts = {e.lower() for e in (*video_exts, *photo_exts)}
    for p in mount_path.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            try:
                total += p.stat().st_size
            except OSError:
                continue
    return total
