// W20: the agent's node row "Ajan değerlendirmesi" and its polling.
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "../api/client";
import { agentDecision } from "../api/agentSample";
import type { AgentDecision, Lang } from "../api/types";
import { LangContext } from "../i18n";
import { sample } from "../test/samples";
import { AgentPanel, useAgent } from "./AgentPanel";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const run = () => sample("run_p01_ready");
const decision = (state: AgentDecision["state"], step?: number) => agentDecision(run(), state, step);

function Harness({ runId }: { runId: string }) {
  const d = useAgent(runId);
  return <div data-testid="state">{d ? d.state : "none"}</div>;
}

test("polls every 2 s while running and stops when done", async () => {
  vi.useFakeTimers();
  const get = vi
    .spyOn(api, "agentStatus")
    .mockResolvedValueOnce(decision("running", 1))
    .mockResolvedValueOnce(decision("running", 2))
    .mockResolvedValue(decision("done"));
  render(<Harness runId="R1" />);
  await act(() => vi.advanceTimersByTimeAsync(0));
  expect(screen.getByTestId("state")).toHaveTextContent("running");
  expect(get).toHaveBeenCalledTimes(1);
  await act(() => vi.advanceTimersByTimeAsync(1_900));
  expect(get).toHaveBeenCalledTimes(1);
  await act(() => vi.advanceTimersByTimeAsync(100));
  expect(get).toHaveBeenCalledTimes(2);
  await act(() => vi.advanceTimersByTimeAsync(2_000));
  expect(get).toHaveBeenCalledTimes(3);
  expect(screen.getByTestId("state")).toHaveTextContent("done");
  await act(() => vi.advanceTimersByTimeAsync(20_000));
  expect(get).toHaveBeenCalledTimes(3);
  expect(get).toHaveBeenCalledWith("R1");
});

test("polls at most 60 times", async () => {
  vi.useFakeTimers();
  const get = vi.spyOn(api, "agentStatus").mockResolvedValue(decision("running"));
  render(<Harness runId="R1" />);
  await act(() => vi.advanceTimersByTimeAsync(200_000));
  expect(get).toHaveBeenCalledTimes(60);
});

test("fallback and off stop the polling; no agent (404) or an error is none", async () => {
  vi.useFakeTimers();
  for (const [answer, shown] of [
    [decision("fallback"), "fallback"],
    [decision("off"), "off"],
    [null, "none"],
  ] as const) {
    const get = vi.spyOn(api, "agentStatus").mockResolvedValue(answer);
    const { unmount } = render(<Harness runId="R1" />);
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(screen.getByTestId("state")).toHaveTextContent(shown);
    expect(get).toHaveBeenCalledTimes(1);
    unmount();
    get.mockRestore();
  }
  vi.spyOn(api, "agentStatus").mockRejectedValue(new Error("network"));
  render(<Harness runId="R1" />);
  await act(() => vi.advanceTimersByTimeAsync(0));
  expect(screen.getByTestId("state")).toHaveTextContent("none");
});

function show(d: AgentDecision | null, lang: Lang = "TR") {
  return render(
    <LangContext.Provider value={lang}>
      <AgentPanel decision={d} />
    </LangContext.Provider>,
  );
}

test("five nodes with their state; the animation only on the running node", () => {
  show(decision("running", 2));
  const panel = screen.getByTestId("agent-panel");
  expect(panel).toHaveTextContent("Ajan değerlendirmesi");
  const nodes = within(panel).getAllByTestId("agent-node");
  expect(nodes.map((n) => n.dataset.state)).toEqual(["done", "done", "running", "waiting", "waiting"]);
  expect(nodes.map((n) => n.dataset.node)).toEqual(["adaylar", "arastirma", "analiz", "kontrol", "karar"]);
  expect(within(nodes[2]).getByTestId("node-spinner")).toBeInTheDocument();
  expect(within(panel).getAllByTestId("node-spinner")).toHaveLength(1);
  expect(nodes[0]).toHaveTextContent("tamam");
  expect(nodes[3]).toHaveTextContent("bekliyor");
  expect(nodes[0]).toHaveTextContent("8 sn"); // started 10:00:00, finished 10:00:08
});

test("a click on a node opens its notes and sub-nodes", async () => {
  const d = decision("done");
  show(d);
  const nodes = screen.getAllByTestId("agent-node");
  expect(screen.queryByTestId("node-details")).toBeNull();
  await userEvent.click(nodes[2]);
  expect(nodes[2]).toHaveAttribute("aria-expanded", "true");
  const details = screen.getByTestId("node-details");
  const analiz = d.nodes[2];
  analiz.children.forEach((c) => {
    expect(details).toHaveTextContent(c.label);
    c.notes.forEach((n) => expect(details).toHaveTextContent(n));
  });
  await userEvent.click(nodes[3]);
  expect(screen.getByTestId("node-details")).toHaveTextContent(d.nodes[3].notes[0]);
  await userEvent.click(nodes[3]);
  expect(screen.queryByTestId("node-details")).toBeNull();
});

test("a failed node shows hata; the cost of the decision", () => {
  show(decision("fallback"));
  const nodes = screen.getAllByTestId("agent-node");
  expect(nodes[3].dataset.state).toBe("failed");
  expect(nodes[3]).toHaveTextContent("hata");
  expect(screen.getByTestId("agent-panel")).toHaveTextContent("$0,09");
});

test("off or no decision: nothing", () => {
  const { container } = show(decision("off"));
  expect(container).toBeEmptyDOMElement();
  const { container: c2 } = show(null);
  expect(c2).toBeEmptyDOMElement();
});

test("W20 EN node row", () => {
  show(decision("running", 2), "EN");
  const panel = screen.getByTestId("agent-panel");
  expect(panel).toHaveTextContent("Agent review");
  expect(panel).toHaveTextContent("running");
  expect(panel).toHaveTextContent("waiting");
  expect(panel).toHaveTextContent("8 s");
});
