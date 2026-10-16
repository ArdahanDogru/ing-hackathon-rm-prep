// W28: the product code (TEFAS code / BIST ticker) everywhere a product is a title.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { api } from "../api/client";
import { agentDecision } from "../api/agentSample";
import type { Lang, OptionView, RunView } from "../api/types";
import { explain } from "../explain";
import { LangContext } from "../i18n";
import { productCode, withCode } from "../product";
import { PrintCard } from "../screens/PrintCard";
import { renderDashboard, renderWith } from "../test/render";
import { asKind, sample } from "../test/samples";
import { AgentPicks } from "./AgentPicks";
import { AllocationCard } from "./AllocationCard";
import { chipName } from "./ApprovalBar";
import { CategoryList } from "./CategoryList";
import { FundCard } from "./FundCard";
import { OptionsCards } from "./OptionsCards";
import { OptionsTable } from "./OptionsTable";
import { PipelinePanel } from "./PipelinePanel";
import { ResearchPanel } from "./ResearchPanel";

afterEach(() => vi.restoreAllMocks());

const v = sample("run_p01_ready");
const PPN = v.options["fund:PPN"];
const TD = v.options["time_deposit:ing_e_vadeli"];
const show = (ui: ReactElement, lang: Lang = "TR") => render(<LangContext.Provider value={lang}>{ui}</LangContext.Provider>);
const badges = (el: HTMLElement) => within(el).queryAllByTestId("code-badge").map((b) => b.textContent);

test("productCode: the part after ':' for a fund, an ETF and a share; nothing for the ING deposits", () => {
  expect(productCode("fund:PPN")).toBe("PPN");
  expect(productCode("etf:GLDTR")).toBe("GLDTR");
  expect(productCode("stock:THYAO")).toBe("THYAO");
  expect(productCode("deposit:ing_turuncu")).toBe("");
  expect(productCode("time_deposit:ing_e_vadeli")).toBe("");
  expect(withCode("fund:PPN", "Nurol · Para Piyasası (TL)")).toBe("PPN · Nurol · Para Piyasası (TL)");
  expect(withCode("time_deposit:ing_e_vadeli", "ING e-Vadeli")).toBe("ING e-Vadeli");
});

test("the top-3 cards: a code badge before the name for a fund, an ETF and a share; none for a deposit", () => {
  const options = [PPN, asKind(v.options["fund:IST"], "etf"), asKind(v.options["fund:AIS"], "stock"), TD];
  show(<OptionsCards options={options} baseline={null} onOpen={vi.fn()} onEvidence={vi.fn()} />);
  const cards = screen.getAllByTestId("option-card");
  expect(badges(cards[0])).toEqual(["PPN"]);
  expect(badges(cards[1])).toEqual(["IST"]);
  expect(badges(cards[2])).toEqual(["AIS"]);
  expect(badges(cards[3])).toEqual([]);
});

test("the table and compare headers", () => {
  show(<OptionsTable options={[PPN]} baseline={v.baseline} onOpen={vi.fn()} onEvidence={vi.fn()} />);
  const heads = screen.getAllByTestId("compare-head");
  expect(badges(heads[0])).toEqual(["PPN"]);
  expect(badges(heads[1])).toEqual([]); // the deposit baseline
});

test("the fund card and the drawer title: the code in the title badge, no longer in the sub-title", () => {
  const { container } = show(<FundCard option={PPN} />);
  const title = screen.getByRole("heading", { level: 2 }).parentElement as HTMLElement;
  expect(badges(title)).toEqual(["PPN"]);
  expect(container).not.toHaveTextContent(`${PPN.label} · PPN`);
  expect(container).toHaveTextContent(PPN.label.replace(/\s+/g, " "));
});

test("the fund card of a deposit has no badge", () => {
  const { container } = show(<FundCard option={TD} />);
  expect(badges(container)).toEqual([]);
});

test("the categories rows", async () => {
  const cat = v.categories[0];
  show(<CategoryList categories={[cat]} options={v.options} selected={[]} onToggle={vi.fn()} onOpen={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { expanded: false }));
  const rows = screen.getAllByTestId("fund-row");
  rows.forEach((r, i) => expect(badges(r)).toEqual([productCode(cat.option_ids[i])].filter(Boolean)));
});

test("the Dağılım rows (the best option of a class)", () => {
  show(<AllocationCard view={v} onOpen={vi.fn()} />);
  const i = v.allocation.findIndex((a) => a.option_id?.startsWith("fund:"));
  expect(badges(screen.getAllByTestId("alloc-row")[i])).toEqual([productCode(v.allocation[i].option_id!)]);
});

test("the meeting chips: 'PPN · Nurol · Para Piyasası (TL)'; a deposit without a code", () => {
  expect(chipName(PPN, "fund:PPN")).toBe("PPN · Nurol · Para Piyasası (TL)");
  expect(chipName(TD, TD.option_id)).not.toMatch(/·.*·/);
  expect(chipName(TD, TD.option_id)).not.toContain("ing_e_vadeli");
});

test("the dashboard: the approval-bar chips carry the codes", () => {
  renderDashboard(v);
  const chips = screen.getAllByTestId("chip").map((c) => c.textContent?.replace("✕", "").trim());
  expect(chips).toEqual(v.top.map((id) => chipName(v.options[id], id)));
  expect(chips[0]?.startsWith("PPN · ")).toBe(true);
});

test("the agent's picks, the dropped option and the engine ranking", async () => {
  const d = agentDecision(v, "done");
  show(<AgentPicks view={v} decision={d} onOpen={vi.fn()} onEvidence={vi.fn()} onAllocation={vi.fn()} />);
  const picks = screen.getAllByTestId("agent-pick");
  picks.forEach((p, i) => expect(badges(p)[0]).toBe(productCode(d.picks[i].option_id)));
  expect(badges(screen.getByTestId("agent-dropped"))).toEqual([productCode(d.dropped[0].option_id)]);
  await userEvent.click(screen.getByRole("button", { name: /Motor sıralaması/ }));
  expect(badges(screen.getByTestId("engine-rank"))).toEqual(d.engine_top3.map(productCode));
});

test("pipeline step 5 picks", () => {
  show(<PipelinePanel view={v} onOpen={vi.fn()} onDetails={vi.fn()} />);
  const step = screen.getAllByTestId("pipeline-step")[4];
  expect(within(step).getAllByTestId("pipe-pick").map((p) => badges(p)[0])).toEqual(v.result.recommended.map(productCode));
});

test("the closest alternative in Neden bu öneri?", () => {
  const x = explain(v, "fund:PPN")!;
  show(<FundCard option={PPN} explanation={x} />);
  expect(badges(screen.getByTestId("alternative"))).toEqual([productCode(x.alternative!.option_id)]);
});

test("the research panel product headers", async () => {
  vi.spyOn(api, "research").mockResolvedValue({
    state: "ready",
    questions: [],
    products: [{ option_id: "fund:PPN", label: PPN.label, company: "", summary: "", findings: [], news: [], news_days: 0, lang: "TR", provider: "exa", created_at: "", cost_usd: 0, checks: [], error: "", version: 2 }],
  });
  renderWith(<ResearchPanel view={v} />);
  const head = await screen.findByTestId("research-product");
  expect(badges(within(head).getAllByRole("heading")[0])).toEqual(["PPN"]);
});

test("the agent panel: the research sub-nodes of the candidates", async () => {
  const { AgentPanel } = await import("./AgentPanel");
  show(<AgentPanel decision={agentDecision(v, "done")} />);
  await userEvent.click(screen.getAllByTestId("agent-node")[1]);
  expect(badges(screen.getByTestId("node-details"))).toContain("PPN");
});

test("the meeting-text screen: each recommendation heading", async () => {
  const { MeetingText } = await import("../screens/MeetingText");
  vi.spyOn(api, "narrative").mockResolvedValue(sample("narrative_p01_tr"));
  vi.spyOn(api, "glossary").mockResolvedValue([]);
  const a = sample("run_p01_approved");
  renderWith(<MeetingText view={a} />);
  const options = await screen.findAllByTestId("doc-option");
  options.forEach((o, i) => expect(badges(o)[0]).toBe(productCode(a.result.rm_selected[i])));
});

test("the print card: each recommendation heading", () => {
  const a: RunView = sample("run_p01_approved");
  show(<PrintCard view={a} narrative={sample("narrative_p01_tr")} />);
  const heads = screen.getAllByTestId("print-option");
  heads.forEach((h, i) => expect(badges(h)[0]).toBe(productCode(a.result.rm_selected[i])));
});

test("the brief's sources list: 'PPN · …' for a cited fund", async () => {
  const brief = { run_id: v.result.run_id, lang: "TR" as const, text: "Özet.", source: "llm" as const, model: "m", prompt_version: "b1", checks: [], created_at: "", cost_usd: 0, cite: ["fund:PPN"] };
  vi.spyOn(api, "brief").mockResolvedValue(brief);
  renderDashboard(v);
  await userEvent.click(await screen.findByRole("button", { name: /Kaynaklar/ }));
  expect(screen.getByTestId("brief-sources")).toHaveTextContent(`PPN · ${(PPN as OptionView).short_label}`);
});

test("the rejected options of the Elenen note carry their code (rejected_by_rule items have option_id)", async () => {
  const rule = v.rejected_by_rule[0];
  expect(rule.options[0].option_id).toBeTruthy();
  renderDashboard(v);
  await userEvent.click(screen.getByRole("button", { name: "Elenenleri gör" }));
  const note = screen.getByRole("dialog");
  await userEvent.click(within(note).getByRole("button", { name: new RegExp(rule.label) }));
  const items = within(within(note).getByTestId(`rule-${rule.rule_id}`)).getAllByRole("listitem");
  items.slice(0, 5).forEach((li, i) => expect(badges(li)).toEqual([productCode(rule.options[i].option_id ?? "")].filter(Boolean)));
  expect(badges(items[0])).toEqual([productCode(rule.options[0].option_id!)]);
});

test("a rejected option without option_id (an older API) shows its label only", async () => {
  const w: RunView = structuredClone(v);
  w.rejected_by_rule[0].options = w.rejected_by_rule[0].options.map(({ label, reasons }) => ({ label, reasons }));
  renderDashboard(w);
  await userEvent.click(screen.getByRole("button", { name: "Elenenleri gör" }));
  const note = screen.getByRole("dialog");
  await userEvent.click(within(note).getByRole("button", { name: new RegExp(w.rejected_by_rule[0].label) }));
  expect(badges(within(note).getByTestId(`rule-${w.rejected_by_rule[0].rule_id}`))).toEqual([]);
});
