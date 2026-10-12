import { screen, waitFor } from "@testing-library/react";
import { api } from "../api/client";
import type { NarrativeBrief } from "../api/types";
import { renderDashboard } from "../test/render";
import { sample } from "../test/samples";

const base = (): NarrativeBrief => ({
  run_id: sample("run_p01_ready").result.run_id,
  lang: "TR",
  text: "",
  source: "template",
  model: "",
  prompt_version: "b1",
  checks: [],
  created_at: "2026-10-12T09:00:00+03:00",
  cost_usd: 0,
  cite: [],
});
const llmBrief = (text: string): NarrativeBrief => ({ ...base(), text, source: "llm", model: "claude-haiku-5-5", cost_usd: 0.003, cite: ["E2075d858", "fund:PPN"] });
const templateBrief = (): NarrativeBrief => ({ ...base(), text: "Varlığı TL mevduat ağırlıklı." });

beforeEach(() => localStorage.clear());
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

test("replaces the plain sentence with the LLM brief", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.spyOn(api, "brief").mockResolvedValueOnce("running").mockResolvedValue(llmBrief("Müşteri mevduat ağırlıklı; düzenli gelir istiyor."));
  renderDashboard(sample("run_p01_ready"));
  expect(screen.getByTestId("brief-text")).toHaveTextContent(sample("run_p01_ready").result.persona.durum);
  vi.advanceTimersByTime(2100);
  expect(await screen.findByText("AI özeti")).toBeInTheDocument();
  expect(screen.getByTestId("brief-text")).toHaveTextContent("düzenli gelir istiyor");
  expect(screen.getByText("AI özeti")).toHaveAttribute("title", expect.stringContaining("claude-haiku-5-5"));
});

test("keeps the plain sentence when the brief fails", async () => {
  vi.spyOn(api, "brief").mockResolvedValue(templateBrief());
  renderDashboard(sample("run_p01_ready"));
  await waitFor(() => expect(api.brief).toHaveBeenCalled());
  expect(screen.queryByText("AI özeti")).toBeNull();
  expect(screen.getByTestId("brief-text")).toHaveTextContent(sample("run_p01_ready").result.persona.durum);
});

test("an API error keeps the plain sentence", async () => {
  vi.spyOn(api, "brief").mockRejectedValue(new Error("boom"));
  renderDashboard(sample("run_p01_ready"));
  await waitFor(() => expect(api.brief).toHaveBeenCalled());
  expect(screen.queryByText("AI özeti")).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("stops polling after 10 running answers", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const brief = vi.spyOn(api, "brief").mockResolvedValue("running");
  renderDashboard(sample("run_p01_ready"));
  for (let i = 0; i < 12; i++) {
    vi.advanceTimersByTime(2100);
    await Promise.resolve();
  }
  await waitFor(() => expect(brief).toHaveBeenCalledTimes(10));
  vi.advanceTimersByTime(10000);
  expect(brief).toHaveBeenCalledTimes(10);
});

test("no brief call for a needs_rm_input run", () => {
  const brief = vi.spyOn(api, "brief");
  renderDashboard(sample("run_needs_input"));
  expect(brief).not.toHaveBeenCalled();
});

test("the language switch asks for the brief in that language", async () => {
  const brief = vi.spyOn(api, "brief").mockResolvedValue(llmBrief("The client holds TL deposits."));
  renderDashboard(sample("run_p01_ready"), () => {}, "EN");
  await waitFor(() => expect(brief).toHaveBeenCalledWith(sample("run_p01_ready").result.run_id, "EN"));
  expect(await screen.findByText("AI summary")).toBeInTheDocument();
});

test("Kaynaklar lists what the LLM brief cites", async () => {
  vi.spyOn(api, "brief").mockResolvedValue(llmBrief("Müşteri mevduat ağırlıklı."));
  const v = sample("run_p01_ready");
  renderDashboard(v);
  await screen.findByText("AI özeti");
  const { default: userEvent } = await import("@testing-library/user-event");
  await userEvent.click(screen.getByRole("button", { name: /Kaynaklar/ }));
  expect(screen.getByTestId("brief-sources")).toHaveTextContent("E2075d858");
  expect(screen.getByTestId("brief-sources")).toHaveTextContent(v.options["fund:PPN"].short_label);
});

test("the real LLM brief sample: text, label, its cites under Kaynaklar", async () => {
  const b = sample("brief_p01_tr");
  vi.spyOn(api, "brief").mockResolvedValue(b);
  const v = sample("run_p01_ready");
  renderDashboard(v);
  await waitFor(() => expect(screen.getByTestId("brief-text")).toHaveTextContent(b.text));
  expect(screen.getByText("AI özeti")).toBeInTheDocument();
  expect(b.text.length).toBeLessThanOrEqual(280);
  const { default: userEvent } = await import("@testing-library/user-event");
  const sources = screen.getByRole("button", { name: /Kaynaklar/ });
  const base = 1 + (v.result.persona.rm_notu.trim() ? 1 : 0);
  expect(sources).toHaveTextContent(`(${base + b.cite.length})`);
  await userEvent.click(sources);
  b.cite.filter((c) => v.options[c]).forEach((c) => expect(screen.getByTestId("brief-sources")).toHaveTextContent(v.options[c].short_label));
});
