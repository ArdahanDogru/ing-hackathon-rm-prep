// Meeting text as a document (docs/web-ui.md "Meeting text (A)"; mockup redesign-v4.html tab 5)
// with section-by-section editing ("Section-by-section editing of the meeting text").
import { useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { GlossaryTerm, NarrativeView, OptionKind, OptionView, RunView, SectionKey } from "../api/types";
import { BlockEditor } from "../components/BlockEditor";
import { ClientPresentation, type BlockOpts } from "../components/ClientPresentation";
import { snapshotDate } from "../components/BriefCard";
import { DocumentSection, SourceMark } from "../components/DocumentSection";
import { ErrorBox } from "../components/ErrorBox";
import { EvidencePopup } from "../components/EvidencePopup";
import { FindingList, isBlocking } from "../components/FindingList";
import { sourceName } from "../components/KindBadge";
import { LifecycleTabs } from "../components/LifecycleTabs";
import { NotesBox, type SaveState } from "../components/NotesBox";
import { SourceList, type Source } from "../components/SourceList";
import { TermsBox } from "../components/TermsBox";
import { fmtDateTime, fmtPct } from "../format";
import { LangContext, useT } from "../i18n";
import { Markdown } from "../markdown";

const SAVE_DELAY_MS = 800;
const HIGHLIGHT_MS = 2000;
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

/** W27: "Müşteri sunumu" (the page for the client) or "RM hazırlık notu" (the document below). */
export type MeetingMode = "presentation" | "note";

export function MeetingText({ view, initialMode = "presentation" }: { view: RunView; initialMode?: MeetingMode }) {
  const t = useT();
  const lang = useContext(LangContext);
  const r = view.result;
  const runId = r.run_id;

  const [draft, setDraft] = useState<NarrativeView | null>(null);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
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
  const [mode, setMode] = useState<MeetingMode>(initialMode);
  const [editing, setEditing] = useState(false);

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
  const perOption = selected.map((id) => ({ id, sentences: sentences("oneriler").filter((s) => s.option_ids[0] === id) }));
  const approved = draft?.status === "approved";
  const editable = !!draft && !approved;
  /** rm_edits[block] === "": the block is deleted (v1.9). */
  const gone = (block: string) => edits[block] === "";
  /** An approved text leaves out a section whose blocks are all deleted. */
  const hidden = (blocks: string[]) => approved && blocks.length > 0 && blocks.every(gone);
  const tpBlocks = tpFromNarrator ? points.map((_, i) => `talking_points:${i}`) : [];
  const optionBlocks = perOption.map((o) => `oneriler:${o.id}`);

  // source numbers: every cited sentence, in document order, without the sentences of edited blocks
  const live = (block: string, cs: Cited[]) => (block in edits ? [] : cs);
  const ordered = [
    ...live("ozet", sentences("ozet")),
    ...live("piyasa_notu", sentences("piyasa_notu")),
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
    const list = LIST_BLOCKS.has(id);
    // the presentation shows its marks only while the RM edits (W27)
    const marks = opts.controls ?? true;
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
          initial={edited ?? original.map((c) => c.text).join(list ? "\n" : " ")}
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
            <EditedText text={edited} list={list} />
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

  /** W27: a block of the client page: its sentences as plain text (no source numbers). */
  const presBlock = (id: string, title: string, opts: BlockOpts = {}) => {
    const own = id.startsWith("oneriler:")
      ? (perOption.find((o) => `oneriler:${o.id}` === id)?.sentences ?? [])
      : sentences(id as SectionKey);
    if (!own.length && !(id in edits)) return null;
    const content = LIST_BLOCKS.has(id) ? (
      <ul className="list-disc space-y-1.5 pl-6">
        {own.map((c, i) => (
          <li key={i}>{c.text}</li>
        ))}
      </ul>
    ) : (
      <p className="m-0">{own.map((c) => c.text).join(" ")}</p>
    );
    return block(id, title, own, content, undefined, { controls: editing, ...opts });
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
      <div className="print:hidden">
        <LifecycleTabs runId={runId} approved={r.rm_status === "approved"} active="text" />
      </div>

      <div data-testid="meeting-toolbar" className="mx-auto mb-4 flex max-w-[960px] flex-wrap items-center justify-between gap-3 print:hidden">
        <div role="group" aria-label={t("meetingText")} className="flex rounded-full bg-white p-1 shadow-sm">
          {(
            [
              ["presentation", t("presTab")],
              ["note", t("prepTab")],
            ] as const
          ).map(([m, label]) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              className={`min-h-[40px] rounded-full px-4 text-[15px] ${mode === m ? "bg-ink font-semibold text-white" : "text-muted hover:text-ink"}`}
              onClick={() => setMode(m)}
            >
              {label}
            </button>
          ))}
        </div>
        {mode === "presentation" && draft && (
          <div className="flex flex-wrap gap-2">
            {editable && (
              <button
                type="button"
                aria-pressed={editing}
                className={`min-h-[40px] rounded-lg px-4 text-[15px] ${editing ? "bg-[#FFF1B8] font-semibold text-[#3D2F00]" : "border border-gray-300 bg-white"}`}
                onClick={() => setEditing(!editing)}
              >
                {`✎ ${editing ? t("presEditing") : t("presEdit")}`}
              </button>
            )}
            <button
              type="button"
              disabled={blocking}
              title={blocking ? t("cardBlocked") : undefined}
              className="min-h-[40px] rounded-lg bg-ink px-4 text-[15px] font-semibold text-white disabled:opacity-50"
              onClick={() => window.print()}
            >
              {`⤓ ${t("presPrint")}`}
            </button>
          </div>
        )}
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
        <ErrorBox error={loadError} onRetry={load} />
      ) : !draft ? (
        <p className="animate-pulse rounded-2xl bg-white p-6 text-base text-muted shadow-sm">{t("textPreparing")}</p>
      ) : mode === "presentation" ? (
        <ClientPresentation
          view={view}
          draft={draft}
          editing={editing && editable}
          block={presBlock}
          note={note}
          onNote={editNote}
          optionNotes={optionNotes}
          onOptionNote={editOptionNote}
          saveState={saveState}
        />
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
                {!hidden(["ozet"]) && (
                  <DocumentSection title={t("meetingAim")}>
                    {block("ozet", t("meetingAim"), sentences("ozet"), <p className="max-w-[68ch]">{prose(sentences("ozet"))}</p>)}
                  </DocumentSection>
                )}

                {sentences("piyasa_notu").length > 0 && !hidden(["piyasa_notu"]) && (
                  <DocumentSection title={t("marketNote")}>
                    {block("piyasa_notu", t("marketNote"), sentences("piyasa_notu"), <p className="max-w-[68ch]">{prose(sentences("piyasa_notu"))}</p>)}
                  </DocumentSection>
                )}

                {!hidden(tpBlocks) && (
                  <DocumentSection title={t("tpDoc")} action={sectionDelete(t("tpDoc"), tpBlocks)}>
                    <ul className="max-w-[68ch] space-y-2">
                      {points.map((c, i) => {
                        if (approved && tpFromNarrator && gone(`talking_points:${i}`)) return null;
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
                )}

                {!hidden(["teklif_metni"]) && (
                  <DocumentSection title={t("scriptShort")}>
                    {gone("teklif_metni") ? (
                      block("teklif_metni", t("scriptShort"), [], null)
                    ) : (
                      <blockquote data-testid="script" className="my-2 rounded-r-xl border-l-4 border-cobalt bg-[#F7F9FC] px-5 py-3.5 text-lg">
                        {block("teklif_metni", t("scriptShort"), sentences("teklif_metni"), <div>{prose(sentences("teklif_metni"))}</div>)}
                      </blockquote>
                    )}
                  </DocumentSection>
                )}

                {!hidden(optionBlocks) && (
                  <DocumentSection title={t("recommendations")} action={sectionDelete(t("recommendations"), optionBlocks)}>
                    {perOption.map(({ id, sentences: own }) => {
                      const o = view.options[id];
                      if (gone(`oneriler:${id}`))
                        return approved ? null : (
                          <div key={id} className="mb-3">
                            <b className="text-muted">{docName(o)}</b>
                            {block(`oneriler:${id}`, docName(o), [], null)}
                          </div>
                        );
                      const i = perOption.filter((x) => !gone(`oneriler:${x.id}`)).findIndex((x) => x.id === id);
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
                )}

                {!hidden(["dikkat"]) && (
                  <DocumentSection title={t("attention")}>
                    {block("dikkat", t("attention"), sentences("dikkat"), listOf(sentences("dikkat")))}
                  </DocumentSection>
                )}

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
                    count: hidden([key]) ? 0 : sentences(key).length,
                    body: block(key, label, sentences(key), listOf(sentences(key))),
                  }))}
                />
              </>
            )}
            <p className="mt-6 border-t border-gray-100 pt-3 text-[13px] text-muted">{t("disclaimerNote")}</p>
          </article>

          <aside>
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
            <TermsBox terms={terms} />
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
