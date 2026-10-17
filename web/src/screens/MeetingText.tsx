// Meeting text (docs/web-ui.md "Meeting text (A)", W27 and W28): one page, the client
// presentation with the RM's help in yellow boxes, and section-by-section editing
// ("Section-by-section editing of the meeting text").
import { useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { NarrativeView, OptionKind, OptionView, RunView, SectionKey } from "../api/types";
import { BlockEditor } from "../components/BlockEditor";
import { ClientPresentation, RmNote, restatesFacts, withoutName, type BlockOpts, type SectionId } from "../components/ClientPresentation";
import { snapshotDate } from "../components/BriefCard";
import { SourceMark } from "../components/DocumentSection";
import { ErrorBox } from "../components/ErrorBox";
import { EvidencePopup } from "../components/EvidencePopup";
import { FindingList, isBlocking } from "../components/FindingList";
import { sourceName } from "../components/KindBadge";
import { LifecycleTabs } from "../components/LifecycleTabs";
import { NarrativeProgress } from "../components/NarrativeProgress";
import { NotesBox, type SaveState } from "../components/NotesBox";
import { SourceList, type Source } from "../components/SourceList";
import { fmtDateTime } from "../format";
import { LangContext, useT } from "../i18n";
import { Markdown } from "../markdown";
import { withCode } from "../product";
import { profileChanges } from "../profileChanges";

const SAVE_DELAY_MS = 800;
/** W47: the deleted sections of a run, kept in this browser (the API has no place for them). */
const sectionsKey = (runId: string) => `rmprep.hiddenSections.${runId}`;
function readSections(runId: string): SectionId[] {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(sectionsKey(runId)) ?? "[]");
    return Array.isArray(v) ? (v.filter((x) => typeof x === "string") as SectionId[]) : [];
  } catch {
    return [];
  }
}
const HIGHLIGHT_MS = 2000;

/** A sentence of the document that may cite evidence (narrator sentence or decision talking point). */
interface Cited {
  text: string;
  title: string;
  evidence_ids: string[];
  option_ids: string[];
}

/** "Nurol Para Piyasası (TL)": the issuer's first word and the short name. */
const docName = (o: OptionView) => [o.issuer.split(" ")[0], o.short_label].filter(Boolean).join(" ");

/** Short points, not paragraphs (W29): several items as bullets, one item as a line. */
function Bullets({ items }: { items: ReactNode[] }) {
  if (items.length === 1) return <p className="m-0 max-w-[68ch]">{items[0]}</p>;
  return (
    <ul className="m-0 max-w-[68ch] list-disc space-y-1 pl-5">
      {items.map((x, i) => (
        <li key={i}>{x}</li>
      ))}
    </ul>
  );
}

/** An edited block as plain text: one point per line. */
function EditedText({ text }: { text: string }) {
  return <Bullets items={text.split("\n").map((l) => l.trim()).filter(Boolean)} />;
}

export function MeetingText({ view }: { view: RunView }) {
  const t = useT();
  const lang = useContext(LangContext);
  const r = view.result;
  const runId = r.run_id;

  const [draft, setDraft] = useState<NarrativeView | null>(null);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<number | null>(null);
  useEffect(() => {
    if (highlight === null) return;
    const timer = setTimeout(() => setHighlight(null), HIGHLIGHT_MS);
    return () => clearTimeout(timer);
  }, [highlight]);
  const [openBlock, setOpenBlock] = useState<string | null>(null);
  const [blockError, setBlockError] = useState<string | null>(null);
  const [blockBusy, setBlockBusy] = useState(false);
  /** "Sunum görünümü": the page as the client sees it (and as it prints), without the RM's help */
  const [preview, setPreview] = useState(false);
  const [hiddenSections, setHiddenSections] = useState<SectionId[]>(() => readSections(runId));
  const toggleSection = (id: SectionId, hide: boolean) => {
    const next = hide ? [...new Set([...hiddenSections, id])] : hiddenSections.filter((x) => x !== id);
    setHiddenSections(next);
    try {
      localStorage.setItem(sectionsKey(runId), JSON.stringify(next));
    } catch {
      // no storage (a private window): the deletion holds until the page is left
    }
  };

  const load = useCallback(() => {
    let live = true;
    setDraft(null);
    setLoadError(null);
    setOpenBlock(null);
    api.narrative(runId, lang).then(
      (d) => live && setDraft(d),
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
      // an error of the open editor stays in it; restore and delete errors go above the document
      if (openBlock === blockId) setBlockError((e as Error).message);
      else setActionError((e as Error).message);
    } finally {
      setBlockBusy(false);
    }
  };

  /** "Bölümü sil": delete the blocks one by one ({text: ""} each). */
  const deleteBlocks = async (blockIds: string[]) => {
    setBlockBusy(true);
    setActionError(null);
    try {
      for (const id of blockIds) setDraft(await api.editBlock(runId, lang, id, ""));
      setOpenBlock(null);
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBlockBusy(false);
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
  // W31: without the sentence that only restates the card's labels (real, nominal, risk)
  const perOption = selected.map((id) => ({
    id,
    sentences: sentences("oneriler").filter((s) => s.option_ids[0] === id && !restatesFacts(s.text, view.options[id])),
  }));
  const approved = draft?.status === "approved";
  const editable = !!draft && !approved;
  /** rm_edits[block] === "": the block is deleted (v1.9). */
  const gone = (block: string) => edits[block] === "";
  /** An approved text leaves out a section whose blocks are all deleted. */
  const hidden = (blocks: string[]) => approved && blocks.length > 0 && blocks.every(gone);
  const tpBlocks = tpFromNarrator ? points.map((_, i) => `talking_points:${i}`) : [];

  // source numbers: every cited sentence, in document order, without the sentences of edited blocks
  const live = (block: string, cs: Cited[]) => (block in edits ? [] : cs);
  const ordered = [
    ...live("teklif_metni", sentences("teklif_metni")),
    ...live("ozet", sentences("ozet")),
    ...live("piyasa_notu", sentences("piyasa_notu")),
    ...points.flatMap((c, i) => (tpFromNarrator ? live(`talking_points:${i}`, [c]) : [c])),
    ...perOption.flatMap((o) => live(`oneriler:${o.id}`, o.sentences)),
    ...live("alternatifler", sentences("alternatifler")),
    ...live("dikkat", sentences("dikkat")),
    ...live("varsayimlar", sentences("varsayimlar")),
    ...live("sorular", sentences("sorular")),
  ];
  const date = snapshotDate(r.snapshot_id);
  const sources: Source[] = [];
  const numbers = new Map<string, number>();
  const keyOf = (c: Cited) => [...c.evidence_ids].sort().join("|");
  for (const c of ordered) {
    if (!c.evidence_ids.length || numbers.has(keyOf(c))) continue;
    const named = c.option_ids.map((id) => withCode(id, view.options[id] ? docName(view.options[id]) : id.split(":")[1] ?? id));
    // the data sources of the options: TEFAS (funds, ETFs), Borsa İstanbul (shares), else ING
    const kinds = c.option_ids.map((id) => view.options[id]?.kind ?? (id.split(":")[0] as OptionKind));
    const from = [...new Set(kinds.map(sourceName))].filter((x) => x !== "ING").join(", ") || "ING";
    const where = named.length ? `${named.join(", ")} · ${from}, ${date}` : `${t("dataSource")}, ${date}`;
    numbers.set(keyOf(c), sources.length + 1);
    sources.push({ n: sources.length + 1, label: where, evidenceIds: c.evidence_ids });
  }
  const withMark = (c: Cited) => (
    <>
      {c.text}
      <SourceMark
        n={c.evidence_ids.length ? numbers.get(keyOf(c)) : undefined}
        label={t("sourceMark")}
        onOpen={() => {
          setEvidenceId(c.evidence_ids[0]);
          setHighlight(numbers.get(keyOf(c)) ?? null);
        }}
      />
    </>
  );

  /** One editable block: its content (or the edit), a pencil, "düzenlendi" + "Orijinale dön", findings. */
  const block = (id: string, title: string, original: Cited[], content: ReactNode, prefix?: ReactNode, opts: BlockOpts = {}) => {
    // the client view shows no marks: no edit controls, badges, findings or deleted lines
    const marks = !preview;
    const controls = editable && marks;
    const edited = edits[id];
    if (gone(id))
      return approved || !marks ? null : (
        <div data-testid="deleted-block" data-block={id} className="my-1 border-t border-dashed border-gray-300 pt-1 text-[13px] text-muted">
          {`${t("blockDeleted")} · `}
          <button
            type="button"
            title={`${title}: ${t("undoDelete")}`}
            className="text-[#355FA1] underline"
            disabled={blockBusy}
            onClick={() => sendBlock(id, null)}
          >
            {t("undoDelete")}
          </button>
        </div>
      );
    if (openBlock === id)
      return (
        <BlockEditor
          label={title}
          initial={edited ?? original.map((c) => c.text).join("\n")}
          error={blockError}
          busy={blockBusy}
          onSave={(text) => sendBlock(id, text.trim() ? text : "")}
          onCancel={() => {
            setOpenBlock(null);
            setBlockError(null);
          }}
        />
      );
    return (
      <div data-block={id} className={`group relative ${controls ? "pr-20" : ""}`}>
        {edited !== undefined ? (
          <>
            {prefix}
            <EditedText text={edited} />
          </>
        ) : (
          content
        )}
        {controls && (
          <span className="absolute right-0 top-0 flex items-center text-muted opacity-60 focus-within:opacity-100 group-hover:opacity-100 print:hidden">
            <button
              type="button"
              aria-label={`${title} ${t("editBlock")}`}
              title={`${title} ${t("editBlock")}`}
              className="rounded-lg px-2 py-0.5 hover:bg-gray-100 hover:text-ink"
              onClick={() => {
                setBlockError(null);
                setOpenBlock(id);
              }}
            >
              ✎
            </button>
            {!opts.noDelete && (
              <button
                type="button"
                aria-label={`${title}: ${t("deleteBlock")}`}
                title={`${title}: ${t("deleteBlock")}`}
                disabled={blockBusy}
                className="rounded-lg px-2 py-0.5 text-[13px] hover:bg-gray-100 hover:text-[#B42318]"
                onClick={() => sendBlock(id, "")}
              >
                {t("deleteBlock")}
              </button>
            )}
          </span>
        )}
        {edited !== undefined && marks && (
          <div className="mt-1 flex flex-wrap items-center gap-3 text-[13px] print:hidden">
            <span className="rounded-full bg-[#EEF2F9] px-2 py-0.5 font-semibold text-cobalt">{t("blockEdited")}</span>
            {controls && (
              <button type="button" className="text-[#355FA1] underline" disabled={blockBusy} onClick={() => sendBlock(id, null)}>
                {t("restoreBlock")}
              </button>
            )}
          </div>
        )}
        {marks && <FindingList findings={checks[id] ?? []} />}
      </div>
    );
  };

  /** A block of the client page: its sentences, with source numbers only for the RM. */
  const presBlock = (id: string, title: string, opts: BlockOpts = {}) => {
    const fund = id.startsWith("oneriler:") ? view.options[id.slice("oneriler:".length)] : undefined;
    // a fund card's sentences without the fund's name in front: the card's title is the name
    const own = fund
      ? (perOption.find((o) => `oneriler:${o.id}` === id)?.sentences ?? []).map((c) => ({ ...c, text: withoutName(c.text, fund, lang) }))
      : sentences(id as SectionKey);
    if (!own.length && !(id in edits)) return null;
    const text = (c: Cited) => (preview ? c.text : withMark(c));
    return block(id, title, own, <Bullets items={own.map(text)} />, undefined, opts);
  };

  /** "Bölümü sil" next to the heading of a section with several blocks, while one is left. */
  const sectionDelete = (title: string, blocks: string[]) =>
    editable && blocks.length > 1 && blocks.some((b) => !gone(b)) ? (
      <button
        type="button"
        aria-label={`${title}: ${t("deleteSection")}`}
        disabled={blockBusy}
        className="text-[13px] text-muted hover:text-[#B42318]"
        onClick={() => deleteBlocks(blocks.filter((b) => !gone(b)))}
      >
        {t("deleteSection")}
      </button>
    ) : null;

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
  const listOf = (cs: Cited[]) => <Bullets items={cs.map(withMark)} />;

  /** The RM's help: one yellow box per part, filled only when it has something (or a deleted line). */
  const has = (key: SectionKey) => (sentences(key).length > 0 || key in edits) && !hidden([key]);
  const listNote = (key: SectionKey, label: string) =>
    has(key) ? <RmNote title={label}>{block(key, label, sentences(key), listOf(sentences(key)))}</RmNote> : null;
  const notes = preview
    ? {}
    : {
        cover: (
          <div className="flex flex-col gap-3">
            {/* W30: an approved edited profile says so (RM-only here; the card and the print card say it too) */}
            {view.test_run && view.persona_changes.length > 0 && (
              <p
                data-testid="edited-profile"
                className="m-0 rounded-xl border border-dashed border-[#E3C766] bg-[#FFFBEA] px-5 py-3 text-[15px] text-[#93370D] print:hidden"
              >
                {`${t("editedLine")}: ${profileChanges(view.persona_changes, lang)}`}
              </p>
            )}
            {!hidden(["ozet"]) && (
              <RmNote title={t("meetingAim")}>
                {block("ozet", t("meetingAim"), sentences("ozet"), listOf(sentences("ozet")))}
              </RmNote>
            )}
            {sentences("piyasa_notu").length > 0 && !hidden(["piyasa_notu"]) && (
              <RmNote title={t("marketNote")}>
                {block("piyasa_notu", t("marketNote"), sentences("piyasa_notu"), listOf(sentences("piyasa_notu")))}
              </RmNote>
            )}
          </div>
        ),
        figures: !hidden(tpBlocks) && points.length > 0 && (
          <RmNote title={t("tpDoc")} action={sectionDelete(t("tpDoc"), tpBlocks)}>
            <ul className="space-y-2">
              {points.map((c, i) => {
                if (approved && tpFromNarrator && gone(`talking_points:${i}`)) return null;
                const title = c.title ? <b>{`${c.title}. `}</b> : null;
                const body = (
                  <>
                    {title}
                    {withMark(c)}
                  </>
                );
                return <li key={i}>{tpFromNarrator ? block(`talking_points:${i}`, `${t("tpDoc")} ${i + 1}`, [c], body, title) : body}</li>;
              })}
            </ul>
          </RmNote>
        ),
        funds: listNote("alternatifler", t("otherOptions")),
        risks: listNote("varsayimlar", t("assumptions")),
      };

  const printPage = () => {
    // the print is the client view: render it first, then print
    flushSync(() => setPreview(true));
    window.print();
  };

  return (
    <div className="pb-10">
      <div className="print:hidden">
        <LifecycleTabs runId={runId} approved={r.rm_status === "approved"} active="text" />
      </div>

      {draft && (
        <div data-testid="meeting-toolbar" className="mb-4 flex flex-wrap items-center justify-between gap-3 print:hidden">
          <div data-testid="doc-status" className="text-[13px] text-muted">
            {[
              approved ? `✓ ${t("statusApproved")}${draft.approved_at ? `: ${fmtDateTime(draft.approved_at)}` : ""}` : t("statusDraft"),
              ...modelLine,
            ].join(" · ")}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              aria-pressed={preview}
              className={`min-h-[40px] rounded-lg px-4 text-[15px] ${preview ? "bg-ink font-semibold text-white" : "border border-gray-300 bg-white"}`}
              onClick={() => setPreview(!preview)}
            >
              {`👁 ${preview ? t("presPreviewOn") : t("presPreview")}`}
            </button>
            <button
              type="button"
              disabled={blocking}
              title={blocking ? t("cardBlocked") : undefined}
              className="min-h-[40px] rounded-lg bg-ink px-4 text-[15px] font-semibold text-white disabled:opacity-50"
              onClick={printPage}
            >
              {`⤓ ${t("presPrint")}`}
            </button>
          </div>
        </div>
      )}

      {actionError && (
        <p role="alert" className="mb-4 rounded-xl border border-red-200 bg-white p-3 text-sm print:hidden">
          {`${t("errorTitle")}: ${actionError}`}
        </p>
      )}
      {draft?.source === "template" && (
        <p role="status" className="mb-4 rounded-xl border border-[#FEC84B] bg-[#FFFAEB] px-4 py-3 text-[15px] print:hidden">
          {t("templateBanner")}
        </p>
      )}

      {loadError ? (
        <ErrorBox error={loadError} onRetry={load} />
      ) : !draft ? (
        <NarrativeProgress view={view} />
      ) : (
        <div className={preview ? "mx-auto max-w-[960px]" : "grid items-start gap-7 lg:grid-cols-[minmax(0,1fr)_300px]"}>
          {markdown ? (
            <article data-testid="document" className="rounded-2xl bg-white px-10 py-[34px] text-[17px] leading-[1.7] shadow-sm">
              <div className="mb-2 text-xs font-bold uppercase tracking-[0.06em] text-[#355FA1]">{markdown.label}</div>
              <div className="max-w-[70ch]">
                <Markdown text={markdown.text} />
              </div>
            </article>
          ) : (
            <ClientPresentation
              view={view}
              draft={draft}
              rm={!preview}
              editable={editable}
              block={presBlock}
              notes={notes}
              optionNotes={optionNotes}
              onOptionNote={editOptionNote}
              hidden={hiddenSections}
              onSection={toggleSection}
            />
          )}

          {!preview && (
            <aside className="print:hidden">
              {/* W19: the card first, where "Metni onayla" was; it is closed while a rule finding is open */}
              <section data-testid="card-box" className={box}>
                <h3 className="mb-1 font-bold">{t("card")}</h3>
                {blocking ? (
                  <>
                    {[t("pdfDownload"), t("mdDownload")].map((label) => (
                      <a
                        key={label}
                        role="link"
                        aria-disabled="true"
                        className="flex cursor-not-allowed items-center gap-2 border-t border-gray-100 py-2.5 text-[15px] font-semibold text-muted opacity-60"
                      >
                        {`⤓ ${label}`}
                      </a>
                    ))}
                    <p data-testid="card-blocked" className="mt-1 text-sm text-[#B42318]">
                      {t("cardBlocked")}
                    </p>
                  </>
                ) : (
                  <>
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
                  </>
                )}
                <div data-testid="card-footer" className="mt-1 text-[13px] text-muted">
                  {[...modelLine, `$${cost}`].join(" · ")}
                </div>
              </section>
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
              {!markdown && <SourceList sources={sources} onEvidence={setEvidenceId} highlight={highlight} />}
            </aside>
          )}
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
