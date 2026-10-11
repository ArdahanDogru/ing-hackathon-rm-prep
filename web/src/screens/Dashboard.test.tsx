import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import { renderDashboard, renderWith } from "../test/render";
import { sample } from "../test/samples";
import { Dashboard } from "./Dashboard";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

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

test("Öneriler: table by default, deposit column last, short names, full name on hover", () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  const heads = screen.getAllByTestId("compare-head");
  expect(heads).toHaveLength(v.top.length + 1);
  expect(heads.at(-1)).toHaveTextContent("Karşılaştırma");
  expect(heads[0]).toHaveAttribute("title", expect.stringContaining(v.options[v.top[0]].label));
  expect(heads[0]).toHaveTextContent(v.options[v.top[0]].short_label);
});

test("the table rows: match, return, real, risk, access, category, why", () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  const table = screen.getByRole("table");
  for (const row of ["Uygunluk", "1 yıl getiri", "Reel", "SPK risk", "Paraya erişim", "Kategorisinde", "Neden bu müşteri"])
    expect(within(table).getByRole("rowheader", { name: new RegExp(row) })).toBeInTheDocument();
  const o = v.options[v.top[0]];
  expect(table).toHaveTextContent(`${o.rank!.position}. / ${o.rank!.of}`);
});

test("the view switch shows cards and is remembered", async () => {
  const { unmount } = renderDashboard(sample("run_p01_ready"));
  await userEvent.click(screen.getByRole("button", { name: "Kartlar" }));
  expect(screen.getAllByTestId("option-card")).toHaveLength(3);
  expect(localStorage.getItem("rmprep.view.oneriler")).toBe("cards");
  unmount();
  renderDashboard(sample("run_p01_ready"));
  expect(screen.getAllByTestId("option-card")).toHaveLength(3);
});

test("table with one recommendation", () => {
  const v = sample("run_p01_ready");
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
  for (const t of ["Kategoriler", "Varsayımlar", "Veri notları", "Elenen", "RM notu"])
    expect(screen.getByRole("tab", { name: new RegExp(t) })).toBeInTheDocument();
});

test("K mark opens the evidence pop-up", async () => {
  const ev = vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  renderDashboard(sample("run_p01_ready"));
  await userEvent.click(screen.getAllByRole("button", { name: "Kanıt" })[0]);
  expect(ev).toHaveBeenCalled();
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
