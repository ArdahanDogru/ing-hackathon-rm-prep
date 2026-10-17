// The note box under the brief (W22; before W15 only the market note): "Piyasa notu · TCMB
// EVDS" (the policy rate, USD/TRY and the TCMB funding cost of the run's snapshot, each with
// its date and "K" mark), "Uyarılar" (the client warnings) and "RM notu" (the RM-only notes),
// each with its own title. An empty warnings section says so; no market data: no market section.
import type { MarketBankEntry, MarketNoteItem, Warning } from "../api/types";
import { BankDate, BankDiff, fmtRate } from "./BankContext";
import { fmtDate, fmtUnit } from "../format";
import { LangContext, useT, type LabelKey } from "../i18n";
import { useContext } from "react";
import { KMark } from "./OptionsTable";

/** "%37" for a percent, "49,13 TL" for a TRY price: the one unit formatter (W42). */
export function marketValue(item: MarketNoteItem, lang: "TR" | "EN" = "TR"): string {
  return fmtUnit(item.value, item.unit, lang);
}

const heading = "text-xs font-bold uppercase tracking-[0.06em] text-muted";

function WarningSection({
  testId,
  title,
  empty,
  warnings,
  onEvidence,
}: {
  testId: string;
  title: LabelKey;
  empty: LabelKey;
  warnings: Warning[];
  onEvidence: (id: string) => void;
}) {
  const t = useT();
  return (
    <div data-testid={testId} className="min-w-0">
      <h3 className={heading}>{t(title)}</h3>
      {warnings.length ? (
        <ul className="mt-2 space-y-1.5 text-[13px] leading-snug text-[#344054]">
          {warnings.map((w) => (
            <li key={w.code + w.message} data-audience={w.audience}>
              {w.message}
              <KMark id={w.evidence_ids[0]} onEvidence={onEvidence} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-[13px] text-muted">{t(empty)}</p>
      )}
    </div>
  );
}

/** W25b: one line per entry: the title, then each row "label %rate" with its K mark and date
 * (the own row bold; the banks with the difference in points), the note small under it. */
function BankLine({ entry, onEvidence }: { entry: MarketBankEntry; onEvidence: (id: string) => void }) {
  const t = useT();
  return (
    <div data-testid="bank-line" className="mt-2.5 text-sm">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="text-muted">{entry.title}</span>
        {entry.rows.map((r, i) => (
          <span key={`${r.label}|${i}`} data-testid="bank-part" className={`flex items-baseline gap-1.5 ${r.own ? "font-bold" : ""}`}>
            {r.value === null ? (
              <>
                {r.label} <span className="text-xs font-normal text-muted">{t("bankNoData")}</span>
              </>
            ) : (
              <>
                {r.label} <span className="tabular-nums">{fmtRate(r.value)}</span>
                <KMark id={r.evidence_id || undefined} onEvidence={onEvidence} />
                <BankDate row={r} />
                <BankDiff row={r} />
              </>
            )}
          </span>
        ))}
      </div>
      {entry.note && <p className="mt-1 text-xs text-muted">{entry.note}</p>}
    </div>
  );
}

export function MarketNote({
  items,
  banks = [],
  clientWarnings = [],
  rmWarnings = [],
  onEvidence,
}: {
  items: MarketNoteItem[];
  /** W25b: the bank rates entries of the run */
  banks?: MarketBankEntry[];
  clientWarnings?: Warning[];
  rmWarnings?: Warning[];
  onEvidence: (id: string) => void;
}) {
  const t = useT();
  const lang = useContext(LangContext);
  const market = items.length > 0 || banks.length > 0;
  return (
    <section
      data-testid="notes-box"
      className={`mb-6 grid gap-x-8 gap-y-4 rounded-2xl bg-white px-[26px] py-4 shadow-sm ${
        market ? "lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]" : "lg:grid-cols-2"
      }`}
    >
      {market && (
        <div data-testid="market-note" className="min-w-0">
          <h3 className={heading}>{`${t("marketNote")} · TCMB EVDS`}</h3>
          <ul className="mt-2 flex flex-wrap gap-x-8 gap-y-2 text-sm">
            {items.map((x) => (
              <li key={x.key} data-testid="market-item" className="flex items-baseline gap-2">
                <span className="text-muted">{x.label}</span>
                <b className="tabular-nums">{marketValue(x, lang)}</b>
                <span className="text-xs text-muted">{fmtDate(x.as_of)}</span>
                <KMark id={x.evidence_id} onEvidence={onEvidence} />
              </li>
            ))}
          </ul>
          {banks.map((b) => (
            <BankLine key={b.option_id} entry={b} onEvidence={onEvidence} />
          ))}
        </div>
      )}
      <WarningSection testId="box-warnings" title="warningsTab" empty="noWarnings" warnings={clientWarnings} onEvidence={onEvidence} />
      <WarningSection testId="box-rm-note" title="rmNote" empty="noRmNote" warnings={rmWarnings} onEvidence={onEvidence} />
    </section>
  );
}
