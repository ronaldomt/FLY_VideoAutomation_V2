import { useMemo } from "react";
import { useParams } from "react-router-dom";
import { CustomerStep } from "./steps/CustomerStep";
import { IngestStep } from "./steps/IngestStep";
import { DoneStep } from "./steps/DoneStep";
import { useSessionStore } from "@/state/session-store";
import type { SessionStep } from "@/state/session-store";

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
  useSessionStore((s) => s.ensure(key));

  const step: SessionStep = slice?.step ?? "customer";

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
      <Stepper current={step} />
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
