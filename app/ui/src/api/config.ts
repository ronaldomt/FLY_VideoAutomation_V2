/**
 * Sidecar connection config. Read in priority order:
 *
 *   1. `window.__FLY_SIDECAR__` (injected by Tauri shell at startup
 *      after it reads `~/.fly-video-automation/sidecar.port`).
 *   2. Vite env vars (dev mode).
 *   3. Hardcoded defaults.
 *
 * See CLAUDE.md §10 for the runtime file format.
 */

declare global {
  interface Window {
    __FLY_SIDECAR__?: { url: string; token: string };
  }
}

// Defaults match `backend/run-dev.sh`, which binds uvicorn to :8000 and
// sets FLY_SIDECAR_TOKEN=dev-token. Override in app/ui/.env.local for any
// other dev setup (see app/ui/.env.example).
const DEFAULT_URL = "http://127.0.0.1:8000";
const DEFAULT_TOKEN = "dev-token";

export interface SidecarConfig {
  url: string;
  token: string;
}

export function getSidecarConfig(): SidecarConfig {
  if (typeof window !== "undefined" && window.__FLY_SIDECAR__) {
    return window.__FLY_SIDECAR__;
  }
  const url = (import.meta.env.VITE_SIDECAR_URL as string | undefined) ?? DEFAULT_URL;
  const token = (import.meta.env.VITE_SIDECAR_TOKEN as string | undefined) ?? DEFAULT_TOKEN;
  return { url, token };
}
