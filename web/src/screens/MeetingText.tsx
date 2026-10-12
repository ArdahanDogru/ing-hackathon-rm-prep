// Meeting text as a document (docs/web-ui.md "Meeting text (A)"; mockup redesign-v4.html tab 5)
// with section-by-section editing ("Section-by-section editing of the meeting text").
import { useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { GlossaryTerm, NarrativeView, OptionView, RunView, SectionKey } from "../api/types";
import { BlockEditor } from "../components/BlockEditor";
import { snapshotDate } from "../components/BriefCard";
import { DocumentSection, SourceMark } from "../components/DocumentSection";
import { ErrorBox } from "../components/ErrorBox";
import { EvidencePopup } from "../components/EvidencePopup";
import { FindingList, isBlocking } from "../components/FindingList";
import { LifecycleTabs } from "../components/LifecycleTabs";
import { NotesBox, type SaveState } from "../components/NotesBox";
import { SourceList, type Source } from "../components/SourceList";
import { TermsBox } from "../components/TermsBox";
import { fmtDateTime, fmtPct } from "../format";
import { LangContext, useT } from "../i18n";
import { Markdown } from "../markdown";

const SAVE_DELAY_MS = 800;
/** Blocks shown as lists: an edit is one item per line. */
const LIST_BLOCKS = new Set(["dikkat", "alternatifler", "sorular", "varsayimlar"]);

/** A sentence of the document that may cite evidence (narrator sentence or decision talking point). */
interface Cited {
  text: string;
  title: string;
  evidence_ids: string[];
  option_ids: string[];
}

/** "Nurol Para Piyasası (TL)": the issuer's first word and the short name. */
const docName = (o: OptionView) => [o.issuer.split(" ")[0], o.short_label].filter(Boolean).join(" ");

/** An edited block as plain text: list blocks one item per line, else paragraphs. */
function EditedText({ text, list }: { text: string; list: boolean }) {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  return list ? (
    <ul className="max-w-[68ch] list-disc space-y-1.5 pl-6">
      {lines.map((l, i) => (
        <li key={i}>{l}</li>
      ))}
    </ul>
  ) : (
    <div className="max-w-[68ch]">
      {lines.map((l, i) => (
        <p key={i} className={i ? "mt-2" : ""}>
          {l}
        </p>
      ))}
    </div>
  );
}

function Collapsibles({ items }: { items: { key: SectionKey; label: string; count: number; body: ReactNode }[] }) {
  const [open, setOpen] = useState<SectionKey | null>(null);
  const shown = items.filter((x) => x.count > 0);
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
            {`${x.label}${x.key === "alternatifler" ? "" : ` (${x.count})`} ${open === x.key ? "‹" : "›"}`}
          </button>
        ))}
      </div>
      {shown.map((x) => (
        <div key={x.key} id={`section-${x.key}`} data-testid={`section-${x.key}`} hidden={open !== x.key} className="mt-3 text-base">
          {x.body}
        </div>
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
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [openBlock, setOpenBlock] = useState<string | null>(null);
  const [blockError, setBlockError] = useState<string | null>(null);
  const [blockBusy, setBlockBusy] = useState(false);

  const load = useCallback(() => {
    let live = true;
    setDraft(null);
    setLoadError(null);
    setOpenBlock(null);
    api.narrative(runId, lang).then(
      (d) => {
        if (!live) return;
        setDraft(d);
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

  /** Save a block (text) or restore its original (null); the server answers with the whole view. */
  const sendBlock = async (blockId: string, text: string | null) => {
    setBlockBusy(true);
    setBlockError(null);
    setActionError(null);
    try {
      setDraft(await api.editBlock(runId, lang, blockId, text));
      setOpenBlock(null);
    } catch (e) {
      if (text === null) setActionError((e as Error).message);
      else setBlockError((e as Error).message);
    } finally {
      setBlockBusy(false);
    }
  };

  const approveText = async () => {
    if (!draft) return;
    setActionError(null);
    try {
      // the server composes the Markdown with the edits; it refuses while a blocking finding is open
      setDraft(await api.approveNarrative(runId, lang, draft.markdown));
      setOpenBlock(null);
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  // --- blocks and sentences ------------------------------------------------------------
  const edits = draft?.rm_edits ?? {};
  const checks = draft?.edit_checks ?? {};
  const sentences = (key: SectionKey): Cited[] => draft?.sections.find((s) => s.key === key)?.sentences ?? [];
  const tpFromNarrator = sentences("talking_points").length > 0;
  const points: Cited[] = tpFromNarrator
    ? sentences("talking_points")
    : view.talking_points.map((p) => ({ text: p.text, title: p.label, evidence_ids: p.evidence_ids, option_ids: p.option_ids }));
  const selected = r.rm_selected.filter((id) => view.options[id]);
  // a recommendation sentence belongs to the block of its first option (oneriler:<option_ids[0]>)
  const perOption = selected.map((id) => ({ id, sentences: sentences("oneriler").filter((s) => s.option_ids[0] === id) }));
  const approved = draft?.status === "approved";
  const editable = !!draft && !approved;

  // source numbers: every cited sentence, in document order, without the sentences of edited blocks
  const live = (block: string, cs: Cited[]) => (block in edits ? [] : cs);
  const ordered = [
    ...live("ozet", sentences("ozet")),
    ...points.flatMap((c, i) => (tpFromNarrator ? live(`talking_points:${i}`, [c]) : [c])),
    ...live("teklif_metni", sentences("teklif_metni")),
    ...perOption.flatMap((o) => live(`oneriler:${o.id}`, o.sentences)),
    ...live("dikkat", sentences("dikkat")),
    ...live("alternatifler", sentences("alternatifler")),
    ...live("sorular", sentences("sorular")),
    ...live("varsayimlar", sentences("varsayimlar")),
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
  const withMark = (c: Cited) => (
    <>
      {c.text}
      <SourceMark n={c.evidence_ids.length ? numbers.get(keyOf(c)) : undefined} />
    </>
  );

  /** One editable block: its content (or the edit), a pencil, "düzenlendi" + "Orijinale dön", findings. */
  const block = (id: string, title: string, original: Cited[], content: ReactNode, prefix?: ReactNode) => {
    const list = LIST_BLOCKS.has(id);
    const edited = edits[id];
    if (openBlock === id)
      return (
        <BlockEditor
          label={title}
          initial={edited ?? original.map((c) => c.text).join(list ? "\n" : " ")}
          error={blockError}
          busy={blockBusy}
          onSave={(text) => sendBlock(id, text)}
          onCancel={() => {
            setOpenBlock(null);
            setBlockError(null);
          }}
        />
      );
    return (
      <div data-block={id} className="group relative pr-9">
        {edited !== undefined ? (
          <>
            {prefix}
            <EditedText text={edited} list={list} />
          </>
        ) : (
          content
        )}
        {editable && (
          <button
            type="button"
            aria-label={`${title} ${t("editBlock")}`}
            title={`${title} ${t("editBlock")}`}
            className="absolute right-0 top-0 rounded-lg px-2 py-0.5 text-muted opacity-60 hover:bg-gray-100 hover:text-ink hover:opacity-100 focus:opacity-100 group-hover:opacity-100"
            onClick={() => {
              setBlockError(null);
              setOpenBlock(id);
            }}
          >
            ✎
          </button>
        )}
        {edited !== undefined && (
          <div className="mt-1 flex flex-wrap items-center gap-3 text-[13px]">
            <span className="rounded-full bg-[#EEF2F9] px-2 py-0.5 font-semibold text-cobalt">{t("blockEdited")}</span>
            {editable && (
              <button type="button" className="text-[#355FA1] underline" disabled={blockBusy} onClick={() => sendBlock(id, null)}>
                {t("restoreBlock")}
              </button>
            )}
          </div>
        )}
        <FindingList findings={checks[id] ?? []} />
      </div>
    );
  };

  // Markdown only for a text approved with a whole-text edit (before block editing).
  let markdown: { label: string; text: string } | null = null;
  if (approved && !Object.keys(edits).length && draft.rm_text.trim() !== (draft.draft_markdown ?? draft.rm_text).trim())
    markdown = { label: t("editedText"), text: draft.rm_text };

  const blocking = Object.values(checks).some((fs) => fs.some(isBlocking));
  const cost = draft ? draft.cost_usd.toLocaleString(lang === "TR" ? "tr-TR" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "";
  const modelLine = draft
    ? [draft.source === "template" ? t("templateText") : draft.model, draft.checks.length ? `${draft.checks.length} ${t("checkFindings")}` : t("checkPassed")]
    : [];
  const box = "mb-4 rounded-2xl bg-white px-5 py-[18px] shadow-sm";
  const listOf = (cs: Cited[]) => (
    <ul className="max-w-[68ch] list-disc space-y-1.5 pl-6">
      {cs.map((c, i) => (
        <li key={i}>{withMark(c)}</li>
      ))}
    </ul>
  );
  const prose = (cs: Cited[]) =>
    cs.map((c, i) => (
      <span key={i}>
        {i > 0 && " "}
        {withMark(c)}
      </span>
    ));

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
          <article data-testid="document" className="rounded-2xl bg-white px-10 py-[34px] text-[17px] leading-[1.7] shadow-sm">
            <div data-testid="doc-status" className="text-[13px] text-muted">
              {[
                approved
                  ? `✓ ${t("statusApproved")}${draft.approved_at ? `: ${fmtDateTime(draft.approved_at)}` : ""}`
                  : t("statusDraft"),
                ...modelLine,
              ].join(" · ")}
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
                  {block("ozet", t("meetingAim"), sentences("ozet"), <p className="max-w-[68ch]">{prose(sentences("ozet"))}</p>)}
                </DocumentSection>

                <DocumentSection title={t("tpDoc")}>
                  <ul className="max-w-[68ch] space-y-2">
                    {points.map((c, i) => {
                      const title = c.title ? <b>{`${c.title}. `}</b> : null;
                      const body = (
                        <>
                          {title}
                          {withMark(c)}
                        </>
                      );
                      return (
                        <li key={i}>
                          {tpFromNarrator ? block(`talking_points:${i}`, `${t("tpDoc")} ${i + 1}`, [c], body, title) : body}
                        </li>
                      );
                    })}
                  </ul>
                </DocumentSection>

                <DocumentSection title={t("scriptShort")}>
                  <blockquote data-testid="script" className="my-2 rounded-r-xl border-l-4 border-cobalt bg-[#F7F9FC] px-5 py-3.5 text-lg">
                    {block("teklif_metni", t("scriptShort"), sentences("teklif_metni"), <div>{prose(sentences("teklif_metni"))}</div>)}
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
                        {block(
                          `oneriler:${id}`,
                          docName(o),
                          own,
                          own.map((c, k) => (
                            <p key={k} className="mt-1 max-w-[68ch]">
                              {withMark(c)}
                            </p>
                          )),
                        )}
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
                  {block("dikkat", t("attention"), sentences("dikkat"), listOf(sentences("dikkat")))}
                </DocumentSection>

                <Collapsibles
                  items={(
                    [
                      ["alternatifler", t("otherOptions")],
                      ["sorular", t("questionsToAsk")],
                      ["varsayimlar", t("assumptions")],
                    ] as const
                  ).map(([key, label]) => ({
                    key,
                    label,
                    count: sentences(key).length,
                    body: block(key, label, sentences(key), listOf(sentences(key))),
                  }))}
                />
              </>
            )}
          </article>

          <aside>
            {/* the action first: the column is long with the glossary */}
            {!approved && (
              <div className="mb-4">
                <button
                  type="button"
                  disabled={blocking}
                  className="rounded-xl bg-brand px-[22px] py-3 font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={approveText}
                >
                  {t("approveText")}
                </button>
                {blocking && (
                  <p data-testid="approve-reason" className="mt-2 text-sm text-[#B42318]">
                    {t("approveBlocked")}
                  </p>
                )}
              </div>
            )}
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
            {!markdown && <SourceList sources={sources} onEvidence={setEvidenceId} />}
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
