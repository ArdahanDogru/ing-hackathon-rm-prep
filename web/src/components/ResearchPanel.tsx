// Web research panel (docs/research.md section 11): the recommended products and their
// companies, researched on the web, and the RM's own questions. Information only: it
// never changes the scores, the recommendation or the meeting text.
// W24: the RM marks each bullet ✓ (doğrulandı) or ✗ (yanlış / alakasız: not given to the
// agent); after an agent run the other candidates' research shows too, under its own heading.
import { useContext, useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { FindingMark, Lang, ProductResearch, QuestionAnswer, ResearchFinding, ResearchSource, ResearchView, RunView } from "../api/types";
import { fill, LangContext, useT } from "../i18n";
import { CodeBadge } from "../product";

const POLL_MS = 3000;
const POLL_MAX = 40; // 2 minutes; 3 products take about 10 s
const LIMIT_ERROR = "daily limit"; // rmprep.research.service.LIMIT_ERROR

/** The research of a ready run: asked at once, then every 3 s while it runs (at most 40 calls).
 * An error, or a server without research, gives "off" with no reason (the panel stays hidden).
 * A new `refresh` asks again (W24: after an agent run); the view on screen stays meanwhile. */
export function useResearch(runId: string, lang: Lang, enabled: boolean, refresh: number | string = 0): ResearchView | null {
  const [view, setView] = useState<ResearchView | null>(null);
  const shown = useRef("");
  useEffect(() => {
    const key = `${runId}|${lang}|${enabled}`;
    if (shown.current !== key) setView(null); // another run or language: not the old view
    shown.current = key;
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
          if (v.state === "running" && refresh) return; // a refresh keeps the view on screen while it runs
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
  }, [runId, lang, enabled, refresh]);
  return view;
}

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** "2026-10-10" -> "10.10.2026"; anything else stays as it is. */
function dmy(date: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : date;
}

/** The distinct source URLs of the groups, numbered 1..n in order of appearance (news first, then highlights). */
function sourceIndex(groups: ResearchFinding[][]): Map<string, number> {
  const index = new Map<string, number>();
  for (const group of groups) {
    for (const f of group) {
      for (const s of f.sources) if (!index.has(s.url)) index.set(s.url, index.size + 1);
    }
  }
  return index;
}

function distinctSources(groups: ResearchFinding[][]): ResearchSource[] {
  const seen = new Map<string, ResearchSource>();
  for (const group of groups) {
    for (const f of group) {
      for (const s of f.sources) if (!seen.has(s.url)) seen.set(s.url, s);
    }
  }
  return [...seen.values()];
}

/** Where a finding's mark goes: the product and the run (W24). */
interface MarkTarget {
  optionId: string;
  runId: string;
}

const toggle = (on: boolean) =>
  `ml-1 inline-flex h-5 w-5 items-center justify-center rounded border text-[11px] font-bold ${
    on ? "border-ink bg-ink text-white" : "border-gray-300 bg-white text-muted hover:border-ink"
  }`;

/** One bullet; with an id and a target it has ✓ and ✗ (a second click removes the mark). */
function Bullet({ f, numbers, dated, target }: { f: ResearchFinding; numbers: number[]; dated: boolean; target?: MarkTarget }) {
  const t = useT();
  const [mark, setMark] = useState<FindingMark>(f.mark ?? null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setMark(f.mark ?? null), [f.mark]);
  const send = (next: FindingMark) => {
    if (!f.id || !target) return;
    setError(null);
    api.setMark({ finding_id: f.id, option_id: target.optionId, mark: next, run_id: target.runId }).then(
      (r) => setMark(r.mark),
      (e) => setError(e instanceof ApiError ? e.detail : String(e)),
    );
  };
  const marks = !!f.id && !!target;
  return (
    <li data-mark={mark ?? undefined} className={`mb-1 ${mark === "wrong" ? "opacity-50" : ""}`}>
      {dated && f.date ? `${dmy(f.date)} · ` : ""}
      <span className={mark === "wrong" ? "line-through decoration-gray-400" : ""}>{f.text}</span>
      {numbers.length > 0 && <span className="text-xs text-muted">{` [${numbers.join(", ")}]`}</span>}
      {f.confidence === "low" && <span className="text-xs text-muted">{` · ${t("researchLowConfidence")}`}</span>}
      {mark === "ok" && <span className="ml-1.5 rounded bg-[#ECFDF3] px-1.5 text-[11px] font-semibold text-[#067647]">{t("markOkLabel")}</span>}
      {mark === "wrong" && <span className="ml-1.5 text-[11px] font-semibold text-[#B42318]">{t("markWrongLabel")}</span>}
      {marks && (
        <span className="ml-1 whitespace-nowrap align-[1px]">
          <button type="button" aria-label={t("markOk")} title={t("markOk")} aria-pressed={mark === "ok"} className={toggle(mark === "ok")} onClick={() => send(mark === "ok" ? null : "ok")}>
            ✓
          </button>
          <button type="button" aria-label={t("markWrong")} title={t("markWrong")} aria-pressed={mark === "wrong"} className={toggle(mark === "wrong")} onClick={() => send(mark === "wrong" ? null : "wrong")}>
            ✗
          </button>
        </span>
      )}
      {error && (
        <span role="status" className="ml-1.5 text-xs text-[#B42318]">
          {error}
        </span>
      )}
    </li>
  );
}

function Bullets({ items, index, dated = false, target }: { items: ResearchFinding[]; index: Map<string, number>; dated?: boolean; target?: MarkTarget }) {
  return (
    <ul className="list-disc pl-5 text-sm">
      {items.map((f) => {
        const numbers = [...new Set(f.sources.map((s) => index.get(s.url)).filter((n): n is number => n !== undefined))];
        return <Bullet key={f.id ?? `${f.date}|${f.text}`} f={f} numbers={numbers} dated={dated} target={target} />;
      })}
    </ul>
  );
}

function SourceList({ sources }: { sources: ResearchSource[] }) {
  const t = useT();
  if (sources.length === 0) return null;
  return (
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer text-muted">{fill(t("researchSources"), { n: sources.length })}</summary>
      <ol className="list-decimal pl-5">
        {sources.map((s) => (
          <li key={s.url}>
            <a href={s.url} target="_blank" rel="noreferrer" title={s.title} className="text-[#355FA1] underline">
              {host(s.url)}
            </a>
            {s.title && <span className="text-muted">{` · ${s.title}`}</span>}
            {s.published && <span className="text-muted">{` · ${dmy(s.published)}`}</span>}
          </li>
        ))}
      </ol>
    </details>
  );
}

function ErrorLine({ error }: { error: string }) {
  const t = useT();
  return <p className="mt-2 text-sm text-[#B54708]">{error === LIMIT_ERROR ? t("researchLimit") : fill(t("researchFailed"), { error })}</p>;
}

const HEADING = "mt-2 text-xs font-bold uppercase tracking-[0.06em] text-muted";

function ProductBlock({ p, runId }: { p: ProductResearch; runId: string }) {
  const t = useT();
  // No news section without a news search (news_days 0: the Claude fallback), and no crash on a payload without news.
  const showNews = (p.news_days ?? 0) > 0;
  const news = showNews ? (p.news ?? []) : [];
  const findings = p.findings ?? [];
  const groups = [news, findings];
  const index = sourceIndex(groups);
  const target = { optionId: p.option_id, runId };
  return (
    <article data-testid="research-product" className="rounded-xl bg-[#F7F9FC] px-4 py-3">
      <h3 className="font-semibold">
        <CodeBadge optionId={p.option_id} />
        {p.label}
        {p.company && <span className="ml-2 text-sm font-normal text-muted">{p.company}</span>}
      </h3>
      {p.error ? (
        <ErrorLine error={p.error} />
      ) : (
        <>
          {showNews && (
            <>
              <h4 className={HEADING}>{t("researchNews")}</h4>
              {news.length > 0 ? (
                <Bullets items={news} index={index} dated target={target} />
              ) : (
                <p className="text-sm text-muted">{fill(t("researchNoNews"), { n: p.news_days })}</p>
              )}
            </>
          )}
          <h4 className={HEADING}>{t("researchHighlights")}</h4>
          {findings.length > 0 ? <Bullets items={findings} index={index} target={target} /> : <p className="text-sm text-muted">{t("researchNoFindings")}</p>}
          <SourceList sources={distinctSources(groups)} />
        </>
      )}
    </article>
  );
}

function AnswerBlock({ a }: { a: QuestionAnswer }) {
  const t = useT();
  const groups = [a.findings];
  return (
    <article data-testid="research-answer" className="rounded-xl bg-[#F7F9FC] px-4 py-3">
      <h3 className="font-semibold">{a.question}</h3>
      {a.error ? (
        <ErrorLine error={a.error} />
      ) : a.findings.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("researchNoFindings")}</p>
      ) : (
        <>
          <div className="mt-1">
            <Bullets items={a.findings} index={sourceIndex(groups)} />
          </div>
          <SourceList sources={distinctSources(groups)} />
        </>
      )}
    </article>
  );
}

export function ResearchPanel({ view, refresh = 0 }: { view: RunView; refresh?: number | string }) {
  const t = useT();
  const lang = useContext(LangContext);
  const runId = view.result.run_id;
  const research = useResearch(runId, lang, view.result.state === "ready", refresh);
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
        <div className="grid gap-3">
          {research.products
            .filter((p) => view.result.recommended.includes(p.option_id))
            .map((p) => (
              <ProductBlock key={p.option_id} p={p} runId={runId} />
            ))}
        </div>
      )}
      {research.state === "ready" && research.products.some((p) => !view.result.recommended.includes(p.option_id)) && (
        <div data-testid="research-others" className="mt-4">
          <h3 className="mb-2 text-xs font-bold uppercase tracking-[0.06em] text-muted">{t("researchOthers")}</h3>
          <div className="grid gap-3">
            {research.products
              .filter((p) => !view.result.recommended.includes(p.option_id))
              .map((p) => (
                <ProductBlock key={p.option_id} p={p} runId={runId} />
              ))}
          </div>
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
            <AnswerBlock key={a.question} a={a} />
          ))}
        </div>
      )}
    </section>
  );
}
