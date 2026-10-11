import { colors, riskColors } from "../theme";

export function riskColor(level: number): string {
  const i = Math.min(Math.max(Math.round(level), 1), 7) - 1;
  return riskColors[i];
}

/** SPK risk value as 7 segments; every filled segment takes the level color. */
export function RiskBar({ level, showText = true }: { level: number; showText?: boolean }) {
  const color = riskColor(level);
  return (
    <div>
      <div className="my-1.5 flex gap-[3px]" aria-hidden="true">
        {Array.from({ length: 7 }, (_, i) => {
          const filled = i < level;
          return (
            <span
              key={i}
              data-testid="risk-seg"
              data-filled={filled ? "true" : "false"}
              className="h-1.5 flex-1 rounded"
              style={{ backgroundColor: filled ? color : colors.riskEmpty }}
            />
          );
        })}
      </div>
      {showText && (
        <b className="text-sm" style={{ color }}>
          {`${level} / 7`}
        </b>
      )}
    </div>
  );
}
