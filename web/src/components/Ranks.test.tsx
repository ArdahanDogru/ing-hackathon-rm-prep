// W41: every rank says what it ranks by: the peer rank (1-year return among similar funds)
// and the score ranks (the engine's score for this client).
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Lang, OptionView } from "../api/types";
import { explain } from "../explain";
import { LangContext } from "../i18n";
import { sample } from "../test/samples";
import { FundCard } from "./FundCard";
import { OptionsCards } from "./OptionsCards";
import { OptionsTable } from "./OptionsTable";

const v = sample("run_p01_ready");
const PPN = v.options["fund:PPN"];
const show = (o: OptionView, lang: Lang = "TR", withWhy = false) =>
  render(
    <LangContext.Provider value={lang}>
      <FundCard option={o} explanation={withWhy ? explain(v, o.option_id) : undefined} />
    </LangContext.Provider>,
  );
const peerTile = () => screen.getAllByTestId("fund-tile")[1];

test("the peer box: 'Benzerleri arasında', the place, the stars and '1 yıllık getiriye göre · ilk %x'", () => {
  const o = { ...PPN, better_than_pct: 72 };
  show(o);
  const tile = peerTile();
  expect(tile).toHaveTextContent("Benzerleri arasında");
  expect(tile).toHaveTextContent(`${o.rank!.position}. / ${o.rank!.of}`);
  expect(within(tile).getAllByTestId("star-on")).toHaveLength(o.stars!);
  expect(within(tile).getByTestId("peer-sub")).toHaveTextContent("1 yıllık getiriye göre · ilk %28");
  expect(tile).not.toHaveTextContent("Kategorisinde");
});

test("the info mark opens the pop-up with the numbers and the sub-type; ✕ closes it", async () => {
  show(PPN);
  const info = within(peerTile()).getByRole("button", { name: "Bu sıra nasıl hesaplanır?" });
  expect(info).toHaveAttribute("aria-expanded", "false");
  await userEvent.click(info);
  const pop = screen.getByTestId("peer-info");
  expect(pop).toHaveTextContent(
    `Bu fon, aynı türdeki (${PPN.category_label}) ${PPN.rank!.of} fon arasında 1 yıllık getirisine göre ${PPN.rank!.position}. sırada.`,
  );
  expect(pop).toHaveTextContent("Gruba, bu müşteri için elenen fonlar da girer.");
  expect(pop).toHaveTextContent("Yıldızlar: en iyi %10 = 5, sonraki %22,5 = 4, orta %35 = 3, sonraki %22,5 = 2, son %10 = 1.");
  expect(pop).toHaveTextContent("Bu sıra motorun puanı değildir: puan, müşterinin profiline göre birçok ölçütü tartar.");
  await userEvent.click(within(pop).getByRole("button", { name: "Kapat" }));
  expect(screen.queryByTestId("peer-info")).toBeNull();
});

test("a fund without a rank has no info mark", () => {
  show({ ...PPN, rank: null, stars: null });
  expect(peerTile()).toHaveTextContent("sıralama yok");
  expect(within(peerTile()).queryByRole("button")).toBeNull();
});

test("the score rank in Neden bu öneri? names the score", () => {
  show(PPN, "TR", true);
  expect(screen.getByText(`Puana göre ${explain(v, "fund:PPN")!.of} aday içinde 1. sıra`)).toBeInTheDocument();
});

test("the cards and the table say the place is among similar funds", () => {
  const { unmount } = render(<OptionsCards options={[PPN]} baseline={null} onOpen={vi.fn()} onEvidence={vi.fn()} />);
  expect(screen.getByTestId("option-card")).toHaveTextContent(`${PPN.rank!.position}. / ${PPN.rank!.of} benzerleri arasında`);
  unmount();
  render(<OptionsTable options={[PPN]} baseline={null} onOpen={vi.fn()} onEvidence={vi.fn()} />);
  expect(screen.getByRole("rowheader", { name: "Benzerleri arasında" })).toBeInTheDocument();
});

test("W41 EN", async () => {
  const o = { ...PPN, better_than_pct: 72 };
  show(o, "EN", true);
  const tile = peerTile();
  expect(tile).toHaveTextContent("Among similar funds");
  expect(within(tile).getByTestId("peer-sub")).toHaveTextContent("by 1-year return · top 28 %");
  await userEvent.click(within(tile).getByRole("button", { name: "How is this place made?" }));
  expect(screen.getByTestId("peer-info")).toHaveTextContent(
    `Among the ${o.rank!.of} funds of the same type (${o.category_label}) this fund is number ${o.rank!.position} by 1-year return.`,
  );
  expect(screen.getByText(`By score: rank 1 of ${explain(v, "fund:PPN")!.of} candidates`)).toBeInTheDocument();
});
