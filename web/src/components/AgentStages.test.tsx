// W40: the agent's stage boxes explain themselves: a fixed description on top, the notes as a list,
// a returned proposal step says "geri verildi" (not a failure).
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { agentDecision } from "../api/agentSample";
import type { AgentDecision, Lang } from "../api/types";
import { LangContext } from "../i18n";
import { sample } from "../test/samples";
import { AgentPanel } from "./AgentPanel";

const v = sample("run_p01_ready");
function show(d: AgentDecision, lang: Lang = "TR") {
  render(
    <LangContext.Provider value={lang}>
      <AgentPanel decision={d} />
    </LangContext.Provider>,
  );
}
async function open(i: number) {
  await userEvent.click(screen.getAllByTestId("agent-node")[i]);
  return screen.getByTestId("node-details");
}

const TR = [
  "Motor, müşterinin profiline göre puanladığı ürünlerden en iyi 10 tanesini ajana verir (ING mevduatları hariç). Motorun ilk 3'ü listenin başındadır; ajan yalnızca bu adaylar arasından seçer.",
  "Her aday için web'de fonun kendi bilgileri ve son haberleri aranır. Bugün araştırılmış bir ürün yeniden aranmaz. RM'in ✗ işaretlediği bulgular ajana verilmez; ✓ işaretlenenler “RM doğruladı” diye gider.",
  "Ajan adayların puanlarını, risklerini, portföy dağılımına etkisini ve web bulgularını tartar. Gerekirse iki adayı karşılaştırır ya da bir ürün için ek soru araştırır; sonra üç ürünlük bir öneri yapar.",
  "Ajanın önerisi kurallarla denetlenir: her sayı ve tarih gösterilen kaynakta olmalı, her gerekçenin kaynağı olmalı, yasak ifade olmamalı, seçim ürün sınıfı sınırlarına uymalı. Sorun bulunursa öneri ajana geri verilir; iki kez geçmezse motorun ilk 3'ü kullanılır.",
  "Ajanın son seçimi ve kısa gerekçesi. Ajan karar veremezse motorun ilk 3'ü kullanılır ve nedeni burada yazar.",
];

test("each opened stage box starts with its description; the N of the run in Adaylar", async () => {
  const d = agentDecision(v, "done");
  show(d);
  for (let i = 0; i < 5; i++) {
    const box = await open(i);
    expect(within(box).getByTestId("node-desc")).toHaveTextContent(TR[i]);
    await userEvent.click(screen.getAllByTestId("agent-node")[i]); // close it again
  }
  show({ ...d, n_candidates: 15 });
  await userEvent.click(screen.getAllByTestId("agent-node")[5]);
  expect(screen.getByTestId("node-desc")).toHaveTextContent("en iyi 15 tanesini");
});

test("the notes come as a list under the description; a problem line is indented", async () => {
  const d = agentDecision(v, "done");
  show(d);
  const box = await open(3); // Kontrol
  const items = within(box).getAllByTestId("node-note");
  expect(items.map((x) => x.textContent)).toEqual(d.nodes[3].notes);
  const problem = items.find((x) => x.textContent?.startsWith("– "))!;
  expect(problem).toHaveAttribute("data-problem", "true");
});

test("a returned proposal step says geri verildi, not a red failure; the passed one tamam", async () => {
  const d = agentDecision(v, "done");
  show(d);
  const box = await open(2); // Ajan analizi
  const steps = within(box).getAllByTestId("node-step");
  const returned = steps.find((s) => s.dataset.state === "failed")!;
  expect(returned).toHaveTextContent("Karar önerisi (1. deneme)");
  expect(within(returned).getByTestId("step-state")).toHaveTextContent("geri verildi");
  expect(returned).not.toHaveTextContent("hata");
  expect(within(returned).getByTestId("step-state").className).not.toMatch(/B42318/);
  expect(returned).toHaveTextContent("Kontrolde 2 sorun bulundu; ajan düzeltip yeniden önerdi.");
});

test("a failed stage keeps its failure look", () => {
  show(agentDecision(v, "fallback"));
  const kontrol = screen.getAllByTestId("agent-node")[3];
  expect(kontrol.dataset.state).toBe("failed");
  expect(kontrol).toHaveTextContent("hata");
});

test("W40 EN", async () => {
  show(agentDecision(v, "done"), "EN");
  const box = await open(3);
  expect(within(box).getByTestId("node-desc")).toHaveTextContent("The agent's proposal is checked against rules");
  await userEvent.click(screen.getAllByTestId("agent-node")[2]);
  const returned = within(screen.getByTestId("node-details")).getAllByTestId("node-step").find((s) => s.dataset.state === "failed")!;
  expect(within(returned).getByTestId("step-state")).toHaveTextContent("returned");
});
