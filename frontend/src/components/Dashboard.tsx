import { Fragment, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { usePriceStore } from "@/store/priceStore";
import { useSkillStore } from "@/store/skillStore";
import { useSettingsStore } from "@/store/settingsStore";
import { usePriceSocket } from "@/hooks/usePriceSocket";
import { formatPrice, formatEdge } from "@/lib/utils";
import { SkillSidebar } from "./SkillSidebar";
import { AnalysisRow, type AnalysisResponse } from "./AnalysisRow";
import { ProgressBar } from "./ProgressBar";
import { SettingsMenu } from "./SettingsMenu";

interface Market {
  ticker: string;
  title: string;
  category?: string;
  yes_bid?: number;   // dollars 0..1 (V2)
  yes_ask?: number;   // dollars 0..1 (V2)
}

const ALL_CATEGORIES = "__all__";

interface BatchSnapshot {
  id: string;
  total: number;
  pending: string[];
  in_progress: string[];
  completed: string[];
  failed: Record<string, string>;
  results: Record<string, AnalysisResponse>;
  status: "running" | "done" | "cancelled";
  progress: number;
}

const COLUMN_COUNT = 5;

async function fetchMarkets(limit: number): Promise<Market[]> {
  const r = await fetch(`/api/markets?limit=${limit}`);
  if (!r.ok) throw new Error(`markets ${r.status}`);
  const j = await r.json();
  return j.markets ?? [];
}

async function postAnalyze(body: {
  ticker: string;
  skills: string[];
  market_price: number;
  bankroll: number;
}): Promise<AnalysisResponse> {
  const r = await fetch("/api/analyze", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`analyze ${r.status}: ${await r.text()}`);
  return r.json();
}

async function postBatch(body: {
  tickers: string[];
  skills: string[];
  bankroll: number;
  market_prices: Record<string, number>;
}): Promise<BatchSnapshot> {
  const r = await fetch("/api/batch/analyze", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`batch ${r.status}: ${await r.text()}`);
  return r.json();
}

function LivePriceCell({ ticker, fallback }: { ticker: string; fallback?: number }) {
  const tick = usePriceStore((s) => s.prices[ticker]);
  const value = tick?.yes_bid ?? tick?.price ?? fallback;
  const isLive = tick != null;
  return (
    <span className={isLive ? "font-mono text-emerald-400" : "font-mono text-muted-foreground"}>
      {formatPrice(value)}
      {isLive && <span className="ml-2 text-xs uppercase tracking-wider">live</span>}
    </span>
  );
}

function currentPrice(m: Market, tick?: { yes_bid?: number | null; price?: number | null }): number | undefined {
  return tick?.yes_bid ?? tick?.price ?? m.yes_bid;
}

type SortKey = "ticker" | "edge";
type SortDir = "asc" | "desc";

export function Dashboard() {
  usePriceSocket();
  const connected = usePriceStore((s) => s.connected);
  const prices = usePriceStore((s) => s.prices);
  const activeSkills = useSkillStore((s) => s.active);
  const marketLimit = useSettingsStore((s) => s.marketLimit);

  const { data, isLoading, error } = useQuery({
    queryKey: ["markets", marketLimit],
    queryFn: () => fetchMarkets(marketLimit),
  });
  const [results, setResults] = useState<Record<string, AnalysisResponse>>({});
  const [sortKey, setSortKey] = useState<SortKey>("ticker");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [category, setCategory] = useState<string>(ALL_CATEGORIES);

  const [batchId, setBatchId] = useState<string | null>(null);
  const [batch, setBatch] = useState<BatchSnapshot | null>(null);

  const analyzeMut = useMutation({
    mutationFn: postAnalyze,
    onSuccess: (res) => setResults((prev) => ({ ...prev, [res.ticker]: res })),
  });

  const batchMut = useMutation({
    mutationFn: postBatch,
    onSuccess: (snap) => {
      setBatchId(snap.id);
      setBatch(snap);
    },
  });

  // Poll batch status until done.
  useEffect(() => {
    if (!batchId || batch?.status === "done") return;
    const i = setInterval(async () => {
      try {
        const r = await fetch(`/api/batch/${batchId}`);
        if (!r.ok) return;
        const snap: BatchSnapshot = await r.json();
        setBatch(snap);
        if (Object.keys(snap.results).length) {
          setResults((prev) => ({ ...prev, ...snap.results }));
        }
        if (snap.status === "done") clearInterval(i);
      } catch {
        /* keep polling */
      }
    }, 600);
    return () => clearInterval(i);
  }, [batchId, batch?.status]);

  const runAnalyze = (m: Market) => {
    const price = currentPrice(m, prices[m.ticker]);
    if (price == null) return;
    analyzeMut.mutate({
      ticker: m.ticker,
      skills: Array.from(activeSkills),
      market_price: price,
      bankroll: 1000,
    });
  };

  const runBatch = () => {
    if (!data?.length || activeSkills.size === 0) return;
    const market_prices: Record<string, number> = {};
    for (const m of data) {
      const p = currentPrice(m, prices[m.ticker]);
      if (p != null) market_prices[m.ticker] = p;
    }
    batchMut.mutate({
      tickers: data.map((m) => m.ticker),
      skills: Array.from(activeSkills),
      bankroll: 1000,
      market_prices,
    });
  };

  const categories = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.map((m) => m.category || "Uncategorized"))).sort();
  }, [data]);

  const sorted = useMemo(() => {
    if (!data) return [];
    const filtered =
      category === ALL_CATEGORIES
        ? [...data]
        : data.filter((m) => (m.category || "Uncategorized") === category);
    const factor = sortDir === "asc" ? 1 : -1;
    filtered.sort((a, b) => {
      if (sortKey === "ticker") return a.ticker.localeCompare(b.ticker) * factor;
      const ea = results[a.ticker]?.edge;
      const eb = results[b.ticker]?.edge;
      if (ea == null && eb == null) return 0;
      if (ea == null) return 1;
      if (eb == null) return -1;
      return (ea - eb) * factor;
    });
    return filtered;
  }, [data, sortKey, sortDir, results, category]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "edge" ? "desc" : "asc");
    }
  };

  const clearResults = () => {
    setResults({});
    setBatch(null);
    setBatchId(null);
  };

  const batchInProgress = batch && batch.status !== "done";

  return (
    <div className="flex min-h-screen">
      <SkillSidebar />
      <main className="flex-1 p-8">
        <header className="mb-6 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">KalshiResearcher</h1>
            <p className="text-sm text-muted-foreground">Live market dashboard</p>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="h-9 rounded-md border border-border bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              title="Filter by category"
            >
              <option value={ALL_CATEGORIES}>All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <span className={`inline-block h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-zinc-500"}`} />
            <span className="text-muted-foreground">{connected ? "feed connected" : "feed offline"}</span>
            <Button
              size="sm"
              onClick={runBatch}
              disabled={!data?.length || activeSkills.size === 0 || !!batchInProgress}
              title={activeSkills.size === 0 ? "Select at least one skill" : "Run analysis on every visible market"}
            >
              {batchInProgress ? "Running…" : "Batch Analyze"}
            </Button>
            <SettingsMenu onClearResults={clearResults} />
          </div>
        </header>

        {batch && (
          <div className="mb-4">
            <ProgressBar
              total={batch.total}
              completed={batch.completed.length}
              failed={Object.keys(batch.failed).length}
              inProgress={batch.in_progress.length}
              status={batch.status}
            />
          </div>
        )}

        <div className="rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHead label="Ticker" sortKey="ticker" current={sortKey} dir={sortDir} onClick={toggleSort} className="w-[200px]" />
                <TableHead>Title</TableHead>
                <TableHead className="w-[160px] text-right">Live Price</TableHead>
                <SortableHead label="Edge" sortKey="edge" current={sortKey} dir={sortDir} onClick={toggleSort} className="w-[100px] text-right" />
                <TableHead className="w-[120px] text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell colSpan={COLUMN_COUNT} className="text-center text-muted-foreground">
                    Loading markets…
                  </TableCell>
                </TableRow>
              )}
              {error && (
                <TableRow>
                  <TableCell colSpan={COLUMN_COUNT} className="text-center text-red-400">
                    {(error as Error).message}
                  </TableCell>
                </TableRow>
              )}
              {sorted.map((m) => {
                const pending =
                  analyzeMut.isPending && analyzeMut.variables?.ticker === m.ticker;
                const result = results[m.ticker];
                return (
                  <Fragment key={m.ticker}>
                    <TableRow>
                      <TableCell className="font-mono text-xs">{m.ticker}</TableCell>
                      <TableCell>{m.title}</TableCell>
                      <TableCell className="text-right">
                        <LivePriceCell ticker={m.ticker} fallback={m.yes_bid} />
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        <span className={edgeClass(result?.edge)}>{formatEdge(result?.edge)}</span>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={pending || activeSkills.size === 0}
                          onClick={() => runAnalyze(m)}
                          title={activeSkills.size === 0 ? "Select at least one skill" : "Run analysis"}
                        >
                          {pending ? "Analyzing…" : "Analyze"}
                        </Button>
                      </TableCell>
                    </TableRow>
                    {result && <AnalysisRow data={result} colSpan={COLUMN_COUNT} />}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        </div>
        {analyzeMut.error && (
          <p className="mt-3 text-sm text-red-400">{(analyzeMut.error as Error).message}</p>
        )}
      </main>
    </div>
  );
}

function edgeClass(edge?: number) {
  if (edge == null) return "text-muted-foreground";
  if (edge > 0.02) return "text-emerald-400";
  if (edge < -0.02) return "text-red-400";
  return "text-muted-foreground";
}

function SortableHead({
  label,
  sortKey,
  current,
  dir,
  onClick,
  className,
}: {
  label: string;
  sortKey: SortKey;
  current: SortKey;
  dir: SortDir;
  onClick: (k: SortKey) => void;
  className?: string;
}) {
  const active = current === sortKey;
  const arrow = active ? (dir === "asc" ? "↑" : "↓") : "";
  return (
    <TableHead className={className}>
      <button
        type="button"
        className={`inline-flex items-center gap-1 ${active ? "text-foreground" : ""} hover:text-foreground`}
        onClick={() => onClick(sortKey)}
      >
        {label}
        <span className="text-xs">{arrow}</span>
      </button>
    </TableHead>
  );
}
