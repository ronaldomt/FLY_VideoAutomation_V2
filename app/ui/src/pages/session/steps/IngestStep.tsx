import { api } from "@/api/client";
import { useSessionStore } from "@/state/session-store";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

// How long an SSE error must persist before we escalate from the muted
// "Reconnecting…" badge to the red error banner. EventSource auto-reconnects
// silently, and most disconnects (Tauri webview idle, OS sleep, brief
// network blip) resolve well under this threshold; the work continues on
// the backend regardless.
const RECONNECT_GRACE_MS = 10_000;

export function IngestStep({ sessionKey }: { sessionKey: string }) {
  const slice = useSessionStore((s) => s.sessions[sessionKey]);
  const appendProgress = useSessionStore((s) => s.appendProgress);
  const replaceProgressSnapshot = useSessionStore((s) => s.replaceProgressSnapshot);
  const patch = useSessionStore((s) => s.patch);
  const setStep = useSessionStore((s) => s.setStep);
  const reset = useSessionStore((s) => s.reset);
  const navigate = useNavigate();
  const [sseError, setSseError] = useState<string | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const errorSinceRef = useRef<number | null>(null);
  const escalationTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!slice?.serverSessionId) return;
    const serverSessionId = slice.serverSessionId;

    const clearEscalation = () => {
      if (escalationTimerRef.current !== null) {
        window.clearTimeout(escalationTimerRef.current);
        escalationTimerRef.current = null;
      }
    };

    const teardown = api.subscribeEvents(serverSessionId, {
      onOpen: () => {
        // EventSource opened (first connect OR auto-reconnect after error).
        // The backend will immediately re-emit a DB snapshot of phase state;
        // wipe stale progress so the snapshot can repopulate cleanly without
        // accumulating duplicates from previous connections.
        replaceProgressSnapshot(sessionKey, []);
        errorSinceRef.current = null;
        clearEscalation();
        setReconnecting(false);
        setSseError(null);
      },
      onProgress: (e) => appendProgress(sessionKey, e),
      onVerification: (e) => patch(sessionKey, { verification: e }),
      onDone: () => setStep(sessionKey, "done"),
      onCancelled: () => {
        reset(sessionKey);
        navigate("/");
      },
      onPipelineError: (msg) => {
        const friendly = msg.startsWith("disk_full")
          ? "Disk is full — free up space on the archive drive and retry."
          : msg;
        clearEscalation();
        setReconnecting(false);
        setSseError(friendly);
      },
      onError: () => {
        // EventSource will auto-reconnect; treat as a soft "reconnecting"
        // state and only escalate to a hard error if it persists.
        if (errorSinceRef.current === null) {
          errorSinceRef.current = Date.now();
          setReconnecting(true);
          escalationTimerRef.current = window.setTimeout(() => {
            setSseError(
              "Lost connection to the backend — copy/upload may still be running. " +
                "Check the Logs page if this persists.",
            );
            setReconnecting(false);
          }, RECONNECT_GRACE_MS);
        }
      },
    });

    return () => {
      clearEscalation();
      teardown();
    };
  }, [
    slice?.serverSessionId,
    sessionKey,
    appendProgress,
    replaceProgressSnapshot,
    patch,
    setStep,
    reset,
    navigate,
  ]);

  const events = slice?.progress ?? [];
  const byPhase = events.reduce<
    Record<string, { current: number; total: number; message: string | null | undefined }>
  >((acc, e) => {
    acc[e.phase] = { current: e.current, total: e.total, message: e.message };
    return acc;
  }, {});
  const phases = ["copy_media", "extract_frames", "upload_to_drive"];

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold">Ingest in progress</h1>
        <p className="text-sm text-slate-400">
          Don't unmount the card. You can leave the room — uploads finish in the background.
        </p>
      </header>
      {reconnecting && !sseError ? (
        <div className="rounded-md border border-amber-700/40 bg-amber-950/20 p-3 text-sm text-amber-200">
          Reconnecting… the session keeps running on the backend.
        </div>
      ) : null}
      {sseError ? (
        <div className="rounded-md border border-rose-700/50 bg-rose-950/30 p-3 text-sm text-rose-200">
          {sseError}
        </div>
      ) : null}
      <ul className="flex flex-col gap-3">
        {phases.map((p) => {
          const s = byPhase[p];
          const pct = s && s.total > 0 ? Math.round((s.current / s.total) * 100) : 0;
          return (
            <li key={p} className="rounded-md border border-slate-800 p-3">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{labelFor(p)}</span>
                <span className="text-slate-400">{s ? `${s.current}/${s.total}` : "—"}</span>
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
