// The rate helpers of the bank rows (W25). W46 (the user, 2026-10-17): the fund-card block "Diğer
// bankalar" and the other banks' rows are not shown; the market note (MarketNote) keeps the own ING
// row and uses these helpers.
import type { BankRow } from "../api/types";
import { fmtDate } from "../format";
import { useT } from "../i18n";

const nf2 = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MINUS = "−";

/** "%34,50": the Turkish percent form of the app (% first; W25 asks for two decimals). */
export const fmtRate = (v: number) => `%${nf2.format(v)}`;

/** "+2,50" / "−3,50" / "0,00": the difference in percentage points. */
export function fmtPoints(v: number): string {
  const text = nf2.format(Math.abs(v));
  return text === "0,00" ? text : v < 0 ? `${MINUS}${text}` : `+${text}`;
}

/** The date of a rate; a stale one in amber with "· eski" and a tooltip (W25). */
export function BankDate({ row, className = "" }: { row: BankRow; className?: string }) {
  const t = useT();
  return (
    <span
      data-testid="bank-date"
      data-stale={row.stale ? "true" : undefined}
      title={row.stale ? t("bankStaleTip") : undefined}
      className={`whitespace-nowrap text-xs font-normal tabular-nums ${row.stale ? "text-[#B54708]" : "text-muted"} ${className}`}
    >
      {row.as_of ? fmtDate(row.as_of) : ""}
      {row.stale && ` · ${t("bankStale")}`}
    </span>
  );
}

/** "+2,50 puan" for a bank row (neutral grey: a higher rate elsewhere is not good or bad); empty otherwise. */
export function BankDiff({ row, className = "" }: { row: BankRow; className?: string }) {
  const t = useT();
  const shown = !row.own && row.diff_pp !== null;
  return (
    <span
      data-testid={shown ? "bank-diff" : undefined}
      className={`whitespace-nowrap text-xs font-semibold tabular-nums text-[#475467] ${className}`}
    >
      {shown ? `${fmtPoints(row.diff_pp!)} ${t("bankPoints")}` : ""}
    </span>
  );
}
