"""extract_frames — pull JPGs out of each MP4 in Videos/ → Fotos/.

Default fps lives in settings; can be overridden per session.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractFramesInput(BaseModel):
    session_id: str
    fps: float | None = Field(default=None, gt=0)
