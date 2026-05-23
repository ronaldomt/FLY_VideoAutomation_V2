import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, Search, UserPlus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, SidecarError } from "@/api/client";
import type { CustomerEvent } from "@/api/types";
import { useCardStore } from "@/state/card-store";
import { useSessionStore } from "@/state/session-store";

export function CustomerStep({ sessionKey }: { sessionKey: string }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<{ name: string; phone: string | null } | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const customers = useQuery({
    queryKey: ["customers-today"],
    queryFn: () => api.customersToday(),
  });

  // Poll for card so the user can insert after picking a customer.
  const cardPoll = useQuery({
    queryKey: ["card-current"],
    queryFn: api.cardsCurrent,
    refetchInterval: 2_000,
  });
  const lastCard = useCardStore((s) => s.lastCard);
  const setCard = useCardStore((s) => s.setCard);
  useEffect(() => {
    if (cardPoll.data && cardPoll.data.mount_path !== lastCard?.mount_path) {
      setCard(cardPoll.data);
    }
  }, [cardPoll.data, lastCard?.mount_path, setCard]);

  const patch = useSessionStore((s) => s.patch);
  const setStep = useSessionStore((s) => s.setStep);

  const filtered = useMemo(() => {
    const rows = customers.data?.events ?? [];
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) => r.name.toLowerCase().includes(q));
  }, [customers.data, query]);

  const card = cardPoll.data ?? lastCard;

  const create = useMutation({
    mutationFn: () => {
      if (!selected || !card?.mount_path) throw new Error("no_customer_or_card");
      return api.createSession({
        customer_name: selected.name,
        customer_phone: selected.phone ?? null,
        source_mount_path: card.mount_path,
      });
    },
    onSuccess: (data) => {
      patch(sessionKey, {
        serverSessionId: data.id,
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

  function selectCustomer(name: string, phone: string | null) {
    setSelected({ name, phone });
    setErrorMessage(null);
  }

  // If a customer is selected, show confirmation view.
  if (selected) {
    return (
      <section className="flex flex-col gap-4">
        <header>
          <h1 className="text-xl font-semibold">Ready to start?</h1>
          <p className="text-sm text-slate-400">Confirm the customer and insert the SD card.</p>
        </header>

        <div className="rounded-md border border-slate-800 p-4">
          <div className="text-sm text-slate-400">Customer</div>
          <div className="mt-1 text-base font-medium">{selected.name}</div>
          {selected.phone ? (
            <div className="mt-0.5 font-mono text-sm text-slate-400">{selected.phone}</div>
          ) : null}
        </div>

        <div
          className={`rounded-md border p-3 text-sm ${
            card?.mount_path
              ? "border-emerald-700/40 bg-emerald-950/20 text-emerald-200"
              : "border-amber-700/40 bg-amber-950/30 text-amber-200"
          }`}
        >
          {card?.mount_path
            ? `Card detected: ${card.mount_path}`
            : "No card detected — insert SD card or GoPro to continue."}
        </div>

        {errorMessage ? (
          <div className="rounded-md border border-rose-700/50 bg-rose-950/30 p-3 text-sm text-rose-200">
            {errorMessage}
          </div>
        ) : null}

        <div className="flex items-center justify-between pt-2">
          <button
            type="button"
            onClick={() => {
              setSelected(null);
              setErrorMessage(null);
            }}
            className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-900"
          >
            Change customer
          </button>
          <button
            type="button"
            disabled={!card?.mount_path || create.isPending}
            onClick={() => create.mutate()}
            className="inline-flex items-center gap-2 rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-emerald-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {create.isPending ? "Starting…" : "Start ingest"} <ArrowRight size={14} />
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold">Who's the customer?</h1>
        <p className="text-sm text-slate-400">
          Pick from today's calendar or add a walk-in.
        </p>
      </header>
      <div className="relative">
        <Search size={14} className="absolute left-3 top-2.5 text-slate-500" />
        <input
          type="search"
          placeholder="Search by name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full rounded-md border border-slate-700 bg-slate-900 py-2 pl-9 pr-3 text-sm placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none"
        />
      </div>
      <ul className="divide-y divide-slate-800 overflow-hidden rounded-md border border-slate-800">
        <li>
          <button
            type="button"
            className="flex w-full items-center gap-3 px-4 py-3 text-left text-sm hover:bg-slate-900"
            onClick={() => selectCustomer(query.trim() || "Walk-in", null)}
          >
            <UserPlus size={16} className="text-emerald-400" />
            <span className="font-medium text-emerald-300">
              + New (walk-in){query.trim() ? `: ${query.trim()}` : ""}
            </span>
          </button>
        </li>
        {customers.isLoading ? (
          <li className="px-4 py-6 text-center text-sm text-slate-500">Loading customers…</li>
        ) : customers.isError ? (
          <li className="px-4 py-8 text-center text-sm">
            {customers.error instanceof SidecarError && customers.error.status === 412 ? (
              <span className="text-amber-300">
                Google Calendar not connected.{" "}
                <a href="/settings" className="underline hover:text-amber-200">
                  Go to Settings → Integrations → Reconnect Google
                </a>
              </span>
            ) : (
              <span className="text-rose-400">
                Failed to load calendar — check the backend terminal for details.
              </span>
            )}
          </li>
        ) : filtered.length === 0 ? (
          <li className="px-4 py-6 text-center text-sm text-slate-500">
            No matches. Add a walk-in above.
          </li>
        ) : (
          filtered.map((c: CustomerEvent, i: number) => (
            <li key={`${c.time}-${c.name}-${i}`}>
              <button
                type="button"
                className="flex w-full items-center justify-between px-4 py-3 text-left text-sm hover:bg-slate-900"
                onClick={() => selectCustomer(c.name, c.phone ?? null)}
              >
                <span>
                  <span className="font-mono text-slate-400">{c.time}</span> —{" "}
                  <span className="font-medium">{c.name}</span>
                </span>
                {c.type ? (
                  <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                    {c.type}
                  </span>
                ) : null}
              </button>
            </li>
          ))
        )}
      </ul>
    </section>
  );
}
