import { fmtNum } from "../format";
import { colors } from "../theme";
import { riskColor } from "./RiskBar";

/** Red (0) to green (10), on the same scale as the risk colors. */
export function matchColor(value: number): string {
  const v = Math.min(Math.max(value, 0), 10);
  return riskColor(7 - Math.round((v / 10) * 6));
}

/** Match 0..10 ("uygunluk") as a ring; the number is always shown. */
export function MatchRing({ value, label = "uygunluk", size = 62 }: { value: number; label?: string; size?: number }) {
  const stroke = 7;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const share = Math.min(Math.max(value, 0), 10) / 10;
  return (
    <div className="relative flex-none" style={{ width: size, height: size }}>
      <svg width={size} height={size} aria-hidden="true" className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={colors.riskEmpty} strokeWidth={stroke} />
        <circle
          data-testid="match-arc"
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={matchColor(value)}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${c * share} ${c}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
        <span className="text-[15px] font-bold">{fmtNum(value)}</span>
        <small className="mt-0.5 text-[8px] font-medium text-muted">{label}</small>
      </div>
    </div>
  );
}
