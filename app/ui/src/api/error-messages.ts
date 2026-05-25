/**
 * Maps backend error codes / detail strings to operator-readable messages.
 *
 * Kept centralised so CustomerStep, IngestStep, and the Idle "failed
 * sessions" list all say the same thing for the same underlying problem.
 * Anything not in the table is returned verbatim — the unmapped raw codes
 * are the signal to add a friendlier mapping here.
 */

const PREFIX_MAP: Array<{ prefix: string; friendly: string }> = [
  {
    prefix: "disk_full_at_extract_start",
    friendly: "Disk is full — free space on the archive drive and start a new session.",
  },
  {
    prefix: "disk_full_during_extraction",
    friendly: "Disk filled up during frame extraction. Free space and start a new session.",
  },
  {
    prefix: "disk_full",
    friendly: "Not enough disk space on the archive drive — free space and try again.",
  },
  {
    prefix: "drive_folder_not_found",
    friendly: "Destination Drive folder is missing — re-paste the URL in Settings → Destination.",
  },
  {
    prefix: "session_concurrency_limit",
    friendly:
      "Another session is already running on this workstation. Wait for it to finish or cancel it first.",
  },
  {
    prefix: "interrupted_by_restart",
    friendly: "This session was interrupted by a backend restart. Discard it and create a new one.",
  },
  {
    prefix: "verification_failed",
    friendly:
      "Some uploaded files did not match the local archive. Card wipe is blocked — check Logs for the mismatch list.",
  },
  {
    prefix: "ffmpeg_not_found_on_path",
    friendly:
      "ffmpeg is not installed on this workstation. Install it (e.g. `brew install ffmpeg`) and start a new session.",
  },
  {
    prefix: "ffmpeg_failed",
    friendly:
      "Frame extraction failed. Check Logs for the underlying ffmpeg error (often disk-full or codec).",
  },
  {
    prefix: "card_not_mounted",
    friendly: "The source card is no longer mounted. Re-insert it and try again.",
  },
];

export function friendlyError(raw: string | null | undefined): string {
  if (!raw) return "unknown_error";
  for (const { prefix, friendly } of PREFIX_MAP) {
    if (raw.startsWith(prefix)) return friendly;
  }
  return raw;
}
