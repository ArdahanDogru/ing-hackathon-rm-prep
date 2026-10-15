// W24: the RM marks each research bullet ✓ (doğrulandı) or ✗ (yanlış / alakasız); the other
// candidates' research shows after an agent run.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import type { ProductResearch, ResearchFinding, ResearchView } from "../api/types";
import { renderWith } from "../test/render";
import { sample } from "../test/samples";
import { ResearchPanel } from "./ResearchPanel";

afterEach(() => vi.restoreAllMocks());

const v = sample("run_p01_ready");
const f = (id: string, text: string, over: Partial<ResearchFinding> = {}): ResearchFinding => ({
  id, text, topic: "strateji", confidence: "medium", sources: [{ url: "https://example.com/" + id, title: "Kaynak", published: "" }], date: "", mark: null, ...over,
});
const product = (option_id: string, findings: ResearchFinding[], news: ResearchFinding[] = []): ProductResearch => ({
  option_id, label: option_id.toUpperCase(), company: "", summary: "", findings, news, news_days: news.length ? 30 : 0, lang: "TR",
  provider: "exa", created_at: "", cost_usd: 0, checks: [], error: "", version: 2,
});
const ready = (products: ProductResearch[]): ResearchView => ({ state: "ready", products, questions: [] });
const bullet = (text: string) => screen.getByText(text).closest("li") as HTMLElement;

test("each bullet has ✓ and ✗; ✓ posts the mark and shows RM doğruladı; a second click removes it", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready([product(v.top[0], [f("Fa0000001", "Fon kısa vadeli araçlara yatırım yapar.")])]));
  const mark = vi.spyOn(api, "setMark").mockImplementation(async (m) => ({ finding_id: m.finding_id, mark: m.mark }));
  renderWith(<ResearchPanel view={v} />);
  await screen.findByText("Fon kısa vadeli araçlara yatırım yapar.");
  const li = bullet("Fon kısa vadeli araçlara yatırım yapar.");
  const ok = within(li).getByRole("button", { name: "Doğrulandı" });
  const wrong = within(li).getByRole("button", { name: "Yanlış / alakasız" });
  expect(ok).toHaveAttribute("aria-pressed", "false");
  expect(wrong).toHaveAttribute("aria-pressed", "false");
  await userEvent.click(ok);
  expect(mark).toHaveBeenCalledWith({ finding_id: "Fa0000001", option_id: v.top[0], mark: "ok", run_id: v.result.run_id });
  await waitFor(() => expect(ok).toHaveAttribute("aria-pressed", "true"));
  expect(li).toHaveTextContent("RM doğruladı");
  await userEvent.click(ok);
  expect(mark).toHaveBeenLastCalledWith({ finding_id: "Fa0000001", option_id: v.top[0], mark: null, run_id: v.result.run_id });
  await waitFor(() => expect(ok).toHaveAttribute("aria-pressed", "false"));
  expect(li).not.toHaveTextContent("RM doğruladı");
});

test("✗ dims the bullet with ajana verilmez; news bullets have the toggles too", async () => {
  vi.spyOn(api, "research").mockResolvedValue(
    ready([product(v.top[0], [f("Fa0000001", "Öne çıkan.")], [f("Fa0000002", "Yönetici değişti.", { topic: "haber", date: "2026-10-10" })])]),
  );
  vi.spyOn(api, "setMark").mockImplementation(async (m) => ({ finding_id: m.finding_id, mark: m.mark }));
  renderWith(<ResearchPanel view={v} />);
  await screen.findByText(/Yönetici değişti\./);
  const li = bullet("Yönetici değişti.");
  await userEvent.click(within(li).getByRole("button", { name: "Yanlış / alakasız" }));
  await waitFor(() => expect(li).toHaveAttribute("data-mark", "wrong"));
  expect(li).toHaveClass("opacity-50");
  expect(li).toHaveTextContent("ajana verilmez");
});

test("the marks of the research status show at once", async () => {
  vi.spyOn(api, "research").mockResolvedValue(
    ready([product(v.top[0], [f("Fa0000001", "Doğru.", { mark: "ok" }), f("Fa0000002", "Yanlış.", { mark: "wrong" }), f("Fa0000003", "Bakılmadı.")])]),
  );
  renderWith(<ResearchPanel view={v} />);
  await screen.findByText("Doğru.");
  expect(bullet("Doğru.")).toHaveTextContent("RM doğruladı");
  expect(bullet("Yanlış.")).toHaveAttribute("data-mark", "wrong");
  expect(bullet("Bakılmadı.")).not.toHaveAttribute("data-mark");
});

test("a failed mark keeps the old state and says why", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready([product(v.top[0], [f("Fa0000001", "Öne çıkan.")])]));
  vi.spyOn(api, "setMark").mockRejectedValue(new ApiError(422, "unknown finding"));
  renderWith(<ResearchPanel view={v} />);
  await screen.findByText("Öne çıkan.");
  const li = bullet("Öne çıkan.");
  await userEvent.click(within(li).getByRole("button", { name: "Doğrulandı" }));
  expect(await within(li).findByRole("status")).toHaveTextContent("unknown finding");
  expect(within(li).getByRole("button", { name: "Doğrulandı" })).toHaveAttribute("aria-pressed", "false");
});

test("a finding without an id has no toggles", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready([product(v.top[0], [{ ...f("x", "Kimliksiz."), id: undefined }])]));
  renderWith(<ResearchPanel view={v} />);
  await screen.findByText("Kimliksiz.");
  expect(within(bullet("Kimliksiz.")).queryByRole("button")).toBeNull();
});

test("the other candidates (researched by the agent) are grouped under their own heading", async () => {
  vi.spyOn(api, "research").mockResolvedValue(
    ready([product(v.top[0], [f("Fa0000001", "Önerilen fon.")]), product("fund:OSD", [f("Fa0000009", "Aday fon.")])]),
  );
  renderWith(<ResearchPanel view={v} />);
  const others = await screen.findByTestId("research-others");
  expect(others).toHaveTextContent("Diğer adaylar · ajan araştırdı");
  expect(within(others).getByText("Aday fon.")).toBeInTheDocument();
  expect(within(others).queryByText("Önerilen fon.")).toBeNull();
  expect(within(within(others).getByText("Aday fon.").closest("li") as HTMLElement).getByRole("button", { name: "Doğrulandı" })).toBeInTheDocument();
});

test("a new refresh asks for the research again (after an agent run)", async () => {
  const get = vi.spyOn(api, "research").mockResolvedValue(ready([product(v.top[0], [f("Fa0000001", "Önerilen fon.")])]));
  const { rerender } = renderWith(<ResearchPanel view={v} refresh={0} />);
  await screen.findByText("Önerilen fon.");
  get.mockResolvedValue(ready([product(v.top[0], [f("Fa0000001", "Önerilen fon.")]), product("fund:OSD", [f("Fa0000009", "Aday fon.")])]));
  rerender(<ResearchPanel view={v} refresh={1} />);
  expect(await screen.findByText("Aday fon.")).toBeInTheDocument();
  expect(get).toHaveBeenCalledTimes(2);
});

test("W24 EN marks", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready([product(v.top[0], [f("Fa0000001", "Doğru.", { mark: "ok" }), f("Fa0000002", "Yanlış.", { mark: "wrong" })]), product("fund:OSD", [])]));
  renderWith(<ResearchPanel view={v} />, { lang: "EN" });
  await screen.findByText("Doğru.");
  expect(bullet("Doğru.")).toHaveTextContent("checked by the RM");
  expect(bullet("Yanlış.")).toHaveTextContent("not given to the agent");
  expect(within(bullet("Doğru.")).getByRole("button", { name: "Checked" })).toBeInTheDocument();
  expect(within(bullet("Doğru.")).getByRole("button", { name: "Wrong / not relevant" })).toBeInTheDocument();
  expect(screen.getByTestId("research-others")).toHaveTextContent("Other candidates · researched by the agent");
});
