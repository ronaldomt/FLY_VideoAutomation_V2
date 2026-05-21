import { describe, expect, it } from "vitest";
import type { Settings } from "./types";

/**
 * Smoke test: Settings type is structurally compatible with the JSON shape
 * documented in CLAUDE.md §12. If this stops compiling, the contract drifted.
 */
describe("Settings type", () => {
  it("accepts the documented default shape", () => {
    const s: Settings = {
      local_root: null,
      drive_recent_folders: [],
      calendar_id: "primary",
      extraction: {
        enabled: true,
        fps: 1.0,
        min_interval_seconds: 0.25,
        max_interval_seconds: 10.0,
        output_format: "jpg",
        jpeg_quality: 90,
      },
      ingest: { video_extensions: [".mp4"], photo_extensions: [".jpg"], ignore_hidden: true },
      upload: { parallel_uploads: 4, chunk_size_mb: 16, max_retries: 6 },
      card_wipe: { enabled: false, require_verification: true },
      whatsapp: { auto_open_when_phone_present: true },
      ui: { auto_focus_on_card_insert: true },
      composio: {
        api_key_set: false,
        auth_config_id: null,
        connection_id: null,
        user_id: null,
        toolkit: "google_super",
        last_validated_at: null,
        google_connected: false,
      },
    };
    expect(s.calendar_id).toBe("primary");
  });
});
