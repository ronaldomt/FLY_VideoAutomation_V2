"""make_share_link — Drive share URL + parsed phone (if any).

The frontend uses these to drop the URL on the clipboard and (optionally) open
`wa.me/<phone>?text=<url>` per CLAUDE.md §3 step 6.
"""

from __future__ import annotations

from pydantic import BaseModel


class MakeShareLinkInput(BaseModel):
    session_id: str


class ShareLink(BaseModel):
    url: str
    phone: str | None = None
    whatsapp_url: str | None = None
