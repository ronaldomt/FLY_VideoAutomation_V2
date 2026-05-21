"""wipe_card — guarded delete of card contents.

Hard rules (CLAUDE.md §2, §3, §16):
- Off by default in settings (`card_wipe.enabled=False`).
- Explicit `confirm=True` required in the call.
- Verification must have passed (`require_verification=True` in settings).
- Never silent. Operator must explicitly click the button in the UI.
"""

from __future__ import annotations

from pydantic import BaseModel


class WipeCardInput(BaseModel):
    session_id: str
    confirm: bool = False


class WipeResult(BaseModel):
    ok: bool
    deleted: int
    skipped_reason: str | None = None
