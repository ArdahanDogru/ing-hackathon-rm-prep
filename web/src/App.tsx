// App shell: top bar, run state, routes / (dashboard), /meeting/:runId, /print/:runId.
import { useCallback, useContext, useEffect, useState } from "react";
import { Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, getRunOrRerun, recallInputs, rememberInputs } from "./api/client";
import type { Lang, NarrativeView, Persona, RunInputs, RunView, SourceStatus } from "./api/types";
import { DataFreshness } from "./components/DataFreshness";
import { ErrorBox } from "./components/ErrorBox";
import { DashboardSkeleton } from "./components/Skeleton";
import { TopBar } from "./components/TopBar";
import { Dashboard } from "./screens/Dashboard";
import { MeetingText } from "./screens/MeetingText";
import { PrintCard } from "./screens/PrintCard";
import { LangContext, labels, useT } from "./i18n";

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
  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!run) return <p className="animate-pulse text-sm text-muted">{t("loading")}</p>;
  return <MeetingText view={run} />;
}

function PrintRoute() {
  const { runId = "" } = useParams();
  const lang = useContext(LangContext);
  const [run, setRun] = useState<RunView | null>(null);
  const [text, setText] = useState<NarrativeView | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const load = useCallback(() => {
    setError(null);
    const inputs = recallInputs(runId);
    (inputs ? getRunOrRerun(runId, inputs) : api.getRun(runId))
      .then((v) => {
        setRun(v);
        return api.narrative(runId, lang);
      })
      .then(setText, setError);
  }, [runId, lang]);
  useEffect(load, [load]);
  useEffect(() => {
    if (run && text) {
      const timer = setTimeout(() => window.print(), 400); // after the fonts and layout
      return () => clearTimeout(timer);
    }
  }, [run, text]);
  if (error)
    return (
      <main className="p-8">
        <ErrorBox error={error} onRetry={load} />
      </main>
    );
  if (!run || !text) return <p className="p-8 text-sm text-muted">{labels[lang].loading}</p>;
  return <PrintCard view={run} narrative={text} />;
}

const LANG_KEY = "rmprep.lang";

function savedLang(): Lang {
  try {
    return localStorage.getItem(LANG_KEY) === "EN" ? "EN" : "TR";
  } catch {
    return "TR";
  }
}

export function App() {
  const navigate = useNavigate();
  const printing = useLocation().pathname.startsWith("/print/"); // a print tab loads only its own run
  const [lang, setLangState] = useState<Lang>(savedLang);
  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(LANG_KEY, l);
    } catch {
      // storage blocked: the choice holds for this tab only
    }
  };
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
    if (printing) return;
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
  }, [printing]);
  useEffect(init, [init]);

  // "Yeni veriyle aç" (W14): the new snapshot list, and its newest snapshot
  const openNewest = useCallback(() => {
    api.snapshots().then((ss) => {
      setSnapshots(ss);
      if (ss[0]) setSnapshotId(ss[0]);
    }, setError);
  }, []);

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
                  navigate("/");
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
                      <>
                        <DataFreshness known={snapshots} onOpenNewest={openNewest} />
                        {error ? (
                          <ErrorBox error={error} onRetry={retry} />
                        ) : loading && !run ? (
                          <DashboardSkeleton />
                        ) : run ? (
                          <Dashboard
                            key={run.result.run_id + run.result.rm_status}
                            view={run}
                            onView={setRun}
                            onPersona={setEdited}
                          />
                        ) : (
                          <p className="text-sm text-muted">{labels[lang].noRun}</p>
                        )}
                      </>
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
