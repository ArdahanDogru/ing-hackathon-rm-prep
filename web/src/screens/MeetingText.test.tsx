import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import type { NarrativeView, RunView, SectionKey } from "../api/types";
import { renderWith } from "../test/render";
import { sample } from "../test/samples";
import { MeetingText } from "./MeetingText";

const narrative = () => sample("narrative_p01_tr");
const section = (key: SectionKey, n = narrative()) => n.sections.find((s) => s.key === key);
const sectionText = (key: SectionKey) => section(key)!.sentences[0].text;

/** The sample with one block edited, as the server returns it (markdown with the edit). */
function withEdit(n: NarrativeView, block: string, text: string): NarrativeView {
  return { ...n, rm_edits: { ...n.rm_edits, [block]: text }, markdown: `${n.markdown}\n<!-- ${block} -->\n${text}\n` };
}
/** The sample with blocks deleted (rm_edits[block] = ""), markdown unchanged: no dependence on N14. */
function withDeleted(n: NarrativeView, ...blocks: string[]): NarrativeView {
  return { ...n, rm_edits: { ...n.rm_edits, ...Object.fromEntries(blocks.map((b) => [b, ""])) } };
}
/** editBlock that keeps the state of the edits, as the server does. */
function statefulEdit(start: NarrativeView) {
  let state = start;
  return vi.spyOn(api, "editBlock").mockImplementation(async (_run, _lang, block, text) => {
    const edits = { ...state.rm_edits };
    if (text === null) delete edits[block];
    else edits[block] = text;
    state = { ...state, rm_edits: edits };
    return state;
  });
}
function withChecks(n: NarrativeView, block: string, findings: string[]): NarrativeView {
  return { ...n, edit_checks: { ...n.edit_checks, [block]: findings } };
}

function mockNarrative(n: NarrativeView) {
  return vi.spyOn(api, "narrative").mockResolvedValue(n);
}
function renderMeeting(view: RunView) {
  return renderWith(<MeetingText view={view} initialMode="note" />);
}

beforeEach(() => {
  vi.spyOn(api, "glossary").mockResolvedValue(sample("glossary"));
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// --- plan W9 ---------------------------------------------------------------------

test("sections in order in one document column", async () => {
  mockNarrative(narrative());
  renderMeeting(sample("run_p01_approved"));
  const heads = (await screen.findAllByTestId("doc-heading")).map((h) => h.textContent);
  expect(heads.slice(0, 5)).toEqual(["Görüşmenin amacı", "Konuşulacaklar", "Söyleyebileceğiniz", "Öneriler", "Dikkat"]);
});

test("source numbers match the Kaynaklar list", async () => {
  mockNarrative(narrative());
  renderMeeting(sample("run_p01_approved"));
  const marks = await screen.findAllByTestId("src-mark");
  const items = screen.getAllByTestId("source-item");
  expect(Math.max(...marks.map((m) => Number(m.textContent)))).toBe(items.length);
  expect(document.getElementById(`src-${marks[0].textContent}`)).not.toBeNull();
});

// --- W15 part 1: source numbers -------------------------------------------------------

/** The first cited sentence of the document (the aim, else the first talking point). */
function firstCited(n: NarrativeView, v: RunView) {
  const tp = section("talking_points", n)?.sentences ?? [];
  const points = tp.length ? tp : v.talking_points;
  const s = [...section("ozet", n)!.sentences, ...points].find((x) => x.evidence_ids.length);
  return s!;
}

test("a source number opens the evidence of its sentence and highlights its Kaynaklar entry", async () => {
  mockNarrative(narrative());
  const ev = vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  const v = sample("run_p01_approved");
  renderMeeting(v);
  const mark = (await screen.findAllByTestId("src-mark"))[0];
  expect(mark).not.toHaveAttribute("href");
  vi.useFakeTimers({ shouldAdvanceTime: true });
  await userEvent.click(mark);
  expect(ev).toHaveBeenCalledWith(v.result.snapshot_id, firstCited(narrative(), v).evidence_ids[0]);
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  const item = document.getElementById(`src-${mark.textContent}`)!;
  expect(item).toHaveAttribute("data-highlight", "true");
  expect(screen.getAllByTestId("source-item").filter((x) => x.dataset.highlight === "true")).toHaveLength(1);
  await act(() => vi.advanceTimersByTimeAsync(2_100));
  expect(item).not.toHaveAttribute("data-highlight", "true");
});

test("a source number opens with the keyboard", async () => {
  mockNarrative(narrative());
  const ev = vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  renderMeeting(sample("run_p01_approved"));
  const mark = (await screen.findAllByTestId("src-mark"))[0];
  mark.focus();
  await userEvent.keyboard("{Enter}");
  expect(ev).toHaveBeenCalledTimes(1);
  await userEvent.keyboard("{Escape}");
  mark.focus();
  await userEvent.keyboard(" ");
  expect(ev).toHaveBeenCalledTimes(2);
});

test("collapsed lines open on click", async () => {
  mockNarrative(narrative());
  renderMeeting(sample("run_p01_approved"));
  const line = await screen.findByRole("button", { name: /Varsayımlar/ });
  expect(screen.getByTestId("section-varsayimlar")).not.toBeVisible();
  await userEvent.click(line);
  expect(screen.getByTestId("section-varsayimlar")).toBeVisible();
  expect(line).toHaveTextContent(`(${section("varsayimlar")!.sentences.length})`);
});

test("RM-only warnings only in RM notu", async () => {
  mockNarrative(narrative());
  const v = sample("run_p01_approved");
  renderMeeting(v);
  const doc = await screen.findByTestId("document");
  expect(v.rm_warnings.length).toBeGreaterThan(0);
  v.rm_warnings.forEach((w) => expect(doc).not.toHaveTextContent(w.message));
  v.rm_warnings.forEach((w) => expect(screen.getByTestId("rm-notes")).toHaveTextContent(w.message));
});

// --- the document ----------------------------------------------------------------

test("the document: status line, title, aim, talking points, script, Dikkat", async () => {
  const n = narrative();
  mockNarrative(n);
  const v = sample("run_p01_approved");
  renderMeeting(v);
  const doc = await screen.findByTestId("document");
  expect(within(doc).getByTestId("doc-status")).toHaveTextContent(n.source === "template" ? "şablon metin" : n.model);
  expect(within(doc).getByRole("heading", { level: 1 })).toHaveTextContent(`${v.result.persona.profil}, ${v.result.persona.yas}`);
  expect(doc).toHaveTextContent(sectionText("ozet"));
  section("talking_points")!.sentences.forEach((s) => expect(doc).toHaveTextContent(s.title));
  expect(within(doc).getByTestId("script")).toHaveTextContent(sectionText("teklif_metni"));
  expect(doc).toHaveTextContent(sectionText("dikkat"));
});

test("one block per selected option: short name, facts, need tags, its sentences, a note field", async () => {
  const n = narrative();
  mockNarrative(n);
  const v = sample("run_p01_approved");
  renderMeeting(v);
  const blocks = await screen.findAllByTestId("doc-option");
  expect(blocks).toHaveLength(v.result.rm_selected.length);
  const id = v.result.rm_selected[0];
  const o = v.options[id];
  expect(blocks[0]).toHaveTextContent(o.short_label);
  expect(blocks[0]).toHaveTextContent(`risk ${o.risk!.level}/7`);
  (n.need_tags[id] ?? []).forEach((tag) => expect(within(blocks[0]).getByText(tag)).toBeInTheDocument());
  // a sentence belongs to the block of its first option (server rule: oneriler:<option_ids[0]>)
  section("oneriler")!.sentences.filter((s) => s.option_ids[0] === id).forEach((s) => expect(blocks[0]).toHaveTextContent(s.text));
  expect(within(blocks[0]).getByRole("textbox")).toBeInTheDocument();
});

test("a v1.2 draft without talking_points uses the decision talking points", async () => {
  const n = narrative();
  n.sections = n.sections.filter((s) => s.key !== "talking_points");
  mockNarrative(n);
  const v = sample("run_p01_approved");
  renderMeeting(v);
  const doc = await screen.findByTestId("document");
  expect(doc).toHaveTextContent(v.talking_points[0].label);
  expect(doc).toHaveTextContent(v.talking_points[0].text);
});

test("the lifecycle tab Görüşme metni is active", async () => {
  mockNarrative(narrative());
  renderMeeting(sample("run_p01_approved"));
  expect(await screen.findByRole("tab", { name: /Görüşme metni/ })).toHaveAttribute("aria-selected", "true");
});

test("shows the template banner", async () => {
  mockNarrative({ ...narrative(), source: "template", model: "" });
  renderMeeting(sample("run_p01_approved"));
  expect(await screen.findByText(/otomatik metin doğrulanamadı/)).toBeInTheDocument();
  expect(screen.getByTestId("doc-status")).toHaveTextContent("şablon metin");
});

test("waiting shows Metin hazırlanıyor…; a 504 shows Tekrar dene", async () => {
  const get = vi
    .spyOn(api, "narrative")
    .mockRejectedValueOnce(new ApiError(504, "the meeting text is not ready yet; try again"))
    .mockResolvedValueOnce(narrative());
  renderMeeting(sample("run_p01_approved"));
  expect(screen.getByText("Metin hazırlanıyor…")).toBeInTheDocument();
  await userEvent.click(await screen.findByRole("button", { name: "Tekrar dene" }));
  expect(await screen.findByTestId("document")).toBeInTheDocument();
  expect(get).toHaveBeenCalledTimes(2);
});

// --- notes, edit, approve ----------------------------------------------------------

test("notes autosave", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const notes = vi.spyOn(api, "notes").mockResolvedValue(sample("run_p01_approved"));
  mockNarrative(narrative());
  const v = sample("run_p01_approved");
  renderMeeting(v);
  await userEvent.type(await screen.findByLabelText("Notlarım"), "eşi de gelecek");
  vi.advanceTimersByTime(900);
  expect(notes).toHaveBeenCalled();
  const last = notes.mock.calls.at(-1)!;
  expect(last[0]).toBe(v.result.run_id);
  expect(last[1]).toBe(v.result.rm_note + "eşi de gelecek");
  expect(await screen.findByText(/Kaydedildi/)).toBeInTheDocument();
});

test("an option note is saved with the general note", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const notes = vi.spyOn(api, "notes").mockResolvedValue(sample("run_p01_approved"));
  mockNarrative(narrative());
  const v = sample("run_p01_approved");
  renderMeeting(v);
  const block = (await screen.findAllByTestId("doc-option"))[0];
  await userEvent.type(within(block).getByRole("textbox"), "ilk bu fon");
  vi.advanceTimersByTime(900);
  expect(notes.mock.calls.at(-1)![2]).toEqual({ [v.result.rm_selected[0]]: "ilk bu fon" });
});

test("pencil edits one block; others keep their layout", async () => {
  mockNarrative(sample("narrative_p01_tr"));
  const edit = vi.spyOn(api, "editBlock").mockResolvedValue(withEdit(sample("narrative_p01_tr"), "ozet", "Yeni amaç."));
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: /Görüşmenin amacı.*düzenle/i }));
  expect(screen.getByRole("textbox", { name: /Görüşmenin amacı/ })).toHaveValue(section("ozet")!.sentences.map((x) => x.text).join(" "));
  await userEvent.clear(screen.getByRole("textbox", { name: /Görüşmenin amacı/ }));
  await userEvent.type(screen.getByRole("textbox", { name: /Görüşmenin amacı/ }), "Yeni amaç.");
  await userEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  expect(edit).toHaveBeenCalledWith(expect.any(String), "TR", "ozet", "Yeni amaç.");
  expect(await screen.findByText("düzenlendi")).toBeInTheDocument();
  expect(screen.getByTestId("document")).toHaveTextContent("Yeni amaç.");
  expect(screen.getAllByTestId("doc-option").length).toBeGreaterThan(0);
});

test("Vazgeç closes the editor without a call", async () => {
  mockNarrative(sample("narrative_p01_tr"));
  const edit = vi.spyOn(api, "editBlock");
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: /Söyleyebileceğiniz.*düzenle/i }));
  await userEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
  expect(screen.queryByRole("textbox", { name: /Söyleyebileceğiniz/ })).toBeNull();
  expect(edit).not.toHaveBeenCalled();
});

test("each talking point and each option is its own block", async () => {
  mockNarrative(sample("narrative_p01_tr"));
  const edit = vi.spyOn(api, "editBlock").mockResolvedValue(sample("narrative_p01_tr"));
  const v = sample("run_p01_approved");
  renderMeeting(v);
  const pencils = await screen.findAllByRole("button", { name: /düzenle/i });
  const tp = section("talking_points")!.sentences.length;
  expect(pencils.length).toBeGreaterThanOrEqual(tp + v.result.rm_selected.length);
  const block = (await screen.findAllByTestId("doc-option"))[1];
  await userEvent.click(within(block).getByRole("button", { name: /düzenle/i }));
  await userEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  expect(edit.mock.calls[0][2]).toBe(`oneriler:${v.result.rm_selected[1]}`);
});

test("a server error stays in the editor", async () => {
  mockNarrative(sample("narrative_p01_tr"));
  vi.spyOn(api, "editBlock").mockRejectedValue(new ApiError(422, "boş metin"));
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: /Görüşmenin amacı.*düzenle/i }));
  await userEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("boş metin");
  expect(screen.getByRole("textbox", { name: /Görüşmenin amacı/ })).toBeInTheDocument();
});

// --- W19: no text approval; the card carries the safety check ------------------------------

test("no Metni onayla; the Kart box is first in the right column", async () => {
  mockNarrative(sample("narrative_p01_tr"));
  renderMeeting(sample("run_p01_approved"));
  const box = await screen.findByTestId("card-box");
  expect(screen.queryByRole("button", { name: "Metni onayla" })).toBeNull();
  expect(screen.queryByTestId("approve-reason")).toBeNull();
  expect(box.parentElement!.tagName).toBe("ASIDE");
  expect(box.parentElement!.firstElementChild).toBe(box);
});

test("a blocking finding disables both card links with the reason", async () => {
  mockNarrative(withChecks(withEdit(sample("narrative_p01_tr"), "ozet", "Bu fon kesin getiri sağlar."), "ozet", ["phrase: 'kesin getiri' kullanılmamalı"]));
  renderMeeting(sample("run_p01_approved"));
  expect(await screen.findByText(/'kesin getiri' kullanılmamalı/)).toBeInTheDocument();
  for (const name of [/PDF olarak indir/, /Markdown olarak indir/]) {
    const link = screen.getByRole("link", { name });
    expect(link).toHaveAttribute("aria-disabled", "true");
    expect(link).not.toHaveAttribute("href");
  }
  expect(screen.getByTestId("card-blocked")).toHaveTextContent("Kural bulgusu açık: kartı indirmeden önce düzeltin.");
});

test("a number finding only warns: the card links stay open", async () => {
  mockNarrative(withChecks(withEdit(sample("narrative_p01_tr"), "ozet", "Faiz %99,9."), "ozet", ["number: 99,9 olgularda yok"]));
  const v = sample("run_p01_approved");
  renderMeeting(v);
  expect(await screen.findByText(/99,9 olgularda yok/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /PDF olarak indir/ })).toHaveAttribute("href", `/print/${v.result.run_id}`);
  expect(screen.getByRole("link", { name: /Markdown olarak indir/ })).not.toHaveAttribute("aria-disabled");
  expect(screen.queryByTestId("card-blocked")).toBeNull();
});

test("W19 EN: the reason under the disabled card links", async () => {
  mockNarrative(withChecks(withEdit(sample("narrative_p01_en"), "ozet", "Guaranteed return."), "ozet", ["phrase: 'guaranteed' must not be used"]));
  renderWith(<MeetingText view={sample("run_p01_approved")} initialMode="note" />, { lang: "EN" });
  expect(await screen.findByTestId("card-blocked")).toHaveTextContent("A rule finding is open: fix it before you download the card.");
});

test("Orijinale dön sends null", async () => {
  const edit = vi.spyOn(api, "editBlock").mockResolvedValue(sample("narrative_p01_tr"));
  mockNarrative(withEdit(sample("narrative_p01_tr"), "ozet", "Yeni amaç."));
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: "Orijinale dön" }));
  expect(edit).toHaveBeenCalledWith(expect.any(String), "TR", "ozet", null);
  await waitFor(() => expect(screen.queryByText("düzenlendi")).toBeNull());
});

test("an edited block has no source marks of the replaced sentences", async () => {
  const n = sample("narrative_p01_tr");
  const id = sample("run_p01_approved").result.rm_selected[0];
  mockNarrative(withEdit(n, `oneriler:${id}`, "Kendi cümlem."));
  renderMeeting(sample("run_p01_approved"));
  const block = (await screen.findAllByTestId("doc-option"))[0];
  expect(block).toHaveTextContent("Kendi cümlem.");
  expect(within(block).queryAllByTestId("src-mark")).toHaveLength(0);
  const marks = screen.getAllByTestId("src-mark");
  expect(Math.max(...marks.map((m) => Number(m.textContent)))).toBe(screen.getAllByTestId("source-item").length);
});

test("no whole-text Düzenle any more", async () => {
  mockNarrative(sample("narrative_p01_tr"));
  renderMeeting(sample("run_p01_approved"));
  await screen.findByTestId("document");
  expect(screen.queryByRole("button", { name: "Düzenle" })).toBeNull();
});

test("after a reload, an approved text with a whole-text edit (before W11) shows as Markdown", async () => {
  const d = sample("narrative_p01_tr");
  mockNarrative({ ...d, status: "approved", rm_text: "## Kendi metnim", markdown: "## Kendi metnim" });
  renderMeeting(sample("run_p01_approved"));
  expect(await screen.findByRole("heading", { name: "Kendi metnim" })).toBeInTheDocument();
  expect(screen.getByText("Düzenlenmiş metin")).toBeInTheDocument();
});

// --- right column -----------------------------------------------------------------

test("glossary terms and the card downloads", async () => {
  const n = narrative();
  mockNarrative(n);
  const v = sample("run_p01_approved");
  renderMeeting(v);
  for (const term of sample("glossary")) expect(await screen.findByText(term.form)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Markdown olarak indir/ })).toHaveAttribute("href", api.cardUrl(v.result.run_id));
  expect(screen.getByRole("link", { name: /PDF olarak indir/ })).toHaveAttribute("href", `/print/${v.result.run_id}`);
  // a template draft has no model: the footer says "şablon metin" instead
  expect(screen.getByTestId("card-footer")).toHaveTextContent(n.source === "template" ? "şablon metin" : n.model);
  expect(screen.getByTestId("card-footer")).toHaveTextContent(n.checks.length ? "kontrol bulgusu" : "otomatik kontrol geçti");
});

test("a source item opens the evidence of one of its ids", async () => {
  mockNarrative(narrative());
  const ev = vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  renderMeeting(sample("run_p01_approved"));
  const item = (await screen.findAllByTestId("source-item"))[0];
  await userEvent.click(within(item).getAllByRole("button")[0]);
  expect(ev).toHaveBeenCalled();
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
});

test("EN asks for the EN text", async () => {
  const get = mockNarrative(sample("narrative_p01_en"));
  renderWith(<MeetingText view={sample("run_p01_approved")} initialMode="note" />, { lang: "EN" });
  await screen.findByTestId("document");
  expect(get.mock.calls[0][1]).toBe("EN");
  expect(screen.getAllByTestId("doc-heading")[0]).toHaveTextContent("Aim of the meeting");
});

test("an approved text shows Onaylandı with its time", async () => {
  const d = sample("narrative_p01_tr");
  mockNarrative({ ...d, status: "approved", rm_text: d.markdown, approved_at: "2026-10-12T21:05:00+03:00" });
  renderMeeting(sample("run_p01_approved"));
  expect(await screen.findByTestId("doc-status")).toHaveTextContent("Onaylandı: 12.10.2026 21:05");
});

// --- W15 part 2: deleting -------------------------------------------------------------

test("Sil deletes one block; it shows as Silindi · Geri al without its source numbers", async () => {
  const n = narrative();
  mockNarrative(n);
  const edit = statefulEdit(n);
  renderMeeting(sample("run_p01_approved"));
  const before = (await screen.findAllByTestId("src-mark")).length;
  await userEvent.click(screen.getByRole("button", { name: "Görüşmenin amacı: Sil" }));
  expect(edit).toHaveBeenCalledWith(expect.any(String), "TR", "ozet", "");
  const line = await screen.findByTestId("deleted-block");
  expect(line).toHaveTextContent("Silindi · Geri al");
  expect(screen.getByTestId("document")).not.toHaveTextContent(section("ozet")!.sentences[0].text);
  const cited = section("ozet")!.sentences.filter((x) => x.evidence_ids.length).length;
  if (cited) expect(screen.getAllByTestId("src-mark").length).toBeLessThan(before);
});

test("Geri al restores a deleted block (null)", async () => {
  const n = withDeleted(narrative(), "ozet");
  mockNarrative(n);
  const edit = statefulEdit(n);
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: "Geri al" }));
  expect(edit).toHaveBeenCalledWith(expect.any(String), "TR", "ozet", null);
  await waitFor(() => expect(screen.queryByTestId("deleted-block")).toBeNull());
  expect(screen.getByTestId("document")).toHaveTextContent(section("ozet")!.sentences[0].text);
});

test("Bölümü sil deletes every block of Öneriler, one PUT each", async () => {
  const n = narrative();
  mockNarrative(n);
  const edit = statefulEdit(n);
  const v = sample("run_p01_approved");
  renderMeeting(v);
  await userEvent.click(await screen.findByRole("button", { name: "Öneriler: Bölümü sil" }));
  await waitFor(() => expect(edit).toHaveBeenCalledTimes(v.result.rm_selected.length));
  expect(edit.mock.calls.map((c) => [c[2], c[3]])).toEqual(v.result.rm_selected.map((id) => [`oneriler:${id}`, ""]));
  expect(await screen.findAllByTestId("deleted-block")).toHaveLength(v.result.rm_selected.length);
  expect(screen.queryByRole("button", { name: "Öneriler: Bölümü sil" })).toBeNull();
});

test("Bölümü sil for Konuşulacaklar; one-block sections have no Bölümü sil", async () => {
  const n = narrative();
  mockNarrative(n);
  const edit = statefulEdit(n);
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: "Konuşulacaklar: Bölümü sil" }));
  const tp = section("talking_points")!.sentences.length;
  await waitFor(() => expect(edit).toHaveBeenCalledTimes(tp));
  expect(edit.mock.calls.map((c) => c[2])).toEqual(Array.from({ length: tp }, (_, i) => `talking_points:${i}`));
  expect(screen.queryByRole("button", { name: /Görüşmenin amacı: Bölümü sil/ })).toBeNull();
  expect(screen.queryByRole("button", { name: /Dikkat: Bölümü sil/ })).toBeNull();
});

test("saving an empty text deletes the block", async () => {
  const n = narrative();
  mockNarrative(n);
  const edit = statefulEdit(n);
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: /Görüşmenin amacı.*düzenle/i }));
  await userEvent.clear(screen.getByRole("textbox", { name: /Görüşmenin amacı/ }));
  await userEvent.type(screen.getByRole("textbox", { name: /Görüşmenin amacı/ }), "   ");
  await userEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  expect(edit).toHaveBeenCalledWith(expect.any(String), "TR", "ozet", "");
  expect(await screen.findByTestId("deleted-block")).toBeInTheDocument();
});

test("the approved text leaves deleted blocks and empty sections out", async () => {
  const v = sample("run_p01_approved");
  const d = withDeleted(narrative(), "ozet", "dikkat", ...v.result.rm_selected.map((id) => `oneriler:${id}`));
  mockNarrative({ ...d, status: "approved", rm_text: d.markdown });
  renderMeeting(v);
  const doc = await screen.findByTestId("document");
  expect(screen.queryByTestId("deleted-block")).toBeNull();
  expect(screen.queryAllByTestId("doc-option")).toHaveLength(0);
  const heads = screen.getAllByTestId("doc-heading").map((h) => h.textContent);
  expect(heads).not.toContain("Görüşmenin amacı");
  expect(heads).not.toContain("Öneriler");
  expect(heads).not.toContain("Dikkat");
  expect(doc).not.toHaveTextContent(section("ozet")!.sentences[0].text);
});

test("the screen notes that the disclaimer is always added", async () => {
  mockNarrative(narrative());
  renderMeeting(sample("run_p01_approved"));
  expect(await screen.findByText("Yatırım tavsiyesi değildir notu her zaman eklenir.")).toBeInTheDocument();
});

// --- W15 part 3: the market note block ---------------------------------------------------

test("the market note block after the aim, with its source number, deletable", async () => {
  const n = narrative();
  const note = { text: "Piyasa notu (TCMB EVDS): politika faizi %40,5 (09.10.2026).", option_ids: [], evidence_ids: ["ev-policy-rate"], title: "" };
  n.sections.push({ key: "piyasa_notu", sentences: [note] });
  mockNarrative(n);
  const edit = statefulEdit(n);
  renderMeeting(sample("run_p01_approved"));
  const heads = (await screen.findAllByTestId("doc-heading")).map((h) => h.textContent);
  expect(heads.slice(0, 2)).toEqual(["Görüşmenin amacı", "Piyasa notu"]);
  const block = document.querySelector('[data-block="piyasa_notu"]')!;
  expect(block).toHaveTextContent(note.text);
  expect(within(block as HTMLElement).getByTestId("src-mark")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Piyasa notu: Sil" }));
  expect(edit).toHaveBeenCalledWith(expect.any(String), "TR", "piyasa_notu", "");
});

test("no market note section: no Piyasa notu heading", async () => {
  mockNarrative(narrative());
  renderMeeting(sample("run_p01_approved"));
  const heads = (await screen.findAllByTestId("doc-heading")).map((h) => h.textContent);
  expect(heads).not.toContain("Piyasa notu");
});
