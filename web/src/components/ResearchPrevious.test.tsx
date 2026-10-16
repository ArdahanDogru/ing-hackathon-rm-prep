// W29: the earlier run's research stays (muted) while the agent runs again on the new run.
import { act, screen, waitFor, within } from "@testing-library/react";
import { api } from "../api/client";
import { agentDecision } from "../api/agentSample";
import type { ProductResearch, ResearchFinding, ResearchView } from "../api/types";
import { renderDashboard, renderWith } from "../test/render";
import { sample } from "../test/samples";
import { ResearchPanel } from "./ResearchPanel";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const v = sample("run_p01_ready");
const f = (id: string, text: string): ResearchFinding => ({ id, text, topic: "strateji", confidence: "medium", sources: [], date: "", mark: null });
const product = (option_id: string, findings: ResearchFinding[]): ProductResearch => ({
  option_id, label: option_id.toUpperCase(), company: "", summary: "", findings, news: [], news_days: 0, lang: "TR",
  provider: "exa", created_at: "", cost_usd: 0, checks: [], error: "", version: 2,
});
const NOW = product(v.top[0], [f("Fa0000001", "Yeni listenin bulgusu.")]);
const OLD = product("fund:OSD", [f("Fa0000009", "Önceki listenin bulgusu.")]);
const withPrevious: ResearchView = { state: "ready", products: [NOW], questions: [], previous: { run_id: "R-old", products: [OLD] } };
const without: ResearchView = { state: "ready", products: [NOW, product("fund:GO6", [f("Fa0000010", "Yeni aday.")])], questions: [] };

test("the previous products in a muted section with its label, code badges and marks", async () => {
  vi.spyOn(api, "research").mockResolvedValue(withPrevious);
  renderWith(<ResearchPanel view={v} />);
  const section = await screen.findByTestId("research-previous");
  expect(section).toHaveTextContent("Önceki dağılıma göre — ajan yeniden çalışıyor");
  expect(section).toHaveClass("opacity-70");
  expect(section).toHaveTextContent("Önceki listenin bulgusu.");
  expect(within(section).getByTestId("code-badge")).toHaveTextContent("OSD");
  const li = within(section).getByText("Önceki listenin bulgusu.").closest("li") as HTMLElement;
  expect(within(li).getByRole("button", { name: "Doğrulandı" })).toBeInTheDocument();
  // the run's own products stay above it, not in it
  expect(within(section).queryByText("Yeni listenin bulgusu.")).toBeNull();
  expect(screen.getByText("Yeni listenin bulgusu.")).toBeInTheDocument();
});

test("no previous key: no section", async () => {
  vi.spyOn(api, "research").mockResolvedValue(without);
  renderWith(<ResearchPanel view={v} />);
  await screen.findByText("Yeni listenin bulgusu.");
  expect(screen.queryByTestId("research-previous")).toBeNull();
});

test("while the agent runs the research is asked again every 3 s; the section goes away when the new list comes", async () => {
  vi.useFakeTimers();
  const get = vi.spyOn(api, "research").mockResolvedValueOnce(withPrevious).mockResolvedValueOnce(withPrevious).mockResolvedValue(without);
  renderWith(<ResearchPanel view={v} agentRunning />);
  await act(() => vi.advanceTimersByTimeAsync(0));
  expect(screen.getByTestId("research-previous")).toBeInTheDocument();
  await act(() => vi.advanceTimersByTimeAsync(3_000));
  expect(get).toHaveBeenCalledTimes(2);
  await act(() => vi.advanceTimersByTimeAsync(3_000));
  expect(get).toHaveBeenCalledTimes(3);
  expect(screen.queryByTestId("research-previous")).toBeNull();
  expect(screen.getByText("Yeni aday.")).toBeInTheDocument();
});

test("without a running agent a ready research is asked once", async () => {
  vi.useFakeTimers();
  const get = vi.spyOn(api, "research").mockResolvedValue(withPrevious);
  renderWith(<ResearchPanel view={v} />);
  await act(() => vi.advanceTimersByTimeAsync(10_000));
  expect(get).toHaveBeenCalledTimes(1);
});

test("the dashboard: a running agent keeps the research polled", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.spyOn(api, "agentStatus").mockResolvedValue(agentDecision(v, "running"));
  const get = vi.spyOn(api, "research").mockResolvedValue(withPrevious);
  renderDashboard(v);
  await screen.findByTestId("research-previous");
  await act(() => vi.advanceTimersByTimeAsync(6_500));
  await waitFor(() => expect(get.mock.calls.length).toBeGreaterThanOrEqual(3));
});

test("W29 EN label", async () => {
  vi.spyOn(api, "research").mockResolvedValue(withPrevious);
  renderWith(<ResearchPanel view={v} />, { lang: "EN" });
  expect(await screen.findByTestId("research-previous")).toHaveTextContent("From the earlier split — the agent is running again");
});
