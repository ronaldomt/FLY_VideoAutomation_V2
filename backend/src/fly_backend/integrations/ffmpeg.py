"""ffmpeg wrapper for frame extraction.

Behaviors use FfmpegClient — they never shell out to ffmpeg directly. Tests
swap in a fake.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from ..errors import IntegrationError


@dataclass(slots=True)
class FrameProgress:
    frame_path: Path
    index: int


class FfmpegClient:
    """Real ffmpeg invocation via subprocess. Falls back to a clear error if
    ffmpeg isn't on PATH."""

    def __init__(self, ffmpeg_bin: str | None = None) -> None:
        self.ffmpeg_bin = ffmpeg_bin or shutil.which("ffmpeg") or "ffmpeg"

    async def extract_frames(
        self,
        video: Path,
        out_dir: Path,
        fps: float,
        jpeg_quality: int = 90,
    ) -> AsyncIterator[FrameProgress]:
        if not shutil.which(self.ffmpeg_bin):
            raise IntegrationError("ffmpeg_not_found_on_path")
        out_dir.mkdir(parents=True, exist_ok=True)
        pattern = out_dir / f"{video.stem}_%06d.jpg"
        # ffmpeg `-q:v` 2..31; lower = better. Map 90% -> 3, 50% -> 12.
        qv = max(2, min(31, round(31 - (jpeg_quality / 100) * 29)))
        cmd = [
            self.ffmpeg_bin,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", str(video),
            "-vf", f"fps={fps}",
            "-q:v", str(qv),
            str(pattern),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise IntegrationError(f"ffmpeg_failed: {stderr.decode(errors='replace')[:500]}")
        # ffmpeg writes the files synchronously; emit progress in one pass.
        for i, p in enumerate(sorted(out_dir.glob(f"{video.stem}_*.jpg"))):
            yield FrameProgress(frame_path=p, index=i)


class FakeFfmpegClient:
    """Test double — writes empty placeholder JPGs at the configured fps."""

    async def extract_frames(
        self,
        video: Path,
        out_dir: Path,
        fps: float,
        jpeg_quality: int = 90,
    ) -> AsyncIterator[FrameProgress]:
        out_dir.mkdir(parents=True, exist_ok=True)
        # 3 fake frames per video, regardless of fps.
        for i in range(3):
            p = out_dir / f"{video.stem}_{i:06d}.jpg"
            p.write_bytes(b"")
            yield FrameProgress(frame_path=p, index=i)
