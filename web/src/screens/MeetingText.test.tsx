import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import type { NarrativeView, RunView, SectionKey } from "../api/types";
import { renderWith } from "../test/render";
import { sample } from "../test/samples";
import { MeetingText } from "./MeetingText";

const narrative = () => sample("narrative_p01_tr");
const section = (key: SectionKey, n = narrative()) => n.sections.find((s) => s.key === key);
const sectionText = (key: SectionKey) => section(key)!.sentences[0].text;

/** The sample as narrator N9 will give it: talking_points and need tags added. */
function n9(): NarrativeView {
  const n = narrative();
  const v = sample("run_p01_approved");
  const prios = v.result.persona.oncelikler;
  return {
    ...n,
    sections: [
      ...n.sections.filter((s) => s.key !== "talking_points"),
      {
        key: "talking_points",
        sentences: [
          { text: "Mevduat enflasyonun gerisinde kalabilir.", option_ids: [], evidence_ids: [], title: "Mevduat ve enflasyon" },
          { text: "Önerilen fonlarda paraya aynı gün erişilir.", option_ids: [], evidence_ids: [], title: "Paraya erişim" },
        ],
      },
    ],
    need_tags: Object.fromEntries(v.result.rm_selected.map((id, i) => [id, [prios[i % prios.length]]])),
  };
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

test("each section in its place", async () => {
  const n = n9();
  mockNarrative(n);
  renderMeeting(sample("run_p01_approved"));
  expect(await screen.findByTestId("header-aim")).toHaveTextContent(sectionText("ozet"));
  expect(screen.getAllByTestId("header-point")).toHaveLength(section("talking_points", n)!.sentences.length);
  expect(screen.getByTestId("script")).toHaveTextContent(sectionText("teklif_metni"));
  expect(screen.getAllByTestId("rec-card")).toHaveLength(sample("run_p01_approved").result.rm_selected.length);
  const tags = Object.values(n.need_tags).flat();
  expect(tags.length).toBeGreaterThan(0);
  tags.forEach((t) => expect(screen.getAllByText(t).length).toBeGreaterThan(0));
  expect(screen.getByTestId("dikkat")).toHaveTextContent(sectionText("dikkat"));
});

test("a v1.2 draft without talking_points uses the decision talking points", async () => {
  const n = narrative();
  n.sections = n.sections.filter((s) => s.key !== "talking_points");
  mockNarrative(n);
  const v = sample("run_p01_approved");
  renderMeeting(v);
  const points = await screen.findAllByTestId("header-point");
  expect(points).toHaveLength(v.talking_points.length);
  expect(points[0]).toHaveTextContent(v.talking_points[0].text);
});

test("a recommendation card holds its own sentences and need tags", async () => {
  const n = n9();
  mockNarrative(n);
  const v = sample("run_p01_approved");
  renderMeeting(v);
  const cards = await screen.findAllByTestId("rec-card");
  const id = v.result.rm_selected[0];
  const own = section("oneriler", n)!.sentences.filter((s) => s.option_ids.includes(id));
  own.forEach((s) => expect(cards[0]).toHaveTextContent(s.text));
  n.need_tags[id].forEach((t) => expect(cards[0]).toHaveTextContent(t));
  expect(cards[0]).toHaveTextContent(v.options[id].label);
});

test("collapsed lines: Diğer seçenekler, Sorulacak sorular, Varsayımlar", async () => {
  mockNarrative(narrative());
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: /Sorulacak sorular/ }));
  expect(screen.getByText(sectionText("sorular"))).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Diğer seçenekler/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Varsayımlar/ })).toBeInTheDocument();
});

test("RM-only warnings only in RM notları", async () => {
  mockNarrative(narrative());
  const v = sample("run_p01_approved");
  renderMeeting(v);
  const box = await screen.findByTestId("rm-notes");
  expect(v.rm_warnings.length).toBeGreaterThan(0);
  v.rm_warnings.forEach((w) => expect(box).toHaveTextContent(w.message));
  v.rm_warnings.forEach((w) => expect(screen.getByTestId("client-part")).not.toHaveTextContent(w.message));
});

test("shows the template banner", async () => {
  mockNarrative({ ...narrative(), source: "template", model: "" });
  renderMeeting(sample("run_p01_approved"));
  expect(await screen.findByText(/otomatik metin doğrulanamadı/)).toBeInTheDocument();
});

test("waiting shows Metin hazırlanıyor…; a 504 shows Tekrar dene", async () => {
  const get = vi
    .spyOn(api, "narrative")
    .mockRejectedValueOnce(new ApiError(504, "the meeting text is not ready yet; try again"))
    .mockResolvedValueOnce(narrative());
  renderMeeting(sample("run_p01_approved"));
  expect(screen.getByText("Metin hazırlanıyor…")).toBeInTheDocument();
  await userEvent.click(await screen.findByRole("button", { name: "Tekrar dene" }));
  expect(await screen.findByTestId("header-aim")).toBeInTheDocument();
  expect(get).toHaveBeenCalledTimes(2);
});

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
  const card = (await screen.findAllByTestId("rec-card"))[0];
  await userEvent.type(within(card).getByRole("textbox"), "ilk bu fon");
  vi.advanceTimersByTime(900);
  expect(notes.mock.calls.at(-1)![2]).toEqual({ [v.result.rm_selected[0]]: "ilk bu fon" });
});

test("Düzenle, then Metni onayla sends the edited text and shows it formatted", async () => {
  mockNarrative(narrative());
  const approve = vi
    .spyOn(api, "approveNarrative")
    .mockImplementation(async (_id, _lang, text) => ({ ...narrative(), status: "approved", rm_text: text, markdown: text }));
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: "Düzenle" }));
  const editor = screen.getByLabelText("Markdown");
  await userEvent.clear(editor);
  await userEvent.type(editor, "## Yeni başlık{enter}{enter}Kısa metin.");
  await userEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  expect(screen.getByText("Düzenlenmiş metin")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Yeni başlık" })).toBeInTheDocument();
  expect(screen.queryAllByTestId("rec-card")).toHaveLength(0);
  await userEvent.click(screen.getByRole("button", { name: "Metni onayla" }));
  expect(approve.mock.calls[0][2]).toBe("## Yeni başlık\n\nKısa metin.");
  expect(await screen.findByText(/Onaylandı/)).toBeInTheDocument();
});

test("Metni onayla without an edit sends the draft Markdown", async () => {
  mockNarrative(narrative());
  const approve = vi
    .spyOn(api, "approveNarrative")
    .mockImplementation(async (_id, _lang, text) => ({ ...narrative(), status: "approved", rm_text: text, markdown: text }));
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: "Metni onayla" }));
  expect(approve.mock.calls[0][2]).toBe(narrative().markdown);
  expect(await screen.findAllByTestId("rec-card")).not.toHaveLength(0);
});

test("glossary terms and the card downloads", async () => {
  mockNarrative(narrative());
  const v = sample("run_p01_approved");
  renderMeeting(v);
  for (const term of sample("glossary")) expect(await screen.findByText(term.form)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Markdown olarak indir/ })).toHaveAttribute("href", api.cardUrl(v.result.run_id));
  expect(screen.getByRole("link", { name: /PDF olarak indir/ })).toHaveAttribute("href", `/print/${v.result.run_id}`);
  expect(screen.getByTestId("card-footer")).toHaveTextContent(narrative().model);
});

test("EN asks for the EN text", async () => {
  const get = mockNarrative(sample("narrative_p01_en"));
  renderWith(<MeetingText view={sample("run_p01_approved")} />, { lang: "EN" });
  await screen.findByTestId("header-aim");
  expect(get.mock.calls[0][1]).toBe("EN");
});
