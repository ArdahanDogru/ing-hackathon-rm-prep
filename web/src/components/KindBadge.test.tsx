import { render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import type { Lang, OptionView } from "../api/types";
import { LangContext } from "../i18n";
import { asKind, sample } from "../test/samples";
import { FundCard } from "./FundCard";
import { OptionsCards } from "./OptionsCards";
import { OptionsTable } from "./OptionsTable";

const v = sample("run_p01_ready");
const fund = v.options[v.top[0]];
const three = (): OptionView[] => [fund, asKind(v.options[v.top[1]], "etf"), asKind(v.options[v.top[2]], "stock")];
const noop = () => {};

function show(ui: ReactElement, lang: Lang = "TR") {
  return render(<LangContext.Provider value={lang}>{ui}</LangContext.Provider>);
}

test("cards: BYF for an ETF, Pay for a share, no badge for a fund", () => {
  show(<OptionsCards options={three()} baseline={null} onOpen={noop} onEvidence={noop} />);
  const cards = screen.getAllByTestId("option-card");
  expect(within(cards[0]).queryByTestId("kind-badge")).toBeNull();
  expect(within(cards[1]).getByTestId("kind-badge")).toHaveTextContent("BYF");
  expect(within(cards[2]).getByTestId("kind-badge")).toHaveTextContent("Pay");
});

test("table columns: the badge in the column head; the access of a share", () => {
  show(<OptionsTable options={three()} baseline={null} onOpen={noop} onEvidence={noop} />);
  const heads = screen.getAllByTestId("compare-head");
  expect(within(heads[0]).queryByTestId("kind-badge")).toBeNull();
  expect(within(heads[1]).getByTestId("kind-badge")).toHaveTextContent("BYF");
  expect(within(heads[2]).getByTestId("kind-badge")).toHaveTextContent("Pay");
  expect(screen.getAllByText("2 iş günü (borsa takası)")).toHaveLength(2);
});

test("table: a share without rank says sıralama yok, not a dash", () => {
  show(<OptionsTable options={three()} baseline={null} onOpen={noop} onEvidence={noop} />);
  expect(screen.getByText("sıralama yok")).toBeInTheDocument();
});

test("fund card of an ETF: badge, T+2 access, source TEFAS", () => {
  const etf = three()[1];
  const { container } = show(<FundCard option={etf} snapshotId="20261010-183835-6813" />);
  expect(screen.getByTestId("kind-badge")).toHaveTextContent("BYF");
  expect(screen.getAllByTestId("fund-tile")[2]).toHaveTextContent("2 iş günü (borsa takası)");
  expect(container).toHaveTextContent("Kaynak: TEFAS, 10.10.2026");
  // the code after the official name, as for a fund
  expect(container).toHaveTextContent(`${etf.label.replace(/\s+/g, " ")} · ${etf.option_id.split(":")[1]}`);
});

test("fund card of a share: badge Pay, source Borsa İstanbul", () => {
  const { container } = show(<FundCard option={three()[2]} snapshotId="20261010-183835-6813" />);
  expect(screen.getByTestId("kind-badge")).toHaveTextContent("Pay");
  expect(container).toHaveTextContent("Kaynak: Borsa İstanbul, 10.10.2026");
});

test("EN badges", () => {
  show(<OptionsCards options={three()} baseline={null} onOpen={noop} onEvidence={noop} />, "EN");
  const badges = screen.getAllByTestId("kind-badge").map((b) => b.textContent);
  expect(badges).toEqual(["ETF", "Share"]);
});
