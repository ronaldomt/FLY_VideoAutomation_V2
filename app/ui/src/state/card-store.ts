import { create } from "zustand";
import type { CardDetected } from "@/api/types";

interface CardStore {
  lastCard: CardDetected | null;
  setCard(card: CardDetected | null): void;
}

export const useCardStore = create<CardStore>((set) => ({
  lastCard: null,
  setCard: (card) => set({ lastCard: card }),
}));
