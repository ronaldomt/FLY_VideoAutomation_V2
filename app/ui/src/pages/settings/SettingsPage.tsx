import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, SidecarError } from "@/api/client";
import type { Settings } from "@/api/types";

/**
 * Settings split into 4 sub-tabs per CLAUDE.md §12: Storage, Extraction &
 * Ingest, Upload & Card, Integrations. One PUT /settings call covers all of
 * them — the local form mirrors the server document.
 */
export function SettingsPage() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const [draft, setDraft] = useState<Settings | null>(null);
  const [tab, setTab] = useState<"storage" | "extraction" | "upload" | "integrations">("storage");

  useEffect(() => {
    if (settings.data) setDraft(structuredClone(settings.data));
  }, [settings.data]);

  const save = useMutation({
    mutationFn: (next: Settings) => api.putSettings(next),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });

  if (!draft) {
    return <div className="p-6 text-sm text-slate-400">Loading settings…</div>;
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-6">
      <header>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-sm text-slate-400">
          Settings are persisted at <code>~/.fly-video-automation/settings.json</code>.
        </p>
      </header>
      <nav className="flex gap-1 border-b border-slate-800 text-sm">
        {(["storage", "extraction", "upload", "integrations"] as const).map((t) => (
          <button
            type="button"
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-3 py-2 capitalize ${
              tab === t
                ? "border-emerald-400 text-emerald-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            {t === "upload" ? "Upload & Card" : t === "extraction" ? "Extraction & Ingest" : t}
          </button>
        ))}
      </nav>

      <div className="flex flex-col gap-3">
        {tab === "storage" ? (
          <Field
            label="Local archive root"
            description="Customer folders (`TD_<Name>/Videos/+Fotos/`) live under this path."
          >
            <input
              type="text"
              value={draft.local_root ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, local_root: e.target.value || null })
              }
              placeholder="/Volumes/FLY_Archive"
              className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
            />
          </Field>
        ) : null}

        {tab === "extraction" ? (
          <>
            <Toggle
              label="Extract frames from each video"
              checked={draft.extraction.enabled}
              onChange={(v) =>
                setDraft({ ...draft, extraction: { ...draft.extraction, enabled: v } })
              }
            />
            <Field label="Frames per second" description="Sample rate. Higher = more JPGs.">
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="30"
                value={draft.extraction.fps}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    extraction: { ...draft.extraction, fps: Number(e.target.value) },
                  })
                }
                className="w-32 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              />
            </Field>
            <Field label="JPEG quality" description="2 = tiny / lossy. 100 = huge / near-lossless.">
              <input
                type="number"
                min="1"
                max="100"
                value={draft.extraction.jpeg_quality}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    extraction: {
                      ...draft.extraction,
                      jpeg_quality: Number(e.target.value),
                    },
                  })
                }
                className="w-32 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              />
            </Field>
          </>
        ) : null}

        {tab === "upload" ? (
          <>
            <Field label="Parallel uploads" description="Cap on concurrent Drive uploads.">
              <input
                type="number"
                min="1"
                max="16"
                value={draft.upload.parallel_uploads}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    upload: { ...draft.upload, parallel_uploads: Number(e.target.value) },
                  })
                }
                className="w-32 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              />
            </Field>
            <Toggle
              label="Allow card wipe"
              description="Master switch. Even with this on, wipe still requires a per-session confirmation AND verification."
              checked={draft.card_wipe.enabled}
              onChange={(v) =>
                setDraft({ ...draft, card_wipe: { ...draft.card_wipe, enabled: v } })
              }
            />
            <Toggle
              label="Require verified upload before wipe"
              checked={draft.card_wipe.require_verification}
              onChange={(v) =>
                setDraft({
                  ...draft,
                  card_wipe: { ...draft.card_wipe, require_verification: v },
                })
              }
            />
            <Toggle
              label="Open WhatsApp when a phone is present"
              checked={draft.whatsapp.auto_open_when_phone_present}
              onChange={(v) =>
                setDraft({
                  ...draft,
                  whatsapp: { ...draft.whatsapp, auto_open_when_phone_present: v },
                })
              }
            />
          </>
        ) : null}

        {tab === "integrations" ? (
          <>
            <Field label="Calendar ID" description="Google Calendar identifier — usually `primary`.">
              <input
                type="text"
                value={draft.calendar_id}
                onChange={(e) => setDraft({ ...draft, calendar_id: e.target.value })}
                className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              />
            </Field>
            <DriveBasePanel />
            <ComposioPanel />
          </>
        ) : null}
      </div>

      <div className="flex items-center gap-3 pt-3">
        <button
          type="button"
          disabled={save.isPending}
          onClick={() => draft && save.mutate(draft)}
          className="rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-emerald-950 hover:bg-emerald-400 disabled:opacity-40"
        >
          {save.isPending ? "Saving…" : "Save changes"}
        </button>
        {save.isSuccess ? <span className="text-sm text-emerald-300">Saved.</span> : null}
        {save.isError ? (
          <span className="text-sm text-rose-300">Save failed — see Logs.</span>
        ) : null}
      </div>
    </div>
  );
}

function Field({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-slate-200">{label}</span>
      {description ? <span className="text-xs text-slate-500">{description}</span> : null}
      {children}
    </label>
  );
}

/**
 * Drive base folder panel.
 *
 * The operator pastes the root Google Drive folder URL once. All sessions
 * upload to <base>/YYYY/MMM/MMM-DD/TD_<Name>/VIDEO + FOTOS.
 */
function DriveBasePanel() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["drive-base"], queryFn: api.getDriveBase });
  const [url, setUrl] = useState("");
  const [feedback, setFeedback] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  const save = useMutation({
    mutationFn: () => api.setDriveBase({ drive_folder_url: url.trim() }),
    onSuccess: (r) => {
      setUrl("");
      setFeedback({ kind: "ok", msg: `Saved: ${r.folder_name} (${r.folder_id})` });
      qc.invalidateQueries({ queryKey: ["drive-base"] });
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e) => {
      const detail = e instanceof SidecarError ? extractDetail(e.body) : String(e);
      setFeedback({ kind: "err", msg: `Failed: ${detail}` });
    },
  });

  const s = status.data;

  return (
    <div className="flex flex-col gap-3 rounded-md border border-slate-800 p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-slate-200">Drive base folder</div>
          <div className="text-xs text-slate-500">
            Files go to: base/YYYY/MMM/MMM-DD/TD_Name/VIDEO + FOTOS
          </div>
        </div>
        <span className={s?.configured ? "text-xs text-emerald-400" : "text-xs text-slate-500"}>
          {s?.configured ? "✓ configured" : "○ not set"}
        </span>
      </div>

      {s?.folder_url ? (
        <div className="truncate rounded bg-slate-900 px-2 py-1.5 font-mono text-xs text-slate-400">
          {s.folder_url}
        </div>
      ) : null}

      <Field label="Paste new folder URL" description="Google Drive folder URL to use as the archive root.">
        <input
          type="url"
          value={url}
          onChange={(e) => { setUrl(e.target.value); setFeedback(null); }}
          placeholder="https://drive.google.com/drive/folders/…"
          className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
        />
      </Field>

      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={url.trim().length < 10 || save.isPending}
          onClick={() => save.mutate()}
          className="rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-medium text-emerald-950 hover:bg-emerald-400 disabled:opacity-40"
        >
          {save.isPending ? "Validating…" : "Validate & Save"}
        </button>
      </div>

      {feedback ? (
        <div
          className={`rounded-md border px-3 py-2 text-xs ${
            feedback.kind === "ok"
              ? "border-emerald-700/40 bg-emerald-950/30 text-emerald-200"
              : "border-rose-700/50 bg-rose-950/30 text-rose-200"
          }`}
        >
          {feedback.msg}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Composio integration panel.
 *
 * Two inputs: API key (write-only — never round-tripped from the backend)
 * and auth_config_id (created in the operator's Composio dashboard).
 *
 * Saving the key:
 * - Stores the key in the OS keychain (via the backend), not in
 *   settings.json.
 * - Clears any prior Google connection — the user explicitly chose
 *   "re-auth on every key change" so this isn't accidental.
 * - Does NOT auto-ping; the user clicks Validate to make a live call.
 */
function ComposioPanel() {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["composio-status"],
    queryFn: api.composioStatus,
  });

  const [apiKey, setApiKey] = useState("");
  const [authConfigId, setAuthConfigId] = useState("");
  const [feedback, setFeedback] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [oauthPhase, setOauthPhase] = useState<"idle" | "opened" | "done" | "error">("idle");
  const [oauthConnId, setOauthConnId] = useState("");

  useEffect(() => {
    if (status.data?.auth_config_id) setAuthConfigId(status.data.auth_config_id);
  }, [status.data?.auth_config_id]);

  const save = useMutation({
    mutationFn: () =>
      api.setComposioKey({ api_key: apiKey.trim(), auth_config_id: authConfigId.trim() }),
    onSuccess: () => {
      setApiKey("");
      setFeedback({ kind: "ok", msg: "Saved. Key is in the OS keychain." });
      qc.invalidateQueries({ queryKey: ["composio-status"] });
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e) => {
      const detail =
        e instanceof SidecarError ? extractDetail(e.body) : String(e);
      setFeedback({ kind: "err", msg: `Save failed: ${detail}` });
    },
  });

  const clear = useMutation({
    mutationFn: () => api.clearComposioKey(),
    onSuccess: () => {
      setApiKey("");
      setFeedback({ kind: "ok", msg: "Cleared." });
      qc.invalidateQueries({ queryKey: ["composio-status"] });
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  const ping = useMutation({
    mutationFn: () => api.pingComposio(),
    onSuccess: (r) => {
      setFeedback({
        kind: "ok",
        msg: `Validated at ${new Date(r.validated_at).toLocaleTimeString()}.`,
      });
      qc.invalidateQueries({ queryKey: ["composio-status"] });
    },
    onError: (e) => {
      const detail =
        e instanceof SidecarError ? extractDetail(e.body) : String(e);
      setFeedback({ kind: "err", msg: `Validate failed: ${detail}` });
    },
  });

  const startReconnect = useMutation({
    mutationFn: api.startComposio,
    onSuccess: (result) => {
      window.open(result.auth_url, "_blank", "noopener,noreferrer");
      setOauthConnId(result.connection_request_id);
      setOauthPhase("opened");
    },
    onError: (e) => {
      const detail = e instanceof SidecarError ? extractDetail(e.body) : String(e);
      setFeedback({ kind: "err", msg: `Reconnect failed: ${detail}` });
      setOauthPhase("error");
    },
  });

  const completeReconnect = useMutation({
    mutationFn: () => api.completeComposio(oauthConnId),
    onSuccess: () => {
      setOauthPhase("done");
      setFeedback({ kind: "ok", msg: "Google reconnected." });
      qc.invalidateQueries({ queryKey: ["composio-status"] });
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e) => {
      const detail = e instanceof SidecarError ? extractDetail(e.body) : String(e);
      setFeedback({ kind: "err", msg: `Verification failed: ${detail}` });
      setOauthPhase("error");
    },
  });

  const s = status.data;
  const canSave =
    apiKey.trim().length >= 8 && authConfigId.trim().length >= 4 && !save.isPending;
  const canPing = !!s?.api_key_set && !!s?.auth_config_id && !ping.isPending;
  const canReconnect = !!s?.api_key_set && !!s?.auth_config_id && !startReconnect.isPending;

  return (
    <div className="flex flex-col gap-3 rounded-md border border-slate-800 p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-slate-200">Composio</div>
          <div className="text-xs text-slate-500">
            Toolkit: {s?.toolkit ?? "google_super"} (single auth covers Calendar + Drive)
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className={s?.api_key_set ? "text-emerald-400" : "text-slate-500"}>
            {s?.api_key_set ? "✓" : "○"} API key
          </span>
          <span className={s?.google_connected ? "text-emerald-400" : "text-slate-500"}>
            {s?.google_connected ? "✓" : "○"} Google connected
          </span>
        </div>
      </div>

      <Field
        label="API key"
        description={
          s?.api_key_set
            ? "A key is currently stored in the OS keychain. Paste a new one to rotate (existing Google OAuth will be cleared)."
            : "Create an API key at app.composio.dev → API Keys. Pasting it here stores it in the OS keychain — never in settings.json."
        }
      >
        <input
          type="password"
          autoComplete="off"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={s?.api_key_set ? "•••••••• (paste to rotate)" : "ck_live_…"}
          className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 font-mono text-sm placeholder:text-slate-600 focus:border-emerald-500 focus:outline-none"
        />
      </Field>

      <Field
        label="Auth config ID"
        description="From your Composio dashboard → Auth Configs. Create one for Google with Calendar + Drive scopes; paste its ID here."
      >
        <input
          type="text"
          value={authConfigId}
          onChange={(e) => setAuthConfigId(e.target.value)}
          placeholder="ac_…"
          className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 font-mono text-sm placeholder:text-slate-600 focus:border-emerald-500 focus:outline-none"
        />
      </Field>

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <button
          type="button"
          disabled={!canSave}
          onClick={() => save.mutate()}
          className="rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-medium text-emerald-950 hover:bg-emerald-400 disabled:opacity-40"
        >
          {save.isPending ? "Saving…" : "Save key"}
        </button>
        <button
          type="button"
          disabled={!canPing}
          onClick={() => ping.mutate()}
          className="rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-900 disabled:opacity-40"
        >
          {ping.isPending ? "Validating…" : "Validate"}
        </button>
        <button
          type="button"
          disabled={!s?.api_key_set || clear.isPending}
          onClick={() => {
            if (confirm("Remove the Composio API key from the keychain?")) clear.mutate();
          }}
          className="rounded-md border border-rose-700/60 px-3 py-1.5 text-sm text-rose-300 hover:bg-rose-950/40 disabled:opacity-40"
        >
          Clear key
        </button>
        {s?.last_validated_at ? (
          <span className="ml-auto text-xs text-slate-500">
            Last validated {new Date(s.last_validated_at).toLocaleString()}
          </span>
        ) : null}
      </div>

      <div className="mt-1 border-t border-slate-800 pt-3">
        <div className="mb-2 text-xs font-medium text-slate-400">Google OAuth</div>
        {oauthPhase === "idle" || oauthPhase === "error" || oauthPhase === "done" ? (
          <button
            type="button"
            disabled={!canReconnect}
            onClick={() => { setOauthPhase("idle"); startReconnect.mutate(); }}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-900 disabled:opacity-40"
          >
            {startReconnect.isPending ? "Opening…" : s?.google_connected ? "Reconnect Google" : "Connect Google"}
          </button>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400">Google opened in a new tab. Authorize, then click Verify.</span>
            <button
              type="button"
              disabled={completeReconnect.isPending}
              onClick={() => completeReconnect.mutate()}
              className="rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-medium text-emerald-950 hover:bg-emerald-400 disabled:opacity-40"
            >
              {completeReconnect.isPending ? "Verifying…" : "Verify"}
            </button>
            <button
              type="button"
              onClick={() => setOauthPhase("idle")}
              className="text-xs text-slate-500 hover:text-slate-300"
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {feedback ? (
        <div
          className={`rounded-md border px-3 py-2 text-xs ${
            feedback.kind === "ok"
              ? "border-emerald-700/40 bg-emerald-950/30 text-emerald-200"
              : "border-rose-700/50 bg-rose-950/30 text-rose-200"
          }`}
        >
          {feedback.msg}
        </div>
      ) : null}
    </div>
  );
}

function extractDetail(body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    return typeof d === "string" ? d : JSON.stringify(d);
  }
  return String(body);
}

function Toggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-3">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-900 text-emerald-500 focus:ring-emerald-500"
      />
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {description ? <span className="block text-xs text-slate-500">{description}</span> : null}
      </span>
    </label>
  );
}
