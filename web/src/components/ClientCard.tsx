import type { Persona } from "../api/types";
import { useT } from "../i18n";

/** The client on top: profile, horizon, liquidity, priorities as tags, the constraint in its own color. */
export function ClientCard({ persona, onEdit }: { persona: Persona; onEdit?: () => void }) {
  const t = useT();
  return (
    <section data-testid="client-card" className="flex items-center gap-3 rounded-2xl bg-white px-5 py-4 shadow-sm">
      <div className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-[#EEF2F9] text-sm font-bold text-[#355FA1]">
        {persona.persona_id}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[15px]">
          <b>{`${persona.profil}, ${persona.yas}`}</b>
          <span className="text-muted">
            {` · ${persona.risk_profili} · ${t("horizon")} ${persona.yatirim_ufku} · ${t("liquidity")} ${persona.likidite_ihtiyaci.toLocaleLowerCase("tr")}`}
          </span>
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {persona.oncelikler.map((p) => (
            <span key={p} className="rounded-full bg-[#EEF2F9] px-2.5 py-0.5 text-xs text-[#1D3A6E]">
              {p}
            </span>
          ))}
          {persona.acik_kisitlar.map((k) => (
            <span key={k} className="rounded-full bg-[#FEF0C7] px-2.5 py-0.5 text-xs text-[#93370D]">
              {`${t("constraint")}: ${k}`}
            </span>
          ))}
        </div>
      </div>
      {onEdit && (
        <button type="button" className="text-sm text-[#355FA1] underline" onClick={onEdit}>
          {t("edit")}
        </button>
      )}
    </section>
  );
}
