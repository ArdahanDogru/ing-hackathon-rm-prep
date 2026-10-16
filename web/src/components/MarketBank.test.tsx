// W25b: the bank rates line in the "Piyasa notu" panel (RunView.bank_context, once per run).
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "../api/client";
import type { RunView } from "../api/types";
import { renderDashboard } from "../test/render";
import { sample } from "../test/samples";

afterEach(() => vi.restoreAllMocks());

const view = () => sample("run_p01_ready");
const line = () => within(screen.getByTestId("market-note")).getByTestId("bank-line");
const parts = () => within(line()).getAllByTestId("bank-part");

test("the sample's line: the title and three rows, the own row bold, the note under it", () => {
  const v = view();
  const entry = v.bank_context![0];
  expect(entry.title).toBe("Vadeli mevduat, ~32 gün, 100–250 bin TL");
  renderDashboard(v);
  expect(line()).toHaveTextContent(entry.title);
  expect(parts()).toHaveLength(3);
  expect(parts()[0]).toHaveClass("font-bold");
  expect(parts()[0]).toHaveTextContent("ING e-Vadeli %34,50");
  expect(parts()[0]).toHaveTextContent("16.10.2026");
  expect(within(parts()[0]).queryByTestId("bank-diff")).toBeNull();
  expect(screen.getByTestId("market-note")).toHaveTextContent(entry.note);
});

test("a bank row: the rate, the date and the signed difference in neutral grey", () => {
  renderDashboard(view());
  const isbank = parts()[1];
  expect(isbank).not.toHaveClass("font-bold");
  expect(isbank).toHaveTextContent("İş Bankası (kampanya) %37,00");
  const diff = within(isbank).getByTestId("bank-diff");
  expect(diff).toHaveTextContent("+2,50 puan");
  expect(diff).toHaveClass("text-[#475467]");
});

test("a missing row says veri yok; a negative difference uses the minus sign; a stale date is amber", () => {
  const v = view();
  const rows = v.bank_context![0].rows;
  rows[1] = { ...rows[1], value: 31, diff_pp: -3.5, stale: true, as_of: "2026-10-09" };
  renderDashboard(v);
  expect(parts()[2]).toHaveTextContent("Ziraat (internet) veri yok");
  expect(within(parts()[2]).queryByRole("button", { name: "Kanıt" })).toBeNull();
  expect(within(parts()[1]).getByTestId("bank-diff")).toHaveTextContent("−3,50 puan");
  const date = within(parts()[1]).getByTestId("bank-date");
  expect(date).toHaveAttribute("data-stale", "true");
  expect(date).toHaveTextContent("09.10.2026 · eski");
});

test("the K mark opens the evidence pop-up", async () => {
  const v = view();
  const ev = vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  renderDashboard(v);
  await userEvent.click(within(parts()[1]).getByRole("button", { name: "Kanıt" }));
  expect(ev).toHaveBeenCalledWith(v.result.snapshot_id, v.bank_context![0].rows[1].evidence_id);
});

test("an empty list: no line; no market values but bank rates: the section shows the line", () => {
  const { unmount } = renderDashboard({ ...view(), bank_context: [] });
  expect(within(screen.getByTestId("market-note")).queryByTestId("bank-line")).toBeNull();
  unmount();
  renderDashboard({ ...view(), market_note: [] } as RunView);
  expect(line()).toBeInTheDocument();
  expect(within(screen.getByTestId("market-note")).queryAllByTestId("market-item")).toHaveLength(0);
});

test("W25b EN", () => {
  const v = view();
  v.bank_context![0].rows[2] = { ...v.bank_context![0].rows[2] };
  renderDashboard(v, () => {}, "EN");
  expect(within(parts()[1]).getByTestId("bank-diff")).toHaveTextContent("+2,50 points");
  expect(parts()[2]).toHaveTextContent("no data");
});
