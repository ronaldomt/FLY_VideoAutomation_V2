/**
 * HTTP client for the Python sidecar. All requests carry the per-launch
 * `X-Sidecar-Token` shared secret. See CLAUDE.md §10.
 */

import { getSidecarConfig } from "./config";
import type {
  CardDetected,
  ComposioKeyInput,
  ComposioPingResult,
  ComposioStatus,
  ListTodayCustomersOutput,
  SessionOut,
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
  startComposio: () => request<{ auth_url: string }>("/setup/composio/start", { method: "POST" }),
  completeComposio: () => request<{ ok: boolean }>("/setup/composio/complete", { method: "POST" }),
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
  createSession: (input: StartSessionInput) =>
    request<SessionOut>("/sessions", { method: "POST", body: JSON.stringify(input) }),
  getSession: (id: string) => request<SessionSummary>(`/sessions/${id}`),
  verifySession: (id: string) =>
    request<VerificationReport>(`/sessions/${id}/verify`, { method: "POST" }),
  shareLink: (id: string) => request<ShareLink>(`/sessions/${id}/share-link`),
  wipeCard: (id: string, confirm: boolean) =>
    request<WipeResult>(`/sessions/${id}/wipe-card`, {
      method: "POST",
      body: JSON.stringify({ confirm }),
    }),
  /**
   * Subscribes to `/sessions/:id/events` via EventSource. Returns a teardown
   * function. The SSE stream emits `progress`, `verification`, and `done`
   * events in sequence (see CLAUDE.md §10).
   */
  subscribeEvents(
    id: string,
    handlers: {
      onProgress?: (e: ProgressEventPayload) => void;
      onVerification?: (e: VerificationReport) => void;
      onDone?: (e: { ok: boolean; session_id: string }) => void;
      onError?: (e: Event) => void;
    },
  ): () => void {
    const { url, token } = getSidecarConfig();
    // EventSource doesn't allow custom headers — pass the token via query in dev.
    // The sidecar still validates the standard header for non-SSE requests.
    const sse = new EventSource(
      `${url}/sessions/${id}/events?token=${encodeURIComponent(token)}`,
      { withCredentials: false },
    );
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
