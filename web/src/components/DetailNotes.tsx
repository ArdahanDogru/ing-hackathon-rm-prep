// The pop-up notes of "Bu öneriler nasıl seçildi?" (W22; before: the tabs of the "Detaylar"
// pane, W17): Varsayımlar, Veri notları, Elenen (one row per rule) and Kategoriler.
import { useState } from "react";
import type { RejectedByRule, RunView } from "../api/types";
import { useT, type LabelKey } from "../i18n";
import { CategoryList } from "./CategoryList";
import { NoteDialog } from "./NoteDialog";
import { CodeBadge } from "../product";

export type NoteKind = "categories" | "assumptions" | "dataNotes" | "eliminated";

function RuleRow({ rule }: { rule: RejectedByRule }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="border-t border-gray-100 first:border-t-0">
      <button type="button" aria-expanded={open} className="flex w-full justify-between py-2 text-left" onClick={() => setOpen(!open)}>
        <span>{rule.label}</span>
        <span className="text-muted">{rule.count} ›</span>
      </button>
      {open && (
        <ul data-testid={`rule-${rule.rule_id}`} className="mb-2 ml-3 space-y-1 pr-1 text-xs">
          {rule.options.map((o, i) => (
            <li key={o.label + i}>
              <span className="font-medium">
                {o.option_id && <CodeBadge optionId={o.option_id} />}
                {o.label}
              </span>
              <span className="text-muted">{` · ${o.reasons.join("; ")}`}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

const TITLE: Record<NoteKind, LabelKey> = {
  categories: "categories",
  assumptions: "assumptions",
  dataNotes: "dataNotes",
  eliminated: "eliminated",
};

export function DetailNote({
  kind,
  view,
  onOpen,
  onClose,
}: {
  kind: NoteKind;
  view: RunView;
  onOpen: (id: string) => void;
  onClose: () => void;
}) {
  const t = useT();
  const count: Record<NoteKind, number> = {
    categories: view.categories.length,
    assumptions: view.assumptions.length,
    dataNotes: view.data_notes.length,
    eliminated: view.result.rejected.length,
  };
  const list = (items: string[]) => (
    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-normal">
      {items.map((x, i) => (
        <li key={i}>{x}</li>
      ))}
    </ul>
  );
  const body =
    kind === "categories" ? (
      <CategoryList view={view} onOpen={onOpen} />
    ) : kind === "assumptions" ? (
      list(view.assumptions)
    ) : kind === "dataNotes" ? (
      list(view.data_notes.map((n) => n.message))
    ) : (
      <>
        <ul className="text-sm">
          {view.rejected_by_rule.map((r) => (
            <RuleRow key={r.rule_id} rule={r} />
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted">{t("rejectedMulti")}</p>
      </>
    );
  return (
    <NoteDialog title={`${t(TITLE[kind])} (${count[kind]})`} onClose={onClose}>
      {body}
    </NoteDialog>
  );
}
