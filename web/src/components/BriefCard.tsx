// Brief card (B4 item 3): who the client is, the brief, the data line, readiness n / 3.
import { useState } from "react";
import type { Persona, RunView } from "../api/types";
import { useT } from "../i18n";

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
  brief,
  confirmOpen,
  onEdit,
}: {
  view: RunView;
  brief: string;
  confirmOpen: number;
  onEdit?: () => void;
}) {
  const t = useT();
  const [showSources, setShowSources] = useState(false);
  const r = view.result;
  const p = r.persona;
  const low = (x: string) => x.toLocaleLowerCase("tr");
  const ready = r.state === "ready";
  const steps = [true, ready, ready && confirmOpen === 0];
  const done = steps.filter(Boolean).length;
  const ceiling = view.risk_ceiling;
  const sources = 1 + (p.rm_notu.trim() ? 1 : 0);

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
            {brief}
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
                  <dd>{p.rm_notu}</dd>
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
