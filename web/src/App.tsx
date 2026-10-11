// App shell: top bar, run state, routes / (dashboard), /meeting/:runId, /print/:runId.
import { useCallback, useEffect, useState } from "react";
import { Route, Routes, useParams } from "react-router-dom";
import { api, getRunOrRerun, recallInputs, rememberInputs } from "./api/client";
import type { Lang, Persona, RunInputs, RunView, SourceStatus } from "./api/types";
import { TopBar } from "./components/TopBar";
import { Dashboard } from "./screens/Dashboard";
import { MeetingText } from "./screens/MeetingText";
import { LangContext, labels, useT } from "./i18n";

function ErrorLine({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const t = useT();
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-white p-4 text-sm">
      <b>{t("errorTitle")}:</b> {error.message}{" "}
      <button type="button" className="ml-2 underline" onClick={onRetry}>
        {t("retry")}
      </button>
    </div>
  );
}

function MeetingRoute() {
  const t = useT();
  const { runId = "" } = useParams();
  const [run, setRun] = useState<RunView | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const load = useCallback(() => {
    setError(null);
    const inputs = recallInputs(runId);
    (inputs ? getRunOrRerun(runId, inputs) : api.getRun(runId)).then(setRun, setError);
  }, [runId]);
  useEffect(load, [load]);
  if (error) return <ErrorLine error={error} onRetry={load} />;
  if (!run) return <p className="text-sm text-muted">{t("loading")}</p>;
  return <MeetingText view={run} />;
}

function PrintRoute() {
  const t = useT();
  const { runId = "" } = useParams();
  return (
    <main className="p-8">
      <h1 className="text-xl font-semibold">{t("printCard")}</h1>
      <p className="text-sm text-muted">{runId}</p>
    </main>
  );
}

export function App() {
  const [lang, setLang] = useState<Lang>("TR");
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [snapshots, setSnapshots] = useState<string[]>([]);
  const [personaId, setPersonaId] = useState("");
  const [snapshotId, setSnapshotId] = useState("");
  const [sources, setSources] = useState<Record<string, SourceStatus>>({});
  const [excluded, setExcluded] = useState<string[]>([]);
  const [edited, setEdited] = useState<Persona | null>(null); // a test run's persona
  const [run, setRun] = useState<RunView | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);

  const init = useCallback(() => {
    setError(null);
    setLoading(true);
    Promise.all([api.personas(), api.snapshots()]).then(([ps, ss]) => {
      setPersonas(ps);
      setSnapshots(ss);
      setPersonaId((id) => id || ps[0]?.persona_id || "");
      setSnapshotId((id) => id || ss[0] || "");
      if (!ps.length) setLoading(false);
    }, (e: Error) => {
      setError(e);
      setLoading(false);
    });
  }, []);
  useEffect(init, [init]);

  useEffect(() => {
    if (!snapshotId) return;
    api.sources(snapshotId).then(setSources, () => setSources({}));
  }, [snapshotId]);

  const makeRun = useCallback(() => {
    const persona = edited ?? personas.find((p) => p.persona_id === personaId);
    if (!persona || !snapshotId) return;
    const inputs: RunInputs = { persona, snapshot_id: snapshotId, exclude_sources: excluded };
    setError(null);
    setLoading(true);
    api.run(inputs).then(
      (view) => {
        rememberInputs(view.result.run_id, inputs);
        setRun(view);
        setLoading(false);
      },
      (e: Error) => {
        setError(e);
        setLoading(false);
      },
    );
  }, [personas, personaId, snapshotId, excluded, edited]);
  useEffect(makeRun, [makeRun]);

  const retry = personas.length ? makeRun : init;

  return (
    <LangContext.Provider value={lang}>
      <Routes>
        <Route path="/print/:runId" element={<PrintRoute />} />
        <Route
          path="*"
          element={
            <div className="min-h-screen bg-surface font-sans text-ink">
              <TopBar
                personas={personas}
                personaId={personaId}
                onPersona={(id) => {
                  setEdited(null);
                  setPersonaId(id);
                }}
                snapshots={snapshots}
                snapshotId={snapshotId}
                onSnapshot={setSnapshotId}
                sources={sources}
                excluded={excluded}
                onExcluded={setExcluded}
                lang={lang}
                onLang={setLang}
              />
              <main className="mx-auto max-w-[1400px] p-6">
                <Routes>
                  <Route
                    path="/"
                    element={
                      error ? (
                        <ErrorLine error={error} onRetry={retry} />
                      ) : loading && !run ? (
                        <p className="text-sm text-muted">{labels[lang].loading}</p>
                      ) : run ? (
                        <Dashboard
                          key={run.result.run_id + run.result.rm_status}
                          view={run}
                          onView={setRun}
                          onPersona={setEdited}
                        />
                      ) : (
                        <p className="text-sm text-muted">{labels[lang].noRun}</p>
                      )
                    }
                  />
                  <Route path="/meeting/:runId" element={<MeetingRoute />} />
                </Routes>
              </main>
            </div>
          }
        />
      </Routes>
    </LangContext.Provider>
  );
}
