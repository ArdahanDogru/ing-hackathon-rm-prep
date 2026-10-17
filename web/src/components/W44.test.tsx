// W44: a profile conflict must be resolved before the approval (docs/web-ui.md).
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import { resetAgentMock, resolveMock } from "../api/mock";
import type { ProfileAIView, RunView } from "../api/types";
import { Dashboard } from "../screens/Dashboard";
import { renderDashboard, renderWith } from "../test/render";
import { sample } from "../test/samples";

afterEach(() => vi.restoreAllMocks());

const testRun = (): RunView => sample("run_test"); // one rule conflict: risk_vs_growth
const p01 = (): RunView => sample("run_p01_ready");
const APPROVE = "Onayla ve metni hazırla";

const AI: ProfileAIView = {
  state: "done",
  findings: [
    { id: "ai:abc123", kind: "conflict", fields: ["rm_notu", "yas"], quotes: [{ field: "rm_notu", text: "45 yaşında" }], text: "RM notunda yaş 45, profilde 62." },
    { id: "ai:def456", kind: "confirm", fields: ["durum"], quotes: [], text: "Ev peşinatının tarihini sorun." },
  ],
  reason: "",
};

const conflictItem = (text: string) =>
  within(screen.getByTestId("profile-checks")).getAllByTestId("profile-check").find((li) => li.textContent?.includes(text))!;

async function confirmWith(item: HTMLElement, reason: string) {
  await userEvent.click(within(item).getByRole("button", { name: "Müşteriyle teyit edildi" }));
  await userEvent.type(within(item).getByRole("textbox", { name: "Neden" }), reason);
  await userEvent.click(within(item).getByRole("button", { name: "Kaydet" }));
}

test("each conflict has the two actions; a confirm finding has none", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue(AI);
  renderWith(<Dashboard view={testRun()} onView={() => {}} onPersona={() => {}} />);
  await screen.findAllByTestId("ai-finding");
  const rule = conflictItem("Risk profili Muhafazakâr");
  expect(within(rule).getByRole("button", { name: "Profili düzelt" })).toBeInTheDocument();
  expect(within(rule).getByRole("button", { name: "Müşteriyle teyit edildi" })).toBeInTheDocument();
  const ai = conflictItem("RM notunda yaş 45");
  expect(within(ai).getByRole("button", { name: "Müşteriyle teyit edildi" })).toBeInTheDocument();
  const question = conflictItem("Ev peşinatının");
  expect(within(question).queryByRole("button")).toBeNull();
});

test("'Profili düzelt' opens the edit panel with the conflict's fields marked", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue({ state: "off", findings: [] });
  renderWith(<Dashboard view={testRun()} onView={() => {}} onPersona={() => {}} />);
  await userEvent.click(within(conflictItem("Risk profili")).getByRole("button", { name: "Profili düzelt" }));
  expect(screen.getByTestId("field-check-risk_profili")).toBeInTheDocument();
  expect(screen.getByTestId("field-check-oncelikler")).toBeInTheDocument();
});

test("'Müşteriyle teyit edildi': a required reason; then the item shows the reason and 'teyit edildi'", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue({ state: "off", findings: [] });
  renderDashboard(testRun());
  const item = conflictItem("Risk profili");
  await userEvent.click(within(item).getByRole("button", { name: "Müşteriyle teyit edildi" }));
  const save = within(item).getByRole("button", { name: "Kaydet" });
  expect(save).toBeDisabled();
  await userEvent.type(within(item).getByRole("textbox", { name: "Neden" }), "   ");
  expect(save).toBeDisabled(); // spaces are no reason
  await userEvent.type(within(item).getByRole("textbox", { name: "Neden" }), "Büyüme hedefi uzun vadeli birikim için");
  await userEvent.click(save);
  expect(item).toHaveTextContent("teyit edildi");
  expect(item).toHaveTextContent("Müşteriyle teyit edildi: Büyüme hedefi uzun vadeli birikim için");
  expect(within(item).queryByRole("textbox")).toBeNull();
});

test("the approval bar: disabled with 'n çelişki çözülmedi' and a hover text until every conflict has a reason", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue(AI);
  renderDashboard(testRun());
  await screen.findAllByTestId("ai-finding");
  const button = screen.getByRole("button", { name: APPROVE });
  expect(button).toBeDisabled();
  const open = screen.getByTestId("unresolved");
  expect(open).toHaveTextContent("2 çelişki çözülmedi");
  expect(open).toHaveAttribute("title", expect.stringContaining("Profili düzelt"));
  expect(button).toHaveAttribute("title", expect.stringContaining("Müşteriyle teyit edildi"));
  await confirmWith(conflictItem("Risk profili"), "uzun vade");
  expect(screen.getByTestId("unresolved")).toHaveTextContent("1 çelişki çözülmedi");
  await confirmWith(conflictItem("RM notunda"), "yaş 62 doğru");
  expect(screen.queryByTestId("unresolved")).toBeNull();
  expect(button).toBeEnabled();
  expect(screen.getByRole("button", { name: "Reddet" })).toBeEnabled(); // a rejection needs nothing
});

test("the reasons go with the approval as resolutions", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue(AI);
  const approve = vi.spyOn(api, "approve").mockResolvedValue(sample("run_p01_approved"));
  renderDashboard(testRun());
  await screen.findAllByTestId("ai-finding");
  await confirmWith(conflictItem("Risk profili"), "uzun vade");
  await confirmWith(conflictItem("RM notunda"), "yaş 62 doğru");
  await userEvent.click(screen.getByRole("button", { name: APPROVE }));
  expect(approve).toHaveBeenCalledTimes(1);
  expect(approve.mock.calls[0][1]).toBe("approved");
  expect(approve.mock.calls[0][4]).toEqual([
    { finding_id: "risk_vs_growth", note: "uzun vade" },
    { finding_id: "ai:abc123", note: "yaş 62 doğru" },
  ]);
});

test("a rejection sends no resolutions; no conflict sends an empty list", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue({ state: "off", findings: [] });
  const approve = vi.spyOn(api, "approve").mockResolvedValue(sample("run_p01_approved"));
  renderDashboard(p01());
  expect(screen.queryByTestId("unresolved")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: APPROVE }));
  expect(approve.mock.calls[0][4]).toEqual([]);
});

test("an AI check that is not done never blocks", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue({ state: "running", findings: [] });
  renderDashboard(p01());
  await screen.findByTestId("ai-check-status");
  expect(screen.getByRole("button", { name: APPROVE })).toBeEnabled();
});

test("a 422 shows its text", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue({ state: "off", findings: [] });
  vi.spyOn(api, "approve").mockRejectedValue(new ApiError(422, "Çözülmemiş çelişki var: RM notunda yaş 45"));
  renderDashboard(testRun());
  await confirmWith(conflictItem("Risk profili"), "uzun vade");
  await userEvent.click(screen.getByRole("button", { name: APPROVE }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Çözülmemiş çelişki var: RM notunda yaş 45");
});

test("after the approval: the block shows the recorded reasons, no actions", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue({ state: "off", findings: [] });
  const t = testRun();
  const v: RunView = {
    ...t,
    result: { ...t.result, rm_status: "approved" },
    resolutions: {
      resolutions: [{ id: "risk_vs_growth", source: "rule", text: t.profile_checks![0].text, note: "uzun vade" }],
      ai_check: "running",
      at: "2026-10-17T15:00:00+03:00",
    },
  };
  renderDashboard(v);
  const item = conflictItem("Risk profili");
  expect(item).toHaveTextContent("Müşteriyle teyit edildi: uzun vade");
  expect(within(item).queryByRole("button")).toBeNull();
  expect(screen.getByTestId("profile-checks")).toHaveTextContent("AI kontrolü tamamlanmadan onaylandı (running)");
});

test("EN: the actions, the bar and the recorded reason", async () => {
  vi.spyOn(api, "profileCheck").mockResolvedValue({ state: "off", findings: [] });
  renderWith(<Dashboard view={testRun()} onView={() => {}} onPersona={() => {}} />, { lang: "EN" });
  const item = within(screen.getByTestId("profile-checks")).getAllByTestId("profile-check")[0];
  expect(within(item).getByRole("button", { name: "Fix the profile" })).toBeInTheDocument();
  expect(screen.getByTestId("unresolved")).toHaveTextContent("Unresolved conflicts: 1");
  await userEvent.click(within(item).getByRole("button", { name: "Confirmed with the client" }));
  await userEvent.type(within(item).getByRole("textbox", { name: "Reason" }), "long term");
  await userEvent.click(within(item).getByRole("button", { name: "Save" }));
  expect(item).toHaveTextContent("Confirmed with the client: long term");
  expect(item).toHaveTextContent("confirmed");
});

test("dev:mock: an open conflict gives 422; with the reasons, the approved run has the resolutions", () => {
  resetAgentMock();
  const load = (name: string) => sample(name as never) as unknown;
  const id = testRun().result.run_id;
  const body = { status: "approved", note: "", selected: [] };
  const open = resolveMock("POST", `/api/runs/${id}/approval`, body, load);
  expect(open.status).toBe(422);
  expect((open.body as { detail: string }).detail).toMatch(/^Çözülmemiş çelişki var: Risk profili/);
  const ok = resolveMock("POST", `/api/runs/${id}/approval`, { ...body, resolutions: [{ finding_id: "risk_vs_growth", note: "uzun vade" }] }, load);
  expect(ok.status).toBe(200);
  const view = ok.body as RunView;
  expect(view.result.rm_status).toBe("approved");
  expect(view.resolutions?.resolutions).toEqual([
    { id: "risk_vs_growth", source: "rule", text: testRun().profile_checks![0].text, note: "uzun vade" },
  ]);
  const rejected = resolveMock("POST", `/api/runs/${id}/approval`, { ...body, status: "rejected" }, load);
  expect(rejected.status).toBe(200);
});
