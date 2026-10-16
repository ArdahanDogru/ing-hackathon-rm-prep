// W25: other banks' rates in the fund card as context for the RM (not in the score).
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { BankContext, Lang, OptionView } from "../api/types";
import { LangContext } from "../i18n";
import { sample } from "../test/samples";
import { FundCard } from "./FundCard";
import { OptionsTable } from "./OptionsTable";

const ID = "time_deposit:ing_e_vadeli";
const option = (): OptionView => sample("run_p01_ready").options[ID];

function show(o: OptionView, lang: Lang = "TR", onEvidence = vi.fn()) {
  render(
    <LangContext.Provider value={lang}>
      <FundCard option={o} onEvidence={onEvidence} />
    </LangContext.Provider>,
  );
  return onEvidence;
}
const rows = () => within(screen.getByTestId("bank-context")).getAllByTestId("bank-row");

test("the sample's time deposit has the block with the own row and two banks", () => {
  expect(option().bank_context?.rows).toHaveLength(3);
  show(option());
  const block = screen.getByTestId("bank-context");
  expect(block).toHaveTextContent("Diğer bankalar");
  expect(block).toHaveTextContent("bağlam — puana dahil değil");
  expect(rows()).toHaveLength(3);
});

test("the own row: bold, the rate in Turkish format with its K mark, the date, no difference", async () => {
  const onEvidence = show(option());
  const own = rows()[0];
  expect(own).toHaveAttribute("data-own", "true");
  expect(own).toHaveClass("font-bold");
  expect(own).toHaveTextContent("ING e-Vadeli");
  expect(own).toHaveTextContent("32-45 gün / 99.999,99-250.000 TL");
  expect(own).toHaveTextContent("34,50 %");
  expect(own).toHaveTextContent("16.10.2026");
  expect(within(own).queryByTestId("bank-diff")).toBeNull();
  await userEvent.click(within(own).getByRole("button", { name: "Kanıt" }));
  expect(onEvidence).toHaveBeenCalledWith("Ef018fa9e");
});

test("a bank row: the rate and the signed difference in points, in a neutral color", () => {
  show(option());
  const isbank = rows()[1];
  expect(isbank).not.toHaveClass("font-bold");
  expect(isbank).toHaveTextContent("İş Bankası (kampanya)");
  expect(isbank).toHaveTextContent("37,00 %");
  const diff = within(isbank).getByTestId("bank-diff");
  expect(diff).toHaveTextContent("+2,50 puan");
  expect(diff.className).not.toMatch(/green|red|#067647|#B42318|#12B76A|#F04438/i);
});

test("a negative difference uses the Turkish minus sign", () => {
  const o = option();
  const ctx = o.bank_context as BankContext;
  ctx.rows[1] = { ...ctx.rows[1], value: 31, diff_pp: -3.5 };
  show(o);
  expect(within(rows()[1]).getByTestId("bank-diff")).toHaveTextContent("−3,50 puan");
});

test("a missing row says veri yok, without a K mark or a difference", () => {
  show(option());
  const ziraat = rows()[2];
  expect(ziraat).toHaveTextContent("Ziraat (internet)");
  expect(ziraat).toHaveTextContent("veri yok");
  expect(within(ziraat).queryByRole("button", { name: "Kanıt" })).toBeNull();
  expect(within(ziraat).queryByTestId("bank-diff")).toBeNull();
});

test("a stale row shows its date in the stale style", () => {
  const o = option();
  const ctx = o.bank_context as BankContext;
  ctx.rows[1] = { ...ctx.rows[1], stale: true, as_of: "2026-10-09" };
  show(o);
  const date = within(rows()[1]).getByTestId("bank-date");
  expect(date).toHaveAttribute("data-stale", "true");
  expect(date).toHaveTextContent("09.10.2026");
  expect(date).toHaveTextContent("eski");
  expect(within(rows()[0]).getByTestId("bank-date")).not.toHaveAttribute("data-stale");
});

test("the note under the block", () => {
  show(option());
  expect(screen.getByTestId("bank-context")).toHaveTextContent(option().bank_context!.note);
});

test("no block when bank_context is null (a fund)", () => {
  const v = sample("run_p01_ready");
  const fund = v.options[v.top[0]];
  expect(fund.bank_context ?? null).toBeNull();
  show(fund);
  expect(screen.queryByTestId("bank-context")).toBeNull();
});

test("not in the options table", () => {
  render(<OptionsTable options={[option()]} baseline={null} onOpen={vi.fn()} onEvidence={vi.fn()} />);
  expect(screen.queryByText(/Diğer bankalar/)).toBeNull();
  expect(screen.queryByText(/37,00/)).toBeNull();
});

test("W25 EN labels", () => {
  show(option(), "EN");
  const block = screen.getByTestId("bank-context");
  expect(block).toHaveTextContent("Other banks");
  expect(block).toHaveTextContent("context — not in the score");
  expect(within(rows()[1]).getByTestId("bank-diff")).toHaveTextContent("+2,50 points");
  expect(rows()[2]).toHaveTextContent("no data");
});
