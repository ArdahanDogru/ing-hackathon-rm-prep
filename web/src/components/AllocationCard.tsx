// "Öneriler" as "Mevcut ve hedef dağılım" (W18; docs/web-ui.md "Current and target split",
// before W13 "Model allocation view"; docs/decision.md sections 11 and 17): one row per
// asset class with the client's current share (an estimate until the RM confirms or types
// it), the gap and the best option for this client; the target bands are in the "Hedef
// dağılım" note (W18c, variant B). Without a current split: the W13 band rows. No amounts.
import { useState } from "react";
import { api } from "../api/client";
import type { AllocationRow, Holdings, HoldingsOrigin, RunView } from "../api/types";
import { fmtDate, fmtNum, fmtSigned } from "../format";
import { fill, useT, type LabelKey } from "../i18n";
import { AllocationLegend, AllocationSummary, markColor, pct, SourceLine, StackedBar, TargetNote } from "./AllocationParts";
import { realColor, signedPct } from "./OptionsTable";
import { riskColor } from "./RiskBar";
import { CodeBadge, ProductBadges } from "../product";

/** The total of the RM's split may differ from 100 by this much (contract v1.10). */
const TOTAL_TOLERANCE = 0.5;

const BADGE: Record<string, LabelKey> = {
  rm: "srcRm",
  rm_confirmed: "srcRmConfirmed",
  persona_text: "srcPersonaText",
  profile: "srcEstimate",
  national: "srcEstimate",
};

const parse = (s: string) => Number(s.replace(",", "."));

/** The tooltip of a row's badge: the source of its current_source (label, date, URL), else the rule or profile. */
function sourceTip(a: AllocationRow, holdings: Holdings | undefined): string {
  const src = holdings?.sources.find((s) => s.id === a.current_source);
  return src ? [src.label, fmtDate(src.date), src.url].filter(Boolean).join(" · ") : (a.current_ref ?? "");
}

export function AllocationCard({
  view,
  onOpen,
  onView,
}: {
  view: RunView;
  onOpen: (id: string) => void;
  /** the new run after the RM changed the current split */
  onView?: (v: RunView) => void;
}) {
  const t = useT();
  const runId = view.result.run_id;
  const holdings = view.holdings;
  const [edit, setEdit] = useState<Record<string, string> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // the cited sources (an inferred band is no source); all of them if every band is inferred
  const cited = [...new Set(view.allocation.filter((a) => !a.inferred).map((a) => a.source))];
  const sources = cited.length ? cited : [...new Set(view.allocation.map((a) => a.source))];
  const hasCurrent = view.allocation.some((a) => a.current != null);
  const estimate = holdings?.status === "estimate";
  // persona_text with estimated rows (W18b): name the classes from the client file
  const active = view.allocation.filter((a) => a.active).map((a) => a.label);
  const partly = holdings?.status === "persona_text" && active.length > 0 && active.length < view.allocation.length;
  const banner = estimate
    ? t("allocBanner")
    : partly
      ? fill(t(active.length === 1 ? "allocBannerPartOne" : "allocBannerPartMany"), { classes: active.join(", ") })
      : null;
  const byRm = holdings?.status === "rm" || holdings?.status === "rm_confirmed";

  const send = (shares: Record<string, number> | null, origin?: HoldingsOrigin) => {
    setBusy(true);
    setError(null);
    (shares === null ? api.setHoldings(runId, null) : api.setHoldings(runId, shares, origin)).then(
      (v) => {
        setBusy(false);
        setEdit(null);
        onView?.(v);
      },
      (e: Error) => {
        setBusy(false);
        setError(e.message);
      },
    );
  };
  const currentPoints = () => Object.fromEntries(view.allocation.map((a) => [a.asset_class, a.current ?? 0]));
  const total = edit ? Object.values(edit).reduce((sum, s) => sum + (parse(s) || 0), 0) : 0;
  const valid =
    !!edit &&
    Object.values(edit).every((s) => s.trim() !== "" && parse(s) >= 0 && parse(s) <= 100) &&
    Math.abs(total - 100) <= TOTAL_TOLERANCE + 1e-9;

  /** The best option of a class: short name, real 1-year return, SPK risk, the note text. */
  const best = (a: AllocationRow) => {
    const o = a.option_id ? view.options[a.option_id] : undefined;
    const real = o?.returns.real_1y;
    return (
      <div className="min-w-0 text-sm">
        {hasCurrent && <div className="px-1 text-[11px] font-bold uppercase tracking-[0.05em] text-muted">{t("allocBest")}</div>}
        {o && (
          <button
            type="button"
            title={o.label}
            className="block max-w-full rounded-lg px-1 py-0.5 text-left hover:bg-[#F7F9FC]"
            onClick={() => onOpen(o.option_id)}
          >
            {o.issuer && <span className="block text-[11px] font-bold uppercase tracking-[0.05em] text-muted">{o.issuer}</span>}
            <CodeBadge optionId={o.option_id} />
            <span className="font-semibold">{o.short_label}</span>
            <ProductBadges badges={o.badges} />
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
    );
  };

  /** A row with the current split (W18c): the marker and the range only, no band area; the value; the source line. */
  const currentRow = (a: AllocationRow) => {
    const current = a.current ?? null;
    const low = a.current_low ?? current;
    const high = a.current_high ?? current;
    const badge = a.current_source ? BADGE[a.current_source] : undefined;
    const tone = markColor(a);
    return (
      <li
        key={a.asset_class}
        data-testid="alloc-row"
        className="grid grid-cols-[120px_minmax(0,1fr)_150px_minmax(0,200px)] items-center gap-x-4 gap-y-2 border-b border-gray-100 px-4 py-3.5 last:border-b-0"
      >
        <b>{a.label}</b>
        <div>
          <div className="relative h-[18px] rounded-md bg-[#F2F4F7]">
            {current !== null && (
              <>
                <div
                  data-testid="alloc-current-range"
                  className="absolute top-1/2 h-[2px] -translate-y-1/2"
                  style={{ left: `${low}%`, width: `${high! - low!}%`, backgroundColor: tone }}
                />
                <div
                  data-testid="alloc-current"
                  data-tone={a.active ? "active" : "estimate"}
                  title={`${t("allocCurrent")} ${pct(current)}`}
                  className="absolute -bottom-0.5 -top-0.5 w-[3px] -translate-x-1/2 rounded-sm"
                  style={{ left: `${current}%`, backgroundColor: tone }}
                />
              </>
            )}
          </div>
          <div aria-hidden="true" className="mt-0.5 flex justify-between text-[10px] text-muted">
            <span>0</span>
            <span>50</span>
            <span>100 %</span>
          </div>
        </div>
        <div className="text-sm">
          {current !== null && (
            <div className="tabular-nums">
              <span className="text-xs text-muted">{`${t("allocCurrent")} `}</span>
              <b>{pct(current)}</b>
              {low !== high && <span className="text-xs text-muted">{` (${fmtNum(low!)}–${fmtNum(high!)})`}</span>}
            </div>
          )}
          {badge && (
            <span
              data-testid="alloc-badge"
              title={sourceTip(a, holdings)}
              className={`inline-block cursor-help rounded-md px-1.5 py-px text-[11px] font-semibold ${
                a.active ? "bg-[#EEF2F9] text-[#2C4F8F]" : "bg-[#F2F4F7] text-[#475467]"
              }`}
            >
              {t(badge)}
            </span>
          )}
          {a.gap != null && (
            <div
              data-testid="alloc-gap"
              title={a.gap === 0 ? undefined : `${t(a.gap > 0 ? "allocUnder" : "allocOver")} ${fmtSigned(a.gap)} ${t("allocPoints")}`}
              className={`text-xs ${a.gap === 0 ? "text-[#067647]" : "text-[#B54708]"}`}
            >
              {a.gap === 0 ? t("allocInBand") : `${fmtSigned(a.gap)} ${t("allocPoints")}`}
            </div>
          )}
          {a.gap == null && a.low === null && <div className="text-xs text-muted">{t("noBand")}</div>}
        </div>
        {best(a)}
        <SourceLine row={a} holdings={holdings} />
      </li>
    );
  };

  /** A row without a current split (W13): the band bar, the band and its source. */
  const bandRow = (a: AllocationRow) => {
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
        {best(a)}
      </li>
    );
  };

  return (
    <div data-testid="allocation" className="px-2 pb-1 pt-2">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 pb-2">
        <h3 className="text-[15px] font-bold">{t("allocTitle")}</h3>
        {hasCurrent && <TargetNote view={view} />}
      </div>
      {hasCurrent && <AllocationSummary view={view} />}
      {banner && (
        <p
          data-testid="alloc-banner"
          role="status"
          className="mx-2 mb-3 rounded-xl border border-gray-200 bg-[#F9FAFB] px-4 py-2.5 text-[13px] text-[#344054]"
        >
          {banner}
        </p>
      )}
      {/* the D20 holding hints only without a current split; the summary says it otherwise */}
      {!hasCurrent && view.allocation_notes.length > 0 && (
        <ul
          data-testid="alloc-notes"
          className="mx-2 mb-3 space-y-1 rounded-xl border border-[#FEDF89] bg-[#FFFAEB] px-4 py-2.5 text-[13px] text-[#93370D]"
        >
          {view.allocation_notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      {hasCurrent && <StackedBar rows={view.allocation} />}
      <ul>{view.allocation.map((a) => (hasCurrent ? currentRow(a) : bandRow(a)))}</ul>
      {hasCurrent && <AllocationLegend />}

      {holdings && edit && (
        <div data-testid="alloc-editor" className="mx-2 mt-3 rounded-xl border border-cobalt bg-[#F7F9FC] p-3 text-sm">
          <div className="flex flex-wrap gap-3">
            {view.allocation.map((a) => (
              <label key={a.asset_class} className="flex flex-col gap-1">
                <span className="text-xs text-muted">{a.label}</span>
                <span className="flex items-center gap-1">
                  %
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.1}
                    aria-label={a.label}
                    className="w-20 rounded-lg border border-gray-300 bg-white px-2 py-1 tabular-nums"
                    value={edit[a.asset_class] ?? ""}
                    onChange={(e) => setEdit({ ...edit, [a.asset_class]: e.target.value })}
                  />
                </span>
              </label>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <span data-testid="alloc-total" className={`font-semibold tabular-nums ${valid ? "" : "text-[#B42318]"}`}>
              {`${t("allocTotal")} ${pct(Math.round(total * 10) / 10)}`}
            </span>
            {!valid && <span className="text-xs text-muted">{t("allocTotalHint")}</span>}
            <span className="ml-auto flex gap-2">
              <button
                type="button"
                className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 font-semibold"
                onClick={() => {
                  setEdit(null);
                  setError(null);
                }}
              >
                {t("cancel")}
              </button>
              <button
                type="button"
                disabled={!valid || busy}
                className="rounded-lg bg-ink px-3 py-1.5 font-semibold text-white disabled:opacity-50"
                onClick={() => send(Object.fromEntries(Object.entries(edit).map(([k, s]) => [k, parse(s)])), "rm")}
              >
                {t("save")}
              </button>
            </span>
          </div>
          {error && (
            <p role="alert" className="mt-2 text-sm text-[#B42318]">
              {error}
            </p>
          )}
        </div>
      )}

      {holdings && !edit && (
        <div className="mx-4 mt-3 flex flex-wrap items-center gap-2 text-sm">
          {!byRm && (
            <button
              type="button"
              disabled={busy}
              className="rounded-[10px] bg-ink px-3 py-1.5 font-semibold text-white disabled:opacity-50"
              onClick={() => send(currentPoints(), "rm_confirmed")}
            >
              {t("allocConfirm")}
            </button>
          )}
          <button
            type="button"
            disabled={busy}
            className="rounded-[10px] border border-gray-300 px-3 py-1.5 font-semibold"
            onClick={() => {
              setError(null);
              setEdit(Object.fromEntries(view.allocation.map((a) => [a.asset_class, String(a.current ?? 0)])));
            }}
          >
            {t("allocEdit")}
          </button>
          {byRm && (
            <button
              type="button"
              disabled={busy}
              className="rounded-[10px] border border-gray-300 px-3 py-1.5 font-semibold"
              onClick={() => send(null)}
            >
              {t("allocReset")}
            </button>
          )}
          {error && (
            <p role="alert" className="basis-full text-sm text-[#B42318]">
              {error}
            </p>
          )}
        </div>
      )}

      {!hasCurrent && (
        <p data-testid="alloc-footer" className="px-4 pt-2 text-xs text-muted">
          {`${t("allocFooter")} ${sources.join("; ")}`}
        </p>
      )}
    </div>
  );
}
