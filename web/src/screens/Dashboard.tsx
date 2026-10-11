// Main screen, layout A (docs/web-ui.md "Main screen"; mockups layout.html A, dikkat-v3.html A).
import { useState } from "react";
import { api } from "../api/client";
import type { Persona, RunView } from "../api/types";
import { ApprovalBar } from "../components/ApprovalBar";
import { CategoryList } from "../components/CategoryList";
import { ClientCard } from "../components/ClientCard";
import { CompareCard } from "../components/CompareCard";
import { EvidencePopup } from "../components/EvidencePopup";
import { PersonaPanel } from "../components/PersonaPanel";
import { QuestionsPanel } from "../components/QuestionsPanel";
import { RightPanel } from "../components/RightPanel";
import { TalkingPoints } from "../components/TalkingPoints";
import { TopOptionCard } from "../components/TopOptionCard";
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
    <div role="status" className="mb-3 flex items-center gap-3 rounded-xl border border-[#FEC84B] bg-[#FFFAEB] px-4 py-2.5 text-sm">
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
  const [selected, setSelected] = useState<string[]>(() => (r.rm_selected.length ? r.rm_selected : view.top));
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const pending = r.rm_status === "pending";
  const ready = r.state === "ready";

  const toggle = (id: string) => {
    if (!pending) return;
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  };

  const answer = (questionId: string, value: string) => {
    setError(null);
    api.answer(r.run_id, questionId, value).then(onView, (e: Error) => setError(e.message));
  };

  return (
    <div>
      {view.test_run && <TestBanner view={view} onReset={onPersona && (() => onPersona(null))} />}
      <ClientCard persona={r.persona} onEdit={onPersona && (() => setEditing(true))} />
      {error && (
        <p role="alert" className="mt-3 rounded-xl border border-red-200 bg-white p-3 text-sm">
          {`${t("errorTitle")}: ${error}`}
        </p>
      )}
      <TalkingPoints points={view.talking_points} />

      <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_330px]">
        <div>
          {!ready ? (
            <QuestionsPanel questions={r.questions} onAnswer={answer} />
          ) : view.top.length > 0 ? (
            <>
              <h2 className="text-sm font-semibold">{t("topRecommendations")}</h2>
              <div className="mt-2 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {view.top.map((id, i) =>
                  view.options[id] ? (
                    <TopOptionCard
                      key={id}
                      option={view.options[id]}
                      position={i + 1}
                      selected={selected.includes(id)}
                      onToggle={() => toggle(id)}
                      onEvidence={setEvidenceId}
                    />
                  ) : null,
                )}
                {view.baseline && <CompareCard option={view.baseline} />}
              </div>
              <CategoryList
                categories={view.categories}
                options={view.options}
                selected={selected}
                onToggle={toggle}
                onEvidence={setEvidenceId}
              />
            </>
          ) : (
            <p className="rounded-2xl bg-white p-5 text-sm text-muted shadow-sm">{t("noOptions")}</p>
          )}
        </div>
        <RightPanel view={view} onAnswer={answer} />
      </div>

      {ready && <ApprovalBar view={view} selected={selected} onRemove={toggle} onView={onView} />}

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
      <EvidencePopup
        snapshotId={r.snapshot_id}
        evidenceId={evidenceId ?? ""}
        open={evidenceId !== null}
        onClose={() => setEvidenceId(null)}
      />
    </div>
  );
}
