"""copy_media — card → local archive.

Idempotent: rerunning a session skips files whose `size + md5` already match.
Streams ProgressEvent. See CLAUDE.md §8, §15.
"""

from __future__ import annotations

from pydantic import BaseModel


class CopyMediaInput(BaseModel):
    session_id: str
