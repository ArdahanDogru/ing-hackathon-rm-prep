import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "../api/client";
import { renderDashboard, renderWith } from "../test/render";
import { sample } from "../test/samples";
import { Dashboard } from "./Dashboard";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

test("test run disables approval", () => {
  renderDashboard(sample("run_test"));
  expect(screen.getByRole("button", { name: "Onayla ve metni hazırla" })).toBeDisabled();
  expect(screen.getByText(/Test:/)).toBeInTheDocument();
  expect(screen.getByText(/yaş 62 → 45/)).toBeInTheDocument();
});

test("needs_rm_input shows questions instead of options", () => {
  renderDashboard(sample("run_needs_input"));
  expect(screen.queryAllByTestId("top-card")).toHaveLength(0);
  expect(screen.getAllByTestId("question").length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: "Onayla ve metni hazırla" })).toBeNull();
});

test("an answer makes a new run", async () => {
  const v = sample("run_needs_input");
  const answer = vi.spyOn(api, "answer").mockResolvedValue(sample("run_p01_ready"));
  const onView = vi.fn();
  renderDashboard(v, onView);
  const q = v.result.questions[0];
  await userEvent.click(within(screen.getAllByTestId("question")[0]).getByRole("button", { name: q.choices[0] }));
  expect(answer).toHaveBeenCalledWith(v.result.run_id, q.question_id, q.choices[0]);
  expect(onView).toHaveBeenCalled();
});

test("a question without choices takes a typed answer", async () => {
  const v = sample("run_needs_input");
  v.result.questions[0].choices = [];
  const answer = vi.spyOn(api, "answer").mockResolvedValue(sample("run_p01_ready"));
  renderDashboard(v);
  await userEvent.type(screen.getByLabelText("Yanıtınız"), "hisse olmasın");
  await userEvent.click(screen.getByRole("button", { name: "Yanıtla" }));
  expect(answer.mock.calls[0][2]).toBe("hisse olmasın");
});

test("a fund row opens its fund card", async () => {
  renderDashboard(sample("run_p01_ready"));
  await userEvent.click(within(screen.getAllByTestId("category")[0]).getByRole("button", { expanded: false }));
  const row = screen.getAllByTestId("fund-row")[0];
  await userEvent.click(within(row).getByRole("button", { name: /Ayrıntılar/ }));
  expect(within(row).getByText("Bu müşteri için neden?")).toBeInTheDocument();
});

test("Düzenle opens the persona panel; Uygula calls onPersona", async () => {
  const onPersona = vi.fn();
  const v = sample("run_p01_ready");
  renderWith(<Dashboard view={v} onView={() => {}} onPersona={onPersona} />);
  await userEvent.click(screen.getByRole("button", { name: "Düzenle" }));
  await userEvent.click(screen.getByRole("button", { name: "Uygula" }));
  expect(onPersona.mock.calls[0][0].persona_id).toBe(v.result.persona.persona_id);
});

test("Kanıt on a top card opens the evidence pop-up", async () => {
  const item = sample("evidence_item");
  vi.spyOn(api, "evidence").mockResolvedValue(item);
  renderDashboard(sample("run_p01_ready"));
  await userEvent.click(within(screen.getAllByTestId("top-card")[0]).getByRole("button", { name: "Kanıt" }));
  expect(await screen.findByRole("dialog")).toHaveTextContent(item.source);
});
