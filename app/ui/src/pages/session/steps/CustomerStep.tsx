import { useQuery } from "@tanstack/react-query";
import { Search, UserPlus } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "@/api/client";
import { useSessionStore } from "@/state/session-store";

export function CustomerStep({ sessionKey }: { sessionKey: string }) {
  const [query, setQuery] = useState("");
  const customers = useQuery({
    queryKey: ["customers-today"],
    queryFn: () => api.customersToday(),
  });
  const patch = useSessionStore((s) => s.patch);
  const setStep = useSessionStore((s) => s.setStep);

  const filtered = useMemo(() => {
    const rows = customers.data?.events ?? [];
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) => r.name.toLowerCase().includes(q));
  }, [customers.data, query]);

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
            onClick={() => {
              const name = query.trim() || "Walk-in";
              patch(sessionKey, {
                customer: null,
                walkInName: name,
              });
              setStep(sessionKey, "destination");
            }}
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
          <li className="px-4 py-6 text-center text-sm text-rose-400">
            Could not load customers. Is Composio connected?
          </li>
        ) : filtered.length === 0 ? (
          <li className="px-4 py-6 text-center text-sm text-slate-500">
            No matches. Add a walk-in above.
          </li>
        ) : (
          filtered.map((c, i) => (
            <li key={`${c.time}-${c.name}-${i}`}>
              <button
                type="button"
                className="flex w-full items-center justify-between px-4 py-3 text-left text-sm hover:bg-slate-900"
                onClick={() => {
                  patch(sessionKey, { customer: c, walkInName: null });
                  setStep(sessionKey, "destination");
                }}
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
