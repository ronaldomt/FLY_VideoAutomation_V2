from __future__ import annotations

from pathlib import Path

from sqlmodel import select

from ...context import Context
from ...errors import BehaviorError
from ...persistence.models import FileRecord, Session
from ...util.hashing import md5_file
from ...util.remote_paths import ensure_session_subfolders
from .contract import Mismatch, VerificationReport, VerifyUploadInput


async def run(payload: VerifyUploadInput, ctx: Context) -> VerificationReport:
    log = ctx.logger.bind(behavior="verify_upload", session_id=payload.session_id)
    with ctx.db.session() as db:
        session = db.get(Session, payload.session_id)
        if session is None:
            raise BehaviorError(f"unknown_session: {payload.session_id}")
        if session.drive_folder_id is None:
            raise BehaviorError("session_missing_drive_folder_id")
        local_root = Path(session.local_folder)
        records = db.exec(
            select(FileRecord).where(FileRecord.session_id == payload.session_id)
        ).all()

    video_remote, fotos_remote = await ensure_session_subfolders(session, ctx.drive)
    # Local bucket names ("Videos"/"Fotos" from copy_media) → remote subfolder IDs.
    bucket_map = {"Videos": video_remote, "Fotos": fotos_remote}

    drive_index: dict[tuple[str, str], tuple[int, str]] = {}
    for bucket, remote_id in bucket_map.items():
        for f in await ctx.drive.list_files(remote_id):
            drive_index[(bucket, f.name)] = (f.size, f.md5)

    mismatches: list[Mismatch] = []
    checked = 0
    for record in records:
        bucket, _, name = record.relative_path.partition("/")
        key = (bucket, name)
        local_path = local_root / record.relative_path
        if not local_path.exists():
            mismatches.append(Mismatch(relative_path=record.relative_path, reason="missing_local"))
            continue
        checked += 1
        if key not in drive_index:
            mismatches.append(
                Mismatch(relative_path=record.relative_path, reason="missing_on_drive")
            )
            continue
        drive_size, drive_md5 = drive_index[key]
        local_size = local_path.stat().st_size
        local_md5 = record.md5 or md5_file(local_path)
        if drive_size != local_size:
            mismatches.append(
                Mismatch(
                    relative_path=record.relative_path,
                    reason="size_mismatch",
                    local_size=local_size,
                    drive_size=drive_size,
                )
            )
            continue
        if drive_md5 != local_md5:
            mismatches.append(
                Mismatch(
                    relative_path=record.relative_path,
                    reason="md5_mismatch",
                    local_md5=local_md5,
                    drive_md5=drive_md5,
                )
            )
            continue
        # Mark as verified.
        with ctx.db.session() as db:
            row = db.get(FileRecord, record.id)
            if row is not None:
                row.verified = True
                row.md5 = local_md5
                db.add(row)
                db.commit()

    ok = len(mismatches) == 0
    log.info("verification_complete", ok=ok, checked=checked, mismatches=len(mismatches))
    return VerificationReport(ok=ok, checked=checked, mismatches=mismatches)
