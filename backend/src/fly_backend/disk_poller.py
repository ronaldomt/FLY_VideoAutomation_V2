"""Python-based disk poller for removable media detection.

Runs as a background asyncio task. Complements the Rust disk_watcher for
cases where sysinfo::is_removable() returns False for built-in SD card slots
(common on Apple Silicon Macs where the reader is at Device Location: Internal).

macOS: iterates /Volumes/ and calls `diskutil info -plist` for each directory.
       A volume is considered removable when RemovableMedia or Ejectable is True.
Windows: checks GetDriveTypeW for DRIVE_REMOVABLE (type 2).
Linux: scans /proc/mounts for /media/ and /mnt/ entries.

Polls every 2 seconds. Volumes present at startup are added to the initial
seen-set so they don't fire a detection event on app launch.
"""

from __future__ import annotations

import asyncio
import platform
import plistlib
from pathlib import Path

from .logging import get_logger

# Injected at startup by main.py so we don't import the routes module at module
# load time (avoids circular imports during test collection).
_card_callback: object | None = None


def set_card_callback(cb: object) -> None:
    """Register the coroutine function to call when a new card is detected.

    Signature: async def cb(mount: Path, label: str | None) -> None
    """
    global _card_callback
    _card_callback = cb


async def _poll_once(seen: set[Path]) -> set[Path]:
    """Run one poll iteration. Returns the updated seen-set.

    Exposed for testing. Production code calls start_disk_poller().
    """
    log = get_logger("disk_poller")
    current = await _get_removable_mounts()
    new_mounts = current - seen
    for mount in new_mounts:
        label = mount.name or None
        log.info("disk_poller_new_volume", mount=str(mount), label=label)
        if _card_callback is not None:
            try:
                await _card_callback(mount, label)  # type: ignore[operator]
            except Exception as exc:
                log.error("disk_poller_callback_failed", error=str(exc), mount=str(mount))
    return current


async def start_disk_poller() -> None:
    log = get_logger("disk_poller")
    sys_platform = platform.system()
    log.info("disk_poller_starting", platform=sys_platform)

    # Bootstrap the seen-set from currently mounted volumes so we don't fire
    # events for drives that were already present when the app started.
    seen: set[Path] = await _get_removable_mounts()
    log.info("disk_poller_initial_volumes", count=len(seen), volumes=[str(p) for p in seen])

    while True:
        await asyncio.sleep(2)
        try:
            seen = await _poll_once(seen)
        except Exception as exc:
            log.warning("disk_poller_iteration_failed", error=str(exc))


async def _get_removable_mounts() -> set[Path]:
    sys_platform = platform.system()
    if sys_platform == "Darwin":
        return await _macos_removable_mounts()
    if sys_platform == "Windows":
        return _windows_removable_mounts()
    return await _linux_removable_mounts()


async def _macos_removable_mounts() -> set[Path]:
    result: set[Path] = set()
    volumes_dir = Path("/Volumes")
    if not volumes_dir.exists():
        return result

    for vol in volumes_dir.iterdir():
        if not vol.is_dir() or vol.is_symlink():
            continue
        try:
            proc = await asyncio.create_subprocess_exec(
                "diskutil", "info", "-plist", str(vol),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            if not stdout:
                continue
            info = plistlib.loads(stdout)
            if info.get("RemovableMedia") or info.get("Ejectable"):
                result.add(vol)
        except Exception:
            pass
    return result


def _windows_removable_mounts() -> set[Path]:
    result: set[Path] = set()
    try:
        import ctypes
        DRIVE_REMOVABLE = 2
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = Path(f"{letter}:\\")
            dtype = ctypes.windll.kernel32.GetDriveTypeW(str(drive))  # type: ignore[attr-defined]
            if dtype == DRIVE_REMOVABLE and drive.exists():
                result.add(drive)
    except Exception:
        pass
    return result


async def _linux_removable_mounts() -> set[Path]:
    result: set[Path] = set()
    try:
        proc_mounts = Path("/proc/mounts")
        if not proc_mounts.exists():
            return result
        for line in proc_mounts.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2 and ("/media/" in parts[1] or "/mnt/" in parts[1]):
                result.add(Path(parts[1]))
    except Exception:
        pass
    return result
