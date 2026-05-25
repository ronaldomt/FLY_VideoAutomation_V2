import { api } from "@/api/client";
import { friendlyError } from "@/api/error-messages";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Trash2 } from "lucide-react";

/**
 * Lists recent failed (and cancelled) sessions on the Idle page so the
 * operator can see at a glance what went wrong without opening the Logs
 * page. "Clear all failed" removes the DB rows; it does NOT delete the
 * associated local folders — that's a deliberately separate, scarier
 * action the operator triggers from Finder.
 */
export function FailedSessionsCard() {
  const qc = useQueryClient();
  const failed = useQuery({
    queryKey: ["sessions-recent", "failed"],
    queryFn: () => api.recentSessions({ status: "failed", limit: 20 }),
    refetchInterval: 10_000,
  });

  const clear = useMutation({
    mutationFn: () => api.clearFailedSessions(0),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions-recent"] }),
  });

  const rows = failed.data ?? [];
  if (rows.length === 0) return null;

  return (
    <div className="rounded-lg border border-rose-900/40 bg-rose-950/10 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-rose-200">
          <AlertTriangle size={14} />
          <span className="font-medium">
            {rows.length} failed session{rows.length === 1 ? "" : "s"} awaiting cleanup
          </span>
        </div>
        <button
          type="button"
          onClick={() => clear.mutate()}
          disabled={clear.isPending}
          className="inline-flex items-center gap-1.5 rounded-md border border-rose-800/60 px-2.5 py-1 text-xs text-rose-200 hover:bg-rose-900/30 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Trash2 size={12} />
          {clear.isPending ? "Clearing…" : "Clear all failed"}
        </button>
      </div>
      <ul className="mt-3 divide-y divide-rose-900/30">
        {rows.map((s) => (
          <li key={s.id} className="py-2">
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-sm font-medium text-slate-200">{s.customer_name}</span>
              <span className="font-mono text-xs text-slate-500">
                {formatTimestamp(s.created_at)}
              </span>
            </div>
            <div className="mt-0.5 text-xs text-rose-300">{friendlyError(s.error)}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
