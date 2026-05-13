import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { usePriceStore } from "@/store/priceStore";
import { MARKET_LIMIT_OPTIONS, useSettingsStore, type MarketLimit } from "@/store/settingsStore";

interface Props {
  onClearResults: () => void;
}

export function SettingsMenu({ onClearResults }: Props) {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const marketLimit = useSettingsStore((s) => s.marketLimit);
  const setMarketLimit = useSettingsStore((s) => s.setMarketLimit);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  const clearCache = () => {
    qc.clear();
    onClearResults();
    usePriceStore.setState({ prices: {} });
    try {
      sessionStorage.clear();
      localStorage.removeItem("kalshi-cache");
    } catch {
      /* ignore */
    }
    setOpen(false);
  };

  const onLimitChange = (n: MarketLimit) => {
    setMarketLimit(n);
    qc.invalidateQueries({ queryKey: ["markets"] });
  };

  return (
    <div className="relative" ref={ref}>
      <Button size="sm" variant="outline" onClick={() => setOpen((v) => !v)}>
        Settings
      </Button>
      {open && (
        <div className="absolute right-0 z-10 mt-2 w-72 rounded-md border border-border bg-card p-3 shadow-lg">
          <div className="mb-3">
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Markets per request
            </label>
            <select
              value={marketLimit}
              onChange={(e) => onLimitChange(Number(e.target.value) as MarketLimit)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {MARKET_LIMIT_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n.toLocaleString()}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-muted-foreground">
              Higher = more variety but slower first load and bigger category fetch.
            </p>
          </div>

          <div className="border-t border-border pt-2">
            <button
              type="button"
              className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-muted"
              onClick={clearCache}
            >
              Clear Local Cache
              <span className="block text-xs text-muted-foreground">
                Query cache, prices, and on-screen results
              </span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
