// "Diğer bankalar — bağlam, puana dahil değil" (W25; docs/web-ui.md "Other banks' rates as context
// for the RM"): in the fund card only, for the RM. The own rate first (bold), then the other banks'
// rates with the difference in points, in a neutral color: a higher rate elsewhere is neither good
// nor bad for the RM. Nothing here changes a score or a rank.
import type { BankContext as BankContextData } from "../api/types";
import { fmtDate } from "../format";
import { useT } from "../i18n";
import { KMark } from "./OptionsTable";

const nf2 = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MINUS = "−";

/** "34,50 %" */
export const fmtRate = (v: number) => `${nf2.format(v)} %`;

/** "+2,50" / "−3,50" / "0,00": the difference in percentage points. */
export function fmtPoints(v: number): string {
  const text = nf2.format(Math.abs(v));
  return text === "0,00" ? text : v < 0 ? `${MINUS}${text}` : `+${text}`;
}

export function BankContext({ context, onEvidence }: { context: BankContextData | null | undefined; onEvidence: (id: string) => void }) {
  const t = useT();
  if (!context?.rows.length) return null;
  return (
    <section data-testid="bank-context" className="my-[22px] rounded-xl border border-gray-200 px-4 py-3.5">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <b className="text-sm">{t("bankTitle")}</b>
        <span className="text-xs text-muted">{t("bankSubtitle")}</span>
      </div>
      <ul className="mt-2 divide-y divide-gray-100 text-sm">
        {context.rows.map((r, i) => (
          <li
            key={`${r.label}|${i}`}
            data-testid="bank-row"
            data-own={r.own ? "true" : undefined}
            className={`flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-1.5 ${r.own ? "font-bold" : ""}`}
          >
            <span className="min-w-[150px]">{r.label}</span>
            <span className="flex-1 text-xs font-normal text-muted">{r.cell}</span>
            {r.value === null ? (
              <span className="text-xs font-normal text-muted">{t("bankNoData")}</span>
            ) : (
              <>
                <span className="tabular-nums">
                  {fmtRate(r.value)}
                  <KMark id={r.evidence_id || undefined} onEvidence={onEvidence} />
                </span>
                {r.as_of && (
                  <span
                    data-testid="bank-date"
                    data-stale={r.stale ? "true" : undefined}
                    title={r.stale ? t("bankStaleTip") : undefined}
                    className={`text-xs font-normal tabular-nums ${r.stale ? "text-[#B54708]" : "text-muted"}`}
                  >
                    {fmtDate(r.as_of)}
                    {r.stale && ` · ${t("bankStale")}`}
                  </span>
                )}
                {!r.own && r.diff_pp !== null && (
                  <span data-testid="bank-diff" className="text-xs font-semibold tabular-nums text-[#475467]">
                    {`${fmtPoints(r.diff_pp)} ${t("bankPoints")}`}
                  </span>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
      {context.note && <p className="mt-2 text-xs text-muted">{context.note}</p>}
    </section>
  );
}
