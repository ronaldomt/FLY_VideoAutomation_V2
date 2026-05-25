/**
 * HTTP client for the Python sidecar. All requests carry the per-launch
 * `X-Sidecar-Token` shared secret. See CLAUDE.md §10.
 */

import { getSidecarConfig } from "./config";
import type {
  CardDetected,
  ComposioKeyInput,
  ComposioPingResult,
  ComposioStartResult,
  ComposioStatus,
  DriveBaseInput,
  DriveBaseStatus,
  ListTodayCustomersOutput,
  RecentSession,
  SessionOut,
  SessionStatus,
  SessionSummary,
  Settings,
  SetupStatus,
  ShareLink,
  StartSessionInput,
  VerificationReport,
  WipeResult,
} from "./types";

class SidecarError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { url, token } = getSidecarConfig();
  const headers = new Headers(init.headers);
  headers.set("X-Sidecar-Token", token);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${url}${path}`, { ...init, headers });
  const text = await response.text();
  const body = text ? safeJson(text) : null;
  if (!response.ok) {
    throw new SidecarError(response.status, body, `sidecar_request_failed: ${path}`);
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = {
  health: () => request<{ ok: boolean; version: string }>("/health"),
  getSettings: () => request<Settings>("/settings"),
  putSettings: (settings: Settings) =>
    request<Settings>("/settings", { method: "PUT", body: JSON.stringify(settings) }),
  setupStatus: () => request<SetupStatus>("/setup/status"),
  startComposio: () => request<ComposioStartResult>("/setup/composio/start", { method: "POST" }),
  completeComposio: (connectionRequestId: string) =>
    request<{ ok: boolean }>("/setup/composio/complete", {
      method: "POST",
      body: JSON.stringify({ connection_request_id: connectionRequestId }),
    }),
  composioStatus: () => request<ComposioStatus>("/integrations/composio/status"),
  setComposioKey: (input: ComposioKeyInput) =>
    request<ComposioStatus>("/integrations/composio/key", {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  clearComposioKey: () =>
    request<ComposioStatus>("/integrations/composio/key", { method: "DELETE" }),
  pingComposio: () =>
    request<ComposioPingResult>("/integrations/composio/ping", { method: "POST" }),
  customersToday: (on?: string) =>
    request<ListTodayCustomersOutput>(`/customers/today${on ? `?on=${on}` : ""}`),
  cardsCurrent: () => request<CardDetected | null>("/cards/current"),
  cardsList: () => request<CardDetected[]>("/cards/list"),
  getDriveBase: () => request<DriveBaseStatus>("/setup/drive-base"),
  setDriveBase: (input: DriveBaseInput) =>
    request<{ ok: boolean; folder_id: string; folder_name: string }>("/setup/drive-base", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  createSession: (input: StartSessionInput) =>
    request<SessionOut>("/sessions", { method: "POST", body: JSON.stringify(input) }),
  getSession: (id: string) => request<SessionSummary>(`/sessions/${id}`),
  recentSessions: (opts: { status?: SessionStatus; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (opts.status) params.set("status", opts.status);
    if (opts.limit !== undefined) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<RecentSession[]>(`/sessions/recent${qs ? `?${qs}` : ""}`);
  },
  clearFailedSessions: (olderThanHours = 0) =>
    request<{ deleted: number }>(`/sessions/failed?older_than_hours=${olderThanHours}`, {
      method: "DELETE",
    }),
  verifySession: (id: string) =>
    request<VerificationReport>(`/sessions/${id}/verify`, { method: "POST" }),
  shareLink: (id: string) => request<ShareLink>(`/sessions/${id}/share-link`),
  wipeCard: (id: string, confirm: boolean) =>
    request<WipeResult>(`/sessions/${id}/wipe-card`, {
      method: "POST",
      body: JSON.stringify({ confirm }),
    }),
  cancelSession: (id: string) =>
    request<{ ok: boolean }>(`/sessions/${id}/cancel`, { method: "POST" }),
  /**
   * Subscribes to `/sessions/:id/events` via EventSource. Returns a teardown
   * function. The SSE stream emits `progress`, `verification`, and `done`
   * events in sequence (see CLAUDE.md §10).
   */
  subscribeEvents(
    id: string,
    handlers: {
      onOpen?: () => void;
      onProgress?: (e: ProgressEventPayload) => void;
      onVerification?: (e: VerificationReport) => void;
      onDone?: (e: { ok: boolean; session_id: string }) => void;
      onCancelled?: () => void;
      onPipelineError?: (msg: string) => void;
      onError?: (e: Event) => void;
    },
  ): () => void {
    const { url, token } = getSidecarConfig();
    // EventSource cannot send custom headers — the sidecar auth middleware
    // (backend/src/fly_backend/http/auth.py) explicitly accepts the token via
    // ?token= query parameter, with the standard X-Sidecar-Token header
    // enforced on every other route.
    const sse = new EventSource(`${url}/sessions/${id}/events?token=${encodeURIComponent(token)}`, {
      withCredentials: false,
    });
    sse.addEventListener("open", () => handlers.onOpen?.());
    sse.addEventListener("progress", (e: MessageEvent) => {
      try {
        handlers.onProgress?.(JSON.parse(e.data) as ProgressEventPayload);
      } catch (err) {
        console.error("malformed progress event", err);
      }
    });
    sse.addEventListener("verification", (e: MessageEvent) => {
      try {
        handlers.onVerification?.(JSON.parse(e.data) as VerificationReport);
      } catch (err) {
        console.error("malformed verification event", err);
      }
    });
    sse.addEventListener("done", (e: MessageEvent) => {
      try {
        handlers.onDone?.(JSON.parse(e.data));
      } catch (err) {
        console.error("malformed done event", err);
      }
    });
    sse.addEventListener("cancelled", () => {
      handlers.onCancelled?.();
    });
    sse.addEventListener("pipeline_error", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as { message: string };
        handlers.onPipelineError?.(data.message ?? "unknown_error");
      } catch (err) {
        console.error("malformed pipeline_error event", err);
      }
    });
    sse.onerror = (e) => handlers.onError?.(e);
    return () => sse.close();
  },
};

export interface ProgressEventPayload {
  phase: string;
  current: number;
  total: number;
  message?: string | null;
  ts: string;
}

export { SidecarError };
