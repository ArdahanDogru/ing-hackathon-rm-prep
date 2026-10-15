// W20c: the penalty chip of an agent reason, and the brief written again after the agent changed the top 3.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "../api/client";
import { agentDecision } from "../api/agentSample";
import type { AgentDecision, Lang, NarrativeBrief } from "../api/types";
import { renderDashboard } from "../test/render";
import { sample } from "../test/samples";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

const view = () => sample("run_p01_ready");
const brief = (text: string): NarrativeBrief => ({
  run_id: view().result.run_id, lang: "TR", text, source: "llm", model: "claude-haiku-5-5", prompt_version: "b1",
  checks: [], created_at: "2026-10-15T10:00:00+03:00", cost_usd: 0.003, cite: [],
});

/** The done sample with a penalty cite on the first reason of the first pick. */
function withPenalty(): AgentDecision {
  const d = agentDecision(view(), "done");
  d.picks[0].reasons[0] = { ...d.picks[0].reasons[0], cites: ["puan:penalty_liquidity"] };
  return d;
}

async function show(d: AgentDecision, lang: Lang = "TR") {
  vi.spyOn(api, "agentStatus").mockResolvedValue(d);
  renderDashboard(view(), () => {}, lang);
  return screen.findByTestId("agent-picks");
}

test("a puan:penalty_<rule> chip says Ceza · <rule> and opens the fund card", async () => {
  const box = await show(withPenalty());
  const pick = within(box).getAllByTestId("agent-pick")[0];
  expect(within(pick).queryByText("penalty_liquidity")).toBeNull();
  await userEvent.click(within(pick).getByRole("button", { name: "Ceza · likidite" }));
  expect(await screen.findByRole("heading", { name: "Neden bu öneri?" })).toBeInTheDocument();
});

test("W20c EN penalty chip", async () => {
  const box = await show(withPenalty(), "EN");
  expect(within(within(box).getAllByTestId("agent-pick")[0]).getByRole("button", { name: "Penalty · liquidity" })).toBeInTheDocument();
});

test("an unknown penalty rule keeps its rule name", async () => {
  const d = withPenalty();
  d.picks[0].reasons[0].cites = ["puan:penalty_new_rule"];
  const box = await show(d);
  expect(within(within(box).getAllByTestId("agent-pick")[0]).getByRole("button", { name: "Ceza · new_rule" })).toBeInTheDocument();
});

test("the agent changed the top 3: the brief is asked again and the new text replaces the old one", async () => {
  const get = vi.spyOn(api, "brief").mockResolvedValueOnce(brief("Motorun özeti: PPN, IST ve AIS.")).mockResolvedValue(brief("Ajanın özeti: yeni üç seçenek."));
  await show(agentDecision(view(), "done"));
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  expect(await screen.findByText(/Ajanın özeti: yeni üç seçenek\./)).toBeInTheDocument();
});

test("the brief is not asked again for a fallback, a running agent or the engine's own picks", async () => {
  const v = view();
  const done = agentDecision(v, "done");
  const same: AgentDecision = { ...done, picks: done.engine_top3.map((id) => ({ ...done.picks[0], option_id: id })), dropped: [] };
  for (const d of [agentDecision(v, "fallback"), agentDecision(v, "running"), same]) {
    const get = vi.spyOn(api, "brief").mockResolvedValue(brief("Motorun özeti."));
    const status = vi.spyOn(api, "agentStatus").mockResolvedValue(d);
    const { unmount } = renderDashboard(v);
    await waitFor(() => expect(status).toHaveBeenCalled());
    await screen.findByText(/Motorun özeti\./);
    expect(get).toHaveBeenCalledTimes(1);
    unmount();
    vi.restoreAllMocks();
  }
});
