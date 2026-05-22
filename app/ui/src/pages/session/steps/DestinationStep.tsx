import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { api, SidecarError } from "@/api/client";
import { useCardStore } from "@/state/card-store";
import { useSessionStore } from "@/state/session-store";

export function DestinationStep({ sessionKey }: { sessionKey: string }) {
  const slice = useSessionStore((s) => s.sessions[sessionKey]);
  const patch = useSessionStore((s) => s.patch);
  const setStep = useSessionStore((s) => s.setStep);
  const lastCard = useCardStore((s) => s.lastCard);
  const setCard = useCardStore((s) => s.setCard);
  const [url, setUrl] = useState(slice?.driveFolderUrl ?? "");

  // Poll cards/current so the step works even when the user arrived here
  // before inserting the card (e.g. via the "New session" button on IdlePage).
  const cardPoll = useQuery({
    queryKey: ["card-current"],
    queryFn: api.cardsCurrent,
    refetchInterval: 2_000,
  });
  useEffect(() => {
    if (cardPoll.data && cardPoll.data.mount_path !== lastCard?.mount_path) {
      setCard(cardPoll.data);
    }
  }, [cardPoll.data, lastCard?.mount_path, setCard]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const recent = settings.data?.drive_recent_folders ?? [];

  const customerName = slice?.customer?.name ?? slice?.walkInName ?? "Walk-in";
  const customerPhone = slice?.customer?.phone ?? null;

  const create = useMutation({
    mutationFn: () =>
      api.createSession({
        customer_name: customerName,
        customer_phone: customerPhone,
        drive_folder_url: url.trim(),
        source_mount_path: lastCard?.mount_path ?? "",
      }),
    onSuccess: (data) => {
      patch(sessionKey, {
        serverSessionId: data.id,
        driveFolderUrl: data.drive_folder_url,
        driveFolderName: data.drive_folder_name,
        sourceMountPath: data.source_mount_path,
      });
      setStep(sessionKey, "ingest");
    },
    onError: (e) => {
      if (e instanceof SidecarError) {
        const body = e.body as { detail?: string; error?: string } | null;
        setErrorMessage(body?.detail ?? body?.error ?? "session_failed");
      } else {
        setErrorMessage(String(e));
      }
    },
  });

  useEffect(() => {
    setErrorMessage(null);
  }, [url]);

  const canContinue = url.trim().length > 0 && !!lastCard?.mount_path;

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold">Where should it go?</h1>
        <p className="text-sm text-slate-400">
          Paste the customer's Google Drive folder URL. We'll verify it before copying.
        </p>
      </header>
      <input
        type="url"
        autoFocus
        placeholder="https://drive.google.com/drive/folders/…"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none"
      />
      {recent.length > 0 ? (
        <div className="rounded-md border border-slate-800 p-3 text-xs text-slate-400">
          <div className="mb-2 text-slate-300">Recent destinations</div>
          <ul className="flex flex-col gap-1">
            {recent.map((u) => (
              <li key={u}>
                <button
                  type="button"
                  className="truncate text-left text-slate-300 hover:text-emerald-300"
                  onClick={() => setUrl(u)}
                  title={u}
                >
                  {u}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!lastCard ? (
        <div className="rounded-md border border-amber-700/40 bg-amber-950/30 p-3 text-sm text-amber-200">
          No card detected yet — insert an SD/GoPro card to enable Continue.
        </div>
      ) : null}
      {errorMessage ? (
        <div className="rounded-md border border-rose-700/50 bg-rose-950/30 p-3 text-sm text-rose-200">
          {errorMessage}
        </div>
      ) : null}

      <div className="flex items-center justify-between pt-2">
        <button
          type="button"
          onClick={() => setStep(sessionKey, "customer")}
          className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-900"
        >
          <ArrowLeft size={14} /> Back
        </button>
        <button
          type="button"
          disabled={!canContinue || create.isPending}
          onClick={() => create.mutate()}
          className="inline-flex items-center gap-2 rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-emerald-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {create.isPending ? "Starting…" : "Continue"} <ArrowRight size={14} />
        </button>
      </div>
    </section>
  );
}
