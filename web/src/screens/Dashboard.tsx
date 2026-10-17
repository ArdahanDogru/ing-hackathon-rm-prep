// Dashboard "B4" (docs/web-ui.md "Redesign v2"; mockup redesign-v4.html tab 3):
// lifecycle tabs, brief card, agenda | Öneriler, Detaylar, approval bar.
import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Persona, RunView } from "../api/types";
import { AgentPanel, useAgentRun } from "../components/AgentPanel";
import { AgentPicks, agentTop } from "../components/AgentPicks";
import { Agenda } from "../components/Agenda";
import { ApprovalBar } from "../components/ApprovalBar";
import { BriefCard } from "../components/BriefCard";
import { DetailNote, type NoteKind } from "../components/DetailNotes";
import { EvidencePopup } from "../components/EvidencePopup";
import { FundCard, FundDrawer } from "../components/FundCard";
import { FundDocuments } from "../components/FundDocuments";
import { LifecycleTabs } from "../components/LifecycleTabs";
import { MarketNote } from "../components/MarketNote";
import { OptionsCompare } from "../components/OptionsCompare";
import { PersonaPanel } from "../components/PersonaPanel";
import { aiChecks, aiConfirms, useProfileAI } from "../components/ProfileAI";
import { PipelinePanel } from "../components/PipelinePanel";
import { QuestionsPanel } from "../components/QuestionsPanel";
import { ResearchPanel } from "../components/ResearchPanel";
import { useChecks } from "../checks";
import { explain } from "../explain";
import { LangContext, useT } from "../i18n";
import { profileChanges } from "../profileChanges";

/** W30: "Düzenlenmiş profil: onaylanırsa …" and the changes ("yaş: 62 → 45"). */
function TestBanner({ view, onReset }: { view: RunView; onReset?: () => void }) {
  const t = useT();
  const lang = useContext(LangContext);
  return (
    <div role="status" className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-[#FEC84B] bg-[#FFFAEB] px-4 py-2.5 text-sm">
      <b>{t("editedBanner")}</b>
      <span className="text-[#93370D]">{`${view.result.persona.persona_id}: ${profileChanges(view.persona_changes, lang)}`}</span>
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
  const lang = useContext(LangContext);
  const r = view.result;
  const runId = r.run_id;
  const [selected, setSelected] = useState<string[]>(() => (r.rm_selected.length ? r.rm_selected : view.top));
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [note, setNote] = useState<NoteKind | null>(null);
  const [discussed, toggleDiscussed] = useChecks(`rmprep.agenda.${runId}`);
  const [confirmed, toggleConfirmed] = useChecks(`rmprep.confirm.${runId}`);
  const pending = r.rm_status === "pending";
  const ready = r.state === "ready";
  const ai = useProfileAI(runId, lang, ready); // W43: the AI check of the profile
  const toConfirm = [...view.to_confirm, ...aiConfirms(ai)];
  const openConfirms = toConfirm.filter((_, i) => !confirmed[i]).length;

  // W20: the agent's top 3 replaces the engine's when it is done; the meeting chips follow it
  // until the RM changes them
  const { decision: agent, start: startAgent } = useAgentRun(runId);
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
  // W23: the agent box (running, done or fallback) takes the place next to Gündem
  // W24: after an agent run the research status holds the other candidates too: ask again
  const researchRefresh =
    agent && (agent.state === "done" || agent.state === "fallback") ? `${agent.state}|${agent.created_at}|${agent.n_candidates ?? ""}` : "";
  // W24: the box is always there when the server has an agent (the start form before a run)
  const agentBox = ready && !!agent;
  const options = (
    <OptionsCompare
      view={view}
      onOpen={setOpenId}
      onEvidence={setEvidenceId}
      onView={onView}
      top={picks}
      allocationRequest={allocationRequest}
    />
  );
  const closeDrawer = useCallback(() => setOpenId(null), []);

  return (
    <div>
      <LifecycleTabs runId={runId} approved={r.rm_status === "approved"} active="prep" />
      {view.test_run && <TestBanner view={view} onReset={onPersona && (() => onPersona(null))} />}
      <BriefCard
        view={view}
        confirmOpen={openConfirms}
        ai={ai}
        onEdit={onPersona && (() => setEditing(true))}
        onEvidence={setEvidenceId}
        refresh={agentChanged ? agent.picks.map((p) => p.option_id).join("|") : ""}
      />
      <MarketNote items={view.market_note} banks={view.bank_context ?? []} clientWarnings={view.client_warnings} rmWarnings={view.rm_warnings} onEvidence={setEvidenceId} />
      {error && (
        <p role="alert" className="mb-4 rounded-xl border border-red-200 bg-white p-3 text-sm">
          {`${t("errorTitle")}: ${error}`}
        </p>
      )}

      {ready && (
        <PipelinePanel
          view={view}
          onOpen={setOpenId}
          onDetails={setNote}
          agent={agent}
        />
      )}

      {ready && <AgentPanel decision={agent} />}

      {/* W23: with the agent box, row 1 = Gündem and the agent box (same height: the grid
          stretches both; the taller content sets the row height), row 2 = Öneriler over the full
          width. Without it, Gündem and Öneriler side by side as before. One column on narrow screens. */}
      <div
        data-testid="dash-row1"
        className={`mb-6 grid gap-6 lg:grid-cols-[1fr_2fr] ${agentBox ? "items-stretch" : "items-start"}`}
      >
        <Agenda
          points={view.talking_points}
          confirm={toConfirm}
          discussed={discussed}
          onDiscussed={toggleDiscussed}
          confirmed={confirmed}
          onConfirmed={toggleConfirmed}
          onAnswer={answer}
          onEvidence={setEvidenceId}
        />
        {!ready ? (
          <QuestionsPanel questions={r.questions} onAnswer={answer} />
        ) : !view.top.length ? (
          <p className="rounded-2xl bg-white p-5 text-sm text-muted shadow-sm">{t("noOptions")}</p>
        ) : agentBox ? (
          <AgentPicks
            view={view}
            decision={agent}
            onOpen={setOpenId}
            onEvidence={setEvidenceId}
            onAllocation={() => setAllocationRequest((n) => n + 1)}
            onStart={startAgent}
          />
        ) : (
          options
        )}
      </div>
      {ready && view.top.length > 0 && agentBox && (
        <div data-testid="dash-row2" className="mb-6">
          {options}
        </div>
      )}

      {ready && note && (
        <DetailNote
          kind={note}
          view={view}
          onOpen={(id) => {
            setNote(null); // the fund card opens in place of the note
            setOpenId(id);
          }}
          onClose={() => setNote(null)}
        />
      )}
      {ready && <ResearchPanel view={view} refresh={researchRefresh} agentRunning={agent?.state === "running"} />}

      {ready && <ApprovalBar view={view} selected={selected} openConfirms={openConfirms} onRemove={toggle} onView={onView} />}

      {editing && onPersona && (
        <PersonaPanel
          persona={r.persona}
          checks={[...(view.profile_checks ?? []), ...aiChecks(ai)]}
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
            documents={<FundDocuments runId={runId} option={opened} />}
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
