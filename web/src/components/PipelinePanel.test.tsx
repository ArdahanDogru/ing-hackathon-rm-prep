import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Lang, RunView } from "../api/types";
import { LangContext } from "../i18n";
import { sample, withHoldings } from "../test/samples";
import { PipelinePanel } from "./PipelinePanel";

const setup = () => {
  const v = sample("run_p01_ready");
  const onOpen = vi.fn();
  const onDetails = vi.fn();
  render(<PipelinePanel view={v} onOpen={onOpen} onDetails={onDetails} />);
  return { v, onOpen, onDetails };
};

test("open by default; the summary line with the counts closes it", async () => {
  const { v } = setup();
  const scored = v.result.options.length;
  const rejected = v.result.rejected.length;
  expect(screen.getByRole("button", { name: /Bu öneriler nasıl seçildi\?/ })).toHaveTextContent(
    `${scored + rejected} seçenek → ${rejected} elendi → ${scored} puanlandı → 3 öneri`,
  );
  expect(screen.getAllByTestId("pipeline-step")).toHaveLength(5);
  await userEvent.click(screen.getByRole("button", { name: /Bu öneriler nasıl seçildi\?/ }));
  expect(screen.queryAllByTestId("pipeline-step")).toHaveLength(0);
});

test("five steps, the rules with their counts, the three picks", () => {
  const { v } = setup();
  const steps = screen.getAllByTestId("pipeline-step");
  expect(steps).toHaveLength(5);
  expect(steps[0]).toHaveTextContent(`Risk ≤ ${v.risk_ceiling}`);
  expect(steps[0]).toHaveTextContent(v.result.persona.gelir_nakit_akisi_ihtiyaci);
  v.rejected_by_rule.forEach((x) => expect(steps[2]).toHaveTextContent(`${x.label}${x.count}`));
  expect(within(steps[4]).getAllByRole("button")).toHaveLength(v.result.recommended.length);
  expect(steps[4]).toHaveTextContent("puana göre genel 1.");
});

test("a pick opens its fund card; a step link opens its details tab", async () => {
  const { v, onOpen, onDetails } = setup();
  const steps = screen.getAllByTestId("pipeline-step");
  await userEvent.click(within(steps[4]).getAllByRole("button")[0]);
  expect(onOpen).toHaveBeenCalledWith(v.result.recommended[0]);
  await userEvent.click(screen.getByRole("button", { name: "Elenenleri gör" }));
  expect(onDetails).toHaveBeenCalledWith("eliminated");
});

test("a pick below other options of its group is not ranked first there", () => {
  const { v } = setup();
  const picks = within(screen.getAllByTestId("pipeline-step")[4]).getAllByRole("button");
  // fund:IST is 20th overall and the best debt fund
  expect(picks[v.result.recommended.indexOf("fund:IST")]).toHaveTextContent("puana göre genel 20., kendi türünde 1.");
});

test("no recommendation, no pipeline", () => {
  const v = sample("run_needs_input");
  const { container } = render(<PipelinePanel view={v} onOpen={vi.fn()} onDetails={vi.fn()} />);
  expect(container).toBeEmptyDOMElement();
});

// --- W17b: the real weights and the current split --------------------------------------------

const WEIGHTS = { return: 0.4, risk_fit: 0.2, liquidity: 0.15, income: 0.1, principal: 0.1, allocation_gap: 0.05 };

async function openStep1(v: RunView, lang: Lang = "TR") {
  render(
    <LangContext.Provider value={lang}>
      <PipelinePanel view={v} onOpen={vi.fn()} onDetails={vi.fn()} />
    </LangContext.Provider>,
  );
  // the panel is open by default (d9e5c1b, 2026-10-15): no click
  return screen.getAllByTestId("pipeline-step")[0];
}

test("step 1: the effective weights as bars, largest first, percent without decimals", async () => {
  const v = { ...sample("run_p01_ready"), effective_weights: { ...WEIGHTS, simplicity: 0.003 } };
  const step = await openStep1(v);
  expect(step).toHaveTextContent("Bu müşteri için kriter ağırlıkları");
  const rows = within(step).getAllByTestId("weight-row");
  expect(rows.map((r) => r.querySelector("[data-testid=weight-label]")!.textContent)).toEqual([
    "Getiri",
    "Risk uyumu",
    "Likidite",
    "Düzenli gelir",
    "Anapara koruma",
    "Portföy açığı",
    "Sadelik",
  ]);
  expect(rows[0]).toHaveTextContent("%40");
  expect(rows[5]).toHaveTextContent("%5");
  expect(rows[6]).toHaveTextContent("%0");
  expect((within(rows[0]).getByTestId("weight-bar") as HTMLElement).style.width).toBe("40%");
  // the persona level stays next to income, principal and liquidity
  const p = v.result.persona;
  expect(rows[2]).toHaveTextContent(p.likidite_ihtiyaci);
  expect(rows[3]).toHaveTextContent(p.gelir_nakit_akisi_ihtiyaci);
  expect(rows[4]).toHaveTextContent(p.anapara_koruma_tercihi);
});

test("step 1: no Portföy açığı row when its weight is missing or 0", async () => {
  const { allocation_gap: _, ...rest } = WEIGHTS;
  const step = await openStep1({ ...sample("run_p02_ready"), effective_weights: { ...rest, allocation_gap: 0 } });
  expect(within(step).getAllByTestId("weight-row")).toHaveLength(5);
  expect(step).not.toHaveTextContent("Portföy açığı");
});

test("step 1 without effective_weights (an older API): the three persona levels as before", async () => {
  const v = sample("run_p01_ready");
  const step = await openStep1({ ...v, effective_weights: {} });
  expect(within(step).queryAllByTestId("weight-row")).toHaveLength(0);
  expect(step).toHaveTextContent("Kriter ağırlıklarını belirleyen");
  expect(step).toHaveTextContent(`Düzenli gelir${v.result.persona.gelir_nakit_akisi_ihtiyaci}`);
});

test("step 1: one line about the current split per holdings status; none without holdings", async () => {
  const cases = [
    ["estimate", "Portföy dağılımı: tahmini senaryo (sıralamayı etkilemez)"],
    ["persona_text", "Portföy dağılımı: kısmen müşteri dosyasından"],
    ["rm", "Portföy dağılımı: RM girdi"],
    ["rm_confirmed", "Portföy dağılımı: RM onayladı"],
  ] as const;
  for (const [status, text] of cases) {
    const { unmount } = render(<PipelinePanel view={withHoldings(sample("run_p01_ready"), status)} onOpen={vi.fn()} onDetails={vi.fn()} />);
    expect(screen.getByTestId("pipe-holdings")).toHaveTextContent(text);
    unmount();
  }
  const step = await openStep1({ ...sample("run_p01_ready"), holdings: undefined });
  expect(within(step).queryByTestId("pipe-holdings")).toBeNull();
});

test("W17b EN: weights and the holdings line", async () => {
  const v = { ...withHoldings(sample("run_p01_ready"), "rm_confirmed"), effective_weights: WEIGHTS };
  const step = await openStep1(v, "EN");
  expect(within(step).getAllByTestId("weight-row")[0]).toHaveTextContent("Return40 %");
  expect(step).toHaveTextContent("Portfolio gap");
  expect(within(step).getByTestId("pipe-holdings")).toHaveTextContent("Portfolio split: confirmed by the RM");
});
