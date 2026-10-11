// An opened option (mockup detail-v5.html): match ring, stars and rank in the
// category, SPK risk, access, returns vs the category average, "why".
import type { OptionView } from "../api/types";
import { useT } from "../i18n";
import { MatchRing } from "./MatchRing";
import { OptionNotes } from "./Notes";
import { ReturnBars, type ReturnRow } from "./ReturnBars";
import { RiskBar, riskColor } from "./RiskBar";
import { Stars } from "./Stars";

export function EvidenceLink({ id, onEvidence }: { id: string | undefined; onEvidence?: (id: string) => void }) {
  const t = useT();
  if (!id || !onEvidence) return null;
  return (
    <button type="button" className="text-[11px] text-[#355FA1] underline" onClick={() => onEvidence(id)}>
      {t("evidence")}
    </button>
  );
}

export function FundCard({
  option,
  selected = false,
  onToggle,
  onEvidence,
}: {
  option: OptionView;
  selected?: boolean;
  onToggle?: () => void;
  onEvidence?: (evidenceId: string) => void;
}) {
  const t = useT();
  const o = option;
  const avg = o.category_avg;
  const rows: ReturnRow[] = (
    [
      ["3m", t("period3m")],
      ["6m", t("period6m")],
      ["1y", t("return1y")],
      ["real_1y", t("realReturn")],
    ] as const
  )
    .map(([k, label]) => ({ period: k, label, fund: o.returns[k]?.value ?? null, category: avg ? avg[k] : null }))
    .filter((r) => r.fund !== null);
  const riskWord = o.risk?.level === 1 ? t("lowestRisk") : o.risk?.level === 7 ? t("highestRisk") : "";

  return (
    <div className="rounded-2xl bg-white p-4 text-xs shadow-sm">
      <div className="flex items-center gap-3.5">
        {o.match !== null && <MatchRing value={o.match} label={t("match")} />}
        <div className="min-w-0 flex-1">
          <h4 className="text-[15px] font-semibold">{o.label}</h4>
          <div className="text-[11px] text-muted">{o.category_label}</div>
        </div>
        <div className="text-right">
          {o.rank && o.stars !== null ? (
            <>
              <Stars count={o.stars} />
              <div className="mt-0.5 text-xl font-bold leading-tight">{`${o.rank.position}. / ${o.rank.of}`}</div>
              <div className="text-[11px] text-muted">
                {`${t("categoryRank")} · ${t("return1y")} · `}
                <EvidenceLink id={o.returns["1y"]?.evidence_id} onEvidence={onEvidence} />
              </div>
            </>
          ) : (
            <div className="text-[11px] text-muted">{t("noRank")}</div>
          )}
        </div>
      </div>

      <div className="my-3.5 grid grid-cols-[1.3fr_1fr] gap-2.5">
        <div className="rounded-xl bg-gray-50 p-2.5">
          <div className="text-[11px] text-muted">{t("riskValue")}</div>
          {o.risk ? (
            <>
              <RiskBar level={o.risk.level} showText={false} />
              <div>
                <b style={{ color: riskColor(o.risk.level) }}>{`${o.risk.level} / 7`}</b>
                {riskWord && <span className="text-muted">{` · ${riskWord}`}</span>}{" "}
                <EvidenceLink id={o.risk.evidence_id} onEvidence={onEvidence} />
              </div>
            </>
          ) : (
            <div className="mt-1">—</div>
          )}
        </div>
        <div className="rounded-xl bg-gray-50 p-2.5">
          <div className="text-[11px] text-muted">{t("access")}</div>
          <div className="text-[17px] font-bold">{o.access.label ?? "—"}</div>
          {o.access.days !== null && o.kind === "fund" && (
            <div className="text-[11px] text-muted">
              {`${t("sellValor")} ${o.access.days} ${t("days")} `}
              <EvidenceLink id={o.access.evidence_id} onEvidence={onEvidence} />
            </div>
          )}
        </div>
      </div>

      {rows.length > 0 && (
        <>
          <div className="text-[11px] font-semibold text-[#344054]">{t("returnsTitle")}</div>
          <ReturnBars
            rows={rows}
            fundLabel={t("thisFund")}
            categoryLabel={o.rank ? `${t("categoryAverage")} (${o.rank.of} ${t("funds")})` : t("categoryAverage")}
          />
        </>
      )}

      {o.why.length > 0 && (
        <div className="mt-3 rounded-[10px] bg-[#F3F6FB] px-3 py-2 leading-relaxed">
          <b>{t("whyForClient")}</b>
          <ul className="mt-0.5">
            {o.why.map(([priority, line]) => (
              <li key={priority + line}>{`"${priority}": ${line}.`}</li>
            ))}
          </ul>
        </div>
      )}
      <OptionNotes notes={o.data_notes} />

      <div className="mt-3 text-right">
        <button
          type="button"
          aria-pressed={selected}
          onClick={onToggle}
          className={
            selected
              ? "rounded-[10px] border border-gray-300 px-3.5 py-1.5 font-semibold"
              : "rounded-[10px] bg-brand px-3.5 py-1.5 font-semibold text-white"
          }
        >
          {selected ? `✓ ${t("inSelection")}` : t("addToSelection")}
        </button>
      </div>
    </div>
  );
}
