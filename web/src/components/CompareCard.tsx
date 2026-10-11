import type { OptionView } from "../api/types";
import { fmtPct } from "../format";
import { useT } from "../i18n";
import { OptionNotes } from "./Notes";
import { RealReturn } from "./TopOptionCard";

/** The deposit baseline as "Karşılaştırma": a reference for the RM, not a recommendation. */
export function CompareCard({ option }: { option: OptionView }) {
  const t = useT();
  const r1 = option.returns["1y"];
  return (
    <article data-testid="compare-card" className="rounded-2xl border border-dashed border-gray-300 bg-white/60 p-4">
      <div className="text-[10px] uppercase tracking-wide text-muted">{t("comparison")}</div>
      <h3 className="mt-0.5 text-[14px] font-semibold leading-snug">{option.label}</h3>
      <div className="text-[11px] text-muted">{t("comparisonNote")}</div>
      {r1 && (
        <div className="mt-2 text-[20px] font-bold">
          {fmtPct(r1.value)} <span className="text-[11px] font-normal text-muted">{t("return1y")}</span>
        </div>
      )}
      {option.returns.real_1y && <RealReturn value={option.returns.real_1y.value} />}
      <div className="mt-2 text-xs">
        <span className="text-muted">{t("access")}: </span>
        <b>{option.access.label ?? "—"}</b>
      </div>
      <OptionNotes notes={option.data_notes} />
    </article>
  );
}
