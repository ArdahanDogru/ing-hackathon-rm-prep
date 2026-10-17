// "Öneriler" as cards (B4 "Kartlar"): the recommendations side by side, the deposit as a dashed row.
import type { OptionView } from "../api/types";
import { fmtPct } from "../format";
import { useT } from "../i18n";
import { colors } from "../theme";
import { MatchRing } from "./MatchRing";
import { KindBadge } from "./KindBadge";
import { KMark, fullName, realColor, signedPct, whyLine } from "./OptionsTable";
import { RiskBar } from "./RiskBar";
import { Stars } from "./Stars";
import { CodeBadge, ProductBadges } from "../product";

export function OptionsCards({
  options,
  baseline,
  onOpen,
  onEvidence,
}: {
  options: OptionView[];
  baseline: OptionView | null;
  onOpen: (id: string) => void;
  onEvidence: (id: string) => void;
}) {
  const t = useT();
  return (
    <div className="px-3 pb-1 pt-2.5">
      <div className="grid gap-3.5" style={{ gridTemplateColumns: `repeat(${Math.max(options.length, 1)}, minmax(0, 1fr))` }}>
        {options.map((o, i) => {
          const r1 = o.returns["1y"];
          return (
            <article
              key={o.option_id}
              data-testid="option-card"
              tabIndex={0}
              title={fullName(o)}
              aria-label={o.label}
              className="cursor-pointer rounded-2xl border border-gray-200 bg-white px-[18px] py-4 hover:border-cobalt"
              onClick={() => onOpen(o.option_id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onOpen(o.option_id);
                }
              }}
            >
              <div className="flex justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs font-bold uppercase tracking-[0.05em] text-muted">
                    {o.issuer ? `${i + 1} · ${o.issuer}` : `${i + 1}`}
                  </div>
                  <div className="text-[17px] font-bold leading-snug">
                    <CodeBadge optionId={o.option_id} />
                    {o.short_label}
                    <KindBadge kind={o.kind} />
                    <ProductBadges badges={o.badges} />
                  </div>
                </div>
                {o.match !== null && <MatchRing value={o.match} size={46} label={t("match")} />}
              </div>
              {r1 && (
                <div className="mt-3 text-[28px] font-bold tracking-tight" style={{ color: colors.good.fg }}>
                  {fmtPct(r1.value)} <span className="text-[13px] font-normal text-muted">{t("return1y")}</span>
                  <KMark id={r1.evidence_id} onEvidence={onEvidence} />
                </div>
              )}
              {o.risk && (
                <div className="mt-2 w-28">
                  <RiskBar level={o.risk.level} />
                </div>
              )}
              {o.rank && o.stars !== null && (
                <div className="mt-2 text-[13px]">
                  <Stars count={o.stars} /> <span className="text-muted">{`${o.rank.position}. / ${o.rank.of} ${t("peerShort")}`}</span>
                </div>
              )}
              {whyLine(o) && <div className="mt-2 text-sm text-[#344054]">{whyLine(o)}</div>}
            </article>
          );
        })}
      </div>
      {baseline && (
        <div className="mt-3.5 flex flex-wrap justify-between gap-2 rounded-xl border border-dashed border-catgrey bg-[#FCFCFD] px-4 py-3 text-muted">
          <span>
            <b>{t("comparison")}</b>
            {` · ${baseline.label}`}
          </span>
          <span>
            {baseline.returns["1y"] && (
              <>
                {fmtPct(baseline.returns["1y"].value)}
                <KMark id={baseline.returns["1y"].evidence_id} onEvidence={onEvidence} />
              </>
            )}
            {baseline.returns.real_1y && (
              <>
                {` · ${t("realReturn").toLocaleLowerCase("tr")} `}
                <span style={{ color: realColor(baseline.returns.real_1y.value) }}>{signedPct(baseline.returns.real_1y.value)}</span>
              </>
            )}
            {baseline.access.label && ` · ${baseline.access.label.toLocaleLowerCase("tr")}`}
          </span>
        </div>
      )}
      <p className="px-1 pt-2 text-xs text-muted">{t("cardsNote")}</p>
    </div>
  );
}
