import type { OptionView } from "../api/types";
import { fmtPct } from "../format";
import { useT } from "../i18n";
import { colors } from "../theme";
import { MatchRing } from "./MatchRing";
import { OptionNotes } from "./Notes";
import { RiskBar } from "./RiskBar";
import { Stars } from "./Stars";

export function RealReturn({ value }: { value: number }) {
  const t = useT();
  const c = value < 0 ? colors.bad.fg : colors.good.fg;
  return (
    <div className="text-xs" style={{ color: c }}>
      {`${t("realReturn")}: ${fmtPct(value)}`} <span className="text-muted">({t("realAfter")})</span>
    </div>
  );
}

/** One of the top 3 recommendations (a group head). */
export function TopOptionCard({
  option,
  position,
  selected,
  onToggle,
}: {
  option: OptionView;
  position: number;
  selected: boolean;
  onToggle: () => void;
}) {
  const t = useT();
  const r1 = option.returns["1y"];
  const real = option.returns.real_1y;
  return (
    <article data-testid="top-card" className="flex flex-col rounded-2xl bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[10px] uppercase tracking-wide text-muted">{`${position} · ${option.category_label}`}</div>
          <h3 className="mt-0.5 text-[14px] font-semibold leading-snug">{option.label}</h3>
        </div>
        {option.match !== null && <MatchRing value={option.match} size={46} label={t("match")} />}
      </div>
      {r1 && (
        <div className="mt-2 text-[20px] font-bold">
          {fmtPct(r1.value)} <span className="text-[11px] font-normal text-muted">{t("return1y")}</span>
        </div>
      )}
      {real && <RealReturn value={real.value} />}
      <div className="mt-2 flex items-center justify-between text-xs">
        {option.rank && option.stars !== null ? (
          <span className="flex items-center gap-2">
            <Stars count={option.stars} />
            <span>
              <b>{`${option.rank.position}. / ${option.rank.of}`}</b> <span className="text-muted">{t("categoryRank")}</span>
            </span>
          </span>
        ) : (
          <span className="text-muted">{t("noRank")}</span>
        )}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
        <div>
          <div className="text-[11px] text-muted">{t("riskValue")}</div>
          {option.risk ? <RiskBar level={option.risk.level} /> : <span className="text-muted">—</span>}
        </div>
        <div>
          <div className="text-[11px] text-muted">{t("access")}</div>
          <div className="mt-1 font-semibold">{option.access.label ?? "—"}</div>
        </div>
      </div>
      <OptionNotes notes={option.data_notes} />
      <div className="mt-auto pt-3 text-right">
        <button
          type="button"
          aria-pressed={selected}
          onClick={onToggle}
          className={
            selected
              ? "rounded-[10px] border border-gray-300 px-3 py-1 text-xs font-semibold"
              : "rounded-[10px] bg-brand px-3 py-1 text-xs font-semibold text-white"
          }
        >
          {selected ? `✓ ${t("inSelection")}` : t("addToSelection")}
        </button>
      </div>
    </article>
  );
}
