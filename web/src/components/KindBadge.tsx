// The product kinds of the exchange (contract v1.9, D26): a small badge "BYF" / "Pay".
import type { OptionKind } from "../api/types";
import { useT } from "../i18n";

/** Funds, ETFs and shares have a code in their option id ("fund:PPN", "etf:GLDTR", "stock:THYAO"). */
export const hasCode = (kind: OptionKind) => kind === "fund" || kind === "etf" || kind === "stock";

/** The data source of an option's values. */
export const sourceName = (kind: OptionKind) => (kind === "stock" ? "Borsa İstanbul" : kind === "fund" || kind === "etf" ? "TEFAS" : "ING");

export function KindBadge({ kind }: { kind: OptionKind }) {
  const t = useT();
  if (kind !== "etf" && kind !== "stock") return null;
  const etf = kind === "etf";
  return (
    <span
      data-testid="kind-badge"
      title={t(etf ? "kindEtfLong" : "kindStockLong")}
      className="ml-1.5 inline-block rounded-md border border-[#C7D2E5] bg-[#F7F9FC] px-1.5 py-px align-[2px] text-[11px] font-bold normal-case tracking-normal text-[#2C4F8F]"
    >
      {t(etf ? "kindEtf" : "kindStock")}
    </span>
  );
}
