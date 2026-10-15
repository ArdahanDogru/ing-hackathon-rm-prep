// W24: the RM starts the agent ("Ajanı çalıştır" with N) and can run it again.
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import { agentDecision, notStarted } from "../api/agentSample";
import type { Lang } from "../api/types";
import { renderDashboard } from "../test/render";
import { sample } from "../test/samples";

beforeEach(() => localStorage.clear());
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const view = () => sample("run_p01_ready");

async function showStart(lang: Lang = "TR") {
  const get = vi.spyOn(api, "agentStatus").mockResolvedValue(notStarted(view()));
  renderDashboard(view(), () => {}, lang);
  const box = await screen.findByTestId("agent-picks");
  return { get, box };
}

test("before a run: the text, the field Aday sayısı (10) and Ajanı çalıştır; the engine's top 3 stays", async () => {
  const v = view();
  const { box } = await showStart();
  expect(box).toHaveTextContent("Ajan, motorun en iyi 10 adayını araştırıp ilk 3'ü seçer.");
  expect(within(box).getByRole("spinbutton", { name: "Aday sayısı" })).toHaveValue(10);
  expect(within(box).getByRole("button", { name: "Ajanı çalıştır" })).toBeEnabled();
  expect(box).not.toHaveTextContent("henüz çalıştırılmadı");
  expect(screen.queryByTestId("agent-panel")).toBeNull();
  expect(screen.getAllByTestId("option-card").map((c) => c.getAttribute("aria-label"))).toEqual(v.top.map((id) => v.options[id].label));
  // the box sits next to Gündem (W23 row 1)
  expect(within(screen.getByTestId("dash-row1")).getByTestId("agent-picks")).toBe(box);
});

test("Ajanı çalıştır posts N, shows the node row and polls until done", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const v = view();
  const { get, box } = await showStart();
  const start = vi.spyOn(api, "startAgent").mockResolvedValue(agentDecision(v, "running", 0));
  get.mockResolvedValueOnce(agentDecision(v, "running", 2)).mockResolvedValue(agentDecision(v, "done"));
  const field = within(box).getByRole("spinbutton", { name: "Aday sayısı" });
  await userEvent.clear(field);
  await userEvent.type(field, "15");
  await userEvent.click(within(box).getByRole("button", { name: "Ajanı çalıştır" }));
  expect(start).toHaveBeenCalledWith(v.result.run_id, 15);
  expect(await screen.findByTestId("agent-panel")).toBeInTheDocument();
  expect(screen.getByTestId("agent-picks")).toHaveTextContent("Motor önerisi · ajan değerlendiriyor…");
  await act(() => vi.advanceTimersByTimeAsync(4_100));
  expect(await within(screen.getByTestId("agent-picks")).findByText("Ajan önerisi")).toBeInTheDocument();
});

test("N must be 3–20: the button is off outside", async () => {
  const { box } = await showStart();
  const field = within(box).getByRole("spinbutton", { name: "Aday sayısı" });
  const button = within(box).getByRole("button", { name: "Ajanı çalıştır" });
  for (const [n, ok] of [["2", false], ["3", true], ["20", true], ["21", false], ["", false]] as const) {
    await userEvent.clear(field);
    if (n) await userEvent.type(field, n);
    if (ok) expect(button).toBeEnabled();
    else expect(button).toBeDisabled();
  }
  expect(box).toHaveTextContent("3–20");
});

test("a 422 shows the server detail under the form", async () => {
  const { box } = await showStart();
  vi.spyOn(api, "startAgent").mockRejectedValue(new ApiError(422, "the run is not ready"));
  await userEvent.click(within(box).getByRole("button", { name: "Ajanı çalıştır" }));
  expect(await within(box).findByRole("alert")).toHaveTextContent("the run is not ready");
  expect(within(box).getByRole("button", { name: "Ajanı çalıştır" })).toBeInTheDocument();
});

test("after a run: Yeniden çalıştır with the N of the run", async () => {
  const v = view();
  const get = vi.spyOn(api, "agentStatus").mockResolvedValue({ ...agentDecision(v, "done"), n_candidates: 12 });
  renderDashboard(v);
  const box = await screen.findByTestId("agent-picks");
  await within(box).findByText("Ajan önerisi");
  const start = vi.spyOn(api, "startAgent").mockResolvedValue(agentDecision(v, "running", 0));
  get.mockResolvedValue(agentDecision(v, "running", 1)); // the server runs it again
  expect(within(box).getByRole("spinbutton", { name: "Aday sayısı" })).toHaveValue(12);
  await userEvent.click(within(box).getByRole("button", { name: "Yeniden çalıştır" }));
  expect(start).toHaveBeenCalledWith(v.result.run_id, 12);
  expect(await screen.findByText("Motor önerisi · ajan değerlendiriyor…")).toBeInTheDocument();
});

test("a fallback can run again too", async () => {
  vi.spyOn(api, "agentStatus").mockResolvedValue(agentDecision(view(), "fallback"));
  renderDashboard(view());
  const box = await screen.findByTestId("agent-picks");
  expect(await within(box).findByRole("button", { name: "Yeniden çalıştır" })).toBeInTheDocument();
});

test("off for another reason (no key): the reason and no button", async () => {
  vi.spyOn(api, "agentStatus").mockResolvedValue(agentDecision(view(), "off"));
  renderDashboard(view());
  const box = await screen.findByTestId("agent-picks");
  expect(box).toHaveTextContent("Ajan kapalı: ANTHROPIC_API_KEY yok");
  expect(within(box).queryByRole("button")).toBeNull();
  expect(screen.queryByTestId("agent-panel")).toBeNull();
});

test("no agent on the server (404): no box, Gündem and Öneriler side by side", async () => {
  const get = vi.spyOn(api, "agentStatus").mockResolvedValue(null);
  renderDashboard(view());
  await waitFor(() => expect(get).toHaveBeenCalled());
  expect(screen.queryByTestId("agent-picks")).toBeNull();
  expect(within(screen.getByTestId("dash-row1")).getByTestId("options-compare")).toBeInTheDocument();
});

test("W24 EN start form", async () => {
  const { box } = await showStart("EN");
  expect(box).toHaveTextContent("The agent researches the engine's best 10 candidates and picks the top 3.");
  expect(within(box).getByRole("spinbutton", { name: "Number of candidates" })).toHaveValue(10);
  expect(within(box).getByRole("button", { name: "Run the agent" })).toBeInTheDocument();
});
