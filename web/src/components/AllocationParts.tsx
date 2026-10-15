// The parts of "Mevcut ve hedef dağılım" in variant B (W18c; mockup
// docs/web-ui/mockups/allocation-v2-B.html): the "Hedef dağılım" note, the summary,
// the stacked bar of the current portfolio, the source line of a row and the legend.
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { AllocationRow, Holdings, RunView } from "../api/types";
import { fmtDate, fmtNum, fmtSigned } from "../format";
import { fill, useT, type LabelKey } from "../i18n";

export const pct = (v: number) => `%${fmtNum(v)}`;
const lower = (s: string) => s.toLocaleLowerCase("tr");

/** A fixed colour per class (stacked bar and its legend). */
export const CLASS_COLOR: Record<string, string> = {
  nakit_benzeri: "#1F3A68",
  borclanma: "#6172F3",
  hisse: "#12B76A",
  altin_doviz: "#F79009",
  dengeli: "#98A2B3",
};
const ACTIVE_MARK = "#101828";
const ESTIMATE_MARK = "#98A2B3";
export const markColor = (a: AllocationRow) => (a.active ? ACTIVE_MARK : ESTIMATE_MARK);

const SOURCE_PHRASE: Record<string, LabelKey> = { persona_text: "allocSrcFile", rm: "allocSrcRm", rm_confirmed: "allocSrcRmConfirmed" };
const SOURCE_WORD: Record<string, LabelKey> = { persona_text: "allocWordFile", rm: "allocWordRm", rm_confirmed: "allocWordRmConfirmed" };

/** The gap as text: "−55 puan", "bandın içinde"; "hedef bant yok" without a band; null when unknown. */
export function useGapText(): (a: AllocationRow) => string | null {
  const t = useT();
  return (a) => {
    if (a.low === null || a.high === null) return t("noBand");
    if (a.gap == null) return null;
    return a.gap === 0 ? t("allocInBand") : `${fmtSigned(a.gap)} ${t("allocPoints")}`;
  };
}

/** A label with {cls} in bold, the other placeholders filled. */
function withClass(text: string, cls: string, values: Record<string, string> = {}): ReactNode[] {
  return fill(text, values)
    .split(/(\{cls\})/)
    .map((part, i) => (part === "{cls}" ? <b key={i}>{cls}</b> : part));
}

/** S1–S3: where the money is, the target of that class, and the effect on the ranking. */
export function AllocationSummary({ view }: { view: RunView }) {
  const t = useT();
  const rows = view.allocation.filter((a) => a.current != null);
  if (!rows.length) return null;
  const top = rows.reduce((m, a) => (a.current! > m.current! ? a : m));
  const profile = view.result.persona.risk_profili;
  const active = rows.filter((a) => a.active);
  const gapWeight = view.effective_weights?.allocation_gap ?? 0;
  const moved = active
    .filter((a) => a.gap != null && a.gap !== 0)
    .reduce<AllocationRow | null>((m, a) => (m === null || Math.abs(a.gap!) > Math.abs(m.gap!) ? a : m), null);
  let s3: ReactNode[] | null = null;
  if (gapWeight > 0 && moved) s3 = withClass(t(moved.gap! < 0 ? "allocSumOver" : "allocSumUnder"), lower(moved.label));
  else if (!active.length) s3 = [t("allocSumNone")];
  return (
    <p data-testid="alloc-summary" className="mx-2 mb-3 rounded-[10px] bg-[#F2F4F7] px-4 py-2.5 text-sm leading-normal text-[#344054]">
      {withClass(t("allocSum1"), lower(top.label), {
        x: pct(top.current!),
        src: t(SOURCE_PHRASE[top.current_source ?? ""] ?? "allocSrcEstimate"),
      })}
      {top.low !== null && top.high !== null && ` ${fill(t("allocSum2"), { profile, band: `%${top.low}–${top.high}` })}`}
      {s3 && <> {s3}</>}
    </p>
  );
}

/** "Tahmini mevcut portföy": one segment per class with a share, a label inside from 10 %, a legend. */
export function StackedBar({ rows }: { rows: AllocationRow[] }) {
  const t = useT();
  const shown = rows.filter((a) => a.current != null);
  return (
    <div data-testid="alloc-stack" className="mx-2 mb-2">
      <div className="mb-1 text-xs font-bold text-[#344054]">{t("allocStackTitle")}</div>
      <div className="flex h-6 overflow-hidden rounded-md bg-[#F2F4F7]">
        {shown
          .filter((a) => a.current! > 0)
          .map((a) => (
            <div
              key={a.asset_class}
              data-testid="stack-seg"
              data-class={a.asset_class}
              title={`${a.label} ${pct(a.current!)}`}
              className="flex items-center justify-center overflow-hidden whitespace-nowrap px-1 text-[11px] font-bold text-white"
              style={{ width: `${a.current}%`, backgroundColor: CLASS_COLOR[a.asset_class] ?? ESTIMATE_MARK }}
            >
              {a.current! >= 10 && <span className="truncate">{`${a.label} ${pct(a.current!)}`}</span>}
            </div>
          ))}
      </div>
      <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#475467]">
        {shown.map((a) => (
          <li key={a.asset_class} data-testid="stack-legend" className="flex items-center gap-1.5">
            <i aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: CLASS_COLOR[a.asset_class] ?? ESTIMATE_MARK }} />
            {`${a.label} ${pct(a.current!)} · ${t(SOURCE_WORD[a.current_source ?? ""] ?? "allocWordEstimate")}`}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** "Kaynak: …" under a row, from holdings.sources (id == current_source). */
export function SourceLine({ row, holdings }: { row: AllocationRow; holdings: Holdings | undefined }) {
  const t = useT();
  const kind = row.current_source ?? "";
  const src = holdings?.sources.find((s) => s.id === kind);
  let text: string;
  if (kind === "rm") text = t("allocSrcLineRm");
  else if (kind === "rm_confirmed") text = t("allocSrcLineRmConfirmed");
  else if (kind === "persona_text") {
    const quote = src ? /"([^"]+)"/.exec(src.label)?.[1] : undefined;
    const range = row.current_low != null && row.current_high != null ? ` → %${fmtNum(row.current_low)}–${fmtNum(row.current_high)}` : "";
    text = `${quote ? `${t("allocWordFile")}, "${quote}"` : (src?.label ?? row.current_ref ?? "")}${range}`;
  } else if (kind === "profile") {
    const label = src?.label ?? row.current_ref ?? "";
    text = /varsayım|assumption/i.test(label) ? label : `${label} ${t("allocAssumption")}`;
  } else {
    text = src ? [src.label, src.date ? fmtDate(src.date) : ""].filter(Boolean).join(", ") : (row.current_ref ?? "");
  }
  if (!text) return null;
  return (
    <div data-testid="alloc-source" title={src?.url || undefined} className="col-span-full -mt-1 text-xs text-muted">
      {`${t("source")}: ${text}`}
    </div>
  );
}

/** The legend under the rows: the two markers, the range line, the note. */
export function AllocationLegend() {
  const t = useT();
  return (
    <div data-testid="alloc-legend" className="mx-4 mt-2 flex flex-wrap gap-x-5 gap-y-1 border-t border-gray-100 pt-2.5 text-xs text-[#475467]">
      <span className="flex items-center gap-1.5">
        <i aria-hidden="true" className="inline-block h-3 w-[3px] rounded-sm" style={{ backgroundColor: ACTIVE_MARK }} />
        {t("allocLegActive")}
      </span>
      <span className="flex items-center gap-1.5">
        <i aria-hidden="true" className="inline-block h-3 w-[3px] rounded-sm" style={{ backgroundColor: ESTIMATE_MARK }} />
        {t("allocLegEstimate")}
      </span>
      <span className="flex items-center gap-1.5">
        <i aria-hidden="true" className="inline-block h-[2px] w-[18px] bg-[#344054]" />
        {t("allocLegRange")}
      </span>
      <span>{t("allocLegNote")}</span>
    </div>
  );
}

/** "ⓘ Hedef dağılım (profile)" and its pop-up note: every class with its target, current and gap. */
export function TargetNote({ view }: { view: RunView }) {
  const t = useT();
  const gapText = useGapText();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const pill = useRef<HTMLButtonElement>(null);
  const closeBtn = useRef<HTMLButtonElement>(null);
  const profile = view.result.persona.risk_profili;
  const first = view.allocation[0];

  useEffect(() => {
    if (!open) return;
    closeBtn.current?.focus();
    const outside = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      pill.current?.focus();
    };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const title = `${t("allocNoteTitle")} · ${profile}`;
  return (
    <div ref={wrap} className="relative">
      <button
        ref={pill}
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        className={`rounded-full border px-3 py-1 text-[13px] font-semibold ${open ? "border-cobalt bg-[#EEF2F9] text-[#2C4F8F]" : "border-gray-300 text-ink"}`}
        onClick={() => setOpen((o) => !o)}
      >
        {`ⓘ ${fill(t("allocNotePill"), { profile })}`}
      </button>
      {open && (
        <div
          role="dialog"
          aria-label={title}
          className="absolute right-0 z-20 mt-2 w-[min(640px,90vw)] rounded-xl border border-gray-200 bg-white p-4 text-[13px] shadow-lg"
        >
          <div className="mb-2 flex items-center justify-between">
            <b className="text-sm">{title}</b>
            <button
              ref={closeBtn}
              type="button"
              aria-label={t("close")}
              className="rounded-md px-2 text-muted hover:bg-gray-100"
              onClick={() => {
                setOpen(false);
                pill.current?.focus();
              }}
            >
              ✕
            </button>
          </div>
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-left text-[11px] font-bold uppercase tracking-[0.05em] text-muted">
                <th className="py-1.5 pr-2 font-bold">{t("allocNoteClass")}</th>
                <th className="py-1.5 pr-2 font-bold">{t("allocNoteTarget")}</th>
                <th className="py-1.5 pr-2 font-bold">{t("allocCurrent")}</th>
                <th className="py-1.5 pr-2 font-bold">{t("allocNoteBar")}</th>
                <th className="py-1.5 font-bold">{t("allocNoteGap")}</th>
              </tr>
            </thead>
            <tbody>
              {view.allocation.map((a) => {
                const band = a.low !== null && a.high !== null;
                const gap = gapText(a);
                return (
                  <tr key={a.asset_class} data-testid="note-row" className="border-t border-gray-100">
                    <td className="py-1.5 pr-2">{a.label}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{band ? `%${a.low}–${a.high}` : "—"}</td>
                    <td className="py-1.5 pr-2 tabular-nums">
                      {a.current == null ? "—" : `${pct(a.current)}${a.active ? "" : ` ${t("allocEstimateMark")}`}`}
                    </td>
                    <td className="w-[120px] py-1.5 pr-2">
                      {band && (
                        <div data-testid="note-mini" aria-hidden="true" className="relative h-2.5 rounded bg-[#F2F4F7]">
                          <div data-testid="note-band" className="absolute bottom-0 top-0 rounded bg-[#DCE6F5]" style={{ left: `${a.low}%`, width: `${a.high! - a.low!}%` }} />
                          {a.current != null && (
                            <div
                              data-testid="note-marker"
                              data-tone={a.active ? "active" : "estimate"}
                              className="absolute -bottom-0.5 -top-0.5 w-[3px] -translate-x-1/2 rounded-sm"
                              style={{ left: `${a.current}%`, backgroundColor: markColor(a) }}
                            />
                          )}
                        </div>
                      )}
                    </td>
                    <td className={`py-1.5 ${a.gap ? "font-semibold text-[#B54708]" : "text-muted"}`}>{gap ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {first && (
            <p data-testid="note-source" className="mt-2 text-xs text-muted">
              {`${t("source")}: ${first.source}${first.inferred ? ` ${t("allocInferred")}` : ""}. ${t("allocNoteDisclaimer")}`}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
