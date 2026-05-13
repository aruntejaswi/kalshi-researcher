import { TableCell, TableRow } from "@/components/ui/table";
import { formatPrice } from "@/lib/utils";

export interface AnalysisResponse {
  ticker: string;
  run_id: number;
  context_sheets: { skill_id: string; headline: string; summary: string; citations: { title: string; url: string }[] }[];
  llm: { reasoning: string; probability: number; confidence: number };
  market: { price: number; probability: number };
  combined: { probability: number; model_weight: number; market_weight: number };
  edge: number;
  kelly: {
    side: string;
    edge: number;
    kelly_fraction: number;
    fractional_kelly: number;
    recommended_dollars: number;
    recommended_contracts: number;
  };
}

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

export function AnalysisRow({ data, colSpan }: { data: AnalysisResponse; colSpan: number }) {
  const { llm, market, combined, kelly } = data;
  return (
    <TableRow className="bg-muted/30 hover:bg-muted/30">
      <TableCell colSpan={colSpan} className="space-y-4 p-4">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Stat label="Model" value={pct(llm.probability)} sub={`conf ${pct(llm.confidence)}`} />
          <Stat label="Market" value={pct(market.probability)} sub={formatPrice(market.price)} />
          <Stat
            label="Combined"
            value={pct(combined.probability)}
            sub={`weights ${combined.model_weight.toFixed(2)} / ${combined.market_weight.toFixed(2)}`}
          />
          <Stat
            label={`Kelly · ${kelly.side.toUpperCase()}`}
            value={kelly.side === "pass" ? "no edge" : `$${kelly.recommended_dollars.toFixed(2)}`}
            sub={
              kelly.side === "pass"
                ? `edge ${pct(kelly.edge)}`
                : `${kelly.recommended_contracts} contracts · f=${(kelly.fractional_kelly * 100).toFixed(1)}%`
            }
          />
        </div>

        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Reasoning
          </h4>
          <p className="text-sm leading-relaxed">{llm.reasoning}</p>
        </div>

        {data.context_sheets.length > 0 && (
          <div>
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Context sheets
            </h4>
            <div className="space-y-2">
              {data.context_sheets.map((s) => (
                <div key={s.skill_id} className="rounded-md border border-border bg-background/40 p-3">
                  <div className="text-xs font-mono text-muted-foreground">{s.skill_id}</div>
                  <div className="text-sm font-medium">{s.headline}</div>
                  <p className="mt-1 whitespace-pre-line text-xs text-muted-foreground">{s.summary}</p>
                  {s.citations.length > 0 && (
                    <ul className="mt-2 space-y-0.5 text-xs">
                      {s.citations.map((c, i) => (
                        <li key={i}>
                          <a className="text-emerald-400 hover:underline" href={c.url} target="_blank" rel="noreferrer">
                            {c.title || c.url}
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </TableCell>
    </TableRow>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-md border border-border bg-background/40 p-3">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}
