from __future__ import annotations

import re
from urllib.parse import quote

from ...context import Context
from ...errors import BehaviorError
from ...persistence.models import Session
from .contract import MakeShareLinkInput, ShareLink

_NON_DIGITS = re.compile(r"\D+")


def _to_wa_me_number(phone: str) -> str:
    """wa.me expects digits only. Drops everything non-numeric, including the +."""
    return _NON_DIGITS.sub("", phone)


async def run(payload: MakeShareLinkInput, ctx: Context) -> ShareLink:
    log = ctx.logger.bind(behavior="make_share_link", session_id=payload.session_id)
    with ctx.db.session() as db:
        session = db.get(Session, payload.session_id)
        if session is None:
            raise BehaviorError(f"unknown_session: {payload.session_id}")
        if session.drive_folder_id is None:
            raise BehaviorError("session_missing_drive_folder_id")

    url = await ctx.drive.create_share_link(session.drive_folder_id)

    phone = session.customer_phone
    whatsapp_url: str | None = None
    if phone and ctx.settings.whatsapp.auto_open_when_phone_present:
        digits = _to_wa_me_number(phone)
        if digits:
            text = quote(f"Suas fotos e vídeos: {url}", safe="")
            whatsapp_url = f"https://wa.me/{digits}?text={text}"

    log.info("share_link_made", with_phone=phone is not None)
    return ShareLink(url=url, phone=phone, whatsapp_url=whatsapp_url)
