// W43: the AI check of the client profile (docs/web-ui.md).
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "../api/client";
import { resetAgentMock, resolveMock } from "../api/mock";
import type { ProfileAIView, RunView } from "../api/types";
import { Dashboard } from "../screens/Dashboard";
import { renderDashboard, renderWith } from "../test/render";
import { sample } from "../test/samples";
import { PersonaPanel } from "./PersonaPanel";
import { aiChecks } from "./ProfileAI";

afterEach(() => vi.restoreAllMocks());

const DONE: ProfileAIView = {
  state: "done",
  findings: [
    {
      kind: "conflict",
      fields: ["durum", "likidite_ihtiyaci"],
      quotes: [
        { field: "durum", text: "gelecek yıl ev peşinatı" },
        { field: "likidite_ihtiyaci", text: "Düşük" },
      ],
      text: "Gelecek yıl bir ev peşinatı var, ama likidite ihtiyacı Düşük.",
    },
    { kind: "confirm", fields: ["rm_notu"], quotes: [{ field: "rm_notu", text: "45 yaşında" }], text: "RM notunda yaş 45, profilde 62." },
  ],
  dropped: 0,
  model: "claude-opus-5-5",
  cost_usd: 0.014,
  reason: "",
};

const p01 = (): RunView => sample("run_p01_ready");
const testRun = (): RunView => sample("run_test");

test("while it runs: a muted line 'AI kontrolü sürüyor…', no block", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue({ state: "running", findings: [] });
  renderDashboard(p01());
  const line = await screen.findByTestId("ai-check-status");
  expect(line).toHaveTextContent("AI kontrolü sürüyor…");
  expect(screen.queryByTestId("profile-check")).toBeNull();
});

test("it asks again every 2 s while it runs, then shows the findings", async () => {
  const spy = vi
    .spyOn(api, "profileCheck")
    .mockResolvedValueOnce({ state: "running", findings: [] })
    .mockResolvedValue(DONE);
  renderDashboard(p01());
  await screen.findByText("AI kontrolü sürüyor…");
  await screen.findAllByTestId("ai-finding", {}, { timeout: 4000 });
  expect(spy).toHaveBeenCalledTimes(2);
  expect(spy).toHaveBeenCalledWith(p01().result.run_id, "TR");
  expect(screen.queryByTestId("ai-check-status")).toBeNull();
});

test("done: the AI findings after the rule findings, with the label, the text and the quotes", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue(DONE);
  const v = testRun();
  renderDashboard(v);
  const ai = await screen.findAllByTestId("ai-finding");
  const block = screen.getByTestId("profile-checks");
  const items = within(block).getAllByTestId("profile-check");
  expect(items).toHaveLength(3);
  expect(items[0]).toHaveTextContent(v.profile_checks![0].text); // the rule finding first
  expect(items[1]).toContainElement(ai[0]);
  expect(ai[0]).toHaveTextContent("AI ile bulundu · teyit edin");
  expect(ai[0]).toHaveTextContent(DONE.findings[0].text);
  const quotes = within(ai[0]).getAllByTestId("ai-quote");
  expect(quotes.map((q) => q.textContent)).toEqual(["durum: “gelecek yıl ev peşinatı”", "likidite ihtiyacı: “Düşük”"]);
  expect(ai[1]).toHaveAttribute("data-kind", "confirm");
  expect(block).toHaveTextContent("Profilde çelişki (3)"); // the title counts all findings
});

test("done with AI findings only: the block shows with the AI count", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue({ ...DONE, findings: [DONE.findings[1]] });
  renderDashboard(p01());
  await screen.findByTestId("ai-finding");
  expect(screen.getByTestId("profile-checks")).toHaveTextContent("Sorulacak (1)");
});

test("the AI findings are added at the end of 'Teyit edin'", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue(DONE);
  const v = testRun();
  renderDashboard(v);
  await screen.findAllByTestId("ai-finding");
  const items = screen.getAllByTestId("confirm-item");
  expect(items).toHaveLength(v.to_confirm.length + 2);
  expect(items[items.length - 2]).toHaveTextContent(DONE.findings[0].text);
  expect(items[items.length - 1]).toHaveTextContent(DONE.findings[1].text);
});

test("failed: a small muted line with the reason; off: nothing", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue({ state: "failed", findings: [], reason: "daily limit" });
  const { unmount } = renderDashboard(p01());
  const line = await screen.findByTestId("ai-check-status");
  expect(line).toHaveTextContent("AI kontrolü yapılamadı");
  expect(line).toHaveTextContent("daily limit");
  expect(screen.queryByTestId("profile-checks")).toBeNull();
  unmount();
  const off = vi.spyOn(api, "profileCheck").mockResolvedValue({ state: "off", findings: [], reason: "ai check off" });
  renderDashboard(p01());
  await vi.waitFor(() => expect(off).toHaveBeenCalled());
  expect(screen.queryByTestId("ai-check-status")).toBeNull();
  expect(screen.queryByTestId("profile-checks")).toBeNull();
});

test("an error of the route gives nothing", async () => {
  const spy = vi.spyOn(api, "profileCheck").mockRejectedValue(new Error("down"));
  renderDashboard(p01());
  await vi.waitFor(() => expect(spy).toHaveBeenCalled());
  expect(screen.queryByTestId("ai-check-status")).toBeNull();
});

test("the edit panel: the fields of an AI finding get the amber mark", async () => {
  const checks = aiChecks(DONE);
  render(<PersonaPanel persona={p01().result.persona} checks={checks} onApply={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getByTestId("field-check-likidite_ihtiyaci")).toHaveTextContent(DONE.findings[0].text);
  expect(screen.getByTestId("field-check-rm_notu")).toHaveTextContent(DONE.findings[1].text);
  expect(screen.getByLabelText("likidite ihtiyacı")).toHaveClass("border-[#F79009]");
});

test("the dashboard gives the AI findings to the edit panel", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue(DONE);
  renderWith(<Dashboard view={p01()} onView={() => {}} onPersona={() => {}} />);
  await screen.findAllByTestId("ai-finding");
  await userEvent.click(screen.getAllByRole("button", { name: "Profili düzenle" })[0]);
  expect(screen.getByTestId("field-check-rm_notu")).toBeInTheDocument();
});

test("EN: the label, the field labels and the status lines", async () => {
  const spy = vi.spyOn(api, "profileCheck").mockResolvedValue(DONE);
  const { unmount } = renderDashboard(p01(), () => {}, "EN");
  const ai = await screen.findAllByTestId("ai-finding");
  expect(spy).toHaveBeenCalledWith(p01().result.run_id, "EN");
  expect(ai[0]).toHaveTextContent("Found by AI · confirm");
  expect(within(ai[0]).getAllByTestId("ai-quote")[1]).toHaveTextContent("liquidity need: “Düşük”");
  unmount();
  vi.spyOn(api, "profileCheck").mockResolvedValue({ state: "running", findings: [] });
  const r = renderDashboard(p01(), () => {}, "EN");
  expect(await screen.findByTestId("ai-check-status")).toHaveTextContent("AI check running…");
  r.unmount();
  vi.spyOn(api, "profileCheck").mockResolvedValue({ state: "failed", findings: [], reason: "x" });
  renderDashboard(p01(), () => {}, "EN");
  expect(await screen.findByTestId("ai-check-status")).toHaveTextContent("The AI check could not be done");
});

test("dev:mock: running first, then done with a conflict (two quotes) and a confirm; P02 failed", () => {
  resetAgentMock();
  const load = (name: string) => sample(name as never) as unknown;
  const id = p01().result.run_id;
  const now = vi.spyOn(Date, "now").mockReturnValue(1_000_000);
  const first = resolveMock("GET", `/api/runs/${id}/profile-check?lang=TR`, {}, load);
  expect(first.status).toBe(202);
  expect((first.body as ProfileAIView).state).toBe("running");
  now.mockReturnValue(1_000_000 + 60_000);
  const done = resolveMock("GET", `/api/runs/${id}/profile-check?lang=TR`, {}, load).body as ProfileAIView;
  expect(done.state).toBe("done");
  expect(done.findings.map((f) => f.kind)).toEqual(["conflict", "confirm"]);
  expect(done.findings[0].quotes).toHaveLength(2);
  const p02 = (sample("run_p02_ready") as RunView).result.run_id;
  resolveMock("GET", `/api/runs/${p02}/profile-check?lang=TR`, {}, load);
  now.mockReturnValue(1_000_000 + 120_000);
  const failed = resolveMock("GET", `/api/runs/${p02}/profile-check?lang=TR`, {}, load).body as ProfileAIView;
  expect(failed.state).toBe("failed");
  expect(failed.reason).not.toBe("");
  resetAgentMock();
});
