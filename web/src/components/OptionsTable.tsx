// "Öneriler" as a table (B4 default): one column per recommendation, the deposit last.
import type { ReactNode } from "react";
import type { OptionView } from "../api/types";
import { fmtNum, fmtPct } from "../format";
import { useT } from "../i18n";
import { colors } from "../theme";
import { matchColor } from "./MatchRing";
import { riskColor } from "./RiskBar";
import { Stars } from "./Stars";

/** The small "K" next to a value: opens its evidence. */
export function KMark({ id, onEvidence }: { id: string | undefined; onEvidence: (id: string) => void }) {
  const t = useT();
  if (!id) return null;
  return (
    <button
      type="button"
      aria-label={t("evidence")}
      title={t("evidence")}
      className="ml-1 rounded-md bg-[#EEF2F9] px-[7px] py-px align-[2px] text-[11px] font-bold text-cobalt"
      onClick={(e) => {
        e.stopPropagation();
        onEvidence(id);
      }}
    >
      {t("kMark")}
    </button>
  );
}

export const signedPct = (v: number) => (fmtNum(v) !== "0" && v > 0 ? `+${fmtPct(v)}` : fmtPct(v));
export const realColor = (v: number) => (v < 0 ? colors.bad.fg : colors.good.fg);
export const whyLine = (o: OptionView) => o.why.map(([priority]) => priority).join(" · ");
const code = (o: OptionView) => o.option_id.split(":")[1] ?? o.option_id;
export const fullName = (o: OptionView) => (o.kind === "fund" ? `${o.label} · ${code(o)}` : o.label);

export function OptionsTable({
  options,
  baseline,
  onOpen,
  onEvidence,
}: {
  options: OptionView[];
  baseline: OptionView | null;
  onOpen: (id: string) => void;
  onEvidence: (id: string) => void;
}) {
  const t = useT();
  const cols = baseline ? [...options, baseline] : options;
  const dep = (o: OptionView) => o === baseline;
  const cell = (o: OptionView, content: ReactNode) => (
    <td
      key={o.option_id}
      className={`border-b border-gray-100 px-4 py-[13px] align-top tabular-nums ${dep(o) ? "bg-[#FAFAFB] text-[#475467]" : ""}`}
    >
      {content}
    </td>
  );
  const rows: [string, (o: OptionView) => ReactNode][] = [
    [
      t("rowMatch"),
      (o) =>
        o.match === null ? (
          "—"
        ) : (
          <span>
            <span aria-hidden="true" style={{ color: matchColor(o.match) }}>
              ●{" "}
            </span>
            {fmtNum(o.match)}
          </span>
        ),
    ],
    [
      t("return1yLong"),
      (o) => {
        const r = o.returns["1y"];
        return r ? (
          <>
            {dep(o) ? fmtPct(r.value) : <b>{fmtPct(r.value)}</b>}
            <KMark id={r.evidence_id} onEvidence={onEvidence} />
          </>
        ) : (
          "—"
        );
      },
    ],
    [
      t("rowReal"),
      (o) => {
        const r = o.returns.real_1y;
        return r ? <span style={{ color: realColor(r.value) }}>{signedPct(r.value)}</span> : "—";
      },
    ],
    [
      t("rowRisk"),
      (o) =>
        o.risk ? (
          <>
            <span className="font-semibold" style={{ color: riskColor(o.risk.level) }}>{`${o.risk.level} / 7`}</span>
            <KMark id={o.risk.evidence_id} onEvidence={onEvidence} />
          </>
        ) : (
          "—"
        ),
    ],
    [
      t("access"),
      (o) =>
        o.access.label ? (
          <>
            {o.access.label}
            <KMark id={o.access.evidence_id} onEvidence={onEvidence} />
          </>
        ) : (
          "—"
        ),
    ],
    [
      t("rowCategory"),
      (o) =>
        o.kind !== "fund" ? (
          "—"
        ) : o.rank && o.stars !== null ? (
          <span className="whitespace-nowrap">
            <Stars count={o.stars} /> {`${o.rank.position}. / ${o.rank.of}`}
          </span>
        ) : (
          <span className="text-muted">{t("noRank")}</span>
        ),
    ],
    [t("rowWhy"), (o) => (dep(o) ? "—" : <span className="text-sm text-[#344054]">{whyLine(o) || "—"}</span>)],
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0 text-[15px]">
        <thead>
          <tr>
            <td className="border-b border-gray-100" />
            {cols.map((o, i) =>
              dep(o) ? (
                <th key={o.option_id} scope="col" className="border-b border-gray-100 bg-[#FAFAFB] px-4 py-[13px] text-left align-top font-normal">
                  <div data-testid="compare-head" title={fullName(o)} className="text-[#475467]">
                    <div className="text-xs font-bold uppercase tracking-[0.05em] text-muted">{t("comparison")}</div>
                    <span className="font-semibold">{o.short_label}</span>
                  </div>
                </th>
              ) : (
                <th key={o.option_id} scope="col" className="border-b border-gray-100 px-2 py-2 text-left align-top font-normal">
                  <button
                    type="button"
                    data-testid="compare-head"
                    title={fullName(o)}
                    className="w-full rounded-lg px-2 py-[5px] text-left hover:bg-[#F7F9FC]"
                    onClick={() => onOpen(o.option_id)}
                  >
                    <div className="text-xs font-bold uppercase tracking-[0.05em] text-muted">
                      {o.issuer ? `${i + 1} · ${o.issuer}` : `${i + 1}`}
                    </div>
                    <span className="font-bold">{o.short_label}</span>
                  </button>
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, render]) => (
            <tr key={label}>
              <th scope="row" className="w-[150px] border-b border-gray-100 px-4 py-[13px] text-left align-top text-[13px] font-semibold text-muted">
                {label}
              </th>
              {cols.map((o) => cell(o, render(o)))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-4 pt-2 text-xs text-muted">{t("tableNote")}</p>
    </div>
  );
}
