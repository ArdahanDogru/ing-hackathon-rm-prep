// "Düzenle" side panel: every persona field. An edited persona gives a test run.
import { useState } from "react";
import type { Persona } from "../api/types";
import { useT, type LabelKey } from "../i18n";

type TextField = Exclude<keyof Persona, "persona_id" | "yas" | "oncelikler" | "acik_kisitlar" | "rm_notu">;

const TEXT_FIELDS: TextField[] = [
  "profil",
  "risk_profili",
  "durum",
  "yatirim_amaci",
  "yatirim_ufku",
  "likidite_ihtiyaci",
  "doviz_maruz_kalma_tercihi",
  "gelir_nakit_akisi_ihtiyaci",
  "anapara_koruma_tercihi",
];

const fieldLabel = (f: keyof Persona) => `f_${f}` as LabelKey;
const lines = (s: string) =>
  s
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);

export function PersonaPanel({
  persona,
  onApply,
  onClose,
}: {
  persona: Persona;
  onApply: (p: Persona) => void;
  onClose: () => void;
}) {
  const t = useT();
  const [draft, setDraft] = useState<Persona>(persona);
  const [prios, setPrios] = useState(persona.oncelikler.join("\n"));
  const [limits, setLimits] = useState(persona.acik_kisitlar.join("\n"));
  const [age, setAge] = useState(String(persona.yas));

  const set = (f: keyof Persona, v: string) => setDraft((d) => ({ ...d, [f]: v }));
  const apply = () =>
    onApply({ ...draft, yas: Number.parseInt(age, 10) || persona.yas, oncelikler: lines(prios), acik_kisitlar: lines(limits) });

  const input = "mt-1 w-full rounded-lg border border-gray-300 px-2.5 py-1.5 text-sm";
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/20" onMouseDown={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={t("editPersona")}
        className="flex h-full w-full max-w-md flex-col bg-white shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="border-b border-gray-200 px-5 py-4">
          <h2 className="text-base font-semibold">{`${t("editPersona")} · ${persona.persona_id}`}</h2>
          <p className="mt-1 text-xs text-muted">{t("editNote")}</p>
        </div>
        <form
          className="flex-1 space-y-3 overflow-y-auto px-5 py-4 text-sm"
          onSubmit={(e) => {
            e.preventDefault();
            apply();
          }}
        >
          <label className="block">
            <span className="text-xs text-muted">{t("f_yas")}</span>
            <input
              aria-label={t("f_yas")}
              type="number"
              min={18}
              max={120}
              className={input}
              value={age}
              onChange={(e) => setAge(e.target.value)}
            />
          </label>
          {TEXT_FIELDS.map((f) => (
            <label key={f} className="block">
              <span className="text-xs text-muted">{t(fieldLabel(f))}</span>
              <input aria-label={t(fieldLabel(f))} className={input} value={draft[f]} onChange={(e) => set(f, e.target.value)} />
            </label>
          ))}
          <label className="block">
            <span className="text-xs text-muted">{`${t("f_oncelikler")} (${t("onePerLine")})`}</span>
            <textarea
              aria-label={`${t("f_oncelikler")} (${t("onePerLine")})`}
              rows={3}
              className={input}
              value={prios}
              onChange={(e) => setPrios(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-xs text-muted">{`${t("f_acik_kisitlar")} (${t("onePerLine")})`}</span>
            <textarea
              aria-label={`${t("f_acik_kisitlar")} (${t("onePerLine")})`}
              rows={2}
              className={input}
              value={limits}
              onChange={(e) => setLimits(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-xs text-muted">{t("f_rm_notu")}</span>
            <textarea
              aria-label={t("f_rm_notu")}
              rows={3}
              className={input}
              value={draft.rm_notu}
              onChange={(e) => set("rm_notu", e.target.value)}
            />
          </label>
        </form>
        <div className="flex justify-end gap-2 border-t border-gray-200 px-5 py-3">
          <button type="button" className="rounded-[10px] border border-gray-300 px-3.5 py-1.5 text-sm font-semibold" onClick={onClose}>
            {t("cancel")}
          </button>
          <button type="button" className="rounded-[10px] bg-brand px-3.5 py-1.5 text-sm font-semibold text-white" onClick={apply}>
            {t("apply")}
          </button>
        </div>
      </aside>
    </div>
  );
}
