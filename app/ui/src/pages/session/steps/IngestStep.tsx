import { useEffect, useRef } from "react";
import { api } from "@/api/client";
import { useSessionStore } from "@/state/session-store";

export function IngestStep({ sessionKey }: { sessionKey: string }) {
  const slice = useSessionStore((s) => s.sessions[sessionKey]);
  const appendProgress = useSessionStore((s) => s.appendProgress);
  const patch = useSessionStore((s) => s.patch);
  const setStep = useSessionStore((s) => s.setStep);
  const subscribed = useRef(false);

  useEffect(() => {
    if (subscribed.current || !slice?.serverSessionId) return;
    subscribed.current = true;
    const teardown = api.subscribeEvents(slice.serverSessionId, {
      onProgress: (e) => appendProgress(sessionKey, e),
      onVerification: (e) => patch(sessionKey, { verification: e }),
      onDone: () => {
        // Move to Done once verification arrives.
        setStep(sessionKey, "done");
      },
      onError: () => {
        // SSE error — leave UI; user can retry from Done step.
      },
    });
    return teardown;
  }, [slice?.serverSessionId, sessionKey, appendProgress, patch, setStep]);

  const events = slice?.progress ?? [];
  const byPhase = events.reduce<Record<string, { current: number; total: number; message: string | null | undefined }>>(
    (acc, e) => {
      acc[e.phase] = { current: e.current, total: e.total, message: e.message };
      return acc;
    },
    {},
  );
  const phases = ["copy_media", "extract_frames", "upload_to_drive"];

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold">Ingest in progress</h1>
        <p className="text-sm text-slate-400">
          Don't unmount the card. You can leave the room — uploads finish in the background.
        </p>
      </header>
      <ul className="flex flex-col gap-3">
        {phases.map((p) => {
          const s = byPhase[p];
          const pct = s && s.total > 0 ? Math.round((s.current / s.total) * 100) : 0;
          return (
            <li key={p} className="rounded-md border border-slate-800 p-3">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{labelFor(p)}</span>
                <span className="text-slate-400">
                  {s ? `${s.current}/${s.total}` : "—"}
                </span>
              </div>
              <div className="mt-2 h-1.5 w-full rounded bg-slate-800">
                <div
                  className="h-1.5 rounded bg-emerald-500 transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
              {s?.message ? (
                <div className="mt-1.5 truncate font-mono text-xs text-slate-500">{s.message}</div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function labelFor(phase: string): string {
  switch (phase) {
    case "copy_media":
      return "Copying media";
    case "extract_frames":
      return "Extracting frames";
    case "upload_to_drive":
      return "Uploading to Drive";
    case "verify_upload":
      return "Verifying";
    default:
      return phase;
  }
}
