import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, SidecarError } from "@/api/client";

/**
 * First-run setup. Three steps per CLAUDE.md §9:
 *   1. Pick local archive root.
 *   2. Connect Composio (API key + Google OAuth).
 *   3. Pick the Google Calendar.
 *
 * Step 2 is interactive: once the API key + auth_config_id are saved in
 * Settings → Integrations, the user clicks "Connect Google" here. The backend
 * initiates OAuth via Composio and returns an auth URL; this page opens it in
 * a new tab and then lets the user confirm once they've authorized.
 */
export function SetupPage() {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["setup-status"],
    queryFn: api.setupStatus,
    refetchInterval: 5000, // poll so the check marks update automatically
  });
  const composioStatus = useQuery({
    queryKey: ["composio-status"],
    queryFn: api.composioStatus,
  });

  const [oauthState, setOauthState] = useState<{
    phase: "idle" | "opened" | "verifying" | "done" | "error";
    connectionRequestId?: string;
    errorMsg?: string;
  }>({ phase: "idle" });

  const startOAuth = useMutation({
    mutationFn: api.startComposio,
    onSuccess: (result) => {
      window.open(result.auth_url, "_blank", "noopener,noreferrer");
      setOauthState({ phase: "opened", connectionRequestId: result.connection_request_id });
    },
    onError: (e) => {
      const msg = e instanceof SidecarError ? extractDetail(e.body) : String(e);
      setOauthState({ phase: "error", errorMsg: `Could not start OAuth: ${msg}` });
    },
  });

  const completeOAuth = useMutation({
    mutationFn: () => api.completeComposio(oauthState.connectionRequestId ?? ""),
    onSuccess: () => {
      setOauthState({ phase: "done" });
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      qc.invalidateQueries({ queryKey: ["composio-status"] });
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e) => {
      const msg = e instanceof SidecarError ? extractDetail(e.body) : String(e);
      setOauthState((prev) => ({ ...prev, phase: "error", errorMsg: `Verification failed: ${msg}` }));
    },
  });

  const s = status.data;
  const cs = composioStatus.data;
  const canStartOAuth = !!cs?.api_key_set && !!cs?.auth_config_id && !startOAuth.isPending;

  const steps = useMemo(
    () => [
      {
        title: "Choose local archive folder",
        done: !!s?.local_root_set,
        body: (
          <p className="text-sm text-slate-400">
            Open <strong>Settings → Storage</strong> and paste the path where you want customer
            archives saved (e.g. <code>/Volumes/FLY_Archive</code>).
          </p>
        ),
      },
      {
        title: "Connect Composio + Google",
        done: !!s?.composio_connected,
        body: (
          <ConnectGoogleBody
            apiKeySet={!!cs?.api_key_set}
            authConfigSet={!!cs?.auth_config_id}
            alreadyConnected={!!s?.composio_connected}
            canStart={canStartOAuth}
            oauthState={oauthState}
            onStart={() => startOAuth.mutate()}
            onVerify={() => completeOAuth.mutate()}
            onRetry={() => setOauthState({ phase: "idle" })}
            isPendingStart={startOAuth.isPending}
            isPendingVerify={completeOAuth.isPending}
          />
        ),
      },
      {
        title: "Select the school calendar",
        done: !!s?.calendar_id_set,
        body: (
          <p className="text-sm text-slate-400">
            Default is <code>primary</code>. Change it in{" "}
            <strong>Settings → Integrations → Calendar ID</strong> if the school uses a named
            calendar.
          </p>
        ),
      },
    ],
    [s, cs, oauthState, canStartOAuth, startOAuth, completeOAuth],
  );

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 p-6">
      <header>
        <h1 className="text-xl font-semibold">First-run setup</h1>
        <p className="text-sm text-slate-400">Walk through these once. Re-runs are safe.</p>
      </header>
      <ol className="flex flex-col gap-4">
        {steps.map((step, i) => (
          <li
            key={step.title}
            className={`rounded-md border p-4 ${
              step.done ? "border-emerald-700/40 bg-emerald-950/20" : "border-slate-800"
            }`}
          >
            <div className="flex items-center gap-3">
              <span
                className={`inline-flex h-7 w-7 items-center justify-center rounded-full text-xs ${
                  step.done
                    ? "bg-emerald-500 text-emerald-950"
                    : "border border-slate-600 text-slate-400"
                }`}
              >
                {step.done ? "✓" : i + 1}
              </span>
              <h2 className="text-sm font-medium">{step.title}</h2>
            </div>
            <div className="mt-2 pl-10">{step.body}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function ConnectGoogleBody({
  apiKeySet,
  authConfigSet,
  alreadyConnected,
  canStart,
  oauthState,
  onStart,
  onVerify,
  onRetry,
  isPendingStart,
  isPendingVerify,
}: {
  apiKeySet: boolean;
  authConfigSet: boolean;
  alreadyConnected: boolean;
  canStart: boolean;
  oauthState: { phase: string; connectionRequestId?: string; errorMsg?: string };
  onStart: () => void;
  onVerify: () => void;
  onRetry: () => void;
  isPendingStart: boolean;
  isPendingVerify: boolean;
}) {
  if (alreadyConnected) {
    return (
      <p className="text-sm text-emerald-400">
        Google account is connected. You can re-connect from Settings → Integrations if needed.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3 text-sm text-slate-400">
      {!apiKeySet || !authConfigSet ? (
        <div>
          <p>Before connecting, complete these steps first:</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-slate-500">
            {!apiKeySet && (
              <li>
                Go to <strong>Settings → Integrations</strong> and save a Composio API key.
              </li>
            )}
            {!authConfigSet && (
              <li>
                Set an Auth Config ID in <strong>Settings → Integrations</strong> (Composio
                dashboard → Auth Configs → New → Google Super).
              </li>
            )}
          </ul>
        </div>
      ) : null}

      {oauthState.phase === "idle" && (
        <button
          type="button"
          disabled={!canStart || isPendingStart}
          onClick={onStart}
          className="w-fit rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-emerald-950 hover:bg-emerald-400 disabled:opacity-40"
        >
          {isPendingStart ? "Opening browser…" : "Connect Google"}
        </button>
      )}

      {oauthState.phase === "opened" && (
        <div className="flex flex-col gap-2">
          <p className="text-slate-300">
            A browser tab opened with the Google authorization page. Complete the sign-in using
            the school's Google account, then come back here.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={isPendingVerify}
              onClick={onVerify}
              className="rounded-md bg-emerald-500 px-4 py-1.5 text-sm font-medium text-emerald-950 hover:bg-emerald-400 disabled:opacity-40"
            >
              {isPendingVerify ? "Verifying…" : "I've authorized — verify connection"}
            </button>
            <button
              type="button"
              onClick={onStart}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-900"
            >
              Re-open browser tab
            </button>
          </div>
        </div>
      )}

      {oauthState.phase === "verifying" && (
        <p className="text-slate-400">Verifying connection with Composio…</p>
      )}

      {oauthState.phase === "done" && (
        <p className="text-emerald-400">Google connected successfully.</p>
      )}

      {oauthState.phase === "error" && (
        <div className="flex flex-col gap-2">
          <p className="text-rose-300">{oauthState.errorMsg}</p>
          <button
            type="button"
            onClick={onRetry}
            className="w-fit rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-900"
          >
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

function extractDetail(body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    return typeof d === "string" ? d : JSON.stringify(d);
  }
  return String(body);
}
