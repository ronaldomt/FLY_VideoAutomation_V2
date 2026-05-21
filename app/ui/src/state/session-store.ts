/**
 * Per-session UI state. The route `/session/:sessionId` reads/writes the slice
 * keyed by `sessionId` so the operator can step backwards/forwards through
 * Customer → Destination → Ingest → Done without the URL changing.
 */

import { create } from "zustand";
import type { CustomerEvent, ProgressEvent, VerificationReport } from "@/api/types";

export type SessionStep = "customer" | "destination" | "ingest" | "done";

interface SessionSlice {
  step: SessionStep;
  customer: CustomerEvent | null;
  walkInName: string | null;
  driveFolderUrl: string;
  driveFolderName: string | null;
  sourceMountPath: string | null;
  serverSessionId: string | null;
  progress: ProgressEvent[];
  verification: VerificationReport | null;
  shareUrl: string | null;
}

interface SessionStoreState {
  sessions: Record<string, SessionSlice>;
  ensure(id: string): SessionSlice;
  patch(id: string, p: Partial<SessionSlice>): void;
  setStep(id: string, step: SessionStep): void;
  appendProgress(id: string, e: ProgressEvent): void;
  reset(id: string): void;
}

const emptySlice = (): SessionSlice => ({
  step: "customer",
  customer: null,
  walkInName: null,
  driveFolderUrl: "",
  driveFolderName: null,
  sourceMountPath: null,
  serverSessionId: null,
  progress: [],
  verification: null,
  shareUrl: null,
});

export const useSessionStore = create<SessionStoreState>((set, get) => ({
  sessions: {},
  ensure(id) {
    const s = get().sessions[id];
    if (s) return s;
    const slice = emptySlice();
    set((state) => ({ sessions: { ...state.sessions, [id]: slice } }));
    return slice;
  },
  patch(id, p) {
    set((state) => {
      const existing = state.sessions[id] ?? emptySlice();
      return { sessions: { ...state.sessions, [id]: { ...existing, ...p } } };
    });
  },
  setStep(id, step) {
    set((state) => {
      const existing = state.sessions[id] ?? emptySlice();
      return { sessions: { ...state.sessions, [id]: { ...existing, step } } };
    });
  },
  appendProgress(id, e) {
    set((state) => {
      const existing = state.sessions[id] ?? emptySlice();
      return {
        sessions: {
          ...state.sessions,
          [id]: { ...existing, progress: [...existing.progress, e] },
        },
      };
    });
  },
  reset(id) {
    set((state) => {
      const { [id]: _removed, ...rest } = state.sessions;
      return { sessions: rest };
    });
  },
}));
