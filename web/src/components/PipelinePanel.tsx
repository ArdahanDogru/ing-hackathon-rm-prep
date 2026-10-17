// "Bu öneriler nasıl seçildi?" on the dashboard (docs/web-ui.md W17; mockup
// "Explainability Mockup", board 1): the decision pipeline in five steps, from
// the client profile to the three recommendations. Closed, it is one line of counts.
import { useContext, useState, type ReactNode } from "react";
import type { AgentDecision, RunView, ScoredOption } from "../api/types";
import { stabilityLevel } from "../explain";
import { fmtScore } from "../format";
import { fill, LangContext, useT, type LabelKey } from "../i18n";
import { colors } from "../theme";
import type { NoteKind } from "./DetailNotes";
import { CodeBadge, ProductBadges } from "../product";

/** The holdings status line of step 1 (W17b). */
const HOLDINGS_LINE: Record<string, LabelKey> = {
  estimate: "pipeHoldEstimate",
  persona_text: "pipeHoldPersona",
  rm: "pipeHoldRm",
  rm_confirmed: "pipeHoldRmConfirmed",
};

const byScore = (a: ScoredOption, b: ScoredOption) =>
  b.score - a.score || a.option.option_id.localeCompare(b.option.option_id);

function Step({ n, title, big, unit, tone, children, link }: {
  n: number;
  title: string;
  big: string;
  unit: string;
  tone?: string;
  children: ReactNode;
  link?: ReactNode;
}) {
  return (
    <li data-testid="pipeline-step" className="flex min-w-0 flex-col gap-3 rounded-[14px] border border-gray-200 bg-white p-5">
      <div className="text-xs font-bold uppercase tracking-[0.06em] text-muted">{`${n} · ${title}`}</div>
      <div className="text-[28px] font-bold leading-tight" style={tone ? { color: tone } : undefined}>
        {big}
        <span className="text-base font-semibold text-muted">{` ${unit}`}</span>
      </div>
      {children}
      <div className="flex-1" />
      {link}
    </li>
  );
}

function Bar({ pct, color }: { pct: number; color: string }) {
  return (
    <div className="h-2 rounded bg-[#F2F4F7]" aria-hidden="true">
      <div className="h-2 rounded" style={{ width: `${Math.max(pct, 1)}%`, backgroundColor: color }} />
    </div>
  );
}

export function PipelinePanel({ view, onOpen, onDetails, agent = null }: {
  view: RunView;
  onOpen: (optionId: string) => void;
  /** W22: open the pop-up note of a step link */
  onDetails: (note: NoteKind) => void;
  /** W20b: the agent decision that the dashboard polls (no poll here) */
  agent?: AgentDecision | null;
}) {
  const t = useT();
  const lang = useContext(LangContext);
  const [open, setOpen] = useState(true);
  const r = view.result;
  const p = r.persona;
  const scored = r.options.length;
  const rejected = r.rejected.length;
  const universe = scored + rejected;
  const ranked = [...r.options].sort(byScore);
  // W41: a place in words: "1." in TR (the label adds the dot), "1st" in EN
  const place = (n: number) =>
    lang === "TR" ? String(n) : `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
  // W32: "kendi grubunda" = the sub-type of the categories (category_key); the engine kind without a view
  const groupOf = (o: ScoredOption) => view.options[o.option.option_id]?.category_key ?? (o.option.fund_kind || o.option.kind);
  const picks = r.recommended
    .map((id) => ranked.find((o) => o.option.option_id === id))
    .filter((o): o is ScoredOption => o !== undefined);
  if (picks.length === 0) return null;
  const minStability = Math.min(...picks.map((o) => o.stability));
  const level = stabilityLevel(minStability);
  // W20b: step 5 shows the agent's picks when it is done; the engine's otherwise
  const agentDone = agent?.state === "done" && agent.picks.length > 0;
  const shown: { id: string; scored: ScoredOption | undefined }[] = agentDone
    ? agent.picks.map((x) => ({ id: x.option_id, scored: ranked.find((o) => o.option.option_id === x.option_id) }))
    : picks.map((o) => ({ id: o.option.option_id, scored: o }));
  const nameOf = (id: string, o: ScoredOption | undefined) => {
    const v = view.options[id];
    return v ? [v.issuer, v.short_label].filter(Boolean).join(" ") : (o?.option.label ?? id);
  };
  const agentLine =
    agent?.state === "running"
      ? t("pipeAgentRunning")
      : agent?.state === "fallback"
        ? fill(t("pipeAgentFallback"), { reason: agent.fallback_reason })
        : agentDone
          ? fill(t("pipeAgentEngine"), { names: picks.map((o) => nameOf(o.option.option_id, o)).join(", ") })
          : null;
  const ruleMax = Math.max(1, ...view.rejected_by_rule.map((x) => x.count));
  const link = (label: string, tab: NoteKind) => (
    <button type="button" className="self-start text-[13px] font-semibold text-[#355FA1] underline" onClick={() => onDetails(tab)}>
      {label}
    </button>
  );
  const weights: [string, string][] = [
    [t("crit_income"), p.gelir_nakit_akisi_ihtiyaci],
    [t("crit_principal"), p.anapara_koruma_tercihi],
    [t("crit_liquidity"), p.likidite_ihtiyaci],
  ];
  // W17b: the normalised weights used for this client, largest first; a missing key has weight 0
  const levels: Record<string, string> = {
    income: p.gelir_nakit_akisi_ihtiyaci,
    principal: p.anapara_koruma_tercihi,
    liquidity: p.likidite_ihtiyaci,
  };
  const effective = Object.entries(view.effective_weights ?? {})
    .filter(([, w]) => w > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const pctText = (w: number) => (lang === "TR" ? `%${Math.round(w * 100)}` : `${Math.round(w * 100)} %`);
  const holdingsLine = view.holdings ? HOLDINGS_LINE[view.holdings.status] : undefined;

  return (
    <section data-testid="pipeline" className="mb-6 rounded-2xl bg-white shadow-sm">
      <button
        type="button"
        aria-expanded={open}
        className="flex w-full flex-wrap items-center justify-between gap-2 px-[18px] py-3.5 text-left text-[#344054]"
        onClick={() => setOpen(!open)}
      >
        <b>{t("pipelineTitle")}</b>
        <span className="text-muted">
          {`${fill(t("pipeSummary"), { universe, rejected, scored, picks: picks.length })} ${open ? "‹" : "›"}`}
        </span>
      </button>
      {open && (
        <div className="flex flex-col gap-4 border-t border-gray-100 bg-surface px-[18px] py-4">
          <ol className="grid gap-3 lg:grid-cols-[1fr_1fr_1.15fr_1fr_1.45fr]">
            <Step n={1} title={t("pipeProfile")} big={view.risk_ceiling === null ? "—" : `Risk ≤ ${view.risk_ceiling}`} unit="/ 7"
              link={link(t("pipeSeeAssumptions"), "assumptions")}>
              <div className="text-[13px] leading-normal text-[#344054]">{`${p.risk_profili} · ${p.yatirim_ufku}`}</div>
              <div className="h-px bg-gray-200" />
              <div className="text-xs font-semibold text-muted">{t(effective.length > 0 ? "pipeWeightsUsed" : "pipeWeights")}</div>
              {effective.length > 0 ? (
                <ul className="flex flex-col gap-2 text-[13px]">
                  {effective.map(([key, w]) => (
                    <li key={key} data-testid="weight-row" className="flex flex-col gap-1">
                      <div className="flex justify-between gap-2">
                        <span>
                          <span data-testid="weight-label">{t(`crit_${key}` as LabelKey) ?? key}</span>
                          {levels[key] && (
                            <b className="ml-1.5" style={{ color: colors.chart }}>
                              {levels[key]}
                            </b>
                          )}
                        </span>
                        <span className="tabular-nums text-[#344054]">{pctText(w)}</span>
                      </div>
                      <div className="h-1.5 rounded bg-[#F2F4F7]" aria-hidden="true">
                        <div
                          data-testid="weight-bar"
                          className="h-1.5 rounded"
                          style={{ width: `${Math.round(w * 1000) / 10}%`, backgroundColor: colors.chart }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <ul className="flex flex-col gap-2 text-[13px]">
                  {weights.map(([label, value]) => (
                    <li key={label} className="flex justify-between gap-2">
                      <span>{label}</span>
                      <b style={{ color: colors.chart }}>{value}</b>
                    </li>
                  ))}
                </ul>
              )}
              {holdingsLine && (
                <div data-testid="pipe-holdings" className="text-xs text-[#344054]">
                  {t(holdingsLine)}
                </div>
              )}
            </Step>
            <Step n={2} title={t("pipeUniverse")} big={String(universe)} unit={t("pipeOptions")}
              link={link(t("pipeSeeDataNotes"), "dataNotes")}>
              <div className="text-[13px] leading-normal text-[#344054]">{t("pipeUniverseText")}</div>
              <Bar pct={100} color={colors.chart} />
            </Step>
            <Step n={3} title={t("pipeRules")} big={String(rejected)} unit={t("pipeEliminated")} tone={colors.bad.fg}
              link={link(t("pipeSeeEliminated"), "eliminated")}>
              <div className="text-[13px] leading-normal text-[#344054]">{t("pipeRulesText")}</div>
              <ul className="flex flex-col gap-2.5">
                {view.rejected_by_rule.map((x) => (
                  <li key={x.rule_id} className="flex flex-col gap-1">
                    <div className="flex justify-between gap-2 text-[13px]">
                      <span>{x.label}</span>
                      <b>{x.count}</b>
                    </div>
                    <Bar pct={(x.count / ruleMax) * 100} color={colors.bad.fg} />
                  </li>
                ))}
              </ul>
              {view.rejected_by_rule.length > 1 && <div className="text-xs text-muted">{t("rejectedMulti")}</div>}
            </Step>
            <Step n={4} title={t("pipeScoring")} big={String(scored)} unit={t("pipeCandidates")}
              link={link(t("pipeSeeCategories"), "categories")}>
              <div className="text-[13px] leading-normal text-[#344054]">{t("pipeScoringText")}</div>
              <Bar pct={universe ? (scored / universe) * 100 : 0} color={colors.chart} />
            </Step>
            <li data-testid="pipeline-step" className="flex min-w-0 flex-col gap-3 rounded-[14px] border-2 border-ink bg-white p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-bold uppercase tracking-[0.06em] text-muted">{`5 · ${t("pipePick")}`}</span>
                {agentDone && <span className="rounded-full bg-ink px-2 py-0.5 text-[11px] font-bold text-white">{t("agentBadge")}</span>}
              </div>
              <div className="text-[28px] font-bold leading-tight">
                {shown.length}
                <span className="text-base font-semibold text-muted">{` ${t("pipeOptions")}`}</span>
              </div>
              <div className="text-[13px] leading-normal text-[#344054]">{t("pipePickText")}</div>
              <ul className="flex flex-col gap-2">
                {shown.map(({ id, scored: o }) => {
                  const v = view.options[id];
                  const fresh = agentDone && !agent.engine_top3.includes(id);
                  let where: string;
                  if (!o) where = t("pipeAgentNotTop3");
                  else if (fresh) where = fill(t("pipeAgentEnginePlace"), { n: place(ranked.indexOf(o) + 1) });
                  else {
                    const overall = ranked.indexOf(o) + 1;
                    const inGroup = ranked.filter((x) => groupOf(x) === groupOf(o)).indexOf(o) + 1;
                    where = overall === inGroup
                      ? fill(t("pipeRankOverall"), { n: place(overall) })
                      : `${fill(t("pipeRankOverall"), { n: place(overall) })}, ${fill(t("pipeRankGroup"), { n: place(inGroup) })}`;
                  }
                  return (
                    <li key={id} data-testid="pipe-pick">
                      <button type="button" className="flex w-full flex-col gap-0.5 rounded-[10px] bg-surface px-3 py-2.5 text-left hover:bg-[#EEF1F5]" onClick={() => onOpen(id)}>
                        <span className="flex w-full justify-between gap-2 text-[13px]">
                          <b>
                            <CodeBadge optionId={id} />
                            {nameOf(id, o)}
                            <ProductBadges badges={v?.badges} />
                          </b>
                          {o && <span className="tabular-nums">{fmtScore(o.score, false)}</span>}
                        </span>
                        <span className={`text-xs ${fresh ? "font-semibold text-cobalt" : "text-muted"}`}>
                          {[v?.category_label, where].filter(Boolean).join(" · ")}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
              {agentLine && (
                <div data-testid="pipe-agent" className={`text-xs text-muted ${agent?.state === "running" ? "animate-pulse" : ""}`}>
                  {agentLine}
                </div>
              )}
            </li>
          </ol>
          <div className="flex flex-wrap items-center gap-3.5 rounded-xl border border-gray-200 bg-white px-[18px] py-3.5 text-[13px]">
            <span className="rounded-full px-2.5 py-1 font-bold" style={{ backgroundColor: colors[level].bg, color: colors[level].fg }}>
              {t(level === "good" ? "stabGood" : level === "neutral" ? "stabMid" : "stabBad")}
            </span>
            <span className="text-[#344054]">{fill(t("pipeStability"), { pct: Math.round(minStability * 100) })}</span>
          </div>
        </div>
      )}
    </section>
  );
}
