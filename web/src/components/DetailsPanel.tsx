// "Detaylar" (B4 item 5): one line with counts that opens one panel with tabs.
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { RejectedByRule, RunView } from "../api/types";
import { useT, type LabelKey } from "../i18n";
import { CategoryList } from "./CategoryList";
import { WarningList } from "./Notes";

function RuleRow({ rule }: { rule: RejectedByRule }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="border-t border-gray-100 first:border-t-0">
      <button type="button" aria-expanded={open} className="flex w-full justify-between py-2 text-left" onClick={() => setOpen(!open)}>
        <span>{rule.label}</span>
        <span className="text-muted">{rule.count} ›</span>
      </button>
      {open && (
        <ul data-testid={`rule-${rule.rule_id}`} className="mb-2 ml-3 max-h-72 space-y-1 overflow-y-auto pr-1 text-xs">
          {rule.options.map((o, i) => (
            <li key={o.label + i}>
              <span className="font-medium">{o.label}</span>
              <span className="text-muted">{` · ${o.reasons.join("; ")}`}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export type Tab = "categories" | "assumptions" | "dataNotes" | "eliminated" | "warnings" | "rmNote";

export function DetailsPanel({
  view,
  selected,
  onToggle,
  onOpen,
  request,
}: {
  view: RunView;
  selected: string[];
  onToggle: (id: string) => void;
  onOpen: (id: string) => void;
  /** W17: open the panel on this tab (a new `n` opens it again). */
  request?: { tab: Tab; n: number } | null;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("categories");
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!request) return;
    setOpen(true);
    setTab(request.tab);
    ref.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [request]);
  const tabs: [Tab, LabelKey, number][] = [
    ["categories", "categories", view.categories.length],
    ["assumptions", "assumptions", view.assumptions.length],
    ["dataNotes", "dataNotes", view.data_notes.length],
    ["eliminated", "eliminated", view.result.rejected.length],
    ["warnings", "warningsTab", view.client_warnings.length],
    ["rmNote", "rmNote", view.rm_warnings.length],
  ];
  const list = (items: string[]) => (
    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-normal">
      {items.map((x, i) => (
        <li key={i}>{x}</li>
      ))}
    </ul>
  );
  const panels: Record<Tab, ReactNode> = {
    categories: <CategoryList categories={view.categories} options={view.options} selected={selected} onToggle={onToggle} onOpen={onOpen} />,
    assumptions: list(view.assumptions),
    dataNotes: list(view.data_notes.map((n) => n.message)),
    eliminated: (
      <>
        <ul className="text-sm">
          {view.rejected_by_rule.map((r) => (
            <RuleRow key={r.rule_id} rule={r} />
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted">{t("rejectedMulti")}</p>
      </>
    ),
    // client-audience warnings (may go into client-facing text); "RM notu" is RM-only
    warnings: <WarningList warnings={view.client_warnings} />,
    rmNote: <WarningList warnings={view.rm_warnings} />,
  };

  return (
    <section ref={ref} className="rounded-2xl bg-white shadow-sm">
      <button
        type="button"
        aria-expanded={open}
        className="flex w-full flex-wrap items-center justify-between gap-2 px-[18px] py-3.5 text-left text-[#344054]"
        onClick={() => setOpen(!open)}
      >
        <b>{t("detailsPanel")}</b>
        <span className="text-muted">
          {tabs.map(([, label, n]) => `${t(label)} (${n})`).join(" · ")} {open ? "‹" : "›"}
        </span>
      </button>
      {open && (
        <div className="border-t border-gray-100 px-[18px] pb-4">
          <div role="tablist" className="flex flex-wrap gap-1 border-b border-gray-100">
            {tabs.map(([key, label, n]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                className={
                  tab === key
                    ? "-mb-px border-b-2 border-ink px-3 py-2.5 text-sm font-semibold"
                    : "-mb-px border-b-2 border-transparent px-3 py-2.5 text-sm text-muted hover:text-ink"
                }
                onClick={() => setTab(key)}
              >
                {`${t(label)} (${n})`}
              </button>
            ))}
          </div>
          <div role="tabpanel" className="pt-3">
            {panels[tab]}
          </div>
        </div>
      )}
    </section>
  );
}
