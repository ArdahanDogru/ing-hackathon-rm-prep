import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import type { ProductResearch, QuestionAnswer, ResearchView } from "../api/types";
import { renderWith } from "../test/render";
import { sample } from "../test/samples";
import { ResearchPanel } from "./ResearchPanel";

const NUROL = "https://www.nurolportfoy.com.tr/fon/ppn";
const product = (over: Partial<ProductResearch> = {}): ProductResearch => ({
  option_id: "fund:PPN",
  label: "NUROL PORTFÖY PARA PİYASASI (TL) FONU",
  company: "Nurol Portföy Yönetimi A.Ş.",
  summary: "PPN bir para piyasası fonudur.",
  findings: [
    { text: "Fonun yönetim ücreti %0,7'dir.", topic: "urun", confidence: "high", sources: [{ url: NUROL, title: "PPN", published: "2026-10-12" }] },
    { text: "Şirket Nurol Yatırım Bankası iştirakidir.", topic: "sirket", confidence: "medium", sources: [{ url: "https://fonoloji.com/ppn", title: "PPN", published: "" }] },
  ],
  lang: "TR",
  provider: "exa",
  created_at: "2026-10-14T10:00:00+03:00",
  cost_usd: 0.012,
  checks: [],
  error: "",
  ...over,
});
const answer = (question: string): QuestionAnswer => ({
  question,
  summary: "Nurol Portföy OSTİM payını artırdı.",
  findings: [{ text: "Pay oranı %5,58'e çıktı.", topic: "soru", confidence: "high", sources: [{ url: NUROL, title: "Haber", published: "2026-10-08" }] }],
  lang: "TR",
  provider: "exa",
  created_at: "2026-10-14T10:05:00+03:00",
  cost_usd: 0.007,
  checks: [],
  error: "",
});
const ready = (products = [product()], questions: QuestionAnswer[] = []): ResearchView => ({ state: "ready", products, questions });
const panel = (lang: "TR" | "EN" = "TR") => renderWith(<ResearchPanel view={sample("run_p01_ready")} />, { lang });

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

test("shows a running line, then the findings with their sources and the label", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.spyOn(api, "research").mockResolvedValueOnce({ state: "running" }).mockResolvedValue(ready());
  panel();
  expect(await screen.findByTestId("research-running")).toBeInTheDocument();
  vi.advanceTimersByTime(3100);
  expect(await screen.findByText("Fonun yönetim ücreti %0,7'dir.")).toBeInTheDocument();
  expect(screen.getByText("Web kaynağı, doğrulanmamış")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "nurolportfoy.com.tr" })).toHaveAttribute("href", NUROL);
  expect(screen.getByText("Şirket: Nurol Portföy Yönetimi A.Ş.")).toBeInTheDocument();
  expect(screen.getByText("Şirket Nurol Yatırım Bankası iştirakidir.")).toBeInTheDocument();
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
    ready([product({ error: "daily limit", findings: [] }), product({ option_id: "fund:IST", label: "İSTANBUL PORTFÖY", error: "exa: credit", findings: [] })]),
  );
  panel();
  expect(await screen.findByText("Günlük araştırma limiti doldu.")).toBeInTheDocument();
  expect(screen.getByText("Araştırma yapılamadı: exa: credit")).toBeInTheDocument();
});

test("asks a question and shows the answer", async () => {
  vi.spyOn(api, "research").mockResolvedValue(ready());
  const ask = vi.spyOn(api, "askResearch").mockResolvedValue(answer("Nurol Portföy son haberler"));
  panel();
  const box = await screen.findByLabelText("Ürünler veya şirketler hakkında soru sorun");
  await userEvent.type(box, "Nurol Portföy son haberler");
  await userEvent.click(screen.getByRole("button", { name: "Sor" }));
  expect(ask).toHaveBeenCalledWith(sample("run_p01_ready").result.run_id, "Nurol Portföy son haberler", "TR");
  expect(await screen.findByText("Nurol Portföy OSTİM payını artırdı.")).toBeInTheDocument();
  expect(box).toHaveValue("");
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
  vi.spyOn(api, "research").mockResolvedValue(ready());
  panel("EN");
  expect(await screen.findByText("Web source, not verified")).toBeInTheDocument();
  expect(api.research).toHaveBeenCalledWith(sample("run_p01_ready").result.run_id, "EN");
});

test("no research for a run that is not ready", () => {
  const research = vi.spyOn(api, "research");
  renderWith(<ResearchPanel view={sample("run_needs_input")} />);
  expect(research).not.toHaveBeenCalled();
  expect(screen.queryByTestId("research-panel")).toBeNull();
});
