import { create } from "zustand";
import { persist } from "zustand/middleware";

export const MARKET_LIMIT_OPTIONS = [25, 50, 100, 250, 500, 1000] as const;
export type MarketLimit = (typeof MARKET_LIMIT_OPTIONS)[number];

interface SettingsState {
  marketLimit: MarketLimit;
  setMarketLimit: (n: MarketLimit) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      marketLimit: 25,
      setMarketLimit: (n) => set({ marketLimit: n }),
    }),
    { name: "kalshi-settings" },
  ),
);
