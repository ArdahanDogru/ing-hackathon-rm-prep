// W25b: the bank rates line in the "Piyasa notu" panel (RunView.bank_context, once per run).
// W46 (the user, 2026-10-17): only the own ING row; no other bank and no note.
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

test("the sample's line: the title and the own ING row only, bold, without a note", () => {
  const v = view();
  const entry = v.bank_context![0];
  expect(entry.rows).toHaveLength(3); // the API still sends the other banks
  expect(entry.title).toBe("Vadeli mevduat, ~32 gün, 100–250 bin TL");
  renderDashboard(v);
  expect(line()).toHaveTextContent(entry.title);
  expect(parts()).toHaveLength(1);
  expect(parts()[0]).toHaveClass("font-bold");
  expect(parts()[0]).toHaveTextContent("ING e-Vadeli %34,50");
  expect(parts()[0]).toHaveTextContent("16.10.2026");
  expect(within(parts()[0]).queryByTestId("bank-diff")).toBeNull();
  const note = screen.getByTestId("market-note");
  expect(note).not.toHaveTextContent("İş Bankası");
  expect(note).not.toHaveTextContent("Ziraat");
  expect(note).not.toHaveTextContent("puan");
  expect(note).not.toHaveTextContent(entry.note);
});

test("the K mark of the own row opens the evidence pop-up", async () => {
  const v = view();
  const ev = vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  renderDashboard(v);
  await userEvent.click(within(parts()[0]).getByRole("button", { name: "Kanıt" }));
  expect(ev).toHaveBeenCalledWith(v.result.snapshot_id, v.bank_context![0].rows[0].evidence_id);
});

test("an entry without an own row: no line", () => {
  const v = view();
  v.bank_context![0].rows = v.bank_context![0].rows.filter((r) => !r.own);
  renderDashboard(v);
  expect(within(screen.getByTestId("market-note")).queryByTestId("bank-line")).toBeNull();
});

test("an empty list: no line; no market values but bank rates: the section shows the line", () => {
  const { unmount } = renderDashboard({ ...view(), bank_context: [] });
  expect(within(screen.getByTestId("market-note")).queryByTestId("bank-line")).toBeNull();
  unmount();
  renderDashboard({ ...view(), market_note: [] } as RunView);
  expect(line()).toBeInTheDocument();
  expect(within(screen.getByTestId("market-note")).queryAllByTestId("market-item")).toHaveLength(0);
});
