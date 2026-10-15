// The note box under the brief (W22; before W15 only the market note): "Piyasa notu · TCMB
// EVDS" (the policy rate, USD/TRY and the TCMB funding cost of the run's snapshot, each with
// its date and "K" mark), "Uyarılar" (the client warnings) and "RM notu" (the RM-only notes),
// each with its own title. An empty warnings section says so; no market data: no market section.
import type { MarketNoteItem, Warning } from "../api/types";
import { fmtDate } from "../format";
import { useT, type LabelKey } from "../i18n";
import { KMark } from "./OptionsTable";

const nf = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 4 });

/** "%37" for a percent, "49,1267 TL" for a TRY price. */
export function marketValue(item: MarketNoteItem): string {
  const text = nf.format(item.value);
  return item.unit === "pct" ? `%${text}` : `${text} TL`;
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

export function MarketNote({
  items,
  clientWarnings = [],
  rmWarnings = [],
  onEvidence,
}: {
  items: MarketNoteItem[];
  clientWarnings?: Warning[];
  rmWarnings?: Warning[];
  onEvidence: (id: string) => void;
}) {
  const t = useT();
  return (
    <section
      data-testid="notes-box"
      className={`mb-6 grid gap-x-8 gap-y-4 rounded-2xl bg-white px-[26px] py-4 shadow-sm ${
        items.length ? "lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]" : "lg:grid-cols-2"
      }`}
    >
      {items.length > 0 && (
        <div data-testid="market-note" className="min-w-0">
          <h3 className={heading}>{`${t("marketNote")} · TCMB EVDS`}</h3>
          <ul className="mt-2 flex flex-wrap gap-x-8 gap-y-2 text-sm">
            {items.map((x) => (
              <li key={x.key} data-testid="market-item" className="flex items-baseline gap-2">
                <span className="text-muted">{x.label}</span>
                <b className="tabular-nums">{marketValue(x)}</b>
                <span className="text-xs text-muted">{fmtDate(x.as_of)}</span>
                <KMark id={x.evidence_id} onEvidence={onEvidence} />
              </li>
            ))}
          </ul>
        </div>
      )}
      <WarningSection testId="box-warnings" title="warningsTab" empty="noWarnings" warnings={clientWarnings} onEvidence={onEvidence} />
      <WarningSection testId="box-rm-note" title="rmNote" empty="noRmNote" warnings={rmWarnings} onEvidence={onEvidence} />
    </section>
  );
}
