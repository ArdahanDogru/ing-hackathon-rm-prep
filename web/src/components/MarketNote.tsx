// "Piyasa notu · TCMB EVDS" (docs/web-ui.md W15): the policy rate, USD/TRY and the
// TCMB funding cost of the run's snapshot, each with its date and "K" mark.
import type { MarketNoteItem } from "../api/types";
import { fmtDate } from "../format";
import { useT } from "../i18n";
import { KMark } from "./OptionsTable";

const nf = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 4 });

/** "%40,5" for a percent, else "41,2345 TL". */
export function marketValue(item: MarketNoteItem): string {
  const text = nf.format(item.value);
  return item.unit === "%" ? `%${text}` : [text, item.unit].filter(Boolean).join(" ");
}

export function MarketNote({ items, onEvidence }: { items: MarketNoteItem[] | undefined; onEvidence: (id: string) => void }) {
  const t = useT();
  if (!items?.length) return null;
  return (
    <section data-testid="market-note" className="mb-6 rounded-2xl bg-white px-[26px] py-4 shadow-sm">
      <h3 className="text-xs font-bold uppercase tracking-[0.06em] text-muted">{`${t("marketNote")} · TCMB EVDS`}</h3>
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
    </section>
  );
}
