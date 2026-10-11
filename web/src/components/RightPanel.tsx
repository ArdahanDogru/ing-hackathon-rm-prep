import { useEffect, useState, type ReactNode } from "react";
import type { RunView } from "../api/types";
import { useT } from "../i18n";
import { WarningList } from "./Notes";

const storeKey = (runId: string) => `rmprep.confirm.${runId}`;

function loadChecks(runId: string): boolean[] {
  try {
    return JSON.parse(localStorage.getItem(storeKey(runId)) ?? "[]");
  } catch {
    return [];
  }
}

function Line({ head, children }: { head: ReactNode; children: ReactNode }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-gray-200">
      <button
        type="button"
        data-testid="panel-head"
        aria-expanded={open}
        className="flex w-full items-center justify-between py-2.5 text-left text-[13px] text-[#475467]"
        onClick={() => setOpen(!open)}
      >
        <span>{head}</span>
        <span className="text-xs text-[#355FA1] underline">{open ? t("hide") : `${t("show")} ›`}</span>
      </button>
      {open && <div className="pb-3 text-[13px] leading-snug">{children}</div>}
    </div>
  );
}

function RuleRow({ rule }: { rule: RunView["rejected_by_rule"][number] }) {
  const [open, setOpen] = useState(false);
  return (
    <li>
      <button
        type="button"
        aria-expanded={open}
        className="flex w-full justify-between py-1 text-left"
        onClick={() => setOpen(!open)}
      >
        <span>{rule.label}</span>
        <span className="text-muted">{rule.count} ›</span>
      </button>
      {open && (
        <ul className="mb-2 ml-3 space-y-1 text-xs">
          {rule.options.map((o) => (
            <li key={o.label}>
              <span className="font-medium">{o.label}</span>
              <span className="text-muted">{` · ${o.reasons.join("; ")}`}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** Right panel (mockup dikkat-v3 A): "Teyit edin" checklist, then collapsed lines, then warnings. */
export function RightPanel({
  view,
  onAnswer,
}: {
  view: RunView;
  onAnswer?: (questionId: string, answer: string) => void;
}) {
  const t = useT();
  const runId = view.result.run_id;
  const [checks, setChecks] = useState<boolean[]>(() => loadChecks(runId));
  useEffect(() => {
    try {
      localStorage.setItem(storeKey(runId), JSON.stringify(checks));
    } catch {
      // storage blocked: the checks stay for this page only
    }
  }, [runId, checks]);

  const items = view.to_confirm;
  const open = items.filter((_, i) => !checks[i]).length;
  const warnings = [...view.client_warnings, ...view.rm_warnings];

  return (
    <aside className="rounded-2xl bg-white px-5 py-4 shadow-sm">
      {items.length > 0 && (
        <div className="mb-2">
          <div data-testid="panel-head" className="mb-2 flex items-center gap-2 text-[14px] font-semibold">
            {open > 0 && <span className="h-2 w-2 rounded-full bg-[#F79009]" aria-hidden="true" />}
            {t("confirm")}
            <span data-testid="confirm-status" className={open ? "ml-auto text-xs text-[#B54708]" : "ml-auto text-xs text-muted"}>
              {open ? `${open} ${t("confirmOpen")}` : t("confirmDone")}
            </span>
          </div>
          <ul className="space-y-2">
            {items.map((item, i) => (
              <li key={item.text}>
                <label className="flex items-start gap-2 text-[13px] leading-snug">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={!!checks[i]}
                    onChange={(e) =>
                      setChecks((c) => {
                        const next = [...c];
                        next[i] = e.target.checked;
                        return next;
                      })
                    }
                  />
                  <span className={checks[i] ? "text-muted line-through" : ""}>{item.text}</span>
                </label>
                {item.question_id && item.choices.length > 0 && onAnswer && (
                  <div className="ml-6 mt-1 flex flex-wrap items-center gap-1.5 text-xs">
                    <span className="text-muted">{t("answer")}:</span>
                    {item.choices.map((c) => (
                      <button
                        key={c}
                        type="button"
                        className="rounded-full border border-gray-300 px-2 py-0.5"
                        onClick={() => onAnswer(item.question_id!, c)}
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Line head={`${t("assumptions")} · ${view.assumptions.length}`}>
        <ul className="list-disc space-y-1 pl-4">
          {view.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </Line>
      <Line head={`${t("dataNotes")} · ${view.data_notes.length}`}>
        <ul className="list-disc space-y-1 pl-4">
          {view.data_notes.map((n) => (
            <li key={n.message}>{n.message}</li>
          ))}
        </ul>
      </Line>
      <Line head={`${view.result.rejected.length} ${t("rejectedCount")}`}>
        <ul>
          {view.rejected_by_rule.map((r) => (
            <RuleRow key={r.rule_id} rule={r} />
          ))}
        </ul>
        <p className="mt-1 text-xs text-muted">{t("rejectedMulti")}</p>
      </Line>

      {warnings.length > 0 && (
        <div className="mt-2 border-t border-gray-200 pt-3">
          <h3 className="mb-2 text-[14px] font-semibold">{t("attention")}</h3>
          <WarningList warnings={warnings} />
        </div>
      )}
    </aside>
  );
}
