import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import type { ProductResearch, QuestionAnswer, ResearchFinding, ResearchView } from "../api/types";
import { renderWith } from "../test/render";
import { sample } from "../test/samples";
import { ResearchPanel } from "./ResearchPanel";

const NUROL = "https://www.nurolportfoy.com.tr/fon/ppn";
const FONOLOJI = "https://fonoloji.com/ppn";
const HABER = "https://haber.example.org/a/1";
const src = (url: string, published = "") => ({ url, title: "Kaynak", published });
const finding = (text: string, sources: ResearchFinding["sources"], over: Partial<ResearchFinding> = {}): ResearchFinding => ({
  text,
  topic: "strateji",
  confidence: "medium",
  sources,
  date: "",
  ...over,
});
const product = (over: Partial<ProductResearch> = {}): ProductResearch => ({
  option_id: "fund:PPN",
  label: "NUROL PORTFÖY PARA PİYASASI (TL) FONU",
  company: "Nurol Portföy Yönetimi A.Ş.",
  summary: "",
  news: [
    finding("Yönetici değişti.", [src(NUROL, "2026-10-10")], { topic: "haber", date: "2026-10-10" }),
    finding("Fon birleşmesi onaylandı.", [src(FONOLOJI)], { topic: "haber", date: "2026-09-01" }),
  ],
  news_days: 90,
  findings: [
    finding("Fon kısa vadeli borçlanma araçlarına yatırım yapar.", [src(NUROL), src(HABER)], { confidence: "high" }),
    finding("Getiri faiz oranına duyarlıdır.", [src(FONOLOJI)], { topic: "dikkat" }),
  ],
  lang: "TR",
  provider: "exa",
  created_at: "2026-10-14T10:00:00+03:00",
  cost_usd: 0.025,
  checks: [],
  error: "",
  version: 2,
  ...over,
});
const answer = (question: string): QuestionAnswer => ({
  question,
  summary: "",
  findings: [finding("Pay oranı %5,58'e çıktı.", [src(NUROL, "2026-10-08"), src(HABER)], { topic: "soru", confidence: "high" })],
  lang: "TR",
  provider: "exa",
  created_at: "2026-10-14T10:05:00+03:00",
  cost_usd: 0.007,
  checks: [],
  error: "",
  version: 2,
});
const ready = (products = [product()], questions: QuestionAnswer[] = []): ResearchView => ({ state: "ready", products, questions });
const panel = (lang: "TR" | "EN" = "TR") => renderWith(<ResearchPanel view={sample("run_p01_ready")} />, { lang });

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

test("shows a running line, then the product block and the label", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.spyOn(api, "research").mockResolvedValueOnce({ state: "running" }).mockResolvedValue(ready());
  panel();
  expect(await screen.findByTestId("research-running")).toBeInTheDocument();
  vi.advanceTimersByTime(3100);
  expect(await screen.findByRole("heading", { name: "Son haberler" })).toBeInTheDocument();
  expect(screen.getByText("Web kaynağı, doğrulanmamış")).toBeInTheDocument();
  expect(screen.getByText("Nurol Portföy Yönetimi A.Ş.")).toBeInTheDocument();
});

test("a product block: dated news newest first, highlights with source numbers, closed sources", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready());
  panel();
  const block = await screen.findByTestId("research-product");
  expect(within(block).getByRole("heading", { name: "Son haberler" })).toBeInTheDocument();
  expect(within(block).getByRole("heading", { name: "Öne çıkanlar" })).toBeInTheDocument();
  const bullets = Array.from(block.querySelectorAll("ul > li"));
  expect(bullets.map((li) => li.textContent)).toEqual([
    "10.10.2026 · Yönetici değişti. [1]",
    "01.09.2026 · Fon birleşmesi onaylandı. [2]",
    "Fon kısa vadeli borçlanma araçlarına yatırım yapar. [1, 3]",
    "Getiri faiz oranına duyarlıdır. [2]",
  ]);
  const details = block.querySelector("details") as HTMLDetailsElement;
  expect(details.open).toBe(false);
  expect(within(details).getByText("Kaynaklar (3)")).toBeInTheDocument();
  const links = within(details).getAllByRole("link", { hidden: true });
  expect(links.map((a) => a.textContent)).toEqual(["nurolportfoy.com.tr", "fonoloji.com", "haber.example.org"]);
  expect(links[0]).toHaveAttribute("href", NUROL);
  expect(links[0]).toHaveAttribute("target", "_blank");
  expect(details.textContent).toContain("10.10.2026");
  expect(block.textContent).not.toContain("güven");
});

test("no news gives the no-news line with the window", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready([product({ news: [], news_days: 90 })]));
  panel();
  expect(await screen.findByText("Son 90 günde haber bulunamadı.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Öne çıkanlar" })).toBeInTheDocument();
  expect(screen.getByText("Kaynaklar (3)")).toBeInTheDocument();
});

test("only a low-confidence bullet shows the mark", async () => {
  const findings = [
    finding("Düşük bilgi.", [src(NUROL)], { confidence: "low" }),
    finding("Yüksek bilgi.", [src(NUROL)], { confidence: "high" }),
    finding("Orta bilgi.", [src(NUROL)], { confidence: "medium" }),
  ];
  vi.spyOn(api, "research").mockResolvedValue(ready([product({ news: [], findings })]));
  panel();
  const low = (await screen.findByText(/Düşük bilgi/)).closest("li") as HTMLElement;
  expect(low.textContent).toContain("güven düşük");
  expect(screen.getByText(/Yüksek bilgi/).closest("li")?.textContent).not.toContain("güven");
  expect(screen.getByText(/Orta bilgi/).closest("li")?.textContent).not.toContain("güven");
});

test("a product without highlights says so", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready([product({ news: [], findings: [] })]));
  panel();
  expect(await screen.findByText("Kaynaklı bulgu bulunamadı.")).toBeInTheDocument();
  expect(screen.queryByText(/^Kaynaklar/)).toBeNull();
});

test("hidden on a server without research", async () => {
  vi.spyOn(api, "research").mockResolvedValue({ state: "off", reason: "" });
  panel();
  await waitFor(() => expect(api.research).toHaveBeenCalled());
  expect(screen.queryByTestId("research-panel")).toBeNull();
});

test("off with a reason says so", async () => {
  vi.spyOn(api, "research").mockResolvedValue({ state: "off", reason: "no key in .env: EXA_API_KEY" });
  panel();
  expect(await screen.findByText("Web araştırması kapalı: no key in .env: EXA_API_KEY")).toBeInTheDocument();
});

test("the daily limit and other errors of a product", async () => {
  vi.spyOn(api, "research").mockResolvedValue(
    ready([
      product({ error: "daily limit", findings: [], news: [] }),
      product({ option_id: "fund:IST", label: "İSTANBUL PORTFÖY", error: "exa: credit", findings: [], news: [] }),
    ]),
  );
  panel();
  expect(await screen.findByText("Günlük araştırma limiti doldu.")).toBeInTheDocument();
  expect(screen.getByText("Araştırma yapılamadı: exa: credit")).toBeInTheDocument();
  expect(screen.queryByText("Son haberler")).toBeNull();
});

test("asks a question and shows the answer as numbered bullets with its own sources", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready());
  const ask = vi.spyOn(api, "askResearch").mockResolvedValue(answer("Nurol Portföy son haberler"));
  panel();
  const box = await screen.findByLabelText("Ürünler veya şirketler hakkında soru sorun");
  await userEvent.type(box, "Nurol Portföy son haberler");
  await userEvent.click(screen.getByRole("button", { name: "Sor" }));
  expect(ask).toHaveBeenCalledWith(sample("run_p01_ready").result.run_id, "Nurol Portföy son haberler", "TR");
  const block = await screen.findByTestId("research-answer");
  expect(within(block).getByText("Nurol Portföy son haberler")).toBeInTheDocument();
  expect(within(block).getByText(/Pay oranı %5,58'e çıktı\./).closest("li")?.textContent).toBe("Pay oranı %5,58'e çıktı. [1, 2]");
  expect(within(block).getByText("Kaynaklar (2)")).toBeInTheDocument();
  expect((block.querySelector("details") as HTMLDetailsElement).open).toBe(false);
  expect(box).toHaveValue("");
});

test("an answer with an error shows the error line", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready([product()], [{ ...answer("PPN nedir?"), findings: [], error: "exa: credit" }]));
  panel();
  expect(await screen.findByText("Araştırma yapılamadı: exa: credit")).toBeInTheDocument();
});

test("a refused question shows its reason", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready());
  vi.spyOn(api, "askResearch").mockRejectedValue(new ApiError(422, "Soru müşteri bilgisi içeriyor; yalnızca ürün veya şirket hakkında sorun."));
  panel();
  await userEvent.type(await screen.findByLabelText("Ürünler veya şirketler hakkında soru sorun"), "Müşterim için?");
  await userEvent.click(screen.getByRole("button", { name: "Sor" }));
  expect(await screen.findByText("Soru müşteri bilgisi içeriyor; yalnızca ürün veya şirket hakkında sorun.")).toBeInTheDocument();
});

test("earlier questions of the run come from the server", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready([product()], [answer("PPN nedir?")]));
  panel();
  expect(await screen.findByText("PPN nedir?")).toBeInTheDocument();
});

test("English labels", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready([product({ news: [] })]));
  panel("EN");
  expect(await screen.findByText("Web source, not verified")).toBeInTheDocument();
  expect(api.research).toHaveBeenCalledWith(sample("run_p01_ready").result.run_id, "EN");
  expect(screen.getByRole("heading", { name: "Latest news" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Highlights" })).toBeInTheDocument();
  expect(screen.getByText("Sources (3)")).toBeInTheDocument();
  expect(screen.getByText("No news in the last 90 days.")).toBeInTheDocument();
});

test("no research for a run that is not ready", () => {
  const research = vi.spyOn(api, "research");
  renderWith(<ResearchPanel view={sample("run_needs_input")} />);
  expect(research).not.toHaveBeenCalled();
  expect(screen.queryByTestId("research-panel")).toBeNull();
});
