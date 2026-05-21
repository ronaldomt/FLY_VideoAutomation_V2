import { useQuery } from "@tanstack/react-query";
import { Disc3, Plus } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { api } from "@/api/client";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { useCardStore } from "@/state/card-store";

/**
 * Empty state. Polls `/cards/current`. When a card insert event arrives, the
 * Session page opens automatically (assuming `ui.auto_focus_on_card_insert`).
 * The button below is the manual fallback path for the operator.
 */
export function IdlePage() {
  const navigate = useNavigate();
  const lastCard = useCardStore((s) => s.lastCard);
  const setCard = useCardStore((s) => s.setCard);

  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const card = useQuery({
    queryKey: ["card-current"],
    queryFn: api.cardsCurrent,
    refetchInterval: 2_000,
  });

  useEffect(() => {
    if (card.data && card.data.mount_path !== lastCard?.mount_path) {
      setCard(card.data);
      if (settings.data?.ui.auto_focus_on_card_insert !== false) {
        navigate("/session");
      }
    }
  }, [card.data, lastCard?.mount_path, setCard, navigate, settings.data]);

  return (
    <EmptyState
      title="Insert a card to begin"
      description="The app will jump to the customer picker automatically. You can also start a new session manually."
    >
      <div className="mt-4 flex items-center gap-3">
        <Link
          to="/session"
          className="inline-flex items-center gap-2 rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-emerald-950 hover:bg-emerald-400"
        >
          <Plus size={16} /> New session
        </Link>
      </div>

      <div className="mt-10 grid w-full grid-cols-1 gap-3 text-left">
        <div className="rounded-lg border border-slate-800 p-4">
          <div className="flex items-center gap-2 text-sm text-slate-300">
            <Disc3 size={14} /> Last card
          </div>
          <div className="mt-1 text-sm text-slate-100">
            {lastCard ? (
              <>
                {lastCard.label ?? "(no label)"} — <code className="text-xs">{lastCard.mount_path}</code>
                {lastCard.already_ingested_within_hour ? (
                  <span className="ml-2 text-xs text-amber-300">
                    Already ingested in the last hour
                  </span>
                ) : null}
              </>
            ) : (
              <span className="text-slate-500">No card detected yet.</span>
            )}
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 p-4">
          <div className="text-sm text-slate-300">Backend status</div>
          <div className="mt-1">
            <StatusBadge
              status={settings.isError ? "error" : settings.data ? "ok" : "running"}
              label={
                settings.isError
                  ? "Sidecar unreachable"
                  : settings.data
                    ? `Connected · archive: ${settings.data.local_root ?? "(not set)"}`
                    : "Connecting…"
              }
            />
          </div>
        </div>
      </div>
    </EmptyState>
  );
}
