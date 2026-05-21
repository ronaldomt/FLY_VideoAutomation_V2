import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/api/client";
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
            <div className="rounded-md border border-slate-800 p-3 text-sm">
              <div className="text-slate-300">Composio</div>
              <div className="mt-1 text-slate-400">
                API key: {draft.composio.api_key_set ? "✓ set" : "—"} · Google:{" "}
                {draft.composio.google_connected ? "✓ connected" : "—"}
              </div>
              <div className="mt-2 text-xs text-slate-500">
                Connect via the first-run Setup wizard.
              </div>
            </div>
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
