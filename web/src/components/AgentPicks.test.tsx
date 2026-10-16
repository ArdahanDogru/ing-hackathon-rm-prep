// W20: the agent's top 3 on the dashboard (it replaces the engine's when done).
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "../api/client";
import { agentDecision, SAMPLE_FINDING } from "../api/agentSample";
import type { AgentDecision, Lang, ResearchView, RunView } from "../api/types";
import { renderDashboard } from "../test/render";
import { sample } from "../test/samples";
import { productCode } from "../product";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

const view = () => sample("run_p01_ready");

async function showWith(d: AgentDecision | null, v: RunView = view(), lang: Lang = "TR") {
  const get = vi.spyOn(api, "agentStatus").mockResolvedValue(d);
  renderDashboard(v, () => {}, lang);
  await waitFor(() => expect(get).toHaveBeenCalled());
  return get;
}
const cardLabels = () => screen.getAllByTestId("option-card").map((c) => c.getAttribute("aria-label"));

test("running: the engine's top 3 at once, with Motor önerisi · ajan değerlendiriyor…", async () => {
  const v = view();
  await showWith(agentDecision(v, "running"));
  expect(await screen.findByTestId("agent-picks")).toHaveTextContent("Motor önerisi · ajan değerlendiriyor…");
  expect(cardLabels()).toEqual(v.top.map((id) => v.options[id].label));
  expect(screen.queryByText("Ajan önerisi")).toBeNull();
});

test("done: the agent's top 3 replaces the engine's, with the badge and the change count", async () => {
  const v = view();
  const d = agentDecision(v, "done");
  await showWith(d);
  const box = await screen.findByTestId("agent-picks");
  expect(within(box).getByText("Ajan önerisi")).toBeInTheDocument();
  expect(box).toHaveTextContent("Ajan 1 öneriyi değiştirdi");
  expect(box).toHaveTextContent(d.summary);
  expect(cardLabels()).toEqual(d.picks.map((p) => v.options[p.option_id].label));
  const picks = within(box).getAllByTestId("agent-pick");
  expect(picks).toHaveLength(3);
  expect(picks[1]).toHaveTextContent(d.picks[1].reasons[0].text);
  expect(picks[1]).toHaveTextContent("(tahmini dağılıma göre)");
  expect(picks[1]).toHaveTextContent("(web, doğrulanmamış)");
  // the dropped engine pick and why
  const dropped = within(box).getByTestId("agent-dropped");
  expect(dropped).toHaveTextContent(v.options[d.dropped[0].option_id].short_label);
  expect(dropped).toHaveTextContent(d.dropped[0].reasons[0].text);
});

test("no change: the change note is hidden", async () => {
  const v = view();
  const d = agentDecision(v, "done");
  const same = { ...d, picks: d.engine_top3.map((id) => ({ option_id: id, reasons: d.picks[0].reasons, uses_estimate: false, uses_web: false })), dropped: [] };
  await showWith(same);
  const box = await screen.findByTestId("agent-picks");
  expect(within(box).getByText("Ajan önerisi")).toBeInTheDocument();
  expect(box).not.toHaveTextContent("değiştirdi");
});

test("Motor sıralaması is closed and opens with the engine's top 3", async () => {
  const v = view();
  await showWith(agentDecision(v, "done"));
  const toggle = await screen.findByRole("button", { name: /Motor sıralaması/ });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByTestId("engine-rank")).toBeNull();
  await userEvent.click(toggle);
  const list = screen.getByTestId("engine-rank");
  // W28: the code badge sits between the number and the name
  v.top.forEach((id, i) => expect(list).toHaveTextContent(`${i + 1}. ${productCode(id)}${v.options[id].short_label}`));
});

test("chips: E opens the evidence pop-up", async () => {
  const v = view();
  const d = agentDecision(v, "done");
  const ev = vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  await showWith(d);
  const id = d.picks[0].reasons[0].cites[0];
  await userEvent.click(await screen.findByRole("button", { name: id }));
  expect(ev).toHaveBeenCalledWith(v.result.snapshot_id, id);
});

test("chips: F shows the research finding of the same run, else its id", async () => {
  const v = view();
  const d = agentDecision(v, "done");
  const research: ResearchView = {
    state: "ready",
    questions: [],
    products: [
      {
        option_id: d.picks[1].option_id, label: "", company: "", summary: "", news: [], news_days: 30, lang: "TR", provider: "exa",
        created_at: "", cost_usd: 0, checks: [], error: "", version: 1,
        findings: [{ id: SAMPLE_FINDING, text: "Yönetim ücreti yıllık %1,2.", topic: "is", confidence: "medium", date: "", sources: [{ url: "https://example.com/f", title: "Fon sayfası", published: "" }] }],
      },
    ],
  };
  const get = vi.spyOn(api, "research").mockResolvedValue(research);
  await showWith(d);
  await userEvent.click(await screen.findByRole("button", { name: SAMPLE_FINDING }));
  const f = await screen.findByTestId("agent-finding");
  expect(f).toHaveTextContent("Yönetim ücreti yıllık %1,2.");
  expect(f).toHaveTextContent("web, doğrulanmamış");
  expect(within(f).getByRole("link", { name: "Fon sayfası" })).toHaveAttribute("href", "https://example.com/f");
  expect(get).toHaveBeenCalledWith(v.result.run_id, "TR");
});

test("chips: F without research data shows the id", async () => {
  const d = agentDecision(view(), "done");
  vi.spyOn(api, "research").mockResolvedValue({ state: "off", reason: "" });
  await showWith(d);
  await userEvent.click(await screen.findByRole("button", { name: SAMPLE_FINDING }));
  expect(await screen.findByTestId("agent-finding")).toHaveTextContent(SAMPLE_FINDING);
});

test("chips: puan opens the fund card with Neden bu öneri?; portfoy opens the Dağılım view", async () => {
  const v = view();
  const d = agentDecision(v, "done");
  await showWith(d);
  const box = await screen.findByTestId("agent-picks");
  await userEvent.click(within(within(box).getAllByTestId("agent-pick")[0]).getByRole("button", { name: "Likidite" }));
  expect(await screen.findByRole("heading", { name: "Neden bu öneri?" })).toBeInTheDocument();
  expect(screen.getByRole("dialog")).toHaveTextContent(v.options[d.picks[0].option_id].label.replace(/\s+/g, " "));
  await userEvent.keyboard("{Escape}");
  await userEvent.click(within(within(box).getAllByTestId("agent-pick")[1]).getByRole("button", { name: "Borçlanma" }));
  expect(await screen.findByTestId("allocation")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Dağılım" })).toHaveAttribute("aria-pressed", "true");
});

test("fallback: the engine's top 3 with the reason", async () => {
  const v = view();
  const d = agentDecision(v, "fallback");
  await showWith(d);
  const box = await screen.findByTestId("agent-picks");
  expect(box).toHaveTextContent(`Motor önerisi kullanıldı: ${d.fallback_reason}`);
  expect(screen.queryByText("Ajan önerisi")).toBeNull();
  expect(cardLabels()).toEqual(v.top.map((id) => v.options[id].label));
});

test("no agent on the server: nothing new on screen (W24: off shows its reason, see AgentRun.test)", async () => {
  await showWith(null);
  expect(screen.queryByTestId("agent-picks")).toBeNull();
  expect(screen.queryByTestId("agent-panel")).toBeNull();
});

test("the meeting chips start with the agent's top 3 when the RM did not touch them", async () => {
  const v = view();
  const d = agentDecision(v, "done");
  await showWith(d);
  await waitFor(() =>
    expect(screen.getAllByTestId("chip").map((c) => c.querySelector("[title]")!.getAttribute("title"))).toEqual(
      d.picks.map((p) => v.options[p.option_id].label),
    ),
  );
});

test("the meeting chips stay when the RM changed them before the agent was done", async () => {
  const v = view();
  const d = agentDecision(v, "done");
  let answer: (x: AgentDecision) => void = () => {};
  vi.spyOn(api, "agentStatus").mockReturnValue(new Promise((ok) => (answer = ok)));
  renderDashboard(v);
  const first = v.options[v.top[0]].label;
  await userEvent.click(screen.getByRole("button", { name: `${first} kaldır` }));
  answer(d);
  expect(await within(await screen.findByTestId("agent-picks")).findByText("Ajan önerisi")).toBeInTheDocument();
  expect(screen.getAllByTestId("chip").map((c) => c.querySelector("[title]")!.getAttribute("title"))).toEqual(
    v.top.slice(1).map((id) => v.options[id].label),
  );
});

test("W20 EN", async () => {
  const v = view();
  await showWith(agentDecision(v, "done"), v, "EN");
  const box = await screen.findByTestId("agent-picks");
  expect(within(box).getByText("Agent recommendation")).toBeInTheDocument();
  expect(box).toHaveTextContent("The agent changed 1 recommendation");
  expect(screen.getByRole("button", { name: /Engine ranking/ })).toBeInTheDocument();
});

// --- W23: the layout of the dashboard rows ------------------------------------------------------

test("with the agent box: row 1 = Gündem and the agent box at the same height, row 2 = Öneriler over the full width", async () => {
  await showWith(agentDecision(view(), "done"));
  const row1 = await screen.findByTestId("dash-row1");
  const row2 = screen.getByTestId("dash-row2");
  expect(row1).toHaveClass("grid", "items-stretch", "lg:grid-cols-[1fr_2fr]");
  expect(within(row1).getByTestId("agenda")).toHaveClass("h-full");
  expect(within(row1).getByTestId("agent-picks")).toHaveClass("h-full");
  expect(within(row1).queryByTestId("options-compare")).toBeNull();
  expect(within(row2).getByTestId("options-compare")).toBeInTheDocument();
  expect(row1.compareDocumentPosition(row2) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("while the agent runs the box is in row 1 too", async () => {
  await showWith(agentDecision(view(), "running"));
  expect(within(await screen.findByTestId("dash-row1")).getByTestId("agent-picks")).toBeInTheDocument();
  expect(within(screen.getByTestId("dash-row2")).getByTestId("options-compare")).toBeInTheDocument();
});

test("without the agent box (no agent on the server): Gündem and Öneriler side by side as before, no second row", async () => {
  await showWith(null);
  const row1 = screen.getByTestId("dash-row1");
  expect(row1).toHaveClass("lg:grid-cols-[1fr_2fr]");
  expect(within(row1).getByTestId("agenda")).toBeInTheDocument();
  expect(within(row1).getByTestId("options-compare")).toBeInTheDocument();
  expect(screen.queryByTestId("dash-row2")).toBeNull();
});
