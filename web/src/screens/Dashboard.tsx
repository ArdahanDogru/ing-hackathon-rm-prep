// Dashboard "B4" (docs/web-ui.md "Redesign v2"; mockup redesign-v4.html tab 3):
// lifecycle tabs, brief card, agenda | Öneriler, Detaylar, approval bar.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Persona, RunView } from "../api/types";
import { AgentPanel, useAgent } from "../components/AgentPanel";
import { AgentPicks, agentTop } from "../components/AgentPicks";
import { Agenda } from "../components/Agenda";
import { ApprovalBar } from "../components/ApprovalBar";
import { BriefCard } from "../components/BriefCard";
import { DetailsPanel, type Tab } from "../components/DetailsPanel";
import { EvidencePopup } from "../components/EvidencePopup";
import { FundCard, FundDrawer } from "../components/FundCard";
import { LifecycleTabs } from "../components/LifecycleTabs";
import { MarketNote } from "../components/MarketNote";
import { OptionsCompare } from "../components/OptionsCompare";
import { PersonaPanel } from "../components/PersonaPanel";
import { PipelinePanel } from "../components/PipelinePanel";
import { QuestionsPanel } from "../components/QuestionsPanel";
import { ResearchPanel } from "../components/ResearchPanel";
import { useChecks } from "../checks";
import { explain } from "../explain";
import { labels, useT, type LabelKey } from "../i18n";

const show = (v: unknown) => (Array.isArray(v) ? v.join(", ") : String(v));

/** "Test: P01 değiştirildi (yaş 62 → 45)" */
function TestBanner({ view, onReset }: { view: RunView; onReset?: () => void }) {
  const t = useT();
  const field = (f: string) => {
    const key = `f_${f}` as LabelKey;
    return key in labels.TR ? t(key) : f;
  };
  const changes = view.persona_changes.map((c) => `${field(c.field)} ${show(c.original)} → ${show(c.edited)}`).join("; ");
  return (
    <div role="status" className="mb-4 flex items-center gap-3 rounded-xl border border-[#FEC84B] bg-[#FFFAEB] px-4 py-2.5 text-sm">
      <b>{`${t("testBanner")}:`}</b>
      <span>{`${view.result.persona.persona_id} ${t("changed")} (${changes})`}</span>
      {onReset && (
        <button type="button" className="ml-auto text-sm underline" onClick={onReset}>
          {t("resetPersona")}
        </button>
      )}
    </div>
  );
}

export function Dashboard({
  view,
  onView,
  onPersona,
}: {
  view: RunView;
  onView: (v: RunView) => void;
  /** An edited persona (a test run), or null for the original. */
  onPersona?: (p: Persona | null) => void;
}) {
  const t = useT();
  const r = view.result;
  const runId = r.run_id;
  const [selected, setSelected] = useState<string[]>(() => (r.rm_selected.length ? r.rm_selected : view.top));
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [details, setDetails] = useState<{ tab: Tab; n: number } | null>(null);
  const [discussed, toggleDiscussed] = useChecks(`rmprep.agenda.${runId}`);
  const [confirmed, toggleConfirmed] = useChecks(`rmprep.confirm.${runId}`);
  const pending = r.rm_status === "pending";
  const ready = r.state === "ready";
  const openConfirms = view.to_confirm.filter((_, i) => !confirmed[i]).length;

  // W20: the agent's top 3 replaces the engine's when it is done; the meeting chips follow it
  // until the RM changes them
  const agent = useAgent(runId);
  const picks = agentTop(view, agent);
  // W20c: the API writes the brief from the agent's top 3 once the agent changed it: ask again then
  const agentChanged = agent?.state === "done" && agent.picks.some((p) => !agent.engine_top3.includes(p.option_id));
  const touched = useRef(false);
  const [allocationRequest, setAllocationRequest] = useState(0);
  useEffect(() => {
    if (picks && pending && !touched.current) setSelected(picks);
  }, [picks?.join("|")]);

  const toggle = (id: string) => {
    if (!pending) return;
    touched.current = true;
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  };

  const answer = (questionId: string, value: string) => {
    setError(null);
    api.answer(runId, questionId, value).then(onView, (e: Error) => setError(e.message));
  };

  const opened = openId ? view.options[openId] : undefined;
  const closeDrawer = useCallback(() => setOpenId(null), []);

  return (
    <div>
      <LifecycleTabs runId={runId} approved={r.rm_status === "approved"} active="prep" />
      {view.test_run && <TestBanner view={view} onReset={onPersona && (() => onPersona(null))} />}
      <BriefCard
        view={view}
        confirmOpen={openConfirms}
        onEdit={onPersona && (() => setEditing(true))}
        onEvidence={setEvidenceId}
        refresh={agentChanged ? 1 : 0}
      />
      <MarketNote items={view.market_note} onEvidence={setEvidenceId} />
      {error && (
        <p role="alert" className="mb-4 rounded-xl border border-red-200 bg-white p-3 text-sm">
          {`${t("errorTitle")}: ${error}`}
        </p>
      )}

      {ready && (
        <PipelinePanel
          view={view}
          onOpen={setOpenId}
          onDetails={(tab) => setDetails((d) => ({ tab, n: (d?.n ?? 0) + 1 }))}
          agent={agent}
        />
      )}

      {ready && <AgentPanel decision={agent} />}

      <div className="mb-6 grid items-start gap-6 lg:grid-cols-[1fr_2fr]">
        <Agenda
          points={view.talking_points}
          confirm={view.to_confirm}
          discussed={discussed}
          onDiscussed={toggleDiscussed}
          confirmed={confirmed}
          onConfirmed={toggleConfirmed}
          onAnswer={answer}
          onEvidence={setEvidenceId}
        />
        {ready ? (
          view.top.length > 0 ? (
            <div className="min-w-0">
              <AgentPicks
                view={view}
                decision={agent}
                onOpen={setOpenId}
                onEvidence={setEvidenceId}
                onAllocation={() => setAllocationRequest((n) => n + 1)}
              />
              <OptionsCompare
                view={view}
                onOpen={setOpenId}
                onEvidence={setEvidenceId}
                onView={onView}
                top={picks}
                allocationRequest={allocationRequest}
              />
            </div>
          ) : (
            <p className="rounded-2xl bg-white p-5 text-sm text-muted shadow-sm">{t("noOptions")}</p>
          )
        ) : (
          <QuestionsPanel questions={r.questions} onAnswer={answer} />
        )}
      </div>

      {ready && <DetailsPanel view={view} selected={selected} onToggle={toggle} onOpen={setOpenId} request={details} />}
      {ready && <ResearchPanel view={view} />}

      {ready && <ApprovalBar view={view} selected={selected} openConfirms={openConfirms} onRemove={toggle} onView={onView} />}

      {editing && onPersona && (
        <PersonaPanel
          persona={r.persona}
          onClose={() => setEditing(false)}
          onApply={(p) => {
            setEditing(false);
            onPersona(p);
          }}
        />
      )}
      {opened && (
        <FundDrawer key={opened.option_id} onClose={closeDrawer} paused={evidenceId !== null}>
          <FundCard
            option={opened}
            selected={selected.includes(opened.option_id)}
            snapshotId={r.snapshot_id}
            onToggle={() => toggle(opened.option_id)}
            onEvidence={setEvidenceId}
            explanation={explain(view, opened.option_id)}
          />
        </FundDrawer>
      )}
      <EvidencePopup
        snapshotId={r.snapshot_id}
        evidenceId={evidenceId ?? ""}
        open={evidenceId !== null}
        onClose={() => setEvidenceId(null)}
      />
    </div>
  );
}
