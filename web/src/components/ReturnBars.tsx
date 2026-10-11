import { fmtPct } from "../format";
import { colors } from "../theme";
import { DeltaPill } from "./DeltaPill";

export type ReturnRow = { period: string; fund: number | null; category: number | null; label?: string };

const PERIOD_LABELS: Record<string, string> = { "3m": "3 ay", "6m": "6 ay", "1y": "1 yıl", real_1y: "Reel" };

function Bar({ testId, value, max, color }: { testId: string; value: number; max: number; color: string }) {
  const width = max > 0 ? (Math.abs(value) / max) * 100 : 0;
  return (
    <div className="flex items-center gap-1.5">
      <div
        data-testid={testId}
        className="my-0.5 h-2.5 rounded-[5px]"
        style={{ width: `${Math.max(width, 1.5)}%`, backgroundColor: color, opacity: value < 0 ? 0.55 : 1 }}
      />
      <span className="whitespace-nowrap text-[10px] text-muted">{fmtPct(value)}</span>
    </div>
  );
}

/** Fund (cobalt) vs category average (grey) per period, with a delta pill. */
export function ReturnBars({
  rows,
  fundLabel = "bu fon",
  categoryLabel = "kategori ortalaması",
}: {
  rows: ReturnRow[];
  fundLabel?: string;
  categoryLabel?: string;
}) {
  const values = rows.flatMap((r) => [r.fund, r.category]).filter((v): v is number => v !== null);
  const max = Math.max(0, ...values.map(Math.abs));
  return (
    <div>
      {rows.map((r) => (
        <div key={r.period} className="my-[7px] grid grid-cols-[44px_1fr_74px] items-center gap-2.5">
          <span>{r.label ?? PERIOD_LABELS[r.period] ?? r.period}</span>
          <div>
            {r.fund !== null && <Bar testId={`bar-fund-${r.period}`} value={r.fund} max={max} color={colors.chart} />}
            {r.category !== null && (
              <Bar testId={`bar-cat-${r.period}`} value={r.category} max={max} color={colors.category} />
            )}
          </div>
          <span>{r.fund !== null && r.category !== null && <DeltaPill points={r.fund - r.category} />}</span>
        </div>
      ))}
      <div className="mt-1 flex gap-3.5 text-[11px] text-muted">
        <span>
          <i className="mr-1 inline-block h-2 w-3 rounded" style={{ backgroundColor: colors.chart }} />
          {fundLabel}
        </span>
        <span>
          <i className="mr-1 inline-block h-2 w-3 rounded" style={{ backgroundColor: colors.category }} />
          {categoryLabel}
        </span>
      </div>
    </div>
  );
}
