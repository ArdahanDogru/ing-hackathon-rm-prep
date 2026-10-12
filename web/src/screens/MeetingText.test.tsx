import { screen, waitFor, within } from "@testing-library/react";
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
function withChecks(n: NarrativeView, block: string, findings: string[]): NarrativeView {
  return { ...n, edit_checks: { ...n.edit_checks, [block]: findings } };
}

function mockNarrative(n: NarrativeView) {
  return vi.spyOn(api, "narrative").mockResolvedValue(n);
}
function renderMeeting(view: RunView) {
  return renderWith(<MeetingText view={view} />);
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
  expect(marks[0]).toHaveAttribute("href", `#src-${marks[0].textContent}`);
  expect(document.getElementById(`src-${marks[0].textContent}`)).not.toBeNull();
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

test("a blocking finding disables Metni onayla with the reason", async () => {
  mockNarrative(withChecks(withEdit(sample("narrative_p01_tr"), "ozet", "Bu fon kesin getiri sağlar."), "ozet", ["phrase: 'kesin getiri' kullanılmamalı"]));
  renderMeeting(sample("run_p01_approved"));
  expect(await screen.findByRole("button", { name: "Metni onayla" })).toBeDisabled();
  expect(screen.getByText(/'kesin getiri' kullanılmamalı/)).toBeInTheDocument();
  expect(screen.getByTestId("approve-reason")).toBeInTheDocument();
});

test("a number finding only warns", async () => {
  mockNarrative(withChecks(withEdit(sample("narrative_p01_tr"), "ozet", "Faiz %99,9."), "ozet", ["number: 99,9 olgularda yok"]));
  renderMeeting(sample("run_p01_approved"));
  expect(await screen.findByRole("button", { name: "Metni onayla" })).toBeEnabled();
  expect(screen.getByText(/99,9 olgularda yok/)).toBeInTheDocument();
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

test("Metni onayla sends the composed Markdown; the approved text shows its edits and no pencils", async () => {
  const d = withEdit(sample("narrative_p01_tr"), "ozet", "Yeni amaç.");
  mockNarrative(d);
  const approve = vi
    .spyOn(api, "approveNarrative")
    .mockImplementation(async (_id, _lang, text) => ({ ...d, status: "approved", rm_text: text, markdown: text }));
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: "Metni onayla" }));
  expect(approve.mock.calls[0][2]).toBe(d.markdown);
  expect(await screen.findByTestId("doc-status")).toHaveTextContent("Onaylandı");
  expect(screen.getByTestId("document")).toHaveTextContent("Yeni amaç.");
  expect(screen.queryAllByRole("button", { name: /düzenle/i })).toHaveLength(0);
  expect(screen.queryByRole("button", { name: "Metni onayla" })).toBeNull();
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
  renderWith(<MeetingText view={sample("run_p01_approved")} />, { lang: "EN" });
  await screen.findByTestId("document");
  expect(get.mock.calls[0][1]).toBe("EN");
  expect(screen.getAllByTestId("doc-heading")[0]).toHaveTextContent("Aim of the meeting");
});
