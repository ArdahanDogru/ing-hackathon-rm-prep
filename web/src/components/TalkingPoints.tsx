import type { TalkingPoint } from "../api/types";
import { useT } from "../i18n";
import { colors } from "../theme";

/** "Müşteriyle konuşulacaklar": 2–3 cards, each a label, a large figure and one sentence. */
export function TalkingPoints({ points }: { points: TalkingPoint[] }) {
  const t = useT();
  if (!points.length) return null;
  return (
    <section className="mt-4">
      <h2 className="text-sm font-semibold">{t("talkingPoints")}</h2>
      <div className="mt-2 grid gap-3" style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}>
        {points.map((p) => (
          <div
            key={p.code}
            data-testid="talking-point"
            className="rounded-2xl bg-white p-4 shadow-sm"
            style={{ borderTop: `3px solid ${colors.chart}` }}
          >
            <div className="mb-1.5 text-[11px] uppercase tracking-wide text-muted">{p.label}</div>
            <div className="text-[22px] font-bold leading-tight">{p.figure}</div>
            <div className="mt-1 text-[13px] leading-snug">{p.text}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
