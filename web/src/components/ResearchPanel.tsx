// Web research panel (docs/research.md section 11): the recommended products and their
// companies, researched on the web, and the RM's own questions. Information only: it
// never changes the scores, the recommendation or the meeting text.
import { useContext, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { Lang, ProductResearch, QuestionAnswer, ResearchFinding, ResearchView, RunView } from "../api/types";
import { fill, LangContext, useT, type LabelKey } from "../i18n";

const POLL_MS = 3000;
const POLL_MAX = 40; // 2 minutes; 3 products take about 10 s
const LIMIT_ERROR = "daily limit"; // rmprep.research.service.LIMIT_ERROR
const CONFIDENCE: Record<ResearchFinding["confidence"], LabelKey> = {
  high: "researchConfHigh",
  medium: "researchConfMedium",
  low: "researchConfLow",
};

/** The research of a ready run: asked at once, then every 3 s while it runs (at most 40 calls).
 * An error, or a server without research, gives "off" with no reason (the panel stays hidden). */
export function useResearch(runId: string, lang: Lang, enabled: boolean): ResearchView | null {
  const [view, setView] = useState<ResearchView | null>(null);
  useEffect(() => {
    setView(null);
    if (!enabled) return;
    let done = false;
    let calls = 0;
    const stop = () => {
      done = true;
      clearInterval(timer);
    };
    const ask = () => {
      if (done) return;
      if (calls >= POLL_MAX) {
        setView({ state: "off", reason: "" });
        return stop();
      }
      calls += 1;
      api.research(runId, lang).then(
        (v) => {
          if (done) return;
          setView(v);
          if (v.state !== "running") stop();
        },
        () => {
          if (!done) setView({ state: "off", reason: "" });
          stop();
        },
      );
    };
    const timer = setInterval(ask, POLL_MS);
    ask();
    return stop;
  }, [runId, lang, enabled]);
  return view;
}

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function FindingList({ findings }: { findings: ResearchFinding[] }) {
  const t = useT();
  return (
    <ul className="text-sm">
      {findings.map((f) => (
        <li key={f.text} className="mb-2">
          <span>{f.text}</span>
          <span className="ml-2 text-xs text-muted">
            {f.sources.map((s, i) => (
              <span key={s.url}>
                {i > 0 && " · "}
                <a href={s.url} target="_blank" rel="noreferrer" title={s.title} className="text-[#355FA1] underline">
                  {host(s.url)}
                </a>
                {s.published && ` (${s.published})`}
              </span>
            ))}
            {` · ${t(CONFIDENCE[f.confidence])}`}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ErrorLine({ error }: { error: string }) {
  const t = useT();
  return <p className="mt-2 text-sm text-[#B54708]">{error === LIMIT_ERROR ? t("researchLimit") : fill(t("researchFailed"), { error })}</p>;
}

function ProductCard({ p }: { p: ProductResearch }) {
  const t = useT();
  const product = p.findings.filter((f) => f.topic !== "sirket");
  const company = p.findings.filter((f) => f.topic === "sirket");
  return (
    <article data-testid="research-product" className="rounded-xl bg-[#F7F9FC] px-4 py-3">
      <h3 className="font-semibold">{p.label}</h3>
      {p.company && <p className="text-sm text-muted">{`${t("researchCompany")}: ${p.company}`}</p>}
      {p.error ? (
        <ErrorLine error={p.error} />
      ) : (
        <>
          {p.summary && <p className="mt-2 text-sm">{p.summary}</p>}
          {p.findings.length === 0 && <p className="mt-2 text-sm text-muted">{t("researchNoFindings")}</p>}
          {product.length > 0 && (
            <>
              <h4 className="mt-2 text-xs font-bold uppercase tracking-[0.06em] text-muted">{t("researchProduct")}</h4>
              <FindingList findings={product} />
            </>
          )}
          {company.length > 0 && (
            <>
              <h4 className="mt-2 text-xs font-bold uppercase tracking-[0.06em] text-muted">{t("researchCompany")}</h4>
              <FindingList findings={company} />
            </>
          )}
        </>
      )}
    </article>
  );
}

function AnswerCard({ a }: { a: QuestionAnswer }) {
  const t = useT();
  return (
    <article data-testid="research-answer" className="rounded-xl bg-[#F7F9FC] px-4 py-3">
      <h3 className="font-semibold">{a.question}</h3>
      {a.error ? (
        <ErrorLine error={a.error} />
      ) : (
        <>
          {a.summary && <p className="mt-1 text-sm">{a.summary}</p>}
          {a.findings.length === 0 ? <p className="mt-2 text-sm text-muted">{t("researchNoFindings")}</p> : <FindingList findings={a.findings} />}
        </>
      )}
    </article>
  );
}

export function ResearchPanel({ view }: { view: RunView }) {
  const t = useT();
  const lang = useContext(LangContext);
  const runId = view.result.run_id;
  const research = useResearch(runId, lang, view.result.state === "ready");
  const [asked, setAsked] = useState<QuestionAnswer[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  useEffect(() => {
    setAsked([]);
    setRefused(null);
  }, [runId, lang]);

  if (research === null || (research.state === "off" && !research.reason)) return null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setRefused(null);
    api
      .askResearch(runId, q, lang)
      .then(
        (a) => {
          setAsked((xs) => [a, ...xs.filter((x) => x.question !== a.question)]);
          setQuestion("");
        },
        (err) => setRefused(err instanceof ApiError ? err.detail : String(err)),
      )
      .finally(() => setBusy(false));
  };

  const earlier = research.state === "ready" ? research.questions : [];
  const answers = [...asked, ...earlier.filter((s) => !asked.some((a) => a.question === s.question))];

  return (
    <section data-testid="research-panel" className="mb-6 rounded-2xl bg-white px-[26px] py-[22px] shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-bold">{t("researchTitle")}</h2>
        <span className="rounded-full bg-[#FEF0C7] px-2 py-0.5 text-[11px] font-semibold text-[#B54708]">{t("researchLabel")}</span>
      </div>
      <p className="mb-3 text-[13px] text-muted">{t("researchNote")}</p>
      {research.state === "off" && <p className="text-sm text-muted">{fill(t("researchOff"), { reason: research.reason })}</p>}
      {research.state === "running" && (
        <p data-testid="research-running" className="text-sm text-muted">
          {t("researchRunning")}
        </p>
      )}
      {research.state === "ready" && (
        <div className="grid gap-3 lg:grid-cols-3">
          {research.products.map((p) => (
            <ProductCard key={p.option_id} p={p} />
          ))}
        </div>
      )}
      {research.state !== "off" && (
        <form onSubmit={submit} className="mt-4 flex gap-2">
          <input
            aria-label={t("researchAsk")}
            placeholder={t("researchAsk")}
            value={question}
            maxLength={300}
            onChange={(e) => setQuestion(e.target.value)}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          />
          <button
            type="submit"
            disabled={busy || !question.trim()}
            className="rounded-lg bg-cobalt px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? t("researchAsking") : t("researchAskButton")}
          </button>
        </form>
      )}
      {refused && (
        <p role="status" className="mt-2 text-sm text-[#B54708]">
          {refused}
        </p>
      )}
      {answers.length > 0 && (
        <div className="mt-3 grid gap-3">
          {answers.map((a) => (
            <AnswerCard key={a.question} a={a} />
          ))}
        </div>
      )}
    </section>
  );
}
