import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { sample } from "../test/samples";
import { FundCard, FundDrawer } from "./FundCard";

const top0 = () => {
  const v = sample("run_p01_ready");
  return v.options[v.top[0]];
};

test("fund card: names, three tiles, bars, why, risk, button", () => {
  const o = top0();
  const { container } = render(<FundCard option={o} snapshotId="20261010-183835-6813" />);
  expect(screen.getByRole("heading", { name: o.short_label })).toBeInTheDocument();
  expect(container).toHaveTextContent(o.label.replace(/\s+/g, " "));
  const tiles = screen.getAllByTestId("fund-tile");
  expect(tiles).toHaveLength(3);
  expect(tiles[0]).toHaveTextContent("Uygunluk");
  expect(tiles[1]).toHaveTextContent(`${o.rank!.position}. / ${o.rank!.of}`);
  expect(within(tiles[1]).getAllByTestId("star-on")).toHaveLength(o.stars!);
  expect(tiles[2]).toHaveTextContent(o.access.label!);
  expect(screen.getByTestId("bar-fund-1y")).toBeInTheDocument();
  expect(screen.getByText("Bu müşteri için neden?")).toBeInTheDocument();
  o.why.forEach(([, line]) => expect(container).toHaveTextContent(line)); // plain text: why lines hold "+", "("
  expect(container).toHaveTextContent(`SPK risk ${o.risk!.level} / 7`);
  expect(container).toHaveTextContent("Kaynak: TEFAS, 10.10.2026");
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

test("Kanıtları göster lists the evidence; one opens", async () => {
  const o = top0();
  const onEvidence = vi.fn();
  render(<FundCard option={o} onEvidence={onEvidence} />);
  await userEvent.click(screen.getByRole("button", { name: /Kanıtları göster/ }));
  await userEvent.click(screen.getByRole("button", { name: o.returns["1y"]!.evidence_id }));
  expect(onEvidence).toHaveBeenCalledWith(o.returns["1y"]!.evidence_id);
});

test("selected fund shows Seçimden çıkar and toggles", async () => {
  const onToggle = vi.fn();
  render(<FundCard option={top0()} selected onToggle={onToggle} />);
  await userEvent.click(screen.getByRole("button", { name: "Seçimden çıkar" }));
  expect(onToggle).toHaveBeenCalled();
});

test("the share in words (W41): '1 yıllık getiriye göre · ilk %N', the share only for the upper half", () => {
  const o = { ...top0(), better_than_pct: 96 };
  const { unmount } = render(<FundCard option={o} />);
  expect(screen.getByTestId("peer-sub")).toHaveTextContent("1 yıllık getiriye göre · ilk %4");
  unmount();
  render(<FundCard option={{ ...o, better_than_pct: 30 }} />);
  expect(screen.getByTestId("peer-sub").textContent).toBe("1 yıllık getiriye göre");
});

test("the drawer: ✕ closes; focus moves in", async () => {
  const onClose = vi.fn();
  render(
    <FundDrawer onClose={onClose}>
      <FundCard option={top0()} />
    </FundDrawer>,
  );
  const close = screen.getByRole("button", { name: "Kapat" });
  expect(close).toHaveFocus();
  await userEvent.click(close);
  expect(onClose).toHaveBeenCalled();
});
