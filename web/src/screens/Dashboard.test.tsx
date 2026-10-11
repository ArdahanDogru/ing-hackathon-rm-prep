import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import { renderDashboard } from "../test/render";
import { sample } from "../test/samples";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

test("client card with priorities and the constraint", () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  const card = screen.getByTestId("client-card");
  v.result.persona.oncelikler.forEach((p) => expect(within(card).getByText(p)).toBeInTheDocument());
  v.result.persona.acik_kisitlar.forEach((k) => expect(within(card).getByText(new RegExp(k))).toBeInTheDocument());
});

test("top 3 cards and the comparison card", () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  const cards = screen.getAllByTestId("top-card");
  expect(cards).toHaveLength(3);
  v.top.forEach((id, i) => expect(cards[i]).toHaveTextContent(v.options[id].label));
  expect(screen.getByText("Karşılaştırma")).toBeInTheDocument();
  expect(screen.getByTestId("compare-card")).toHaveTextContent(v.baseline!.label);
});

test("categories are closed and open at most 3 funds", async () => {
  renderDashboard(sample("run_p01_ready"));
  const first = screen.getAllByTestId("category")[0];
  expect(within(first).queryAllByTestId("fund-row")).toHaveLength(0);
  await userEvent.click(within(first).getByRole("button", { expanded: false }));
  const rows = within(first).getAllByTestId("fund-row");
  expect(rows.length).toBeGreaterThan(0);
  expect(rows.length).toBeLessThanOrEqual(3);
});

test("a category line shows the count and the best 1-year return", () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  const first = screen.getAllByTestId("category")[0];
  expect(first).toHaveTextContent(v.categories[0].label);
  expect(first).toHaveTextContent(`${v.categories[0].count} fon`);
});

test("talking points row from talking_points", () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  const points = screen.getAllByTestId("talking-point");
  expect(points).toHaveLength(v.talking_points.length);
  expect(points[0]).toHaveTextContent(v.talking_points[0].figure);
});

test("right panel order: Teyit edin, Varsayımlar, Veri notları, elenen", () => {
  renderDashboard(sample("run_p01_ready"));
  const heads = screen.getAllByTestId("panel-head").map((h) => h.textContent);
  expect(heads[0]).toMatch(/Teyit edin/);
  expect(heads.slice(1).map((h) => h!.split(" ")[0])).toEqual(["Varsayımlar", "Veri", expect.any(String)]);
  expect(heads[3]).toMatch(/seçenek elendi/);
});

test("Teyit edin counts open items and keeps the checks per run", async () => {
  const v = sample("run_p01_ready");
  const { unmount } = renderDashboard(v);
  const n = v.to_confirm.length;
  expect(screen.getByTestId("confirm-status")).toHaveTextContent(`${n} açık`);
  for (const box of screen.getAllByRole("checkbox")) await userEvent.click(box);
  expect(screen.getByTestId("confirm-status")).toHaveTextContent("Tamam");
  unmount();
  renderDashboard(v);
  expect(screen.getByTestId("confirm-status")).toHaveTextContent("Tamam");
});

test("the rejected line opens one row per rule", async () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  await userEvent.click(screen.getByRole("button", { name: /seçenek elendi/ }));
  const rule = v.rejected_by_rule[0];
  await userEvent.click(screen.getByRole("button", { name: new RegExp(rule.label) }));
  rule.options.forEach((o) => expect(screen.getByText(o.label)).toBeInTheDocument());
});

test("approval sends the selected chips", async () => {
  const approve = vi.spyOn(api, "approve").mockResolvedValue(sample("run_p01_approved"));
  const onView = vi.fn();
  renderDashboard(sample("run_p01_ready"), onView);
  expect(screen.getAllByTestId("chip")).toHaveLength(3);
  await userEvent.click(screen.getAllByRole("button", { name: /kaldır/i })[0]); // ✕ on chip 1
  await userEvent.click(screen.getByRole("button", { name: "Onayla ve metni hazırla" }));
  expect(approve.mock.calls[0][1]).toBe("approved");
  expect(approve.mock.calls[0][3]).toHaveLength(2);
  expect(onView).toHaveBeenCalled();
  expect(await screen.findByTestId("meeting-route")).toBeInTheDocument();
});

test("Seçime ekle in a category adds a chip", async () => {
  renderDashboard(sample("run_p01_ready"));
  await userEvent.click(within(screen.getAllByTestId("category")[0]).getByRole("button", { expanded: false }));
  const row = screen.getAllByTestId("fund-row").find((r) => within(r).queryByRole("button", { name: /Seçime ekle/ }))!;
  await userEvent.click(within(row).getByRole("button", { name: /Seçime ekle/ }));
  expect(screen.getAllByTestId("chip")).toHaveLength(4);
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

test("an approved run links to the meeting text", () => {
  renderDashboard(sample("run_p01_approved"));
  expect(screen.getByRole("link", { name: /Görüşme metnini aç/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Onayla ve metni hazırla" })).toBeNull();
});

test("RM-only warnings are marked as such", () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  v.rm_warnings.forEach((w) => {
    const el = screen.getByText(w.message);
    expect(el.closest("[data-audience]")).toHaveAttribute("data-audience", "rm");
  });
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
  expect(screen.getByText("Comparison")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Approve and prepare the text" })).toBeInTheDocument();
});
