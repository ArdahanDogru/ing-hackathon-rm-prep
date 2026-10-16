// "Belgeler" (W26; docs/web-ui.md "Fund documents: links to the manager's own site"): in the
// fund drawer of a fund or an ETF, the official izahname and YBF links found on the manager's
// own site, loaded when the drawer opens. Links only: the web makes no link to KAP or to any
// other site. Not in the score, the agent, the meeting text or the card.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { FundDocument, FundDocuments as Docs, OptionView } from "../api/types";
import { fmtDate, fmtDay } from "../format";
import { useT, type LabelKey } from "../i18n";

const KIND_LABEL: Record<FundDocument["kind"], LabelKey> = { izahname: "docIzahname", ybf: "docYbf" };

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function External({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-baseline gap-1 font-semibold text-[#2C4F8F] underline">
      {children}
      <span data-testid="external-mark" aria-hidden="true" className="text-xs no-underline">
        ↗
      </span>
    </a>
  );
}

export function FundDocuments({ runId, option }: { runId: string; option: OptionView }) {
  const t = useT();
  const [docs, setDocs] = useState<Docs | "loading" | "error">("loading");
  const shown = option.kind === "fund" || option.kind === "etf";

  const load = useCallback(() => {
    if (!shown) return () => {};
    let live = true;
    setDocs("loading");
    api.documents(runId, option.option_id).then(
      (d) => live && setDocs(d),
      () => live && setDocs("error"),
    );
    return () => {
      live = false;
    };
  }, [runId, option.option_id, shown]);
  useEffect(load, [load]);

  if (!shown) return null;
  const failed = docs === "error" || (typeof docs === "object" && docs.status === "failed");
  return (
    <section data-testid="fund-documents" className="my-[22px] rounded-xl border border-gray-200 px-4 py-3.5 text-sm">
      <b>{t("docTitle")}</b>
      {docs === "loading" ? (
        <p className="mt-1.5 animate-pulse text-muted">{t("docLoading")}</p>
      ) : failed ? (
        <div className="mt-1.5 flex flex-wrap items-center gap-3">
          <span className="text-muted">{t("docFailed")}</span>
          <button type="button" className="rounded-[10px] border border-gray-300 px-3 py-1 text-[13px] font-semibold" onClick={load}>
            {t("retry")}
          </button>
        </div>
      ) : docs.status === "ok" ? (
        <>
          <ul className="mt-1.5 space-y-1">
            {docs.docs.map((d) => (
              <li key={d.url}>
                <External href={d.url}>{[t(KIND_LABEL[d.kind]) ?? d.label, d.date ? fmtDate(d.date) : ""].filter(Boolean).join(" · ")}</External>
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-xs text-muted">
            {`${t("docSource")}: ${docs.page_url ? host(docs.page_url) : docs.manager_label}, ${t("docChecked")} ${fmtDay(docs.checked_at)}`}
          </p>
        </>
      ) : docs.status === "not_found" ? (
        <p className="mt-1.5 text-muted">
          {t("docNotFound")}
          {docs.page_url && (
            <span className="ml-1.5">
              <External href={docs.page_url}>{host(docs.page_url)}</External>
            </span>
          )}
        </p>
      ) : (
        <p className="mt-1.5 text-muted">{docs.reason}</p>
      )}
    </section>
  );
}
