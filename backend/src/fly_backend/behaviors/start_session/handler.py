from __future__ import annotations

import re
import uuid
from datetime import UTC
from pathlib import Path

from sqlmodel import select

from ...context import Context
from ...errors import BehaviorError, NotConfiguredError
from ...persistence.models import Session, SessionStatus
from ...util.disk import check_free_space, estimate_card_size
from .contract import SessionOut, StartSessionInput

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9 _\-]+")


def _sanitize_customer_name(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("", name).strip()
    return cleaned or "Walk-in"


async def run(payload: StartSessionInput, ctx: Context) -> SessionOut:
    log = ctx.logger.bind(behavior="start_session")
    if not ctx.settings.local_root:
        raise NotConfiguredError("local_root_not_set")

    base_folder_id = ctx.settings.drive_base_folder_id
    if not base_folder_id:
        raise NotConfiguredError("drive_base_folder_not_set")

    if not payload.source_mount_path.exists():
        raise BehaviorError(f"card_not_mounted: {payload.source_mount_path}")

    safe_name = _sanitize_customer_name(payload.customer_name)
    local_root = Path(ctx.settings.local_root)
    local_folder = local_root / f"TD_{safe_name}"
    (local_folder / "Videos").mkdir(parents=True, exist_ok=True)
    (local_folder / "Fotos").mkdir(parents=True, exist_ok=True)

    # Disk-full pre-check (CLAUDE.md §16). Add 50% headroom for extracted frames.
    card_bytes = estimate_card_size(
        payload.source_mount_path,
        ctx.settings.ingest.video_extensions,
        ctx.settings.ingest.photo_extensions,
    )
    estimated = int(card_bytes * 1.5)
    disk = check_free_space(local_folder, estimated)

    session_id = uuid.uuid4().hex
    with ctx.db.session() as db:
        # Walk-ins log (CLAUDE.md §3): if no phone and the parsed name
        # didn't come from a calendar match, dump to _logs/walkins-<date>.csv.
        existing = db.exec(
            select(Session).where(
                Session.customer_name == payload.customer_name,
                Session.local_folder == str(local_folder),
            )
        ).first()
        if existing is not None:
            log.info(
                "reusing_local_folder_for_customer",
                customer=payload.customer_name,
                session_id=existing.id,
            )
        db.add(
            Session(
                id=session_id,
                customer_name=payload.customer_name,
                customer_phone=payload.customer_phone,
                drive_folder_url=ctx.settings.drive_base_folder_url or "",
                drive_folder_id=base_folder_id,
                source_mount_path=str(payload.source_mount_path),
                local_folder=str(local_folder),
                status=SessionStatus.queued if disk.ok else SessionStatus.failed,
                error=None if disk.ok else f"disk_full: shortfall={disk.shortfall_bytes}",
            )
        )
        db.commit()

    if payload.customer_phone is None:
        _append_walkin_log(ctx, payload.customer_name, session_id)

    log.info(
        "session_started",
        session_id=session_id,
        local_folder=str(local_folder),
        disk_ok=disk.ok,
    )

    return SessionOut(
        id=session_id,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        drive_folder_id=base_folder_id,
        drive_folder_url=ctx.settings.drive_base_folder_url or "",
        drive_folder_name="",
        source_mount_path=payload.source_mount_path,
        local_folder=local_folder,
        status="queued" if disk.ok else "failed",
        disk_check_ok=disk.ok,
        estimated_card_bytes=card_bytes,
        free_bytes=disk.free_bytes,
        shortfall_bytes=disk.shortfall_bytes,
    )


def _append_walkin_log(ctx: Context, customer_name: str, session_id: str) -> None:
    """CLAUDE.md §3: walk-ins logged to `<RootLocal>/_logs/walkins-YYYY-MM-DD.csv`."""
    from datetime import date, datetime

    root = Path(ctx.settings.local_root or ".")
    logs = root / "_logs"
    logs.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    log_file = logs / f"walkins-{today}.csv"
    write_header = not log_file.exists()
    with log_file.open("a", encoding="utf-8") as f:
        if write_header:
            f.write("timestamp_utc,session_id,customer_name\n")
        ts = datetime.now(UTC).isoformat()
        # Escape commas/newlines in the name field.
        safe = customer_name.replace('"', '""')
        f.write(f'{ts},{session_id},"{safe}"\n')
