import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Clipboard, MessageCircle, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { useSessionStore } from "@/state/session-store";

export function DoneStep({ sessionKey }: { sessionKey: string }) {
  const slice = useSessionStore((s) => s.sessions[sessionKey]);
  const patch = useSessionStore((s) => s.patch);

  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const verification = slice?.verification;

  const share = useQuery({
    queryKey: ["share-link", slice?.serverSessionId],
    queryFn: () => api.shareLink(slice!.serverSessionId!),
    enabled: !!slice?.serverSessionId,
  });

  useEffect(() => {
    if (share.data?.url && share.data.url !== slice?.shareUrl) {
      patch(sessionKey, { shareUrl: share.data.url });
      void navigator.clipboard.writeText(share.data.url).catch(() => undefined);
    }
  }, [share.data, sessionKey, patch, slice?.shareUrl]);

  const wipe = useMutation({
    mutationFn: () => api.wipeCard(slice!.serverSessionId!, true),
  });

  const [confirmingWipe, setConfirmingWipe] = useState(false);
  const allVerified = !!verification?.ok;
  const wipeAllowed =
    settings.data?.card_wipe.enabled === true && allVerified && !!slice?.serverSessionId;

  return (
    <section className="flex flex-col gap-4">
      <header className="flex items-center gap-2 text-emerald-300">
        <CheckCircle2 size={20} />
        <h1 className="text-xl font-semibold">Done</h1>
      </header>
      {verification ? (
        <div className="rounded-md border border-slate-800 p-3 text-sm">
          <div className="text-slate-300">Verification</div>
          <div className="mt-1">
            {verification.ok ? (
              <span className="text-emerald-400">
                ✓ {verification.checked} files matched local ↔ Drive
              </span>
            ) : (
              <span className="text-rose-400">
                ✗ {verification.mismatches.length} mismatch
                {verification.mismatches.length === 1 ? "" : "es"} — see Logs
              </span>
            )}
          </div>
        </div>
      ) : null}

      <div className="rounded-md border border-slate-800 p-3">
        <div className="text-sm text-slate-300">Drive folder</div>
        <code className="mt-1 block truncate font-mono text-xs text-slate-200">
          {share.data?.url ?? "Resolving…"}
        </code>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!share.data?.url}
            onClick={() =>
              share.data?.url && void navigator.clipboard.writeText(share.data.url)
            }
            className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-900 disabled:opacity-40"
          >
            <Clipboard size={14} /> Copy link
          </button>
          {share.data?.whatsapp_url ? (
            <a
              href={share.data.whatsapp_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-medium text-emerald-950 hover:bg-emerald-400"
            >
              <MessageCircle size={14} /> Open WhatsApp
            </a>
          ) : null}
        </div>
      </div>

      <div className="rounded-md border border-slate-800 p-3">
        <div className="text-sm font-medium text-slate-300">Card wipe</div>
        <p className="mt-1 text-xs text-slate-500">
          Off by default. Only available when verification passed AND the global setting is on.
        </p>
        {wipe.isSuccess ? (
          <div className="mt-2 text-sm text-emerald-300">
            ✓ Wiped {wipe.data?.deleted ?? 0} files from card.
          </div>
        ) : confirmingWipe ? (
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => wipe.mutate()}
              className="inline-flex items-center gap-2 rounded-md bg-rose-500 px-3 py-1.5 text-sm font-medium text-rose-950 hover:bg-rose-400"
            >
              <Trash2 size={14} /> Confirm wipe
            </button>
            <button
              type="button"
              onClick={() => setConfirmingWipe(false)}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-900"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            disabled={!wipeAllowed}
            onClick={() => setConfirmingWipe(true)}
            className="mt-2 inline-flex items-center gap-2 rounded-md border border-rose-700/60 px-3 py-1.5 text-sm text-rose-300 hover:bg-rose-950/40 disabled:cursor-not-allowed disabled:opacity-40"
            title={
              !wipeAllowed
                ? settings.data?.card_wipe.enabled
                  ? "Verification has not passed yet."
                  : "Card wipe is disabled in Settings."
                : undefined
            }
          >
            <Trash2 size={14} /> Wipe card now
          </button>
        )}
      </div>
    </section>
  );
}
