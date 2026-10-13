import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderDashboard } from "../test/render";
import { sample } from "../test/samples";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

async function openAllocation() {
  await userEvent.click(screen.getByRole("button", { name: "Dağılım" }));
}

test("the switch has Dağılım; one row per class; the choice is remembered", async () => {
  const v = sample("run_p01_ready");
  const { unmount } = renderDashboard(v);
  await openAllocation();
  expect(screen.getAllByTestId("alloc-row")).toHaveLength(v.allocation.length);
  expect(localStorage.getItem("rmprep.view.oneriler")).toBe("allocation");
  unmount();
  renderDashboard(sample("run_p01_ready"));
  expect(screen.getAllByTestId("alloc-row")).toHaveLength(v.allocation.length);
});

test("a row: label, band bar on 0-100 with the range; dengeli has no bar", async () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  await openAllocation();
  const rows = screen.getAllByTestId("alloc-row");
  v.allocation.forEach((a, i) => {
    expect(rows[i]).toHaveTextContent(a.label);
    const bar = within(rows[i]).queryByTestId("alloc-band");
    if (a.low === null || a.high === null) {
      expect(bar).toBeNull();
      expect(rows[i]).toHaveTextContent("hedef bant yok");
    } else {
      expect(bar!.style.left).toBe(`${a.low}%`);
      expect(bar!.style.width).toBe(`${a.high - a.low}%`);
      expect(rows[i]).toHaveTextContent(`%${a.low}–${a.high}`);
    }
  });
});

test("an inferred band has an asterisk with the tooltip", async () => {
  const v = sample("run_p01_ready");
  v.allocation[0] = { ...v.allocation[0], inferred: true, source: "çıkarım" };
  renderDashboard(v);
  await openAllocation();
  const mark = within(screen.getAllByTestId("alloc-row")[0]).getByText("*");
  expect(mark).toHaveAttribute("title", "Kaynak yok: Muhafazakâr–Dengeli arası çıkarım");
  expect(within(screen.getAllByTestId("alloc-row")[1]).queryByText("*")).toBeNull();
});

test("the best option: short name, real 1-year return, SPK risk; a click opens the fund card", async () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  await openAllocation();
  const i = v.allocation.findIndex((a) => a.option_id && !a.note);
  const o = v.options[v.allocation[i].option_id!];
  const row = screen.getAllByTestId("alloc-row")[i];
  const pick = within(row).getByRole("button", { name: new RegExp(o.short_label.replace(/[()]/g, "\\$&")) });
  expect(row).toHaveTextContent(`risk ${o.risk!.level}/7`);
  await userEvent.click(pick);
  expect(screen.getByRole("dialog")).toHaveTextContent(o.label.replace(/\s+/g, " "));
});

test("note texts: a class without an option, and a negative real return next to its option", async () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  await openAllocation();
  const rows = screen.getAllByTestId("alloc-row");
  v.allocation.forEach((a, i) => {
    if (a.note_text) expect(rows[i]).toHaveTextContent(a.note_text);
    if (!a.option_id) expect(within(rows[i]).queryByRole("button")).toBeNull();
  });
  expect(v.allocation.some((a) => a.note === "ceiling" && !a.option_id)).toBe(true);
  expect(v.allocation.some((a) => a.note === "negative_real" && a.option_id)).toBe(true);
});

test("the holding hints above the rows and the footer with the source", async () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  await openAllocation();
  const view = screen.getByTestId("allocation");
  v.allocation_notes.forEach((n) => expect(within(view).getByTestId("alloc-notes")).toHaveTextContent(n));
  expect(within(view).getByTestId("alloc-footer")).toHaveTextContent(
    `Gösterge model dağılım (stratejik), tutar değildir. Kaynak: ${v.allocation[0].source}`,
  );
  expect(view).not.toHaveTextContent(/fazla|eksik|mevcut/i);
});

test("no allocation: no Dağılım button, a remembered choice falls back to the cards", () => {
  localStorage.setItem("rmprep.view.oneriler", "allocation");
  const v = sample("run_p01_ready");
  renderDashboard({ ...v, allocation: [], allocation_notes: [] });
  expect(screen.queryByRole("button", { name: "Dağılım" })).toBeNull();
  expect(screen.getAllByTestId("option-card").length).toBeGreaterThan(0);
});

test("EN labels", async () => {
  renderDashboard(sample("run_p01_ready"), () => {}, "EN");
  await userEvent.click(screen.getByRole("button", { name: "Allocation" }));
  expect(screen.getByTestId("alloc-footer")).toHaveTextContent("Indicative model allocation");
});
