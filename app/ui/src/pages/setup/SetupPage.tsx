import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "@/api/client";

/**
 * First-run setup. Three steps per CLAUDE.md §9:
 *   1. Pick local archive root.
 *   2. Connect Composio (API key + Google OAuth).
 *   3. Pick the Google Calendar.
 *
 * For v1 the wizard reads `/setup/status` and shows progress. The actual
 * Composio OAuth handoff is BLOCKED on a human action — see BLOCKERS.md.
 */
export function SetupPage() {
  const status = useQuery({ queryKey: ["setup-status"], queryFn: api.setupStatus });

  const steps = useMemo(
    () => [
      {
        title: "Choose local archive folder",
        done: !!status.data?.local_root_set,
        body: (
          <p className="text-sm text-slate-400">
            Open <strong>Settings → Storage</strong> and paste the path where you want customer
            archives saved (e.g. <code>/Volumes/FLY_Archive</code>).
          </p>
        ),
      },
      {
        title: "Connect Composio + Google",
        done: !!status.data?.composio_connected,
        body: (
          <div className="text-sm text-slate-400">
            <p>
              The agent cannot complete this autonomously — see{" "}
              <code>BLOCKERS.md</code> in the repo root.
            </p>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs text-slate-500">
              <li>Sign up at app.composio.dev and create an API key.</li>
              <li>
                Paste the key into <code>settings.json</code> (UI input lands when the
                Composio wiring goes live).
              </li>
              <li>Run the Google OAuth flow in your browser to authorize the school account.</li>
            </ol>
          </div>
        ),
      },
      {
        title: "Select the school calendar",
        done: !!status.data?.calendar_id_set,
        body: (
          <p className="text-sm text-slate-400">
            Default is <code>primary</code>. Change it in{" "}
            <strong>Settings → Integrations → Calendar ID</strong> if the school uses a named
            calendar.
          </p>
        ),
      },
    ],
    [status.data],
  );

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 p-6">
      <header>
        <h1 className="text-xl font-semibold">First-run setup</h1>
        <p className="text-sm text-slate-400">Walk through these once. Re-runs are safe.</p>
      </header>
      <ol className="flex flex-col gap-4">
        {steps.map((s, i) => (
          <li
            key={s.title}
            className={`rounded-md border p-4 ${
              s.done ? "border-emerald-700/40 bg-emerald-950/20" : "border-slate-800"
            }`}
          >
            <div className="flex items-center gap-3">
              <span
                className={`inline-flex h-7 w-7 items-center justify-center rounded-full text-xs ${
                  s.done ? "bg-emerald-500 text-emerald-950" : "border border-slate-600 text-slate-400"
                }`}
              >
                {s.done ? "✓" : i + 1}
              </span>
              <h2 className="text-sm font-medium">{s.title}</h2>
            </div>
            <div className="mt-2 pl-10">{s.body}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}
