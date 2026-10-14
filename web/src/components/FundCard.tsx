// The fund card, layout "A" (docs/web-ui.md "Fund card (A)"; mockup redesign-v4.html
// tab 4): shown in a side panel (FundDrawer) on the dashboard.
import { useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { OptionView } from "../api/types";
import type { Explanation } from "../explain";
import { fmtNum, fmtPct } from "../format";
import { LangContext, useT } from "../i18n";
import { snapshotDate } from "./BriefCard";
import { ReturnBars, type ReturnRow } from "./ReturnBars";
import { RiskBar, riskColor } from "./RiskBar";
import { Stars } from "./Stars";
import { WhyPanel } from "./WhyPanel";

function Tile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div data-testid="fund-tile" className="rounded-xl bg-[#F7F9FC] px-3.5 py-3">
      <div className="text-xs font-bold uppercase tracking-[0.06em] text-muted">{label}</div>
      {children}
    </div>
  );
}

export function FundCard({
  option,
  selected = false,
  snapshotId,
  onToggle,
  onEvidence,
  explanation,
}: {
  option: OptionView;
  selected?: boolean;
  snapshotId?: string;
  onToggle?: () => void;
  onEvidence?: (evidenceId: string) => void;
  /** W15: the engine's reasoning; without it the card shows the `why` lines. */
  explanation?: Explanation | null;
}) {
  const t = useT();
  const lang = useContext(LangContext);
  const [showEv, setShowEv] = useState(false);
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
  // "Kategoride ilk %4": the share of the category at or above this fund; only for the upper half.
  const top = o.better_than_pct !== null ? 100 - o.better_than_pct : null;
  const share =
    top !== null && top <= 50 ? (lang === "TR" ? `Kategoride ilk ${fmtPct(top)}` : `Top ${fmtNum(top)} % of the category`) : null;
  const riskWord = o.risk?.level === 1 ? t("lowestRisk") : o.risk?.level === 7 ? t("highestRisk") : "";
  const code = o.kind === "fund" ? (o.option_id.split(":")[1] ?? "") : "";
  const evidence = [
    ...new Set(
      [...Object.values(o.returns).map((f) => f?.evidence_id), o.risk?.evidence_id, o.access.evidence_id].filter(
        (x): x is string => !!x,
      ),
    ),
  ];

  return (
    <div className="text-[15px]">
      <div className="text-xs font-bold uppercase tracking-[0.05em] text-muted">
        {[o.issuer, o.category_label].filter(Boolean).join(" · ")}
      </div>
      <h2 className="mt-1 text-[22px] font-bold leading-tight">{o.short_label}</h2>
      <div className="mt-1 text-[13px] text-muted">{code ? `${o.label} · ${code}` : o.label}</div>

      <div className="my-[22px] grid grid-cols-3 gap-3">
        <Tile label={t("rowMatch")}>
          <div className="text-2xl font-bold">{o.match === null ? "—" : fmtNum(o.match)}</div>
        </Tile>
        <Tile label={t("rowCategory")}>
          {o.rank && o.stars !== null ? (
            <>
              <div className="text-2xl font-bold">{`${o.rank.position}. / ${o.rank.of}`}</div>
              <Stars count={o.stars} />
              {share && <div className="mt-0.5 text-[11px] font-semibold text-[#067647]">{share}</div>}
            </>
          ) : (
            <div className="mt-1 text-sm text-muted">{t("noRank")}</div>
          )}
        </Tile>
        <Tile label={t("access")}>
          <div className="mt-1 text-base font-bold leading-snug">{o.access.label ?? "—"}</div>
        </Tile>
      </div>

      {rows.length > 0 && (
        <>
          <div className="mb-2.5 text-xs font-bold uppercase tracking-[0.06em] text-muted">{t("returnsTitle")}</div>
          <div className="text-sm">
            <ReturnBars
              rows={rows}
              fundLabel={t("thisFund")}
              categoryLabel={o.rank ? `${t("categoryAverage")} (${o.rank.of} ${t("funds")})` : t("categoryAverage")}
            />
          </div>
        </>
      )}

      {explanation ? (
        <WhyPanel explanation={explanation} onEvidence={onEvidence} />
      ) : o.why.length > 0 && (
        <div className="my-[22px] rounded-xl bg-[#F7F9FC] px-4 py-3.5">
          <b>{t("whyForClient")}</b>
          <ul className="mt-1.5 text-sm leading-normal text-[#344054]">
            {o.why.map(([priority, line]) => (
              <li key={priority + line}>{`• ${priority} — ${line}`}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2.5">
        {o.risk && (
          <>
            <div className="w-40">
              <RiskBar level={o.risk.level} showText={false} />
            </div>
            <span className="text-[13px] text-muted">
              <span className="font-semibold" style={{ color: riskColor(o.risk.level) }}>{`SPK risk ${o.risk.level} / 7`}</span>
              {riskWord && ` · ${riskWord}`}
            </span>
          </>
        )}
        <span className="flex-1" />
        <button type="button" aria-pressed={selected} onClick={onToggle} className="rounded-xl bg-brand px-[22px] py-3 font-bold text-white">
          {selected ? t("removeSelection") : t("addToSelection")}
        </button>
      </div>

      <div className="mt-4 text-[13px] text-muted">
        {snapshotId && `${t("source")}: ${o.kind === "fund" ? "TEFAS" : "ING"}, ${snapshotDate(snapshotId)} · `}
        {evidence.length > 0 && (
          <button type="button" aria-expanded={showEv} className="text-[#355FA1] underline" onClick={() => setShowEv(!showEv)}>
            {`${t("showEvidence")} (${evidence.length})`}
          </button>
        )}
        {showEv && (
          <ul className="mt-2 flex flex-wrap gap-2 text-xs">
            {evidence.map((id) => (
              <li key={id}>
                <button type="button" className="rounded-full border border-gray-300 px-2 py-0.5 font-mono" onClick={() => onEvidence?.(id)}>
                  {id}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** A side panel on the right (about 520 px); the dashboard stays visible. Escape and ✕
 * close it; the focus moves into it and back to the element that opened it. While
 * `paused` (a pop-up is open over it), Escape belongs to the pop-up. */
export function FundDrawer({ onClose, paused = false, children }: { onClose: () => void; paused?: boolean; children: ReactNode }) {
  const t = useT();
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => opener?.focus?.();
  }, []);
  useEffect(() => {
    if (paused) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [paused, onClose]);
  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-label={t("fundCard")}
      className="fixed bottom-0 right-0 top-0 z-40 w-full max-w-[520px] overflow-y-auto border-l border-gray-200 bg-white px-[30px] py-7 shadow-2xl"
    >
      <button
        ref={closeRef}
        type="button"
        aria-label={t("close")}
        className="float-right -mr-2 -mt-1 rounded-lg px-2 py-1 text-lg text-muted hover:bg-gray-100"
        onClick={onClose}
      >
        ✕
      </button>
      {children}
    </aside>
  );
}
