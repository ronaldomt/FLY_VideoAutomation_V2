import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CustomerStep } from "./steps/CustomerStep";
import { IngestStep } from "./steps/IngestStep";
import { DoneStep } from "./steps/DoneStep";
import { useSessionStore } from "@/state/session-store";
import type { SessionStep } from "@/state/session-store";
import { api } from "@/api/client";

/**
 * The unified Session route. A single page that walks the operator through
 * Customer → Ingest → Done. Step transitions are driven by the Zustand store,
 * not the URL — the URL stays on `/session/:sessionId` throughout.
 * Drive destination is a base folder configured once in Settings.
 * See CLAUDE.md §9.
 */
export function SessionPage() {
  const { sessionId } = useParams();
  const key = sessionId ?? "draft";
  const slice = useSessionStore((s) => s.sessions[key]);
  const reset = useSessionStore((s) => s.reset);
  const existingStep = useSessionStore((s) => s.sessions[key]?.step);
  useSessionStore((s) => s.ensure(key));
  const navigate = useNavigate();
  const [confirmCancel, setConfirmCancel] = useState(false);

  // Safety net: if arriving at /session (no explicit sessionId) while the draft
  // slot is already at "done", wipe it so the operator gets a clean start.
  useEffect(() => {
    if (!sessionId && existingStep === "done") {
      reset("draft");
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const step: SessionStep = slice?.step ?? "customer";

  // Reset confirm state whenever step changes.
  useEffect(() => {
    setConfirmCancel(false);
  }, [step]);

  const handleCancel = () => {
    const serverId = slice?.serverSessionId;
    if (serverId) {
      api.cancelSession(serverId).catch(() => {});
    }
    reset(key);
    navigate("/");
  };

  const body = useMemo(() => {
    switch (step) {
      case "customer":
        return <CustomerStep sessionKey={key} />;
      case "ingest":
        return <IngestStep sessionKey={key} />;
      case "done":
        return <DoneStep sessionKey={key} />;
      default:
        return null;
    }
  }, [step, key]);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <Stepper current={step} />
        {step !== "done" && (
          <div className="flex items-center gap-2">
            {confirmCancel ? (
              <>
                <button
                  onClick={handleCancel}
                  className="rounded-md bg-rose-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-600"
                >
                  Yes, cancel
                </button>
                <button
                  onClick={() => setConfirmCancel(false)}
                  className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:border-slate-500"
                >
                  Keep going
                </button>
              </>
            ) : (
              <button
                onClick={() => setConfirmCancel(true)}
                className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-400 hover:border-rose-700/60 hover:text-rose-400"
              >
                Cancel session
              </button>
            )}
          </div>
        )}
      </div>
      {body}
    </div>
  );
}

const STEPS: { id: SessionStep; label: string }[] = [
  { id: "customer", label: "Customer" },
  { id: "ingest", label: "Ingest" },
  { id: "done", label: "Done" },
];

function Stepper({ current }: { current: SessionStep }) {
  const idx = STEPS.findIndex((s) => s.id === current);
  return (
    <ol className="flex items-center gap-2 text-sm">
      {STEPS.map((s, i) => {
        const active = i === idx;
        const done = i < idx;
        return (
          <li key={s.id} className="flex items-center gap-2">
            <span
              className={`inline-flex h-7 w-7 items-center justify-center rounded-full border ${
                active
                  ? "border-emerald-400 text-emerald-300"
                  : done
                    ? "border-emerald-700 bg-emerald-700 text-emerald-100"
                    : "border-slate-700 text-slate-500"
              }`}
            >
              {i + 1}
            </span>
            <span className={active ? "font-medium" : "text-slate-400"}>{s.label}</span>
            {i < STEPS.length - 1 ? <span className="px-1 text-slate-700">›</span> : null}
          </li>
        );
      })}
    </ol>
  );
}
