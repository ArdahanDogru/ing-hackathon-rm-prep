// The agent's top 3 on the dashboard (W20; spec docs/superpowers/specs/2026-10-15-agent-decision-design.md
// section 8): while the agent runs, the engine's top 3 stays with "Motor önerisi · ajan
// değerlendiriyor…"; when it is done, its picks replace the engine's ("Ajan önerisi"), each
// reason with citation chips; "Motor sıralaması" is a closed section; a fallback shows its reason.
import { useContext, useState } from "react";
import { api } from "../api/client";
import type { AgentDecision, AgentPick, ResearchFinding, ResearchView, RunView } from "../api/types";
import { fill, LangContext, useT } from "../i18n";
import { useLabelOf } from "./WhyPanel";

/** The ids of the agent's picks that have an option view (the cards and the meeting chips use them). */
export function agentTop(view: RunView, d: AgentDecision | null): string[] | null {
  if (d?.state !== "done") return null;
  const ids = d.picks.map((p) => p.option_id).filter((id) => view.options[id]);
  return ids.length ? ids : null;
}

function findingOf(research: ResearchView | null, id: string): ResearchFinding | undefined {
  if (!research || research.state !== "ready") return undefined;
  const all = [
    ...research.products.flatMap((p) => [...p.findings, ...p.news]),
    ...research.questions.flatMap((q) => q.findings),
  ];
  return all.find((f) => f.id === id);
}

const chipClass = "rounded-full border border-gray-300 bg-white px-2 py-px text-[11px] font-semibold text-[#344054] hover:border-cobalt";

export function AgentPicks({
  view,
  decision,
  onOpen,
  onEvidence,
  onAllocation,
}: {
  view: RunView;
  decision: AgentDecision | null;
  onOpen: (optionId: string) => void;
  onEvidence: (evidenceId: string) => void;
  /** open the Dağılım view (a portfoy:<class> chip) */
  onAllocation: () => void;
}) {
  const t = useT();
  const lang = useContext(LangContext);
  const labelOf = useLabelOf();
  const [engineOpen, setEngineOpen] = useState(false);
  const [finding, setFinding] = useState<string | null>(null);
  const [research, setResearch] = useState<ResearchView | null>(null);
  if (!decision || decision.state === "off") return null;

  const name = (id: string) => {
    const o = view.options[id];
    if (!o) return view.result.options.find((x) => x.option.option_id === id)?.option.label ?? id;
    return [o.issuer.split(" ")[0], o.short_label].filter(Boolean).join(" ");
  };
  const allocLabel = (cls: string) => view.allocation.find((a) => a.asset_class === cls)?.label ?? cls;

  const openFinding = (id: string) => {
    setFinding(finding === id ? null : id);
    if (research === null) api.research(view.result.run_id, lang).then(setResearch, () => setResearch({ state: "off", reason: "" }));
  };

  const chip = (cite: string, pick: AgentPick) => {
    if (cite.startsWith("puan:")) {
      // the agent pack writes the score part "penalty:<rule>" as "puan:penalty_<rule>"
      const key = cite.slice(5);
      const part = key.startsWith("penalty_")
        ? { key: `penalty:${key.slice("penalty_".length)}`, penalty: true }
        : { key, penalty: false };
      return (
        <button key={cite} type="button" className={chipClass} title={cite} onClick={() => onOpen(pick.option_id)}>
          {labelOf(part)}
        </button>
      );
    }
    if (cite.startsWith("portfoy:"))
      return (
        <button key={cite} type="button" className={chipClass} title={cite} onClick={onAllocation}>
          {allocLabel(cite.slice(8))}
        </button>
      );
    const web = cite.startsWith("F");
    return (
      <button
        key={cite}
        type="button"
        aria-expanded={web ? finding === cite : undefined}
        className={`${chipClass} font-mono`}
        onClick={() => (web ? openFinding(cite) : onEvidence(cite))}
      >
        {cite}
      </button>
    );
  };

  const reasons = (p: AgentPick) => (
    <ul className="mt-1 space-y-1.5">
      {p.reasons.map((r, i) => {
        const shown = r.cites.find((c) => c === finding);
        const f = shown ? findingOf(research, shown) : undefined;
        return (
          <li key={i} className="text-[13px] leading-normal text-[#344054]">
            {r.text}
            {r.labels.map((l) => (
              <span key={l} className="ml-1 text-xs italic text-[#B54708]">
                {l}
              </span>
            ))}
            <span className="ml-1.5 inline-flex flex-wrap gap-1 align-[1px]">{r.cites.map((c) => chip(c, p))}</span>
            {shown && (
              <div data-testid="agent-finding" className="mt-1 rounded-lg border border-[#FEDF89] bg-[#FFFAEB] px-3 py-1.5 text-xs">
                {f ? (
                  <>
                    {f.text}
                    <span className="ml-1 italic text-[#B54708]">{`(${t("agentFindingWeb")})`}</span>
                    {f.sources.map((s) => (
                      <a key={s.url} href={s.url} target="_blank" rel="noreferrer" className="ml-1.5 text-[#355FA1] underline">
                        {s.title || s.url}
                      </a>
                    ))}
                  </>
                ) : (
                  <span className="font-mono">{shown}</span>
                )}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );

  const box = "h-full min-w-0 rounded-2xl bg-white px-5 py-4 shadow-sm"; // W23: as tall as Gündem next to it
  if (decision.state === "running")
    return (
      <section data-testid="agent-picks" className={box}>
        <p className="animate-pulse text-sm font-semibold text-muted">{t("agentRunning")}</p>
      </section>
    );
  if (decision.state === "fallback")
    return (
      <section data-testid="agent-picks" className={box}>
        <p className="text-sm text-[#344054]">{fill(t("agentFallback"), { reason: decision.fallback_reason })}</p>
      </section>
    );

  const changed = decision.picks.filter((p) => !decision.engine_top3.includes(p.option_id)).length;
  return (
    <section data-testid="agent-picks" className={box}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-ink px-2.5 py-0.5 text-xs font-bold text-white">{t("agentBadge")}</span>
        {changed > 0 && (
          <span className="text-sm font-semibold text-[#344054]">
            {changed === 1 ? t("agentChangedOne") : fill(t("agentChangedMany"), { k: changed })}
          </span>
        )}
      </div>
      {decision.summary && <p className="mt-2 text-sm text-[#344054]">{decision.summary}</p>}
      <ol className="mt-3 space-y-3">
        {decision.picks.map((p, i) => (
          <li key={p.option_id} data-testid="agent-pick" className="border-t border-gray-100 pt-2.5">
            <button type="button" className="text-left text-sm font-bold hover:underline" onClick={() => onOpen(p.option_id)}>
              {`${i + 1} · ${name(p.option_id)}`}
            </button>
            {reasons(p)}
          </li>
        ))}
      </ol>
      {decision.dropped.length > 0 && (
        <div data-testid="agent-dropped" className="mt-3 rounded-xl bg-[#F9FAFB] px-3 py-2">
          <div className="text-xs font-bold uppercase tracking-[0.05em] text-muted">{t("agentDropped")}</div>
          {decision.dropped.map((p) => (
            <div key={p.option_id} className="mt-1">
              <span className="text-[13px] font-semibold line-through decoration-gray-400">{name(p.option_id)}</span>
              {reasons(p)}
            </div>
          ))}
        </div>
      )}
      <button
        type="button"
        aria-expanded={engineOpen}
        className="mt-3 text-[13px] font-semibold text-[#355FA1]"
        onClick={() => setEngineOpen(!engineOpen)}
      >
        {`${t("agentEngineRank")} ${engineOpen ? "‹" : "›"}`}
      </button>
      {engineOpen && (
        <ol data-testid="engine-rank" className="mt-1 space-y-0.5 text-[13px] text-[#344054]">
          {decision.engine_top3.map((id, i) => {
            const o = view.options[id];
            return (
              <li key={id}>
                {`${i + 1}. ${o ? o.short_label : name(id)}`}
                {o?.issuer && <span className="text-muted">{` · ${o.issuer}`}</span>}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
