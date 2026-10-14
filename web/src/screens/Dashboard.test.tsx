import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import { renderDashboard, renderWith } from "../test/render";
import { sample, withMarketNote } from "../test/samples";
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
  for (const row of ["Uygunluk", "1 yıl getiri", "Reel", "SPK risk", "Paraya erişim", "Kategorisinde", "Neden bu müşteri"])
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

test("Detaylar opens categories, assumptions, data notes, eliminated, RM note", async () => {
  renderDashboard(sample("run_p01_ready"));
  await userEvent.click(screen.getByRole("button", { name: /Detaylar/ }));
  for (const t of ["Kategoriler", "Varsayımlar", "Veri notları", "Elenen", "Uyarılar", "RM notu"])
    expect(screen.getByRole("tab", { name: new RegExp(t) })).toBeInTheDocument();
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

test("Ayrıntılar in Detaylar opens the same drawer", async () => {
  renderDashboard(sample("run_p01_ready"));
  await userEvent.click(screen.getByRole("button", { name: /Detaylar/ }));
  await userEvent.click(within(screen.getAllByTestId("category")[0]).getByRole("button", { expanded: false }));
  await userEvent.click(screen.getAllByRole("button", { name: "Ayrıntılar" })[0]);
  expect(within(screen.getByRole("dialog")).getAllByTestId("fund-tile")).toHaveLength(3);
});

// --- kept from the first design ---------------------------------------------------

test("Detaylar: a category opens at most 3 funds; RM notu holds the RM-only warnings", async () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  await userEvent.click(screen.getByRole("button", { name: /Detaylar/ }));
  const first = screen.getAllByTestId("category")[0];
  await userEvent.click(within(first).getByRole("button", { expanded: false }));
  const rows = within(first).getAllByTestId("fund-row");
  expect(rows.length).toBeGreaterThan(0);
  expect(rows.length).toBeLessThanOrEqual(3);
  await userEvent.click(screen.getByRole("tab", { name: /RM notu/ }));
  v.rm_warnings.forEach((w) => expect(screen.getByRole("tabpanel")).toHaveTextContent(w.message));
});

test("Detaylar: client warnings in Uyarılar, never under RM notu", async () => {
  const v = sample("run_p01_ready");
  const w = { code: "concentration", message: "Üç öneri de TL faizine bağlı.", evidence_ids: [], option_ids: [], audience: "client" as const };
  renderDashboard({ ...v, client_warnings: [w] });
  expect(screen.getByRole("button", { name: /Detaylar/ })).toHaveTextContent("Uyarılar (1)");
  await userEvent.click(screen.getByRole("button", { name: /Detaylar/ }));
  await userEvent.click(screen.getByRole("tab", { name: /Uyarılar/ }));
  expect(screen.getByRole("tabpanel")).toHaveTextContent(w.message);
  await userEvent.click(screen.getByRole("tab", { name: /RM notu/ }));
  expect(screen.getByRole("tabpanel")).not.toHaveTextContent(w.message);
});

test("Detaylar: Elenen opens one row per rule", async () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  await userEvent.click(screen.getByRole("button", { name: /Detaylar/ }));
  await userEvent.click(screen.getByRole("tab", { name: /Elenen/ }));
  const rule = v.rejected_by_rule[0];
  await userEvent.click(screen.getByRole("button", { name: new RegExp(rule.label) }));
  const list = screen.getByTestId(`rule-${rule.rule_id}`);
  rule.options.slice(0, 5).forEach((o) => expect(list).toHaveTextContent(o.label.replace(/\s+/g, " ").trim()));
});

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

test("test run disables approval", () => {
  renderDashboard(sample("run_test"));
  expect(screen.getByRole("button", { name: "Onayla ve metni hazırla" })).toBeDisabled();
  expect(screen.getByText(/Test:/)).toBeInTheDocument();
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
  const v = withMarketNote(sample("run_p01_ready"));
  const ev = vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  renderDashboard(v);
  const card = screen.getByTestId("market-note");
  expect(card).toHaveTextContent("Piyasa notu · TCMB EVDS");
  expect(screen.getByTestId("brief-card").compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  const rows = within(card).getAllByTestId("market-item");
  expect(rows).toHaveLength(3);
  expect(rows[0]).toHaveTextContent("Politika faizi");
  expect(rows[0]).toHaveTextContent("%40,5");
  expect(rows[0]).toHaveTextContent("09.10.2026");
  expect(rows[1]).toHaveTextContent("41,2345 TL");
  expect(rows[2]).toHaveTextContent("%40,48");
  await userEvent.click(within(rows[1]).getByRole("button", { name: "Kanıt" }));
  expect(ev).toHaveBeenCalledWith(v.result.snapshot_id, "ev-usd-try");
});

test("no market note: no card", () => {
  renderDashboard({ ...sample("run_p01_ready"), market_note: [] });
  expect(screen.queryByTestId("market-note")).toBeNull();
});

test("market note card in EN", () => {
  renderDashboard(withMarketNote(sample("run_p01_ready")), () => {}, "EN");
  expect(screen.getByTestId("market-note")).toHaveTextContent("Market note · TCMB EVDS");
});
