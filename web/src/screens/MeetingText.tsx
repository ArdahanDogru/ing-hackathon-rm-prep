// Meeting text as a document (docs/web-ui.md "Meeting text (A)"; mockup redesign-v4.html tab 5):
// one document column and a narrow right column.
import { useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { GlossaryTerm, NarrativeView, OptionView, RunView, SectionKey } from "../api/types";
import { snapshotDate } from "../components/BriefCard";
import { DocumentSection, SourceMark } from "../components/DocumentSection";
import { ErrorBox } from "../components/ErrorBox";
import { EvidencePopup } from "../components/EvidencePopup";
import { LifecycleTabs } from "../components/LifecycleTabs";
import { NotesBox, type SaveState } from "../components/NotesBox";
import { SourceList, type Source } from "../components/SourceList";
import { TermsBox } from "../components/TermsBox";
import { fmtPct } from "../format";
import { LangContext, useT } from "../i18n";
import { Markdown } from "../markdown";

const SAVE_DELAY_MS = 800;

/** A sentence of the document that may cite evidence (narrator sentence or decision talking point). */
interface Cited {
  text: string;
  title: string;
  evidence_ids: string[];
  option_ids: string[];
}

/** "Nurol Para Piyasası (TL)": the issuer's first word and the short name. */
const docName = (o: OptionView) => [o.issuer.split(" ")[0], o.short_label].filter(Boolean).join(" ");

function Collapsibles({ items }: { items: { key: SectionKey; label: string; texts: ReactNode[] }[] }) {
  const [open, setOpen] = useState<SectionKey | null>(null);
  const shown = items.filter((x) => x.texts.length > 0);
  if (!shown.length) return null;
  return (
    <div className="mt-2 border-t border-gray-100 pt-3">
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-[15px] text-muted">
        {shown.map((x) => (
          <button
            key={x.key}
            type="button"
            aria-expanded={open === x.key}
            aria-controls={`section-${x.key}`}
            className="hover:text-ink"
            onClick={() => setOpen(open === x.key ? null : x.key)}
          >
            {`${x.label}${x.key === "alternatifler" ? "" : ` (${x.texts.length})`} ${open === x.key ? "‹" : "›"}`}
          </button>
        ))}
      </div>
      {shown.map((x) => (
        <ul
          key={x.key}
          id={`section-${x.key}`}
          data-testid={`section-${x.key}`}
          hidden={open !== x.key}
          className="mt-3 list-disc space-y-1.5 pl-6 text-base leading-normal"
        >
          {x.texts.map((node, i) => (
            <li key={i}>{node}</li>
          ))}
        </ul>
      ))}
    </div>
  );
}

export function MeetingText({ view }: { view: RunView }) {
  const t = useT();
  const lang = useContext(LangContext);
  const r = view.result;
  const runId = r.run_id;

  const [draft, setDraft] = useState<NarrativeView | null>(null);
  const [draftMd, setDraftMd] = useState<string | null>(null); // the unedited draft's Markdown (API: draft_markdown)
  const [loadError, setLoadError] = useState<Error | null>(null);
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
        setDraftMd(d.draft_markdown ?? (d.status === "approved" ? null : d.markdown));
        api.glossary(lang, runId).then((x) => live && setTerms(x), () => live && setTerms([]));
      },
      (e: Error) => live && setLoadError(e),
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
      const text = edited ?? draft.draft_markdown ?? draft.markdown;
      const d = await api.approveNarrative(runId, lang, text);
      setDraft(d);
      setEdited(null); // the approved text (d.rm_text) is now the one shown
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  // --- the document's sentences, in display order, and their source numbers ---------
  const sentences = (key: SectionKey): Cited[] => draft?.sections.find((s) => s.key === key)?.sentences ?? [];
  const points: Cited[] = sentences("talking_points").length
    ? sentences("talking_points")
    : view.talking_points.map((p) => ({ text: p.text, title: p.label, evidence_ids: p.evidence_ids, option_ids: p.option_ids }));
  const selected = r.rm_selected.filter((id) => view.options[id]);
  const perOption = selected.map((id) => ({ id, sentences: sentences("oneriler").filter((s) => s.option_ids.includes(id)) }));
  const ordered = [
    ...sentences("ozet"),
    ...points,
    ...sentences("teklif_metni"),
    ...perOption.flatMap((o) => o.sentences),
    ...sentences("dikkat"),
    ...sentences("alternatifler"),
    ...sentences("sorular"),
    ...sentences("varsayimlar"),
  ];
  const date = snapshotDate(r.snapshot_id);
  const sources: Source[] = [];
  const numbers = new Map<string, number>();
  const keyOf = (c: Cited) => [...c.evidence_ids].sort().join("|");
  for (const c of ordered) {
    if (!c.evidence_ids.length || numbers.has(keyOf(c))) continue;
    const named = c.option_ids.map((id) => (view.options[id] ? docName(view.options[id]) : id.split(":")[1] ?? id));
    const anyFund = c.option_ids.some((id) => id.startsWith("fund:"));
    const where = named.length ? `${named.join(", ")} · ${anyFund ? "TEFAS" : "ING"}, ${date}` : `${t("dataSource")}, ${date}`;
    numbers.set(keyOf(c), sources.length + 1);
    sources.push({ n: sources.length + 1, label: where, evidenceIds: c.evidence_ids });
  }
  const mark = (c: Cited) => <SourceMark n={c.evidence_ids.length ? numbers.get(keyOf(c)) : undefined} />;
  const withMark = (c: Cited) => (
    <>
      {c.text}
      {mark(c)}
    </>
  );

  // Which text to show: the document for an unedited draft, else the Markdown.
  let markdown: { label: string; text: string } | null = null;
  if (edited !== null) markdown = { label: t("editedText"), text: edited };
  else if (draft?.status === "approved" && (draftMd === null || draft.rm_text.trim() !== draftMd.trim()))
    markdown = { label: draftMd === null ? t("statusApproved") : t("editedText"), text: draft.rm_text };

  const approved = draft?.status === "approved" && edited === null;
  const cost = draft ? draft.cost_usd.toLocaleString(lang === "TR" ? "tr-TR" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "";
  const modelLine = draft
    ? [draft.source === "template" ? t("templateText") : draft.model, draft.checks.length ? `${draft.checks.length} ${t("checkFindings")}` : t("checkPassed")]
    : [];

  const box = "mb-4 rounded-2xl bg-white px-5 py-[18px] shadow-sm";

  return (
    <div className="pb-10">
      <LifecycleTabs runId={runId} approved={r.rm_status === "approved"} active="text" />

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
        <ErrorBox error={loadError} onRetry={load} />
      ) : !draft ? (
        <p className="animate-pulse rounded-2xl bg-white p-6 text-base text-muted shadow-sm">{t("textPreparing")}</p>
      ) : (
        <div className="grid items-start gap-7 lg:grid-cols-[minmax(0,1fr)_300px]">
          {editing !== null ? (
            <div className="rounded-2xl bg-white p-5 shadow-sm">
              <textarea
                aria-label={t("markdown")}
                className="min-h-[520px] w-full rounded-xl border border-gray-300 p-4 font-mono text-[15px] leading-relaxed"
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
            <article data-testid="document" className="rounded-2xl bg-white px-10 py-[34px] text-[17px] leading-[1.7] shadow-sm">
              <div data-testid="doc-status" className="text-[13px] text-muted">
                {[approved ? `✓ ${t("statusApproved")}` : t("statusDraft"), ...modelLine].join(" · ")}
              </div>
              <h1 className="mb-[18px] mt-1.5 text-[26px] font-bold leading-snug">
                {`${t("meetingText")} — ${r.persona.profil}, ${r.persona.yas}`}
              </h1>

              {markdown ? (
                <>
                  <div className="mb-2 text-xs font-bold uppercase tracking-[0.06em] text-[#355FA1]">{markdown.label}</div>
                  <div className="max-w-[70ch]">
                    <Markdown text={markdown.text} />
                  </div>
                </>
              ) : (
                <>
                  <DocumentSection title={t("meetingAim")}>
                    <p className="max-w-[68ch]">
                      {sentences("ozet").map((c, i) => (
                        <span key={i}>
                          {i > 0 && " "}
                          {withMark(c)}
                        </span>
                      ))}
                    </p>
                  </DocumentSection>

                  <DocumentSection title={t("tpDoc")}>
                    <ul className="max-w-[68ch] space-y-2">
                      {points.map((c, i) => (
                        <li key={i}>
                          {c.title && <b>{`${c.title}. `}</b>}
                          {withMark(c)}
                        </li>
                      ))}
                    </ul>
                  </DocumentSection>

                  <DocumentSection title={t("scriptShort")}>
                    <blockquote
                      data-testid="script"
                      className="my-2 rounded-r-xl border-l-4 border-cobalt bg-[#F7F9FC] px-5 py-3.5 text-lg"
                    >
                      {sentences("teklif_metni").map((c, i) => (
                        <span key={i}>
                          {i > 0 && " "}
                          {withMark(c)}
                        </span>
                      ))}
                    </blockquote>
                  </DocumentSection>

                  <DocumentSection title={t("recommendations")}>
                    {perOption.map(({ id, sentences: own }, i) => {
                      const o = view.options[id];
                      const r1 = o.returns["1y"];
                      const facts = [
                        r1 ? fmtPct(r1.value) : null,
                        o.risk ? `${t("riskShort")} ${o.risk.level}/7` : null,
                        o.access.label ? o.access.label.toLocaleLowerCase(lang === "TR" ? "tr" : "en") : null,
                      ].filter(Boolean);
                      return (
                        <div key={id} data-testid="doc-option" className="mb-5" title={o.label}>
                          <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1">
                            <b>{`${i + 1} · ${docName(o)}`}</b>
                            <span className="text-muted">{facts.join(" · ")}</span>
                            {(draft.need_tags[id] ?? []).map((tag) => (
                              <span key={tag} className="rounded-full bg-[#EEF2F9] px-[11px] py-1 text-[13px] leading-none text-[#2C4F8F]">
                                {tag}
                              </span>
                            ))}
                          </div>
                          {own.map((c, k) => (
                            <p key={k} className="mt-1 max-w-[68ch]">
                              {withMark(c)}
                            </p>
                          ))}
                          <textarea
                            rows={2}
                            aria-label={`${t("myNote")}: ${docName(o)}`}
                            placeholder={t("optionNote")}
                            className="mt-2 w-full max-w-[68ch] resize-y rounded-xl border border-dashed border-[#C7D2E5] bg-[#FBFCFE] px-3.5 py-2 text-[15px] leading-normal focus:border-solid"
                            value={optionNotes[id] ?? ""}
                            onChange={(e) => editOptionNote(id, e.target.value)}
                          />
                        </div>
                      );
                    })}
                  </DocumentSection>

                  <DocumentSection title={t("attention")}>
                    <ul className="max-w-[68ch] space-y-1.5">
                      {sentences("dikkat").map((c, i) => (
                        <li key={i}>{withMark(c)}</li>
                      ))}
                    </ul>
                  </DocumentSection>

                  <Collapsibles
                    items={[
                      { key: "alternatifler", label: t("otherOptions"), texts: sentences("alternatifler").map(withMark) },
                      { key: "sorular", label: t("questionsToAsk"), texts: sentences("sorular").map(withMark) },
                      { key: "varsayimlar", label: t("assumptions"), texts: sentences("varsayimlar").map(withMark) },
                    ]}
                  />
                </>
              )}
            </article>
          )}

          <aside>
            {/* the actions first: the column is long with the glossary */}
            <div className="mb-4 flex flex-wrap gap-2.5">
              {editing === null && (
                <button
                  type="button"
                  className="rounded-xl border border-catgrey bg-white px-[18px] py-[11px] font-semibold"
                  onClick={() => setEditing(edited ?? (draft.status === "approved" ? draft.rm_text : draft.markdown))}
                >
                  {t("edit")}
                </button>
              )}
              {!approved && (
                <button type="button" className="rounded-xl bg-brand px-[22px] py-3 font-bold text-white" onClick={approveText}>
                  {t("approveText")}
                </button>
              )}
            </div>
            <div className="mb-4 rounded-2xl shadow-sm">
              <NotesBox value={note} onChange={editNote} state={saveState} />
            </div>
            <section data-testid="rm-notes" className={box}>
              <h3 className="font-bold">
                <span className="text-[#B54708]">{t("rmNote")}</span>
                {` · ${t("onlyForYou")}`}
              </h3>
              <ul className="mt-2 space-y-2 text-sm leading-normal text-[#344054]">
                {view.rm_warnings.map((w) => (
                  <li key={w.code + w.message}>{w.message}</li>
                ))}
              </ul>
            </section>
            {!markdown && editing === null && <SourceList sources={sources} onEvidence={setEvidenceId} />}
            <TermsBox terms={terms} />
            <section className={box}>
              <h3 className="mb-1 font-bold">{t("card")}</h3>
              <Link
                to={`/print/${encodeURIComponent(runId)}`}
                target="_blank"
                className="flex items-center gap-2 border-t border-gray-100 py-2.5 text-[15px] font-semibold text-[#2C4F8F]"
              >
                {`⤓ ${t("pdfDownload")}`}
              </Link>
              <a
                href={api.cardUrl(runId, lang)}
                download={`${runId}.md`}
                className="flex items-center gap-2 border-t border-gray-100 py-2.5 text-[15px] font-semibold text-[#2C4F8F]"
              >
                {`⤓ ${t("mdDownload")}`}
              </a>
              <div data-testid="card-footer" className="mt-1 text-[13px] text-muted">
                {[...modelLine, `$${cost}`].join(" · ")}
              </div>
            </section>
          </aside>
        </div>
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
