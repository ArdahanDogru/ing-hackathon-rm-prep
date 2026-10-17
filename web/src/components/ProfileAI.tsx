// W43: the AI check of the client profile (docs/web-ui.md). The API starts it when a run opens;
// the web asks every 2 s while it runs (at most 90 s). Its findings join the W42 profile block,
// the "Teyit edin" list and the marks of "Profili düzenle". Display only.
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ConfirmItem, Lang, Persona, ProfileAIFinding, ProfileAIView, ProfileCheck } from "../api/types";
import { useT, type LabelKey } from "../i18n";
import { Resolve, type ResolveProps } from "./Resolve";

const POLL_MS = 2000;
const POLL_MAX = 45; // 90 s

/** The AI check of a ready run: asked at once, then every 2 s while it runs. An error, or no
 * answer after 90 s, gives "off" (nothing on screen). */
export function useProfileAI(runId: string, lang: Lang, enabled: boolean): ProfileAIView | null {
  const [view, setView] = useState<ProfileAIView | null>(null);
  const shown = useRef("");
  useEffect(() => {
    const key = `${runId}|${lang}|${enabled}`;
    if (shown.current !== key) setView(null); // another run or language: not the old findings
    shown.current = key;
    if (!enabled) return;
    let done = false;
    let calls = 0;
    const stop = () => {
      done = true;
      clearInterval(timer);
    };
    const off: ProfileAIView = { state: "off", findings: [] };
    const ask = () => {
      if (done) return;
      if (calls >= POLL_MAX) {
        setView(off);
        return stop();
      }
      calls += 1;
      api.profileCheck(runId, lang).then(
        (v) => {
          if (done) return;
          setView(v);
          if (v.state !== "running") stop();
        },
        () => {
          if (!done) setView(off);
          stop();
        },
      );
    };
    const timer = setInterval(ask, POLL_MS);
    ask();
    return stop;
  }, [runId, lang, enabled]);
  return view;
}

/** "ai:<hash>" from the API (W44); a list place without it. */
const aiId = (f: ProfileAIFinding, i: number) => f.id ?? `ai-${i}`;

const findings = (v: ProfileAIView | null | undefined): ProfileAIFinding[] => (v?.state === "done" ? v.findings : []);

/** The AI findings as profile checks (the marks of the edit panel). */
export function aiChecks(v: ProfileAIView | null | undefined): ProfileCheck[] {
  return findings(v).map((f, i) => ({ id: aiId(f, i), kind: f.kind, fields: f.fields, text: f.text }));
}

/** The AI findings as "Teyit edin" items (after the API's items). */
export function aiConfirms(v: ProfileAIView | null | undefined): ConfirmItem[] {
  return findings(v).map((f) => ({ text: f.text, question_id: null, choices: [] }));
}

/** W48: one finding = one white card in the row of the profile block; a colored stripe on the left
 * (amber: a conflict, grey: a question), the action at the bottom so the cards of a row line up. */
export const findingCard = (kind: ProfileCheck["kind"]) =>
  `flex flex-col gap-1.5 rounded-lg border border-l-4 border-gray-200 bg-white px-3 py-2.5 text-[13px] leading-snug text-[#344054] ${
    kind === "conflict" ? "border-l-[#F79009]" : "border-l-[#98A2B3]"
  }`;

/** W48: the soft label on top of a card: "Çelişki" (amber) or "Sorulacak" (grey). */
export function KindChip({ kind }: { kind: ProfileCheck["kind"] }) {
  const t = useT();
  return (
    <span
      className={`rounded px-1.5 py-px text-[11px] font-semibold ${
        kind === "conflict" ? "bg-[#FFFAEB] text-[#B54708]" : "bg-[#F2F4F7] text-[#475467]"
      }`}
    >
      {t(kind === "conflict" ? "pcConflict" : "pcConfirm")}
    </span>
  );
}

/** The AI findings in the profile block: the labels, the text, the quotes under it. */
export function AIFindings({ view, resolve }: { view: ProfileAIView | null | undefined; resolve?: ResolveProps }) {
  const t = useT();
  return (
    <>
      {findings(view).map((f, i) => (
        <li key={aiId(f, i)} data-testid="profile-check" data-kind={f.kind} className={findingCard(f.kind)}>
          <span data-testid="ai-finding" data-kind={f.kind} className="contents">
            <span className="flex flex-wrap gap-1.5">
              <KindChip kind={f.kind} />
              <span className="rounded bg-[#F4F3FF] px-1.5 py-px text-[11px] font-semibold text-[#6941C6]">{t("aiFound")}</span>
            </span>
            <span>{f.text}</span>
            {f.quotes.length > 0 && (
              <span className="flex flex-wrap gap-1.5 text-xs">
                {f.quotes.map((q, j) => (
                  <span key={j} data-testid="ai-quote" className="rounded border border-gray-200 bg-[#F9FAFB] px-1.5 py-px text-[#475467]">
                    {`${t(`f_${q.field as keyof Persona}` as LabelKey)}: “${q.text}”`}
                  </span>
                ))}
              </span>
            )}
          </span>
          {f.kind === "conflict" && (
            <div className="mt-auto">
              <Resolve id={aiId(f, i)} resolve={resolve} />
            </div>
          )}
        </li>
      ))}
    </>
  );
}

/** "AI kontrolü sürüyor…" while it runs; "AI kontrolü yapılamadı" with the reason when it failed. */
export function AIStatus({ view, className = "mt-2" }: { view: ProfileAIView | null | undefined; className?: string }) {
  const t = useT();
  if (view?.state !== "running" && view?.state !== "failed") return null;
  return (
    <p data-testid="ai-check-status" className={`${className} text-xs text-muted`}>
      {view.state === "running" ? t("aiRunning") : `${t("aiFailed")}${view.reason ? ` (${view.reason})` : ""}`}
    </p>
  );
}
