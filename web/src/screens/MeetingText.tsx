// "Görüşme hazırlığı" view (docs/web-ui.md "Meeting text" and section 5; mockup meeting-text-v9.html).
import { useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { GlossaryTerm, NarrativeView, RunView, SectionKey } from "../api/types";
import { EvidencePopup } from "../components/EvidencePopup";
import { HeaderCard, type HeaderPoint } from "../components/HeaderCard";
import { NotesBox, type SaveState } from "../components/NotesBox";
import { RecommendationCard } from "../components/RecommendationCard";
import { TermsBox } from "../components/TermsBox";
import { LangContext, useT } from "../i18n";
import { Markdown } from "../markdown";

const SAVE_DELAY_MS = 800;

function Collapsed({ label, items }: { label: string; items: string[] }) {
  const [open, setOpen] = useState(false);
  if (!items.length) return null;
  return (
    <div className="border-t border-gray-100">
      <button
        type="button"
        aria-expanded={open}
        className="flex w-full items-center justify-between py-3 text-left text-base text-[#475467]"
        onClick={() => setOpen(!open)}
      >
        <span>{`${label} · ${items.length}`}</span>
        <span>{open ? "‹" : "›"}</span>
      </button>
      {open && (
        <ul className="list-disc space-y-1.5 pb-3 pl-6 text-base leading-normal">
          {items.map((x, i) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SectionHead({ icon, tone, children }: { icon: string; tone: "blue" | "amber"; children: ReactNode }) {
  const c = tone === "blue" ? "bg-[#EEF2F9] text-[#355FA1]" : "bg-[#FFFAEB] text-[#B54708]";
  return (
    <h2 className="mb-3.5 mt-1.5 flex items-center gap-2.5 text-[22px] font-bold">
      <span aria-hidden="true" className={`flex h-[34px] w-[34px] items-center justify-center rounded-[10px] text-[17px] ${c}`}>
        {icon}
      </span>
      {children}
    </h2>
  );
}

export function MeetingText({ view }: { view: RunView }) {
  const t = useT();
  const lang = useContext(LangContext);
  const r = view.result;
  const runId = r.run_id;

  const [draft, setDraft] = useState<NarrativeView | null>(null);
  const [draftMd, setDraftMd] = useState<string | null>(null); // the unedited draft's Markdown
  const [loadError, setLoadError] = useState<string | null>(null);
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [edited, setEdited] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);

  const load = useCallback(() => {
    let live = true;
    setDraft(null);
    setLoadError(null);
    setEdited(null);
    setEditing(null);
    api.narrative(runId, lang).then(
      (d) => {
        if (!live) return;
        setDraft(d);
        setDraftMd(d.status === "approved" ? null : d.markdown);
        api.glossary(lang, runId).then((x) => live && setTerms(x), () => live && setTerms([]));
      },
      (e: Error) => live && setLoadError(e.message),
    );
    return () => {
      live = false;
    };
  }, [runId, lang]);
  useEffect(load, [load]);

  // RM notes: saved SAVE_DELAY_MS after the last keystroke.
  const [note, setNote] = useState(r.rm_note);
  const [optionNotes, setOptionNotes] = useState<Record<string, string>>(r.rm_option_notes);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const changed = useRef(false);
  useEffect(() => {
    if (!changed.current) return;
    const timer = setTimeout(() => {
      setSaveState("saving");
      const filled = Object.fromEntries(Object.entries(optionNotes).filter(([, v]) => v.trim()));
      api.notes(runId, note, filled).then(
        () => setSaveState("saved"),
        (e: Error) => setSaveState({ error: e.message }),
      );
    }, SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [runId, note, optionNotes]);
  const editNote = (v: string) => {
    changed.current = true;
    setNote(v);
  };
  const editOptionNote = (id: string, v: string) => {
    changed.current = true;
    setOptionNotes((n) => ({ ...n, [id]: v }));
  };

  const approveText = async () => {
    if (!draft) return;
    setActionError(null);
    try {
      const text = edited ?? draft.markdown;
      const d = await api.approveNarrative(runId, lang, text);
      setDraft(d);
      setEdited(null); // the approved text (d.rm_text) is now the one shown
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  const sentences = (key: SectionKey) => draft?.sections.find((s) => s.key === key)?.sentences ?? [];
  const texts = (key: SectionKey) => sentences(key).map((s) => s.text);

  // Which text to show: the cards for an unedited draft, else the Markdown.
  let markdown: { label: string; text: string } | null = null;
  if (edited !== null) markdown = { label: t("editedText"), text: edited };
  else if (draft?.status === "approved" && (draftMd === null || draft.rm_text.trim() !== draftMd.trim()))
    markdown = { label: draftMd === null ? t("statusApproved") : t("editedText"), text: draft.rm_text };

  const approved = draft?.status === "approved" && edited === null;
  const points: HeaderPoint[] = sentences("talking_points").length
    ? sentences("talking_points").map((s) => ({ title: s.title, text: s.text }))
    : view.talking_points.map((p) => ({ title: p.label, text: p.text }));
  const cost = draft ? draft.cost_usd.toLocaleString(lang === "TR" ? "tr-TR" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "";

  return (
    <div className="pb-10">
      <div className="mb-5 flex flex-wrap items-center gap-3.5">
        <h1 className="text-[26px] font-bold">{t("meetingText")}</h1>
        {draft && (
          <span
            className={
              approved
                ? "rounded-full bg-[#ECFDF3] px-3 py-1 text-[13px] font-semibold text-[#067647]"
                : "rounded-full bg-[#FFFAEB] px-3 py-1 text-[13px] font-semibold text-[#B54708]"
            }
          >
            {approved ? `✓ ${t("statusApproved")}` : t("statusDraft")}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2.5">
          <Link to="/" className="text-sm underline">
            {t("backToDashboard")}
          </Link>
          {draft && editing === null && (
            <button
              type="button"
              className="rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-base font-semibold text-[#344054]"
              onClick={() => setEditing(edited ?? (draft.status === "approved" ? draft.rm_text : draft.markdown))}
            >
              {t("edit")}
            </button>
          )}
          {draft && !approved && (
            <button type="button" className="rounded-xl bg-brand px-5 py-2.5 text-base font-semibold text-white" onClick={approveText}>
              {t("approveText")}
            </button>
          )}
        </div>
      </div>

      {actionError && (
        <p role="alert" className="mb-4 rounded-xl border border-red-200 bg-white p-3 text-sm">
          {`${t("errorTitle")}: ${actionError}`}
        </p>
      )}
      {draft?.source === "template" && (
        <p role="status" className="mb-4 rounded-xl border border-[#FEC84B] bg-[#FFFAEB] px-4 py-3 text-[15px]">
          {t("templateBanner")}
        </p>
      )}

      {loadError ? (
        <div role="alert" className="rounded-xl border border-red-200 bg-white p-4 text-sm">
          <b>{t("errorTitle")}:</b> {loadError}{" "}
          <button type="button" className="ml-2 underline" onClick={load}>
            {t("retry")}
          </button>
        </div>
      ) : !draft ? (
        <p className="animate-pulse rounded-2xl bg-white p-6 text-base text-muted shadow-sm">{t("textPreparing")}</p>
      ) : editing !== null ? (
        <div className="rounded-[18px] bg-white p-5 shadow-sm">
          <textarea
            aria-label={t("markdown")}
            className="min-h-[480px] w-full rounded-xl border border-gray-300 p-4 font-mono text-[15px] leading-relaxed"
            value={editing}
            onChange={(e) => setEditing(e.target.value)}
          />
          <div className="mt-3 flex justify-end gap-2">
            <button type="button" className="rounded-xl border border-gray-300 px-4 py-2 font-semibold" onClick={() => setEditing(null)}>
              {t("cancel")}
            </button>
            <button
              type="button"
              className="rounded-xl bg-ink px-4 py-2 font-semibold text-white"
              onClick={() => {
                setEdited(editing);
                setEditing(null);
              }}
            >
              {t("save")}
            </button>
          </div>
        </div>
      ) : (
        <>
          {markdown ? (
            <section className="mb-6 rounded-[18px] bg-white px-8 py-6 text-[17px] leading-relaxed shadow-sm">
              <div className="mb-2 text-[13px] font-bold uppercase tracking-[0.06em] text-[#355FA1]">{markdown.label}</div>
              <div className="max-w-[70ch]">
                <Markdown text={markdown.text} />
              </div>
            </section>
          ) : (
            <div data-testid="client-part">
              <HeaderCard
                persona={r.persona}
                aim={texts("ozet").join(" ")}
                points={points}
                script={texts("teklif_metni").join(" ")}
                notes={<NotesBox value={note} onChange={editNote} state={saveState} />}
              />
            </div>
          )}

          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
            <div>
              {markdown ? (
                <section className="mb-6 max-w-xl">
                  <NotesBox value={note} onChange={editNote} state={saveState} />
                </section>
              ) : (
                <div data-testid="client-part-2">
                  <SectionHead icon="★" tone="blue">
                    {t("recommendations")}
                  </SectionHead>
                  {r.rm_selected.map((id, i) =>
                    view.options[id] ? (
                      <RecommendationCard
                        key={id}
                        option={view.options[id]}
                        position={i + 1}
                        sentences={sentences("oneriler").filter((s) => s.option_ids.includes(id))}
                        tags={draft.need_tags[id] ?? []}
                        note={optionNotes[id] ?? ""}
                        onNote={(v) => editOptionNote(id, v)}
                        onEvidence={setEvidenceId}
                      />
                    ) : null,
                  )}

                  <SectionHead icon="!" tone="amber">
                    {t("attention")}
                  </SectionHead>
                  <section data-testid="dikkat" className="mb-4 rounded-[18px] bg-white px-6 py-4 shadow-sm">
                    <ul>
                      {texts("dikkat").map((x, i) => (
                        <li key={i} className="flex items-start gap-3.5 border-t border-gray-100 py-3 text-[17px] leading-normal first:border-t-0">
                          <span
                            aria-hidden="true"
                            className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-[#FEF3F2] text-sm font-bold text-[#B42318]"
                          >
                            !
                          </span>
                          <span>{x}</span>
                        </li>
                      ))}
                    </ul>
                    <Collapsed label={t("otherOptions")} items={texts("alternatifler")} />
                    <Collapsed label={t("questionsToAsk")} items={texts("sorular")} />
                    <Collapsed label={t("assumptions")} items={texts("varsayimlar")} />
                  </section>
                </div>
              )}

              <section data-testid="rm-notes" className="rounded-[18px] bg-white px-6 py-5 shadow-sm">
                <h2 className="flex items-center gap-2 text-[17px] font-bold">
                  {t("rmNotes")}
                  <span className="rounded-full bg-[#F2F4F7] px-2 py-0.5 text-xs font-semibold text-[#475467]">{t("onlyForYou")}</span>
                </h2>
                <ul className="mt-2 space-y-2 text-base leading-normal text-[#344054]">
                  {view.rm_warnings.map((w) => (
                    <li key={w.code + w.message}>{w.message}</li>
                  ))}
                </ul>
              </section>
            </div>

            <div>
              <TermsBox terms={terms} />
              <section className="rounded-[18px] bg-white px-5 py-5 shadow-sm">
                <h3 className="mb-1 text-[17px] font-semibold">{t("card")}</h3>
                <Link
                  to={`/print/${encodeURIComponent(runId)}`}
                  target="_blank"
                  className="flex items-center gap-2 border-t border-gray-100 py-3 text-base font-semibold text-[#2C4F8F]"
                >
                  {`⤓ ${t("pdfDownload")}`}
                </Link>
                <a
                  href={api.cardUrl(runId, lang)}
                  download={`${runId}.md`}
                  className="flex items-center gap-2 border-t border-gray-100 py-3 text-base font-semibold text-[#2C4F8F]"
                >
                  {`⤓ ${t("mdDownload")}`}
                </a>
                <div data-testid="card-footer" className="mt-2 text-[13px] text-muted">
                  {[
                    draft.source === "template" ? t("templateText") : draft.model,
                    draft.checks.length ? `${draft.checks.length} ${t("checkFindings")}` : t("checkPassed"),
                    `$${cost}`,
                  ].join(" · ")}
                </div>
              </section>
            </div>
          </div>
        </>
      )}

      <EvidencePopup
        snapshotId={r.snapshot_id}
        evidenceId={evidenceId ?? ""}
        open={evidenceId !== null}
        onClose={() => setEvidenceId(null)}
      />
    </div>
  );
}
