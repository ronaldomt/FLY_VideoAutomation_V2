"""Settings round-trip + drive-folder MRU."""

from __future__ import annotations

from pathlib import Path

from fly_backend.settings import Settings, load_settings, save_settings


def test_defaults_match_claudemd_schema(settings_path: Path) -> None:
    s = Settings()
    assert s.calendar_id == "primary"
    assert s.extraction.fps == 1.0
    assert s.extraction.jpeg_quality == 90
    assert s.upload.parallel_uploads == 4
    assert s.card_wipe.enabled is False
    assert s.card_wipe.require_verification is True
    assert s.composio.api_key_set is False
    assert s.composio.google_connected is False


def test_save_and_load_round_trip(settings_path: Path) -> None:
    s = Settings(local_root=str(settings_path.parent / "archive"))
    s.extraction.fps = 2.0
    s.upload.parallel_uploads = 8
    save_settings(s, settings_path)

    reloaded = load_settings(settings_path)
    assert reloaded.local_root == s.local_root
    assert reloaded.extraction.fps == 2.0
    assert reloaded.upload.parallel_uploads == 8


def test_remember_drive_folder_caps_and_dedups(settings_path: Path) -> None:
    s = Settings()
    for i in range(7):
        s.remember_drive_folder(f"https://drive.google.com/drive/folders/F{i}")
    assert len(s.drive_recent_folders) == 5
    # Most recent first.
    assert s.drive_recent_folders[0].endswith("F6")

    # Re-adding an existing URL moves it to the front, doesn't duplicate.
    s.remember_drive_folder("https://drive.google.com/drive/folders/F3")
    assert s.drive_recent_folders[0].endswith("F3")
    assert sum(1 for u in s.drive_recent_folders if u.endswith("F3")) == 1


def test_put_settings_persists(client, settings_path: Path) -> None:  # type: ignore[no-untyped-def]
    payload = Settings(local_root="/tmp/archive").model_dump(mode="json")
    payload["extraction"]["fps"] = 3.0
    r = client.put("/settings", json=payload)
    assert r.status_code == 200
    # Reload from disk to prove persistence.
    on_disk = load_settings(settings_path)
    assert on_disk.local_root == "/tmp/archive"
    assert on_disk.extraction.fps == 3.0
