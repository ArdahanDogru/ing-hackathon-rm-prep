import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { sample } from "../test/samples";
import { FundCard } from "./FundCard";

const top0 = () => {
  const v = sample("run_p01_ready");
  return v.options[v.top[0]];
};

test("fund card: ring, stars, rank, risk, access, bars, why", () => {
  const o = top0();
  render(<FundCard option={o} />);
  expect(screen.getByText(`${o.rank!.position}. / ${o.rank!.of}`)).toBeInTheDocument();
  expect(screen.getAllByTestId("star-on")).toHaveLength(o.stars!);
  expect(screen.getByText(o.access.label!)).toBeInTheDocument();
  expect(screen.getByText(`${o.risk!.level} / 7`)).toBeInTheDocument();
  expect(screen.getByTestId("bar-fund-1y")).toBeInTheDocument();
  expect(screen.getByText("Bu müşteri için neden?")).toBeInTheDocument();
  o.why.forEach(([, line]) => expect(screen.getByText(new RegExp(line))).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Seçime ekle" })).toBeInTheDocument();
});

test("fund without rank says so", () => {
  const o = { ...top0(), rank: null, stars: null };
  render(<FundCard option={o} />);
  expect(screen.getByText("sıralama yok")).toBeInTheDocument();
  expect(screen.queryAllByTestId("star-on")).toHaveLength(0);
});

test("a fund without category averages shows only its own bars", () => {
  const o = { ...top0(), category_avg: null };
  render(<FundCard option={o} />);
  expect(screen.getByTestId("bar-fund-1y")).toBeInTheDocument();
  expect(screen.queryByTestId("bar-cat-1y")).toBeNull();
});

test("Kanıt opens the evidence of the 1-year return", async () => {
  const o = top0();
  const onEvidence = vi.fn();
  render(<FundCard option={o} onEvidence={onEvidence} />);
  await userEvent.click(screen.getAllByRole("button", { name: "Kanıt" })[0]);
  expect(onEvidence).toHaveBeenCalledWith(o.returns["1y"]!.evidence_id);
});

test("selected fund shows Seçimde and toggles", async () => {
  const onToggle = vi.fn();
  render(<FundCard option={top0()} selected onToggle={onToggle} />);
  await userEvent.click(screen.getByRole("button", { name: /Seçimde/ }));
  expect(onToggle).toHaveBeenCalled();
});
