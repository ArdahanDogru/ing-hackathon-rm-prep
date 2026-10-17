import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import { renderDashboard, renderWith } from "../test/render";
import { sample } from "../test/samples";
import { Dashboard } from "./Dashboard";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());
const tableView = () => localStorage.setItem("rmprep.view.oneriler", "table"); // the cards view is the default

// --- plan W7 -------------------------------------------------------------------

test("lifecycle tabs: Görüşme metni only after approval", () => {
  renderDashboard(sample("run_p01_ready"));
  expect(screen.getByRole("tab", { name: /Hazırlık/ })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: /Görüşme metni/ })).toHaveAttribute("aria-disabled", "true");
});

test("brief card: profile line, plain sentence first, readiness 2 / 3", () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  expect(screen.getByTestId("brief-text")).toHaveTextContent(v.result.persona.durum);
  expect(screen.getByTestId("readiness")).toHaveTextContent("2 / 3");
  const card = screen.getByTestId("brief-card");
  expect(card).toHaveTextContent(`${v.result.persona.profil}, ${v.result.persona.yas}`);
  expect(card).toHaveTextContent(v.result.persona.risk_profili);
  v.result.persona.acik_kisitlar.forEach((k) => expect(card).toHaveTextContent(k));
});

test("the profile line shows the fund risk ceiling; with null only the profile", () => {
  const v = sample("run_p01_ready");
  const { unmount } = renderDashboard(v);
  expect(screen.getByTestId("brief-card")).toHaveTextContent(`${v.result.persona.risk_profili} (fon riski en fazla ${v.risk_ceiling} / 7)`);
  unmount();
  renderDashboard(sample("run_needs_input"));
  expect(screen.getByTestId("brief-card")).not.toHaveTextContent("fon riski en fazla");
});

test("agenda: at most 3 points and the Teyit edin items", () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  expect(screen.getAllByTestId("agenda-point").length).toBe(Math.min(3, v.talking_points.length));
  expect(screen.getAllByTestId("confirm-item")).toHaveLength(v.to_confirm.length);
});

test("ticking every Teyit edin item makes readiness 3 / 3 and clears the reminder", async () => {
  renderDashboard(sample("run_p01_ready"));
  expect(screen.getByText(/konu teyit edilmedi/)).toBeInTheDocument();
  for (const box of screen.getAllByRole("checkbox", { name: /teyit/i })) await userEvent.click(box);
  expect(screen.getByTestId("readiness")).toHaveTextContent("3 / 3");
  expect(screen.queryByText(/konu teyit edilmedi/)).toBeNull();
});

test("open Teyit edin items remind but do not block approval", () => {
  renderDashboard(sample("run_p01_ready"));
  expect(screen.getByText(/konu teyit edilmedi/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Onayla ve metni hazırla" })).toBeEnabled();
});

test("Öneriler: cards by default", () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  expect(screen.getByRole("button", { name: "Kartlar" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getAllByTestId("option-card")).toHaveLength(v.top.length);
  expect(screen.queryByRole("table")).toBeNull();
});

test("the table: deposit column last, short names, full name on hover", () => {
  const v = sample("run_p01_ready");
  tableView();
  renderDashboard(v);
  const heads = screen.getAllByTestId("compare-head");
  expect(heads).toHaveLength(v.top.length + 1);
  expect(heads.at(-1)).toHaveTextContent("Karşılaştırma");
  expect(heads[0]).toHaveAttribute("title", expect.stringContaining(v.options[v.top[0]].label));
  expect(heads[0]).toHaveTextContent(v.options[v.top[0]].short_label);
});

test("the table rows: match, return, real, risk, access, category, why", () => {
  const v = sample("run_p01_ready");
  tableView();
  renderDashboard(v);
  const table = screen.getByRole("table");
  for (const row of ["Uygunluk", "1 yıl getiri", "Reel", "SPK risk", "Paraya erişim", "Benzerleri arasında", "Neden bu müşteri"])
    expect(within(table).getByRole("rowheader", { name: new RegExp(row) })).toBeInTheDocument();
  const o = v.options[v.top[0]];
  expect(table).toHaveTextContent(`${o.rank!.position}. / ${o.rank!.of}`);
});

test("the view switch shows the table and is remembered", async () => {
  const { unmount } = renderDashboard(sample("run_p01_ready"));
  await userEvent.click(screen.getByRole("button", { name: "Tablo" }));
  expect(screen.getByRole("table")).toBeInTheDocument();
  expect(localStorage.getItem("rmprep.view.oneriler")).toBe("table");
  unmount();
  renderDashboard(sample("run_p01_ready"));
  expect(screen.getByRole("table")).toBeInTheDocument();
});

test("table with one recommendation", () => {
  const v = sample("run_p01_ready");
  tableView();
  renderDashboard({ ...v, top: v.top.slice(0, 1) });
  expect(screen.getAllByTestId("compare-head")).toHaveLength(2);
});

test("needs_rm_input shows questions instead of Öneriler", () => {
  renderDashboard(sample("run_needs_input"));
  expect(screen.queryByTestId("options-compare")).toBeNull();
  expect(screen.getAllByTestId("question").length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: "Onayla ve metni hazırla" })).toBeNull();
});

test("K mark opens the evidence pop-up", async () => {
  const ev = vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  renderDashboard(sample("run_p01_ready"));
  await userEvent.click(screen.getAllByRole("button", { name: "Kanıt" })[0]);
  expect(ev).toHaveBeenCalled();
});

// --- plan W8: fund card as a side panel ---------------------------------------------

test("a column click opens the drawer with the full name and three tiles", async () => {
  const v = sample("run_p01_ready");
  tableView();
  renderDashboard(v);
  await userEvent.click(screen.getAllByTestId("compare-head")[0]);
  const d = screen.getByRole("dialog");
  expect(d).toHaveTextContent(v.options[v.top[0]].label.replace(/\s+/g, " "));
  expect(within(d).getAllByTestId("fund-tile")).toHaveLength(3);
});

test("Escape closes the drawer and returns focus", async () => {
  tableView();
  renderDashboard(sample("run_p01_ready"));
  const head = screen.getAllByTestId("compare-head")[0];
  await userEvent.click(head);
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(head).toHaveFocus();
});

test("Seçime ekle / Seçimden çıkar changes the chips", async () => {
  tableView();
  renderDashboard(sample("run_p01_ready"));
  await userEvent.click(screen.getAllByTestId("compare-head")[0]);
  await userEvent.click(screen.getByRole("button", { name: "Seçimden çıkar" }));
  expect(screen.getAllByTestId("chip")).toHaveLength(2);
  expect(screen.getByRole("button", { name: "Seçime ekle" })).toBeInTheDocument();
});

test("a card click opens the drawer too; a K mark inside the evidence pop-up, not the drawer", async () => {
  const v = sample("run_p01_ready");
  vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  renderDashboard(v);
  await userEvent.click(screen.getByRole("button", { name: "Kartlar" }));
  const card = screen.getAllByTestId("option-card")[1];
  await userEvent.click(within(card).getByRole("button", { name: "Kanıt" }));
  expect(screen.getAllByRole("dialog")).toHaveLength(1); // the evidence pop-up only
  await userEvent.keyboard("{Escape}");
  await userEvent.click(card);
  expect(screen.getByRole("dialog")).toHaveTextContent(v.options[v.top[1]].short_label);
});

test("Escape with the evidence pop-up over the drawer closes only the pop-up", async () => {
  vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  tableView();
  renderDashboard(sample("run_p01_ready"));
  await userEvent.click(screen.getAllByTestId("compare-head")[0]);
  await userEvent.click(screen.getByRole("button", { name: /Kanıtları göster/ }));
  await userEvent.click(within(screen.getByRole("dialog")).getAllByRole("button", { name: /^E/ })[0]);
  expect(screen.getAllByRole("dialog")).toHaveLength(2);
  await userEvent.keyboard("{Escape}");
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
});

// --- kept from the first design ---------------------------------------------------

test("approval sends the selected chips", async () => {
  const approve = vi.spyOn(api, "approve").mockResolvedValue(sample("run_p01_approved"));
  const onView = vi.fn();
  renderDashboard(sample("run_p01_ready"), onView);
  expect(screen.getAllByTestId("chip")).toHaveLength(3);
  await userEvent.click(screen.getAllByRole("button", { name: /kaldır/i })[0]);
  await userEvent.click(screen.getByRole("button", { name: "Onayla ve metni hazırla" }));
  expect(approve.mock.calls[0][1]).toBe("approved");
  expect(approve.mock.calls[0][3]).toHaveLength(2);
  expect(onView).toHaveBeenCalled();
  expect(await screen.findByTestId("meeting-route")).toBeInTheDocument();
});

test("no chip selected: approval is disabled with the reason", async () => {
  renderDashboard(sample("run_p01_ready"));
  for (const b of screen.getAllByRole("button", { name: /kaldır/i })) await userEvent.click(b);
  expect(screen.getByRole("button", { name: "Onayla ve metni hazırla" })).toBeDisabled();
  expect(screen.getByText(/En az bir seçenek/)).toBeInTheDocument();
});

test("a rejection error from the API is shown", async () => {
  vi.spyOn(api, "approve").mockRejectedValue(new ApiError(422, "a rejection needs a note"));
  renderDashboard(sample("run_p01_ready"));
  await userEvent.click(screen.getByRole("button", { name: "Reddet" }));
  expect(await screen.findByText(/a rejection needs a note/)).toBeInTheDocument();
});

test("an approved run: the meeting tab is active and the bar links to the text", () => {
  renderDashboard(sample("run_p01_approved"));
  expect(screen.getByRole("tab", { name: /Görüşme metni/ })).not.toHaveAttribute("aria-disabled", "true");
  expect(screen.getByRole("link", { name: /Görüşme metnini aç/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Onayla ve metni hazırla" })).toBeNull();
});

test("a test run (an edited profile) can be approved (W30; see EditedProfile.test)", () => {
  renderDashboard(sample("run_test"));
  expect(screen.getByRole("button", { name: "Onayla ve metni hazırla" })).toBeEnabled();
  expect(screen.getByText(/Düzenlenmiş profil:/)).toBeInTheDocument();
});

test("an answer makes a new run", async () => {
  const v = sample("run_needs_input");
  const answer = vi.spyOn(api, "answer").mockResolvedValue(sample("run_p01_ready"));
  const onView = vi.fn();
  renderDashboard(v, onView);
  const q = v.result.questions.find((x) => x.blocking && x.answer === null)!;
  const box = screen.getAllByTestId("question")[0];
  if (q.choices.length) await userEvent.click(within(box).getByRole("button", { name: q.choices[0] }));
  else {
    await userEvent.type(within(box).getByLabelText("Yanıtınız"), "hisse olmasın");
    await userEvent.click(within(box).getByRole("button", { name: "Yanıtla" }));
  }
  expect(answer.mock.calls[0][1]).toBe(q.question_id);
  expect(onView).toHaveBeenCalled();
});

test("Profili düzenle opens the persona panel; Uygula calls onPersona", async () => {
  const onPersona = vi.fn();
  const v = sample("run_p01_ready");
  renderWith(<Dashboard view={v} onView={() => {}} onPersona={onPersona} />);
  await userEvent.click(screen.getByRole("button", { name: "Profili düzenle" }));
  await userEvent.click(screen.getByRole("button", { name: "Uygula" }));
  expect(onPersona.mock.calls[0][0].persona_id).toBe(v.result.persona.persona_id);
});

test("Kaynaklar lists the client file and its note", async () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  await userEvent.click(screen.getByRole("button", { name: /Kaynaklar/ }));
  expect(screen.getByTestId("brief-sources")).toHaveTextContent(v.result.persona.rm_notu);
});

test("no score numbers on the page", () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  const scores = v.result.options.map((o) => o.score.toFixed(3));
  scores.forEach((s) => expect(document.body.textContent).not.toContain(s));
  scores.forEach((s) => expect(document.body.textContent).not.toContain(s.replace(".", ",")));
});

test("EN labels", () => {
  renderDashboard(sample("run_p01_ready"), () => {}, "EN");
  expect(screen.getAllByText("Comparison").length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: "Approve and prepare the text" })).toBeInTheDocument();
});

test("after approval the bar shows the RM decision time", () => {
  const v = sample("run_p01_approved");
  renderDashboard(v);
  expect(screen.getByTestId("decided-at")).toHaveTextContent(/^Onaylandı: \d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$/);
  renderDashboard({ ...v, result: { ...v.result, rm_status: "rejected", rm_decided_at: "2026-10-12T09:15:00+03:00" } });
  expect(screen.getAllByTestId("decided-at")[1]).toHaveTextContent("Reddedildi: 12.10.2026 09:15");
});

test("a decision without a time (an older run) shows the status only", () => {
  const v = sample("run_p01_approved");
  renderDashboard({ ...v, result: { ...v.result, rm_decided_at: null } });
  expect(screen.getByTestId("decided-at")).toHaveTextContent(/^Onaylandı$/);
});

// --- W15 part 3: market note -----------------------------------------------------------

test("market note card: value, date and K per item, under the brief", async () => {
  const v = sample("run_p01_ready");
  const ev = vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  renderDashboard(v);
  const card = screen.getByTestId("market-note");
  expect(card).toHaveTextContent("Piyasa notu · TCMB EVDS");
  expect(screen.getByTestId("brief-card").compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  const rows = within(card).getAllByTestId("market-item");
  expect(rows).toHaveLength(v.market_note.length);
  const nf = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 }); // W42: the one unit formatter
  const tl = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 4 }); // TRY: 2 to 4
  v.market_note.forEach((m, i) => {
    expect(rows[i]).toHaveTextContent(m.label);
    expect(rows[i]).toHaveTextContent(m.unit === "pct" ? `%${nf.format(m.value)}` : `${tl.format(m.value)} TL`);
    expect(rows[i]).toHaveTextContent(m.as_of.split("-").reverse().join("."));
  });
  await userEvent.click(within(rows[1]).getByRole("button", { name: "Kanıt" }));
  expect(ev).toHaveBeenCalledWith(v.result.snapshot_id, v.market_note[1].evidence_id);
});

test("market values: a percent and a TRY price", async () => {
  const { marketValue } = await import("../components/MarketNote");
  const item = { key: "k", label: "l", as_of: "2026-10-09", evidence_id: "E" };
  expect(marketValue({ ...item, value: 37.25, unit: "pct" })).toBe("%37,25");
  expect(marketValue({ ...item, value: 49.1267, unit: "TRY" })).toBe("49,1267 TL"); // W42: the one unit formatter, TRY with up to 4 decimals
});

test("no market note and no bank rates: no market section (W25b: bank rates alone show it)", () => {
  renderDashboard({ ...sample("run_p01_ready"), market_note: [], bank_context: [] });
  expect(screen.queryByTestId("market-note")).toBeNull();
});

test("market note card in EN", () => {
  renderDashboard(sample("run_p01_ready"), () => {}, "EN");
  expect(screen.getByTestId("market-note")).toHaveTextContent("Market note · TCMB EVDS");
});

// --- W22: the Detaylar pane is gone; its content is in pop-up notes and the note box ---------

/** Open the note of a pipeline link ("Varsayımları gör" …). */
async function openNote(link: string) {
  await userEvent.click(screen.getByRole("button", { name: link }));
  return screen.getByRole("dialog");
}

test("no Detaylar pane any more", () => {
  renderDashboard(sample("run_p01_ready"));
  expect(screen.queryByRole("button", { name: /Detaylar/ })).toBeNull();
  for (const tab of ["Kategoriler", "Elenen", "Uyarılar", "RM notu"]) expect(screen.queryByRole("tab", { name: new RegExp(tab) })).toBeNull();
});

test("the pipeline links open one note each, titled with the count", async () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  const cases = [
    ["Varsayımları gör", `Varsayımlar (${v.assumptions.length})`, v.assumptions[0]],
    ["Veri notlarını gör", `Veri notları (${v.data_notes.length})`, v.data_notes[0].message],
    ["Elenenleri gör", `Elenen (${v.result.rejected.length})`, v.rejected_by_rule[0].label],
    ["Kategorileri gör", `Kategoriler (${v.categories.length})`, v.categories[0].label],
  ] as const;
  for (const [link, title, text] of cases) {
    const note = await openNote(link);
    expect(within(note).getByRole("heading", { name: title })).toBeInTheDocument();
    expect(note).toHaveAccessibleName(title);
    expect(note).toHaveTextContent(text);
    await userEvent.click(within(note).getByRole("button", { name: "Kapat" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  }
});

test("a note closes with Esc and an outside click; the focus goes back to its link", async () => {
  renderDashboard(sample("run_p01_ready"));
  const link = screen.getByRole("button", { name: "Varsayımları gör" });
  await openNote("Varsayımları gör");
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(link).toHaveFocus();
  await openNote("Varsayımları gör");
  await userEvent.click(screen.getByTestId("note-backdrop"));
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("a note keeps the focus inside (Tab and Shift+Tab wrap)", async () => {
  renderDashboard(sample("run_p01_ready"));
  const note = await openNote("Elenenleri gör");
  const focusable = within(note).getAllByRole("button");
  expect(focusable[0]).toHaveFocus();
  await userEvent.tab({ shift: true });
  expect(focusable.at(-1)).toHaveFocus();
  await userEvent.tab();
  expect(focusable[0]).toHaveFocus();
});

test("Elenen: one row per rule with its options", async () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  const note = await openNote("Elenenleri gör");
  const rule = v.rejected_by_rule[0];
  await userEvent.click(within(note).getByRole("button", { name: new RegExp(rule.label) }));
  const list = within(note).getByTestId(`rule-${rule.rule_id}`);
  rule.options.slice(0, 5).forEach((o) => expect(list).toHaveTextContent(o.label.replace(/\s+/g, " ").trim()));
  expect(note).toHaveTextContent("Bir fon birden fazla kurala takılabilir.");
});

test("Kategoriler: a class opens to its sub-types, a sub-type to at most 5 funds (W32; see Categories.test)", async () => {
  renderDashboard(sample("run_p01_ready"));
  const note = await openNote("Kategorileri gör");
  const first = within(note).getAllByTestId("category")[0];
  await userEvent.click(within(first).getAllByRole("button")[0]);
  const sub = within(first).getAllByTestId("subtype")[0];
  await userEvent.click(within(sub).getAllByRole("button")[0]);
  const rows = within(sub).getAllByTestId("fund-row");
  expect(rows.length).toBeGreaterThan(0);
  expect(rows.length).toBeLessThanOrEqual(5);
});

test("the note box: Piyasa notu, Uyarılar and RM notu, each with its own title", () => {
  const v = sample("run_p01_ready");
  const w = { code: "concentration", message: "Üç öneri de TL faizine bağlı.", evidence_ids: ["E2075d858"], option_ids: [], audience: "client" as const };
  renderDashboard({ ...v, client_warnings: [w] });
  const box = screen.getByTestId("notes-box");
  expect(within(box).getByTestId("market-note")).toHaveTextContent("Piyasa notu · TCMB EVDS");
  const warnings = within(box).getByTestId("box-warnings");
  expect(warnings).toHaveTextContent("Uyarılar");
  expect(warnings).toHaveTextContent(w.message);
  expect(within(warnings).getByRole("button", { name: "Kanıt" })).toBeInTheDocument();
  const rm = within(box).getByTestId("box-rm-note");
  expect(rm).toHaveTextContent("RM notu");
  v.rm_warnings.forEach((x) => expect(rm).toHaveTextContent(x.message));
  expect(rm).not.toHaveTextContent(w.message); // client warnings never under RM notu
});

test("the note box: an empty section says so", () => {
  const v = sample("run_p01_ready");
  renderDashboard({ ...v, client_warnings: [], rm_warnings: [] });
  expect(screen.getByTestId("box-warnings")).toHaveTextContent("Uyarı yok");
  expect(screen.getByTestId("box-rm-note")).toHaveTextContent("RM notu yok");
});

test("a warning K mark opens the evidence pop-up", async () => {
  const v = sample("run_p01_ready");
  const ev = vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  const w = { code: "concentration", message: "Üç öneri de TL faizine bağlı.", evidence_ids: ["E2075d858"], option_ids: [], audience: "client" as const };
  renderDashboard({ ...v, client_warnings: [w] });
  await userEvent.click(within(screen.getByTestId("box-warnings")).getByRole("button", { name: "Kanıt" }));
  expect(ev).toHaveBeenCalledWith(v.result.snapshot_id, "E2075d858");
});

test("W22 EN: the notes and the box", async () => {
  const v = sample("run_p01_ready");
  renderDashboard({ ...v, client_warnings: [] }, () => {}, "EN");
  expect(screen.getByTestId("box-warnings")).toHaveTextContent("No warnings");
  expect(screen.getByTestId("box-rm-note")).toHaveTextContent("RM note");
  await userEvent.click(screen.getByRole("button", { name: "See the assumptions" }));
  expect(screen.getByRole("dialog")).toHaveAccessibleName(`Assumptions (${v.assumptions.length})`);
  expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
});
