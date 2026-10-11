// needs_rm_input: the open blocking questions take the place of the options.
import { useState } from "react";
import type { ClarificationQuestion } from "../api/types";
import { useT } from "../i18n";

function Question({ q, onAnswer }: { q: ClarificationQuestion; onAnswer: (answer: string) => void }) {
  const t = useT();
  const [text, setText] = useState("");
  return (
    <li data-testid="question" className="border-t border-gray-100 py-3 first:border-t-0">
      <p className="text-[15px] font-medium">{q.text}</p>
      <p className="mt-0.5 text-xs text-muted">{q.reason}</p>
      {q.choices.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {q.choices.map((c) => (
            <button
              key={c}
              type="button"
              className="rounded-full border border-gray-300 px-3 py-1 text-sm hover:border-ink"
              onClick={() => onAnswer(c)}
            >
              {c}
            </button>
          ))}
        </div>
      ) : (
        <form
          className="mt-2 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) onAnswer(text.trim());
          }}
        >
          <input
            aria-label={t("yourAnswer")}
            placeholder={t("yourAnswer")}
            className="flex-1 rounded-lg border border-gray-300 px-2.5 py-1.5 text-sm"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button type="submit" className="rounded-[10px] bg-ink px-3.5 py-1.5 text-sm font-semibold text-white">
            {t("answer")}
          </button>
        </form>
      )}
    </li>
  );
}

export function QuestionsPanel({
  questions,
  onAnswer,
}: {
  questions: ClarificationQuestion[];
  onAnswer: (questionId: string, answer: string) => void;
}) {
  const t = useT();
  const open = questions.filter((q) => q.blocking && q.answer === null);
  return (
    <section className="rounded-2xl bg-white px-5 py-4 shadow-sm">
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <span className="h-2 w-2 rounded-full bg-[#F79009]" aria-hidden="true" />
        {t("questionsTitle")}
      </h2>
      <ul className="mt-2">
        {open.map((q) => (
          <Question key={q.question_id} q={q} onAnswer={(a) => onAnswer(q.question_id, a)} />
        ))}
      </ul>
    </section>
  );
}
