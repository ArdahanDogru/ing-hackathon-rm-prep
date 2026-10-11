import { useState } from "react";
import type { NarrativeSentence, OptionView } from "../api/types";
import { fmtPct } from "../format";
import { useT } from "../i18n";
import { RiskBar } from "./RiskBar";

/** One selected option in the meeting text: tiles, need tags, its sentences, evidence, a note. */
export function RecommendationCard({
  option,
  position,
  sentences,
  tags,
  note,
  onNote,
  onEvidence,
}: {
  option: OptionView;
  position: number;
  sentences: NarrativeSentence[];
  tags: string[];
  note: string;
  onNote: (v: string) => void;
  onEvidence: (id: string) => void;
}) {
  const t = useT();
  const [showEv, setShowEv] = useState(false);
  const facts = [option.returns["1y"]?.evidence_id, option.risk?.evidence_id, option.access.evidence_id];
  const evidence = [...new Set([...sentences.flatMap((s) => s.evidence_ids), ...facts].filter((x): x is string => !!x))];
  const r1 = option.returns["1y"];

  return (
    <article data-testid="rec-card" className="mb-4 rounded-[18px] bg-white px-6 py-5 shadow-sm">
      <div className="flex items-center gap-3.5">
        <div className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-[#EEF2F9] text-[17px] font-bold text-[#355FA1]">
          {position}
        </div>
        <div>
          <div className="text-xl font-bold">{option.label}</div>
          <div className="text-[15px] text-muted">{option.category_label}</div>
        </div>
      </div>
      <div className="my-4 grid grid-cols-3 gap-3">
        <div className="rounded-xl bg-[#F7F9FC] px-3.5 py-3">
          <div className="text-[13px] text-muted">{t("return1yLong")}</div>
          <div className="mt-0.5 text-[22px] font-bold">{r1 ? fmtPct(r1.value) : "—"}</div>
        </div>
        <div className="rounded-xl bg-[#F7F9FC] px-3.5 py-3">
          <div className="text-[13px] text-muted">{t("risk")}</div>
          {option.risk ? <RiskBar level={option.risk.level} /> : <div className="mt-0.5 text-[22px] font-bold">—</div>}
        </div>
        <div className="rounded-xl bg-[#F7F9FC] px-3.5 py-3">
          <div className="text-[13px] text-muted">{t("access")}</div>
          <div className="mt-0.5 text-[22px] font-bold">{option.access.label ?? "—"}</div>
        </div>
      </div>
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {tags.map((tag) => (
            <span key={tag} className="rounded-full bg-[#EEF2F9] px-3 py-1.5 text-sm font-medium text-[#2C4F8F]">
              {tag}
            </span>
          ))}
        </div>
      )}
      {sentences.map((s, i) => (
        <p key={i} className="mt-2 max-w-[66ch] text-[17px] leading-[1.65]">
          {s.text}
        </p>
      ))}
      {evidence.length > 0 && (
        <div className="mt-3">
          <button
            type="button"
            aria-expanded={showEv}
            className="text-sm font-semibold text-[#355FA1]"
            onClick={() => setShowEv(!showEv)}
          >
            {`${t("showEvidence")} (${evidence.length}) ›`}
          </button>
          {showEv && (
            <ul className="mt-1 flex flex-wrap gap-2 text-xs">
              {evidence.map((id) => (
                <li key={id}>
                  <button type="button" className="rounded-full border border-gray-300 px-2 py-0.5 font-mono" onClick={() => onEvidence(id)}>
                    {id}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <label className="mt-3.5 block">
        <span className="text-[13px] font-semibold text-[#355FA1]">{t("myNote")}</span>
        <textarea
          rows={2}
          placeholder={t("optionNote")}
          className="mt-1 w-full resize-y rounded-xl border border-dashed border-[#C7D2E5] bg-[#FBFCFE] px-3.5 py-2.5 text-[15px] focus:border-solid"
          value={note}
          onChange={(e) => onNote(e.target.value)}
        />
      </label>
    </article>
  );
}
