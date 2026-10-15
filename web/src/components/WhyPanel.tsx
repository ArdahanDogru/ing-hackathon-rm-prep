// "Neden bu öneri?" in the fund card (docs/web-ui.md W16; mockup "Explainability
// Mockup", board 2): rank, stability and confidence, the score parts as bars with
// the engine's reason under each, the hard rules passed, the closest alternative.
import { useContext } from "react";
import { confidenceLevel, stabilityLevel, type Explanation, type Level, type ScoreRow } from "../explain";
import { fmtScore } from "../format";
import { fill, labels, LangContext, useT, type LabelKey } from "../i18n";
import { colors } from "../theme";

const chip: Record<Level, { bg: string; fg: string }> = colors;

/** The label of a score part: the criterion, or "Ceza · <rule>" for "penalty:<rule>". */
export function useLabelOf() {
  const lang = useContext(LangContext);
  const t = useT();
  return (row: Pick<ScoreRow, "key" | "penalty">): string => {
    if (!row.penalty) return labels[lang][`crit_${row.key}` as LabelKey] ?? row.key;
    const rule = row.key.slice("penalty:".length);
    return `${t("penalty")} · ${labels[lang][`pen_${rule}` as LabelKey] ?? rule}`;
  };
}

function Row({ row, scale }: { row: ScoreRow; scale: number }) {
  const labelOf = useLabelOf();
  const width = scale > 0 ? Math.round((Math.abs(row.value) / scale) * 100) : 0;
  const fg = row.penalty ? colors.bad.fg : colors.chart;
  return (
    <li data-testid="score-row" className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <b>{labelOf(row)}</b>
        {row.priorities.map((p) => (
          <span key={p} data-testid="priority-tag" className="rounded-full bg-[#E8EEF8] px-2 py-0.5 text-[11px] font-semibold text-[#355FA1]">
            {p}
          </span>
        ))}
        <span className="flex-1" />
        <b className="tabular-nums" style={row.penalty ? { color: fg } : undefined}>
          {fmtScore(row.value)}
        </b>
      </div>
      <div className="h-2 rounded bg-[#E4E7EC]" aria-hidden="true">
        {width > 0 && <div className="h-2 rounded" style={{ width: `${Math.max(width, 2)}%`, backgroundColor: fg }} />}
      </div>
      {row.reason && <div className="text-xs leading-snug text-[#475467]">{row.reason}</div>}
    </li>
  );
}

function Chip({ level, title, children }: { level: Level; title: string; children: string }) {
  return (
    <span title={title} className="rounded-full px-2.5 py-1 font-semibold" style={{ backgroundColor: chip[level].bg, color: chip[level].fg }}>
      {children}
    </span>
  );
}

export function WhyPanel({ explanation: x, onEvidence }: { explanation: Explanation; onEvidence?: (id: string) => void }) {
  const t = useT();
  const labelOf = useLabelOf();
  const rows = [...x.criteria, ...x.penalties];
  const scale = Math.max(0, ...rows.map((r) => Math.abs(r.value)));
  const stab = stabilityLevel(x.stability);
  const conf = confidenceLevel(x.confidence);
  const word = { good: "Good", neutral: "Mid", bad: "Bad" } as const;
  const passed = x.constraints.filter((c) => c.passed);
  const pct = (v: number) => `%${Math.round(v * 100)}`;

  return (
    <>
      <section data-testid="why-panel" className="my-[22px] flex flex-col gap-4 rounded-xl bg-[#F7F9FC] px-4 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-[17px] font-bold">{t("whyThis")}</h3>
          <span className="text-[13px] text-muted">{fill(t("whyRank"), { n: x.position, of: x.of })}</span>
        </div>

        <div className="flex flex-wrap gap-2 text-xs">
          {x.recommended && (
            <Chip level={stab} title={t("stabHint")}>
              {`${t("stability")} ${pct(x.stability)} · ${t(`stab${word[stab]}` as LabelKey)}`}
            </Chip>
          )}
          <Chip level={conf} title={t("confHint")}>
            {`${t("confidence")} ${pct(x.confidence)} · ${t(`conf${word[conf]}` as LabelKey)}`}
          </Chip>
        </div>

        <div className="text-xs font-bold uppercase tracking-[0.06em] text-muted">{t("howScore")}</div>
        <ul className="flex flex-col gap-3.5">
          {x.criteria.map((r) => (
            <Row key={r.key} row={r} scale={scale} />
          ))}
          {x.penalties.length > 0 && <li aria-hidden="true" className="h-px bg-[#E4E7EC]" />}
          {x.penalties.map((r) => (
            <Row key={r.key} row={r} scale={scale} />
          ))}
        </ul>
        <div className="flex items-baseline justify-between border-t-2 border-ink pt-2.5">
          <b>{t("totalScore")}</b>
          <b data-testid="total-score" className="text-xl tabular-nums">
            {fmtScore(x.score, false)}
          </b>
        </div>
      </section>

      {passed.length > 0 && (
        <section className="mb-[22px]">
          <div className="mb-2.5 text-xs font-bold uppercase tracking-[0.06em] text-muted">{t("rulesPassed")}</div>
          <ul className="flex flex-col gap-2">
            {passed.map((c) => (
              <li key={c.rule_id} className="flex items-start gap-2.5 rounded-xl border border-gray-200 px-3.5 py-3">
                <svg aria-hidden="true" width="20" height="20" viewBox="0 0 20 20" fill="none" stroke={colors.good.fg} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className="mt-px flex-none">
                  <path d="M4 10.5l4 4 8-9" />
                </svg>
                <span className="min-w-0 flex-1 text-[13px] text-[#475467]">{c.reason}</span>
                {c.evidence_ids.map((id) => (
                  <button key={id} type="button" className="rounded-full border border-gray-300 px-2 py-0.5 font-mono text-xs" onClick={() => onEvidence?.(id)}>
                    {id}
                  </button>
                ))}
              </li>
            ))}
          </ul>
        </section>
      )}

      {x.alternative && (
        <section data-testid="alternative" className="mb-[22px]">
          <div className="mb-2.5 text-xs font-bold uppercase tracking-[0.06em] text-muted">{t("closestAlt")}</div>
          <div className="flex flex-col gap-2 rounded-xl border border-gray-200 p-3.5">
            <div className="flex justify-between gap-3 text-sm">
              <b>{x.alternative.label}</b>
              <span className="tabular-nums text-muted">{fmtScore(x.alternative.score, false)}</span>
            </div>
            <div className="text-[13px] leading-normal text-[#344054]">
              {x.alternative.diff ? (
                <>
                  {`${t("altBiggest")}: `}
                  <b>{labelOf({ key: x.alternative.diff.key, penalty: x.alternative.diff.key.startsWith("penalty:") })}</b>
                  {` · ${t("thisOption")} ${fmtScore(x.alternative.diff.mine)}, ${t("altShort")} ${fmtScore(x.alternative.diff.theirs)}`}
                  {x.alternative.diff.reason && <div className="mt-1 text-xs text-[#475467]">{x.alternative.diff.reason}</div>}
                </>
              ) : (
                t("altSame")
              )}
            </div>
          </div>
        </section>
      )}
    </>
  );
}
