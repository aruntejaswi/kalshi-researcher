import { create } from "zustand";

export interface PriceTick {
  yes_bid?: number | null;
  yes_ask?: number | null;
  price?: number | null;
  ts?: number | null;
}

interface PriceState {
  prices: Record<string, PriceTick>;
  connected: boolean;
  apply: (batch: Record<string, PriceTick>) => void;
  setConnected: (v: boolean) => void;
}

export const usePriceStore = create<PriceState>((set) => ({
  prices: {},
  connected: false,
  apply: (batch) =>
    set((state) => ({ prices: { ...state.prices, ...batch } })),
  setConnected: (v) => set({ connected: v }),
}));
