import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { explain } from "../explain";
import { LangContext } from "../i18n";
import { sample } from "../test/samples";
import { FundCard } from "./FundCard";

const setup = (id = "fund:PPN") => {
  const v = sample("run_p01_ready");
  return { v, o: v.options[id], x: explain(v, id)! };
};

test("the fund card shows the engine's reasoning instead of the why lines", () => {
  const { o, x } = setup();
  const { container } = render(<FundCard option={o} explanation={x} />);
  expect(screen.getByRole("heading", { name: "Neden bu öneri?" })).toBeInTheDocument();
  expect(screen.queryByText("Bu müşteri için neden?")).toBeNull();
  expect(container).toHaveTextContent(`${x.of} aday içinde 1. sıra`);
  expect(screen.getAllByTestId("score-row")).toHaveLength(x.criteria.length + x.penalties.length);
  x.criteria.forEach((r) => expect(container).toHaveTextContent(r.reason));
  expect(screen.getByTestId("total-score")).toHaveTextContent(new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(x.score));
  expect(container).toHaveTextContent("Kararlılık %100 · kararlı");
  expect(container).toHaveTextContent("Veri güveni %90 · yüksek");
});

test("priority tags sit on their criteria", () => {
  const { o, x } = setup();
  render(<FundCard option={o} explanation={x} />);
  const income = screen.getAllByTestId("score-row").find((r) => r.textContent?.startsWith("Düzenli gelir"))!;
  expect(within(income).getByTestId("priority-tag")).toHaveTextContent("düzenli gelir");
});

test("a passed rule opens its evidence", async () => {
  const { o, x } = setup();
  const onEvidence = vi.fn();
  render(<FundCard option={o} explanation={x} onEvidence={onEvidence} />);
  expect(screen.getByText("Geçtiği kesin kurallar")).toBeInTheDocument();
  const id = x.constraints.find((c) => c.rule_id === "risk_ceiling")!.evidence_ids[0];
  await userEvent.click(screen.getByRole("button", { name: id }));
  expect(onEvidence).toHaveBeenCalledWith(id);
});

test("the closest alternative names the largest difference", () => {
  const { o, x } = setup();
  render(<FundCard option={o} explanation={x} />);
  const alt = screen.getByTestId("alternative");
  expect(alt).toHaveTextContent(x.alternative!.label);
  expect(alt).toHaveTextContent(x.alternative!.diff ? "En büyük fark" : "Puan bileşenleri aynı.");
});

test("the criterion allocation_gap shows as Portföy açığı (W18), in EN too", () => {
  const { v, o } = setup();
  const s = v.result.options.find((y) => y.option.option_id === "fund:PPN")!;
  s.score_parts = { ...s.score_parts, allocation_gap: 0.4 };
  s.reasons = { ...s.reasons, allocation_gap: "Nakit benzeri payı persona metnine göre %75; Muhafazakâr model bandı %10–20." };
  const { unmount } = render(<FundCard option={o} explanation={explain(v, "fund:PPN")} />);
  const row = screen.getAllByTestId("score-row").find((r) => r.textContent?.startsWith("Portföy açığı"));
  expect(row).toHaveTextContent("persona metnine göre %75");
  unmount();
  render(
    <LangContext.Provider value="EN">
      <FundCard option={o} explanation={explain(v, "fund:PPN")} />
    </LangContext.Provider>,
  );
  expect(screen.getAllByTestId("score-row").some((r) => r.textContent?.startsWith("Portfolio gap"))).toBe(true);
});

test("penalty rows are labelled in English too", () => {
  const { v, o } = setup();
  const s = v.result.options.find((y) => y.option.option_id === "fund:PPN")!;
  s.score_parts = { ...s.score_parts, "penalty:fund_size": -0.1 };
  s.reasons = { ...s.reasons, "penalty:fund_size": "Fon küçük." };
  render(
    <LangContext.Provider value="EN">
      <FundCard option={o} explanation={explain(v, "fund:PPN")} />
    </LangContext.Provider>,
  );
  const rows = screen.getAllByTestId("score-row");
  expect(rows[rows.length - 1]).toHaveTextContent("Penalty · fund size");
  expect(screen.getByRole("heading", { name: "Why this option?" })).toBeInTheDocument();
});
