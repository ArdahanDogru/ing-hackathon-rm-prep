// "Öneriler" as the model allocation (W13; docs/web-ui.md "Model allocation view",
// docs/decision.md section 11): one row per asset class with its strategic band and
// the best option for this client. No current shares and no amounts (future work).
import type { RunView } from "../api/types";
import { useT } from "../i18n";
import { realColor, signedPct } from "./OptionsTable";
import { riskColor } from "./RiskBar";

export function OptionsAllocation({ view, onOpen }: { view: RunView; onOpen: (id: string) => void }) {
  const t = useT();
  // the cited sources (an inferred band is no source); all of them if every band is inferred
  const cited = [...new Set(view.allocation.filter((a) => !a.inferred).map((a) => a.source))];
  const sources = cited.length ? cited : [...new Set(view.allocation.map((a) => a.source))];

  return (
    <div data-testid="allocation" className="px-2 pb-1 pt-2">
      {view.allocation_notes.length > 0 && (
        <ul
          data-testid="alloc-notes"
          className="mx-2 mb-3 space-y-1 rounded-xl border border-[#FEDF89] bg-[#FFFAEB] px-4 py-2.5 text-[13px] text-[#93370D]"
        >
          {view.allocation_notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      <ul>
        {view.allocation.map((a) => {
          const o = a.option_id ? view.options[a.option_id] : undefined;
          const real = o?.returns.real_1y;
          const band = a.low !== null && a.high !== null;
          return (
            <li
              key={a.asset_class}
              data-testid="alloc-row"
              className="grid grid-cols-[150px_minmax(0,1fr)_140px_minmax(0,260px)] items-center gap-4 border-b border-gray-100 px-4 py-3.5 last:border-b-0"
            >
              <b>{a.label}</b>
              <div>
                {band ? (
                  <div className="relative h-[22px] rounded-md bg-[#F2F4F7]" aria-label={`${t("allocBand")} %${a.low}–${a.high}`}>
                    <div
                      data-testid="alloc-band"
                      className="absolute bottom-0 top-0 rounded-md border border-[#9DB4DB] bg-[#DCE6F5]"
                      style={{ left: `${a.low}%`, width: `${a.high! - a.low!}%` }}
                    />
                  </div>
                ) : (
                  <span className="text-sm text-muted">{t("noBand")}</span>
                )}
              </div>
              <div className="text-sm">
                {band && <div className="font-semibold tabular-nums">{`%${a.low}–${a.high}`}</div>}
                <div className="text-xs text-muted">
                  {a.source}
                  {a.inferred && (
                    <span title={t("inferredTip")} className="ml-0.5 cursor-help font-bold text-[#B54708]">
                      *
                    </span>
                  )}
                </div>
              </div>
              <div className="min-w-0 text-sm">
                {o && (
                  <button
                    type="button"
                    title={o.label}
                    className="block max-w-full rounded-lg px-1 py-0.5 text-left hover:bg-[#F7F9FC]"
                    onClick={() => onOpen(o.option_id)}
                  >
                    {o.issuer && <span className="block text-[11px] font-bold uppercase tracking-[0.05em] text-muted">{o.issuer}</span>}
                    <span className="font-semibold">{o.short_label}</span>
                  </button>
                )}
                {o && (
                  <div className="px-1 text-[13px] text-muted">
                    {real && (
                      <>
                        {`${t("realReturn").toLocaleLowerCase("tr")} `}
                        <span style={{ color: realColor(real.value) }}>{signedPct(real.value)}</span>
                      </>
                    )}
                    {real && o.risk && " · "}
                    {o.risk && <span style={{ color: riskColor(o.risk.level) }}>{`${t("riskShort")} ${o.risk.level}/7`}</span>}
                  </div>
                )}
                {a.note_text && <div className={`px-1 text-[13px] ${o ? "text-[#B54708]" : "text-muted"}`}>{a.note_text}</div>}
              </div>
            </li>
          );
        })}
      </ul>
      <p data-testid="alloc-footer" className="px-4 pt-2 text-xs text-muted">
        {`${t("allocFooter")} ${sources.join("; ")}`}
      </p>
    </div>
  );
}
