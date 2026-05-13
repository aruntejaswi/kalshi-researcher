interface Props {
  total: number;
  completed: number;
  failed: number;
  inProgress: number;
  status: string;
}

export function ProgressBar({ total, completed, failed, inProgress, status }: Props) {
  const done = completed + failed;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="rounded-md border border-border bg-card/60 p-3">
      <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {status === "done" ? "Batch complete" : `Analyzing ${inProgress} of ${total}`} · {done}/{total}
          {failed > 0 && <span className="ml-2 text-red-400">{failed} failed</span>}
        </span>
        <span className="font-mono">{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full transition-all duration-300 ${
            status === "done" ? "bg-emerald-500" : "bg-emerald-400/80"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
