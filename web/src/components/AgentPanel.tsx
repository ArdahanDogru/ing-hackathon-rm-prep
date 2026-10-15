// "Ajan değerlendirmesi" (W20; spec docs/superpowers/specs/2026-10-15-agent-decision-design.md
// sections 4 and 8): the agent's five nodes in a row with their state, time and cost; a click
// opens the notes and the sub-nodes. No raw model thinking: the notes are the `amac` texts and
// the check results.
import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AgentDecision, AgentNode, AgentNodeState } from "../api/types";
import { fill, LangContext, useT, type LabelKey } from "../i18n";

const POLL_MS = 2000;
const MAX_POLLS = 60;

/** The agent decision of a run and a way to start it (W24: the RM starts it). The decision is
 * asked at once, then every 2 s while it runs (at most 60 times); `start(n)` posts N and polls again. */
export function useAgentRun(runId: string): { decision: AgentDecision | null; start: (n: number) => Promise<void> } {
  const [decision, setDecision] = useState<AgentDecision | null>(null);
  const [round, setRound] = useState(0); // a new round polls again (after a start)
  const shownRun = useRef(runId);
  useEffect(() => {
    let live = true;
    let polls = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    if (shownRun.current !== runId) setDecision(null); // another run: not the old decision
    shownRun.current = runId;
    const poll = () => {
      polls += 1;
      api.agentStatus(runId).then(
        (d) => {
          if (!live) return;
          setDecision(d);
          if (d?.state === "running" && polls < MAX_POLLS) timer = setTimeout(poll, POLL_MS);
        },
        () => live && setDecision(null), // no agent on this server: the engine's view only
      );
    };
    poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [runId, round]);
  const start = useCallback(
    async (n: number) => {
      const d = await api.startAgent(runId, n); // an ApiError goes to the caller (the form shows it)
      setDecision(d);
      setRound((r) => r + 1);
    },
    [runId],
  );
  return { decision, start };
}

/** The agent decision of a run (polled). */
export function useAgent(runId: string): AgentDecision | null {
  return useAgentRun(runId).decision;
}

const STATE_WORD: Record<AgentNodeState, LabelKey> = {
  waiting: "nodeWaiting",
  running: "nodeRunning",
  done: "nodeDone",
  failed: "nodeFailed",
};
const STATE_TONE: Record<AgentNodeState, string> = {
  waiting: "border-gray-200 bg-white text-muted",
  running: "border-cobalt bg-[#EEF2F9] text-ink",
  done: "border-[#ABEFC6] bg-[#ECFDF3] text-ink",
  failed: "border-[#FECDCA] bg-[#FEF3F2] text-ink",
};

/** "$0,04" (TR) / "$0.04" (EN). */
export function useCost(): (usd: number) => string {
  const lang = useContext(LangContext);
  return (usd) => `$${usd.toLocaleString(lang === "TR" ? "tr-TR" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function seconds(n: AgentNode): number | null {
  if (!n.started_at || !n.finished_at) return null;
  return Math.max(0, Math.round((Date.parse(n.finished_at) - Date.parse(n.started_at)) / 1000));
}

function NodeDetails({ node }: { node: AgentNode }) {
  const t = useT();
  return (
    <div data-testid="node-details" className="mt-3 rounded-xl border border-gray-200 bg-white px-4 py-3 text-[13px] text-[#344054]">
      <b>{node.label}</b>
      {node.notes.length > 0 ? (
        <ul className="mt-1 list-disc space-y-0.5 pl-5">
          {node.notes.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      ) : (
        !node.children.length && <p className="mt-1 text-muted">{t("nodeNoNotes")}</p>
      )}
      {node.children.length > 0 && (
        <ul className="mt-2 space-y-1">
          {node.children.map((c) => (
            <li key={c.id} className="flex flex-wrap items-baseline gap-x-2">
              <span className={c.state === "failed" ? "text-[#B42318]" : ""}>{`${c.state === "done" ? "✓" : c.state === "failed" ? "✕" : "·"} ${c.label}`}</span>
              <span className="text-xs text-muted">{t(STATE_WORD[c.state])}</span>
              {c.notes.map((x) => (
                <span key={x} className="basis-full pl-4 text-xs text-muted">
                  {x}
                </span>
              ))}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function AgentPanel({ decision }: { decision: AgentDecision | null }) {
  const t = useT();
  const cost = useCost();
  const [open, setOpen] = useState<string | null>(null);
  if (!decision || decision.state === "off" || !decision.nodes.length) return null;
  const opened = decision.nodes.find((n) => n.id === open);
  return (
    <section data-testid="agent-panel" className="mb-6 rounded-2xl bg-white px-[18px] py-3.5 shadow-sm">
      <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-2">
        <b className="text-[#344054]">{t("agentTitle")}</b>
        <span className="text-xs text-muted">{[decision.model, cost(decision.cost_usd)].filter(Boolean).join(" · ")}</span>
      </div>
      <ol className="grid gap-2 sm:grid-cols-5">
        {decision.nodes.map((n, i) => {
          const s = seconds(n);
          return (
            <li key={n.id}>
              <button
                type="button"
                data-testid="agent-node"
                data-node={n.id}
                data-state={n.state}
                aria-expanded={open === n.id}
                className={`flex w-full flex-col gap-0.5 rounded-xl border px-3 py-2 text-left text-[13px] ${STATE_TONE[n.state]} ${open === n.id ? "ring-2 ring-cobalt/40" : ""}`}
                onClick={() => setOpen(open === n.id ? null : n.id)}
              >
                <span className="flex items-center gap-1.5 font-semibold">
                  {n.state === "running" && (
                    <span data-testid="node-spinner" aria-hidden="true" className="relative flex h-2 w-2">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cobalt opacity-60" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-cobalt" />
                    </span>
                  )}
                  {`${i + 1} · ${n.label}`}
                </span>
                <span className="text-xs text-muted">
                  {[t(STATE_WORD[n.state]), s !== null ? fill(t("nodeSeconds"), { n: s }) : "", n.cost_usd > 0 ? cost(n.cost_usd) : ""]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      {opened && <NodeDetails node={opened} />}
    </section>
  );
}
