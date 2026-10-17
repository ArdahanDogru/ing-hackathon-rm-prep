// W32: categories by what a fund invests in: classes → sub-types → the best 5 funds.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Lang } from "../api/types";
import { fmtPct, fmtScore } from "../format";
import { LangContext } from "../i18n";
import { productCode } from "../product";
import { renderDashboard } from "../test/render";
import { sample } from "../test/samples";
import { CategoryList } from "./CategoryList";
import { FundCard } from "./FundCard";
import { PipelinePanel } from "./PipelinePanel";

afterEach(() => vi.restoreAllMocks());

const v = sample("run_p01_ready");
const show = (lang: Lang = "TR", onOpen = vi.fn()) => {
  render(
    <LangContext.Provider value={lang}>
      <CategoryList view={v} onOpen={onOpen} />
    </LangContext.Provider>,
  );
  return onOpen;
};
const classRow = (label: string) => screen.getAllByTestId("category").find((c) => c.querySelector("button")?.textContent?.startsWith(label))!;

test("the header counts every scored option and the classes; one row per class with its count", () => {
  const total = v.categories.reduce((n, c) => n + c.count, 0);
  expect(total).toBe(v.result.options.length);
  show();
  expect(screen.getByTestId("categories-head")).toHaveTextContent(`${total} aday, ${v.categories.length} sınıf`);
  const rows = screen.getAllByTestId("category");
  expect(rows).toHaveLength(v.categories.length);
  v.categories.forEach((c, i) => {
    expect(rows[i]).toHaveTextContent(c.label);
    expect(rows[i]).toHaveTextContent(String(c.count));
  });
});

test("a class opens to its sub-types; a sub-type shows its best 5 funds and Tümünü göster shows all", async () => {
  show();
  const cls = v.categories[0]; // Nakit benzeri
  const sub = cls.subtypes.find((s) => s.count > 5)!; // Para piyasası
  const row = classRow(cls.label);
  await userEvent.click(within(row).getAllByRole("button")[0]);
  const subs = within(row).getAllByTestId("subtype");
  expect(subs).toHaveLength(cls.subtypes.length);
  const subRow = subs[cls.subtypes.indexOf(sub)];
  expect(subRow).toHaveTextContent(sub.label);
  expect(subRow).toHaveTextContent(String(sub.count));
  await userEvent.click(within(subRow).getAllByRole("button")[0]);
  expect(within(subRow).getAllByTestId("fund-row")).toHaveLength(5);
  await userEvent.click(within(subRow).getByRole("button", { name: `Tümünü göster (${sub.count})` }));
  expect(within(subRow).getAllByTestId("fund-row")).toHaveLength(sub.count);
  expect(within(subRow).queryByRole("button", { name: /Tümünü göster/ })).toBeNull();
});

test("a fund row: the code badge, the name, the score, the 1-year return and the badges; a click opens its card", async () => {
  const onOpen = show();
  // a sub-type with a Katılım fund among its first 5
  const cls = v.categories.find((c) => c.subtypes.some((s) => s.option_ids.slice(0, 5).some((id) => v.options[id]?.badges?.length)))!;
  const sub = cls.subtypes.find((s) => s.option_ids.slice(0, 5).some((id) => v.options[id]?.badges?.length))!;
  const row = classRow(cls.label);
  await userEvent.click(within(row).getAllByRole("button")[0]);
  const subRow = within(row).getAllByTestId("subtype")[cls.subtypes.indexOf(sub)];
  await userEvent.click(within(subRow).getAllByRole("button")[0]);
  const id = sub.option_ids.slice(0, 5).find((x) => v.options[x]?.badges?.length)!;
  const o = v.options[id];
  const fund = within(subRow).getAllByTestId("fund-row")[sub.option_ids.indexOf(id)];
  expect(within(fund).getByTestId("code-badge")).toHaveTextContent(productCode(id));
  expect(fund).toHaveTextContent(o.short_label);
  const score = v.result.options.find((x) => x.option.option_id === id)!.score;
  expect(fund).toHaveTextContent(fmtScore(score, false));
  if (o.returns["1y"]) expect(fund).toHaveTextContent(fmtPct(o.returns["1y"].value));
  expect(within(fund).getAllByTestId("product-badge").map((b) => b.textContent)).toEqual(o.badges!.map((b) => b.label));
  await userEvent.click(within(fund).getByRole("button"));
  expect(onOpen).toHaveBeenCalledWith(id);
});

test("the dashboard: Kategorileri gör → a fund row opens the fund card", async () => {
  renderDashboard(v);
  await userEvent.click(screen.getByRole("button", { name: "Kategorileri gör" }));
  const note = screen.getByRole("dialog");
  const first = within(note).getAllByTestId("category")[0];
  await userEvent.click(within(first).getAllByRole("button")[0]);
  const sub = within(first).getAllByTestId("subtype")[0];
  await userEvent.click(within(sub).getAllByRole("button")[0]);
  await userEvent.click(within(within(sub).getAllByTestId("fund-row")[0]).getByRole("button"));
  expect(within(screen.getByRole("dialog")).getAllByTestId("fund-tile")).toHaveLength(3);
});

test("step 5: 'kendi grubunda n.' counts within the pick's sub-type (category_key)", () => {
  render(<PipelinePanel view={v} onOpen={vi.fn()} onDetails={vi.fn()} />);
  const ranked = [...v.result.options].sort((a, b) => b.score - a.score || a.option.option_id.localeCompare(b.option.option_id));
  const picks = screen.getAllByTestId("pipe-pick");
  v.result.recommended.forEach((id, i) => {
    const key = v.options[id].category_key;
    const overall = ranked.findIndex((o) => o.option.option_id === id) + 1;
    const inGroup = ranked.filter((o) => v.options[o.option.option_id]?.category_key === key).findIndex((o) => o.option.option_id === id) + 1;
    expect(picks[i]).toHaveTextContent(v.options[id].category_label);
    expect(picks[i]).toHaveTextContent(overall === inGroup ? `genel ${overall}. sıra` : `genel ${overall}. sıra, kendi grubunda ${inGroup}.`);
  });
});

test("the fund card: the sub-type in the header and the badges next to the title", () => {
  const id = Object.keys(v.options).find((k) => v.options[k].badges?.length)!;
  const o = v.options[id];
  render(<FundCard option={o} />);
  expect(screen.getByText(new RegExp(o.category_label))).toBeInTheDocument();
  const title = screen.getByRole("heading", { level: 2 }).parentElement as HTMLElement;
  expect(within(title).getAllByTestId("product-badge").map((b) => b.textContent)).toEqual(o.badges!.map((b) => b.label));
});

test("W32 EN header", () => {
  show("EN");
  const total = v.categories.reduce((n, c) => n + c.count, 0);
  expect(screen.getByTestId("categories-head")).toHaveTextContent(`${total} candidates, ${v.categories.length} classes`);
});

test("the badges in the meeting-text headings and the print card", async () => {
  const { api } = await import("../api/client");
  const { MeetingText } = await import("../screens/MeetingText");
  const { PrintCard } = await import("../screens/PrintCard");
  const { renderWith } = await import("../test/render");
  const a = sample("run_p01_approved");
  const id = a.result.rm_selected.find((x) => a.options[x]?.badges?.length)!;
  expect(id).toBeTruthy();
  vi.spyOn(api, "narrative").mockResolvedValue(sample("narrative_p01_tr"));
  vi.spyOn(api, "glossary").mockResolvedValue([]);
  const { unmount } = renderWith(<MeetingText view={a} />);
  const heads = await screen.findAllByTestId("doc-option");
  expect(within(heads[a.result.rm_selected.indexOf(id)]).getAllByTestId("product-badge")[0]).toHaveTextContent(a.options[id].badges![0].label);
  unmount();
  render(<PrintCard view={a} narrative={sample("narrative_p01_tr")} />);
  const print = screen.getAllByTestId("print-option")[a.result.rm_selected.indexOf(id)];
  expect(within(print).getAllByTestId("product-badge")[0]).toHaveTextContent(a.options[id].badges![0].label);
});
