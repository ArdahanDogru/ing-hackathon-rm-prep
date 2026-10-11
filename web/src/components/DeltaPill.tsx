import { fmtNum, fmtSigned } from "../format";
import { colors } from "../theme";

/** Fund minus category in percentage points: green above, red below. */
export function DeltaPill({ points, unit = "puan" }: { points: number; unit?: string }) {
  const tone = fmtNum(points) === "0" ? "neutral" : points > 0 ? "good" : "bad";
  const c = colors[tone];
  return (
    <span
      data-tone={tone}
      className="inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-center text-[11px] font-semibold"
      style={{ backgroundColor: c.bg, color: c.fg }}
    >
      {`${fmtSigned(points)} ${unit}`}
    </span>
  );
}
