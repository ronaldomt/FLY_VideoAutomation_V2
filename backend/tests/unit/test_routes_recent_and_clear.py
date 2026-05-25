"""Tests for GET /sessions/recent and DELETE /sessions/failed."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fly_backend.persistence.db import Database
from fly_backend.persistence.models import FileRecord, Phase, PhaseName, Session, SessionStatus


@pytest.fixture
def configured_settings(settings_path: Path):  # type: ignore[no-untyped-def]
    """The routes' ``_ctx()`` builds the live Composio clients which require
    api_key + connection_id to be set, even when the route only touches the
    DB. Pre-configure them for these tests."""
    from fly_backend import secrets as secrets_mod
    from fly_backend.settings import load_settings, save_settings

    s = load_settings()
    s.composio.api_key_set = True
    s.composio.connection_id = "test_conn_uuid"
    s.composio.user_id = "test_user"
    save_settings(s)
    secrets_mod.set_composio_key("test_api_key")
    return s


def _insert_session(
    status: SessionStatus,
    *,
    customer: str = "Tester",
    error: str | None = None,
    created_at: datetime | None = None,
) -> str:
    """Write a Session row directly via Database — bypasses build_default_context
    so the test doesn't pull live Composio credentials."""
    sid = uuid.uuid4().hex
    db = Database.open_default()
    with db.session() as s:
        s.add(
            Session(
                id=sid,
                customer_name=customer,
                customer_phone=None,
                drive_folder_url="",
                drive_folder_id="folder_root",
                source_mount_path="/dev/null",
                local_folder=f"/tmp/{sid}",
                status=status,
                error=error,
                created_at=created_at or datetime.now(UTC),
            )
        )
        s.commit()
    return sid


def test_recent_returns_failed_only_when_filtered(client, configured_settings) -> None:  # type: ignore[no-untyped-def]
    fail_a = _insert_session(SessionStatus.failed, customer="A", error="disk_full")
    fail_b = _insert_session(SessionStatus.failed, customer="B", error="ffmpeg_failed: …")
    _insert_session(SessionStatus.completed, customer="Done")

    r = client.get("/sessions/recent?status=failed")
    assert r.status_code == 200
    body = r.json()
    ids = [row["id"] for row in body]
    assert set(ids) >= {fail_a, fail_b}
    for row in body:
        assert row["status"] == "failed"


def test_recent_respects_limit(client, configured_settings) -> None:  # type: ignore[no-untyped-def]
    for i in range(5):
        _insert_session(SessionStatus.failed, customer=f"f{i}")
    r = client.get("/sessions/recent?status=failed&limit=2")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_recent_invalid_status_returns_400(client, configured_settings) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/sessions/recent?status=nonsense")
    assert r.status_code == 400


def test_clear_failed_removes_only_failed_and_cancelled(
    client, configured_settings
) -> None:  # type: ignore[no-untyped-def]
    fail_sid = _insert_session(SessionStatus.failed, customer="F")
    cancel_sid = _insert_session(SessionStatus.cancelled, customer="C")
    done_sid = _insert_session(SessionStatus.completed, customer="D")

    r = client.delete("/sessions/failed?older_than_hours=0")
    assert r.status_code == 200
    assert r.json()["deleted"] >= 2

    with Database.open_default().session() as db:
        assert db.get(Session, fail_sid) is None
        assert db.get(Session, cancel_sid) is None
        # Completed survives.
        assert db.get(Session, done_sid) is not None


def test_clear_failed_respects_older_than_hours(
    client, configured_settings
) -> None:  # type: ignore[no-untyped-def]
    old_fail = _insert_session(
        SessionStatus.failed,
        customer="Old",
        created_at=datetime.now(UTC) - timedelta(hours=48),
    )
    fresh_fail = _insert_session(
        SessionStatus.failed,
        customer="Fresh",
        created_at=datetime.now(UTC),
    )

    r = client.delete("/sessions/failed?older_than_hours=24")
    assert r.status_code == 200
    assert r.json()["deleted"] >= 1

    with Database.open_default().session() as db:
        assert db.get(Session, old_fail) is None
        assert db.get(Session, fresh_fail) is not None


def test_clear_failed_cascades_phase_and_filerecord(
    client, configured_settings
) -> None:  # type: ignore[no-untyped-def]
    fail_sid = _insert_session(SessionStatus.failed)
    db_handle = Database.open_default()
    with db_handle.session() as db:
        db.add(
            Phase(
                session_id=fail_sid,
                name=PhaseName.copy_media,
                current=0,
                total=0,
            )
        )
        db.add(FileRecord(session_id=fail_sid, relative_path="Videos/x.mp4", size=1))
        db.commit()
        # Sanity: rows exist.
        from sqlmodel import select

        assert db.exec(select(Phase).where(Phase.session_id == fail_sid)).first() is not None
        assert (
            db.exec(select(FileRecord).where(FileRecord.session_id == fail_sid)).first()
            is not None
        )

    r = client.delete("/sessions/failed?older_than_hours=0")
    assert r.status_code == 200

    with db_handle.session() as db:
        from sqlmodel import select

        assert db.get(Session, fail_sid) is None
        assert db.exec(select(Phase).where(Phase.session_id == fail_sid)).first() is None
        assert (
            db.exec(select(FileRecord).where(FileRecord.session_id == fail_sid)).first()
            is None
        )
