// Main screen, layout A (docs/web-ui.md "Main screen"; mockups layout.html A, dikkat-v3.html A).
import { useState } from "react";
import { api } from "../api/client";
import type { RunView } from "../api/types";
import { ApprovalBar } from "../components/ApprovalBar";
import { CategoryList } from "../components/CategoryList";
import { ClientCard } from "../components/ClientCard";
import { CompareCard } from "../components/CompareCard";
import { RightPanel } from "../components/RightPanel";
import { TalkingPoints } from "../components/TalkingPoints";
import { TopOptionCard } from "../components/TopOptionCard";
import { useT } from "../i18n";

export function Dashboard({ view, onView }: { view: RunView; onView: (v: RunView) => void }) {
  const t = useT();
  const r = view.result;
  const [selected, setSelected] = useState<string[]>(() => (r.rm_selected.length ? r.rm_selected : view.top));
  const pending = r.rm_status === "pending";
  const [error, setError] = useState<string | null>(null);

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const answer = (questionId: string, value: string) => {
    setError(null);
    api.answer(r.run_id, questionId, value).then(onView, (e: Error) => setError(e.message));
  };

  return (
    <div>
      <ClientCard persona={r.persona} />
      {error && (
        <p role="alert" className="mt-3 rounded-xl border border-red-200 bg-white p-3 text-sm">
          {`${t("errorTitle")}: ${error}`}
        </p>
      )}
      <TalkingPoints points={view.talking_points} />

      <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_330px]">
        <div>
          {r.state === "ready" && view.top.length > 0 ? (
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
                      onToggle={() => pending && toggle(id)}
                    />
                  ) : null,
                )}
                {view.baseline && <CompareCard option={view.baseline} />}
              </div>
              <CategoryList
                categories={view.categories}
                options={view.options}
                selected={selected}
                onToggle={(id) => pending && toggle(id)}
              />
            </>
          ) : (
            <p className="rounded-2xl bg-white p-5 text-sm text-muted shadow-sm">{t("noOptions")}</p>
          )}
        </div>
        <RightPanel view={view} onAnswer={answer} />
      </div>

      {r.state === "ready" && <ApprovalBar view={view} selected={selected} onRemove={toggle} onView={onView} />}
    </div>
  );
}
