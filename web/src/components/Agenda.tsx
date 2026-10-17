// "Gündem · müşteriyle konuşulacaklar": talking points as checkable agenda items,
// then the "Teyit edin" items (B4 item 4). W47: over the full width, the points side by side.
import type { ConfirmItem, TalkingPoint } from "../api/types";
import { useT } from "../i18n";

export function Agenda({
  points,
  confirm,
  discussed,
  onDiscussed,
  confirmed,
  onConfirmed,
  onAnswer,
  onEvidence,
}: {
  points: TalkingPoint[];
  confirm: ConfirmItem[];
  discussed: boolean[];
  onDiscussed: (i: number) => void;
  confirmed: boolean[];
  onConfirmed: (i: number) => void;
  onAnswer?: (questionId: string, answer: string) => void;
  onEvidence: (id: string) => void;
}) {
  const t = useT();
  return (
    <section data-testid="agenda" className="h-full rounded-2xl bg-white px-[22px] py-5 shadow-sm">
      <h2 className="mb-3 text-xs font-bold uppercase tracking-[0.06em] text-muted">{t("agenda")}</h2>
      <ul className="mb-4 grid gap-x-8 gap-y-3 lg:grid-cols-3">
        {points.slice(0, 3).map((p, i) => (
          <li key={p.code} data-testid="agenda-point" className="flex items-start gap-3">
            <input
              type="checkbox"
              className="mt-1"
              aria-label={`${t("discussed")}: ${p.label}`}
              checked={!!discussed[i]}
              onChange={() => onDiscussed(i)}
            />
            <div className={discussed[i] ? "text-muted" : ""}>
              <b>{`${p.label} ${p.figure}`}</b>
              {p.evidence_ids.length > 0 && (
                <button
                  type="button"
                  aria-label={`${t("evidence")} ${i + 1}`}
                  className="ml-1 rounded-md bg-[#EEF2F9] px-[7px] py-px align-[2px] text-[11px] font-bold text-cobalt"
                  onClick={() => onEvidence(p.evidence_ids[0])}
                >
                  {i + 1}
                </button>
              )}
              <div className="text-sm leading-normal text-[#344054]">{p.text}</div>
            </div>
          </li>
        ))}
      </ul>
      {confirm.length > 0 && (
        <div className="border-t border-gray-100 pt-3.5">
          <h3 className="mb-2 font-bold text-[#B54708]">{t("confirm")}</h3>
          <ul className="grid gap-x-8 gap-y-3 lg:grid-cols-2">
            {confirm.map((c, i) => (
              <li key={c.text} data-testid="confirm-item" className="flex items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-1"
                  aria-label={`${t("confirmed")}: ${c.text}`}
                  checked={!!confirmed[i]}
                  onChange={() => onConfirmed(i)}
                />
                <div className="text-sm leading-normal">
                  <span className={confirmed[i] ? "text-muted line-through" : "text-[#344054]"}>{c.text}</span>
                  {c.question_id && c.choices.length > 0 && onAnswer && (
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
                      <span className="text-muted">{`${t("answer")}:`}</span>
                      {c.choices.map((ch) => (
                        <button
                          key={ch}
                          type="button"
                          className="rounded-full border border-gray-300 px-2 py-0.5"
                          onClick={() => onAnswer(c.question_id!, ch)}
                        >
                          {ch}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
