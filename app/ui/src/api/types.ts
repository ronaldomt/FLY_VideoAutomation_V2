/**
 * TypeScript shapes mirroring the Pydantic models in `backend/src/fly_backend`.
 *
 * Hand-maintained for v1. Once the backend OpenAPI schema is stable, this file
 * should be regenerated via `openapi-typescript` against `/openapi.json`.
 */

export type SessionStatus = "queued" | "running" | "completed" | "failed";

export interface CustomerEvent {
  time: string;
  name: string;
  phone?: string | null;
  age?: number | null;
  weight?: number | null;
  type?: "HC" | "VIP" | null;
}

export interface ListTodayCustomersOutput {
  events: CustomerEvent[];
  calendar_id: string;
  source: "live" | "mock";
}

export interface SessionOut {
  id: string;
  customer_name: string;
  customer_phone: string | null;
  drive_folder_id: string;
  drive_folder_url: string;
  drive_folder_name: string;
  source_mount_path: string;
  local_folder: string;
  status: SessionStatus;
  disk_check_ok: boolean;
  estimated_card_bytes: number;
  free_bytes: number;
  shortfall_bytes: number;
}

export interface SessionSummary {
  id: string;
  customer_name: string;
  customer_phone: string | null;
  drive_folder_url: string;
  drive_folder_id: string | null;
  source_mount_path: string;
  local_folder: string;
  status: SessionStatus;
  error: string | null;
  phases: PhaseStatus[];
}

export interface PhaseStatus {
  name: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  current: number;
  total: number;
  message: string | null;
}

export interface ProgressEvent {
  phase: string;
  current: number;
  total: number;
  message?: string | null;
  ts: string;
}

export interface VerificationReport {
  ok: boolean;
  checked: number;
  mismatches: Mismatch[];
}

export interface Mismatch {
  relative_path: string;
  reason: string;
  local_md5?: string | null;
  drive_md5?: string | null;
  local_size?: number | null;
  drive_size?: number | null;
}

export interface ShareLink {
  url: string;
  phone: string | null;
  whatsapp_url: string | null;
}

export interface CardDetected {
  mount_path: string;
  volume_id: string;
  label: string | null;
  detected_at: string;
  already_ingested_within_hour: boolean;
}

export interface Settings {
  local_root: string | null;
  drive_recent_folders: string[];
  calendar_id: string;
  extraction: {
    enabled: boolean;
    fps: number;
    min_interval_seconds: number;
    max_interval_seconds: number;
    output_format: string;
    jpeg_quality: number;
  };
  ingest: {
    video_extensions: string[];
    photo_extensions: string[];
    ignore_hidden: boolean;
  };
  upload: {
    parallel_uploads: number;
    chunk_size_mb: number;
    max_retries: number;
  };
  card_wipe: {
    enabled: boolean;
    require_verification: boolean;
  };
  whatsapp: {
    auto_open_when_phone_present: boolean;
  };
  ui: {
    auto_focus_on_card_insert: boolean;
  };
  composio: {
    api_key_set: boolean;
    auth_config_id: string | null;
    connection_id: string | null;
    user_id: string | null;
    toolkit: string;
    last_validated_at: string | null;
    google_connected: boolean;
  };
}

/** Returned by /integrations/composio/status, /key (PUT/DELETE). */
export interface ComposioStatus {
  api_key_set: boolean;
  auth_config_id: string | null;
  user_id: string | null;
  connection_id: string | null;
  google_connected: boolean;
  toolkit: string;
  last_validated_at: string | null;
}

export interface ComposioKeyInput {
  api_key: string;
  auth_config_id: string;
}

export interface ComposioPingResult {
  ok: boolean;
  validated_at: string;
  detail?: string | null;
}

export interface SetupStatus {
  composio_connected: boolean;
  calendar_id_set: boolean;
  local_root_set: boolean;
}

export interface ComposioStartResult {
  auth_url: string;
  connection_request_id: string;
}

export interface StartSessionInput {
  customer_name: string;
  customer_phone?: string | null;
  drive_folder_url: string;
  source_mount_path: string;
  overrides?: { fps?: number; extraction_enabled?: boolean };
}

export interface WipeResult {
  ok: boolean;
  deleted: number;
  skipped_reason: string | null;
}
