// Brief card (B4 item 3): who the client is, the brief, the data line, readiness n / 3.
import { useContext, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Lang, NarrativeBrief, Persona, RunView } from "../api/types";
import { LangContext, useT } from "../i18n";

const POLL_MS = 2000;
const POLL_MAX = 10;

/** The LLM brief of a ready run, or null: asked at once, then every 2 s while it runs,
 * at most 10 calls. A template brief, an error or 10 "running" answers give null (the
 * plain sentence stays). A new `refresh` asks again (W20c: the agent changed the top 3);
 * the brief on screen stays until the new one is there. */
export function useLlmBrief(runId: string, lang: Lang, enabled: boolean, refresh: number | string = 0): NarrativeBrief | null {
  const [brief, setBrief] = useState<NarrativeBrief | null>(null);
  const shown = useRef("");
  useEffect(() => {
    const key = `${runId}|${lang}|${enabled}`;
    if (shown.current !== key) setBrief(null); // another run or language: not the old text
    shown.current = key;
    if (!enabled) return;
    let done = false;
    let calls = 0;
    const stop = () => {
      done = true;
      clearInterval(timer);
    };
    const ask = () => {
      if (done || calls >= POLL_MAX) return stop();
      calls += 1;
      api.brief(runId, lang).then(
        (b) => {
          if (done || b === "running") return;
          if (b.source === "llm") setBrief(b);
          stop();
        },
        stop, // no brief: the plain sentence stays (the brief is not worth an error message)
      );
    };
    const timer = setInterval(ask, POLL_MS);
    ask();
    return stop;
  }, [runId, lang, enabled, refresh]);
  return brief;
}

/** The plain brief (the LLM brief's fallback): durum + yatirim_amaci. */
export function plainBrief(p: Persona): string {
  const s = (x: string) => x.trim().replace(/[.\s]+$/, "");
  return `${s(p.durum)}. ${s(p.yatirim_amaci)}.`;
}

/** "20261010-183835-6813" → "10.10.2026" */
export function snapshotDate(id: string): string {
  const m = /^(\d{4})(\d{2})(\d{2})/.exec(id);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : id;
}

export function BriefCard({
  view,
  confirmOpen,
  onEdit,
  onEvidence,
  refresh = 0,
}: {
  view: RunView;
  confirmOpen: number;
  onEdit?: () => void;
  onEvidence?: (id: string) => void;
  /** a new value asks for the brief again (W20c) */
  refresh?: number | string;
}) {
  const t = useT();
  const lang = useContext(LangContext);
  const [showSources, setShowSources] = useState(false);
  const r = view.result;
  const p = r.persona;
  const llm = useLlmBrief(r.run_id, lang, r.state === "ready", refresh);
  const cite = llm?.cite ?? [];
  const low = (x: string) => x.toLocaleLowerCase("tr");
  const ready = r.state === "ready";
  const steps = [true, ready, ready && confirmOpen === 0];
  const done = steps.filter(Boolean).length;
  const ceiling = view.risk_ceiling;
  const sources = 1 + (p.rm_notu.trim() ? 1 : 0) + cite.length;

  return (
    <section data-testid="brief-card" className="mb-6 rounded-2xl bg-white px-[26px] py-[22px] shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <h1 className="text-[22px] font-bold">{`${p.profil}, ${p.yas}`}</h1>
          <p className="mt-1 text-muted">
            {[
              ceiling ? `${p.risk_profili} (${t("riskCeiling")} ${ceiling} / 7)` : p.risk_profili,
              p.yatirim_ufku,
              `${t("liquidity")} ${low(p.likidite_ihtiyaci)}`,
              `${t("incomeNeed")} ${low(p.gelir_nakit_akisi_ihtiyaci)}`,
            ].join(" · ")}
            {p.acik_kisitlar.map((k) => (
              <span key={k}>
                {" · "}
                <span className="text-[#B54708]">{`${t("constraint")}: ${k}`}</span>
              </span>
            ))}
          </p>
          <p data-testid="brief-text" className="mb-1.5 mt-3.5 max-w-[70ch] text-[17px] leading-relaxed">
            {llm ? llm.text : plainBrief(p)}
            {llm && (
              <span
                title={`${llm.model} · ${llm.prompt_version}`}
                className="ml-2 inline-block rounded-full bg-[#EEF2F9] px-2 py-0.5 align-[2px] text-[11px] font-semibold text-cobalt"
              >
                {t("aiSummary")}
              </span>
            )}
          </p>
          <div className="text-[13px] text-muted">
            {`${t("dataAsOf")}: ${snapshotDate(r.snapshot_id)} · ${t("engine")} · `}
            <button
              type="button"
              aria-expanded={showSources}
              className="text-[#355FA1] underline"
              onClick={() => setShowSources(!showSources)}
            >
              {`${t("sources")} (${sources})`}
            </button>
            {onEdit && (
              <>
                {" · "}
                <button type="button" className="text-[#355FA1] underline" onClick={onEdit}>
                  {t("editProfile")}
                </button>
              </>
            )}
          </div>
          {showSources && (
            <dl data-testid="brief-sources" className="mt-2 max-w-[70ch] rounded-xl bg-[#F7F9FC] px-4 py-3 text-sm">
              <dt className="font-semibold">{`${t("clientFile")} (${p.persona_id})`}</dt>
              <dd className="mb-2">{`${p.durum}. ${p.yatirim_amaci}.`}</dd>
              {p.rm_notu.trim() && (
                <>
                  <dt className="font-semibold">{t("fileNote")}</dt>
                  <dd className="mb-2">{p.rm_notu}</dd>
                </>
              )}
              {cite.length > 0 && (
                <>
                  <dt className="font-semibold">{t("aiCites")}</dt>
                  <dd className="flex flex-wrap gap-1.5">
                    {cite.map((c) =>
                      view.options[c] ? (
                        <span key={c} title={view.options[c].label} className="rounded-full bg-white px-2 py-0.5 text-xs">
                          {view.options[c].short_label}
                        </span>
                      ) : onEvidence && /^E[0-9a-f]+$/i.test(c) ? (
                        <button
                          key={c}
                          type="button"
                          className="rounded-full border border-gray-300 bg-white px-2 py-0.5 font-mono text-[11px]"
                          onClick={() => onEvidence(c)}
                        >
                          {c}
                        </button>
                      ) : (
                        <span key={c} className="rounded-full bg-white px-2 py-0.5 font-mono text-[11px]">
                          {c}
                        </span>
                      ),
                    )}
                  </dd>
                </>
              )}
            </dl>
          )}
        </div>

        <div className="min-w-[230px]">
          <div className="text-xs font-bold uppercase tracking-[0.06em] text-muted">{t("readiness")}</div>
          <div data-testid="readiness" className="my-1 text-[22px] font-bold">{`${done} / 3`}</div>
          <div className="h-1.5 overflow-hidden rounded bg-[#E4E7EC]" aria-hidden="true">
            <div className="h-full bg-cobalt" style={{ width: `${(done / 3) * 100}%` }} />
          </div>
          <div className="mt-2 text-[13px] text-muted">
            {`✓ ${t("stepProfile")} · `}
            {ready ? `✓ ${t("stepOptions")}` : <span className="font-semibold text-[#B54708]">{`○ ${t("stepQuestions")}`}</span>}
            <br />
            {!ready ? null : confirmOpen > 0 ? (
              <span className="font-semibold text-[#B54708]">{`○ ${confirmOpen} ${t("stepConfirmOpen")}`}</span>
            ) : (
              `✓ ${t("stepConfirmDone")}`
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
