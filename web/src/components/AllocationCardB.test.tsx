// W18c: "Mevcut ve hedef dağılım" in variant B (mockup docs/web-ui/mockups/allocation-v2-B.html).
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Lang, RunView } from "../api/types";
import { renderDashboard } from "../test/render";
import { sample, withHoldings } from "../test/samples";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

async function showCard(v: RunView, lang: Lang = "TR") {
  renderDashboard(v, () => {}, lang);
  await userEvent.click(screen.getByRole("button", { name: lang === "TR" ? "Dağılım" : "Allocation" }));
  return screen.getByTestId("allocation");
}
const row = (v: RunView, cls: string) => screen.getAllByTestId("alloc-row")[v.allocation.findIndex((a) => a.asset_class === cls)];

// --- (1) the "Hedef dağılım" note -----------------------------------------------------------

test("the note opens from the header pill and closes with ✕, Esc and an outside click", async () => {
  await showCard(sample("run_p01_ready"));
  const pill = screen.getByRole("button", { name: "ⓘ Hedef dağılım (Muhafazakâr)" });
  expect(pill).toHaveAttribute("aria-expanded", "false");
  await userEvent.click(pill);
  expect(pill).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("dialog", { name: /Hedef dağılım/ })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Kapat" }));
  expect(screen.queryByRole("dialog", { name: /Hedef dağılım/ })).toBeNull();
  expect(pill).toHaveAttribute("aria-expanded", "false");

  await userEvent.click(pill);
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: /Hedef dağılım/ })).toBeNull();
  expect(pill).toHaveFocus();

  await userEvent.click(pill);
  await userEvent.click(screen.getByTestId("alloc-stack"));
  expect(screen.queryByRole("dialog", { name: /Hedef dağılım/ })).toBeNull();
});

test("the note table: target, current (tahmin for an estimate row), mini bar, gap; the band source", async () => {
  const v = sample("run_p01_ready");
  await showCard(v);
  await userEvent.click(screen.getByRole("button", { name: /Hedef dağılım/ }));
  const note = screen.getByRole("dialog", { name: /Hedef dağılım/ });
  const rows = within(note).getAllByTestId("note-row");
  expect(rows).toHaveLength(v.allocation.length);
  const cells = (i: number) => within(rows[i]).getAllByRole("cell").map((c) => c.textContent);
  expect(cells(0)).toEqual(["Nakit benzeri", "%10–20", "%75", "", "−55 puan"]);
  expect(cells(1)).toEqual(["Borçlanma", "%60–70", "%8,1 (tahmin)", "", "+51,9 puan"]);
  expect(cells(3)[4]).toBe("bandın içinde");
  expect(cells(4)).toEqual(["Dengeli (çoklu varlık)", "—", "%3,7 (tahmin)", "", "hedef bant yok"]);
  // the mini bar: the band as a light area, the current as a marker (dark when active); none without a band
  const mini = within(rows[0]).getByTestId("note-mini");
  expect(within(mini).getByTestId("note-band").style.left).toBe("10%");
  expect(within(mini).getByTestId("note-band").style.width).toBe("10%");
  expect(within(mini).getByTestId("note-marker").style.left).toBe("75%");
  expect(within(mini).getByTestId("note-marker")).toHaveAttribute("data-tone", "active");
  expect(within(rows[1]).getByTestId("note-marker")).toHaveAttribute("data-tone", "estimate");
  expect(within(rows[4]).queryByTestId("note-mini")).toBeNull();
  expect(within(note).getByTestId("note-source")).toHaveTextContent(
    "Kaynak: Ata Yatırım, 28.04.2026. Gösterge niteliğinde stratejik bant; ING'nin model portföyü değildir.",
  );
});

test("an inferred band says (çıkarım) in the note source", async () => {
  const v = sample("run_p01_ready");
  v.allocation[0] = { ...v.allocation[0], inferred: true, source: "Muhafazakâr–Dengeli arası" };
  await showCard(v);
  await userEvent.click(screen.getByRole("button", { name: /Hedef dağılım/ }));
  expect(screen.getByTestId("note-source")).toHaveTextContent("Kaynak: Muhafazakâr–Dengeli arası (çıkarım).");
});

// --- (2) the summary ---------------------------------------------------------------------

test("summary for persona_text (P01): the largest class, its target; no ranking sentence without the weight", async () => {
  const card = await showCard(sample("run_p01_ready"));
  const s = within(card).getByTestId("alloc-summary");
  expect(s).toHaveTextContent(
    "Tahmine göre müşterinin parası çoğunlukla nakit benzeri (%75; müşteri dosyasından). Muhafazakâr hedefte bu oran %10–20.",
  );
  expect(s).not.toHaveTextContent("Bu yüzden");
  expect(s).not.toHaveTextContent("sıralamayı etkilemez");
  // the D20 holding hints give way to the summary
  expect(within(card).queryByTestId("alloc-notes")).toBeNull();
});

test("summary: with the allocation_gap weight, an active class over its band lowers its scores", async () => {
  const card = await showCard({ ...sample("run_p01_ready"), effective_weights: { return: 0.5, allocation_gap: 0.1 } });
  expect(within(card).getByTestId("alloc-summary")).toHaveTextContent("Bu yüzden nakit benzeri seçeneklerinin puanı düşüyor.");
});

test("summary for the RM's split: under the band raises the scores of the class with the largest gap", async () => {
  const v = withHoldings(sample("run_p01_ready"), "rm"); // nakit 50 (band 10–20: −30), borçlanma 20 (60–70: +40)
  const card = await showCard(v);
  const s = within(card).getByTestId("alloc-summary");
  expect(s).toHaveTextContent("Tahmine göre müşterinin parası çoğunlukla nakit benzeri (%50; RM'e göre).");
  expect(s).toHaveTextContent("Bu yüzden borçlanma seçeneklerinin puanı artıyor.");
});

test("summary for an estimate (P02): estimate scenario and the advice to ask the client", async () => {
  const v = sample("run_p02_ready");
  const top = [...v.allocation].sort((a, b) => b.current! - a.current!)[0];
  const card = await showCard(v);
  const s = within(card).getByTestId("alloc-summary");
  expect(s).toHaveTextContent(
    `Tahmine göre müşterinin parası çoğunlukla ${top.label.toLocaleLowerCase("tr")} (%${top.current}; tahmini senaryo).`,
  );
  expect(s).toHaveTextContent(`${v.result.persona.risk_profili} hedefte bu oran %${top.low}–${top.high}.`);
  expect(s).toHaveTextContent("Bu tahmin sıralamayı etkilemez; müşteriden gerçek dağılımı alın.");
});

test("the W18 banners stay", async () => {
  const card = await showCard(sample("run_p01_ready"));
  expect(within(card).getByTestId("alloc-banner")).toHaveTextContent("Nakit benzeri payı müşteri dosyasından;");
});

// --- (3) the stacked bar ------------------------------------------------------------------

test("stacked bar: one segment per class with a share, its width, fixed colour, a label from 10 %", async () => {
  const v = sample("run_p01_ready");
  v.allocation = v.allocation.map((a) => (a.asset_class === "hisse" ? { ...a, current: 0, current_low: 0, current_high: 5 } : a));
  const card = await showCard(v);
  const stack = within(card).getByTestId("alloc-stack");
  expect(stack).toHaveTextContent("Tahmini mevcut portföy");
  const segs = within(stack).getAllByTestId("stack-seg");
  expect(segs.map((s) => s.dataset.class)).toEqual(["nakit_benzeri", "borclanma", "altin_doviz", "dengeli"]);
  expect(segs[0].style.width).toBe("75%");
  expect(segs[1].style.width).toBe("8.1%");
  expect(segs[0].style.backgroundColor).toBe("rgb(31, 58, 104)");
  expect(segs[2].style.backgroundColor).toBe("rgb(247, 144, 9)");
  expect(segs[0]).toHaveTextContent("Nakit benzeri %75");
  expect(segs[1]).toHaveTextContent(""); // 8,1 % < 10 %: no label inside
  expect(segs[1]).toHaveAttribute("title", "Borçlanma %8,1");
  const legend = within(stack).getAllByTestId("stack-legend").map((x) => x.textContent);
  expect(legend[0]).toBe("Nakit benzeri %75 · müşteri dosyası");
  expect(legend[1]).toBe("Borçlanma %8,1 · tahmin");
});

test("stacked bar legend: RM and RM onaylı", async () => {
  const { unmount } = renderDashboard(withHoldings(sample("run_p01_ready"), "rm"));
  await userEvent.click(screen.getByRole("button", { name: "Dağılım" }));
  expect(screen.getAllByTestId("stack-legend")[0]).toHaveTextContent("Nakit benzeri %50 · RM");
  unmount();
  await showCard(withHoldings(sample("run_p01_ready"), "rm_confirmed"));
  expect(screen.getAllByTestId("stack-legend")[0]).toHaveTextContent("Nakit benzeri %39 · RM onaylı");
});

// --- (4) the rows -------------------------------------------------------------------------

test("rows: no band area in the track, a dark marker for an active row and a grey one for an estimate", async () => {
  const v = sample("run_p01_ready");
  await showCard(v);
  expect(within(screen.getByTestId("allocation")).queryAllByTestId("alloc-band")).toHaveLength(0);
  expect(within(row(v, "nakit_benzeri")).getByTestId("alloc-current")).toHaveAttribute("data-tone", "active");
  expect(within(row(v, "borclanma")).getByTestId("alloc-current")).toHaveAttribute("data-tone", "estimate");
  expect(row(v, "borclanma")).toHaveTextContent("Mevcut %8,1 (3,1–13,1)");
  expect(row(v, "borclanma")).toHaveTextContent("Bu sınıfta en iyi seçenek");
});

test("source lines: client file with the rule range, a profile assumption, the national source, the RM", async () => {
  const v = sample("run_p01_ready");
  await showCard(v);
  expect(within(row(v, "nakit_benzeri")).getByTestId("alloc-source")).toHaveTextContent(
    'Kaynak: müşteri dosyası, "mevduat ağırlıklı" → %60–90',
  );
  // the API label says "(varsayım)" already: not twice
  const profile = v.holdings!.sources.find((s) => s.id === "profile")!.label;
  expect(within(row(v, "borclanma")).getByTestId("alloc-source").textContent).toBe(`Kaynak: ${profile}`);
});

test("source line of a profile label without (varsayım) adds it; national gives the label and the date", async () => {
  const v = sample("run_p01_ready");
  v.holdings = { ...v.holdings!, sources: v.holdings!.sources.map((s) => (s.id === "profile" ? { ...s, label: "Emekli profili" } : s)) };
  const { unmount } = renderDashboard(v);
  await userEvent.click(screen.getByRole("button", { name: "Dağılım" }));
  expect(within(row(v, "borclanma")).getByTestId("alloc-source")).toHaveTextContent("Kaynak: Emekli profili (varsayım)");
  unmount();
  const n = withHoldings(sample("run_p01_ready"), "estimate");
  await showCard(n);
  expect(within(row(n, "hisse")).getByTestId("alloc-source")).toHaveTextContent(
    "Kaynak: TCMB Finansal İstikrar Raporu 2026-I, Tablo III.1.2, 31.03.2026",
  );
});

test("source lines of the RM's split", async () => {
  const { unmount } = renderDashboard(withHoldings(sample("run_p01_ready"), "rm"));
  await userEvent.click(screen.getByRole("button", { name: "Dağılım" }));
  expect(screen.getAllByTestId("alloc-source")[0]).toHaveTextContent("Kaynak: RM girdisi");
  unmount();
  await showCard(withHoldings(sample("run_p01_ready"), "rm_confirmed"));
  expect(screen.getAllByTestId("alloc-source")[0]).toHaveTextContent("Kaynak: RM onaylı tahmin");
});

// --- (5) the legend -----------------------------------------------------------------------

test("the legend under the rows replaces the old footer; the buttons stay", async () => {
  const card = await showCard(sample("run_p01_ready"));
  const legend = within(card).getByTestId("alloc-legend");
  expect(legend).toHaveTextContent("mevcut pay (RM veya müşteri dosyası)");
  expect(legend).toHaveTextContent("mevcut pay (tahmin)");
  expect(legend).toHaveTextContent("tahminin aralığı");
  expect(legend).toHaveTextContent("ⓘ Hedef dağılım: tüm sınıfların hedef bandı");
  expect(within(card).queryByTestId("alloc-footer")).toBeNull();
  expect(within(card).getByRole("button", { name: "Tahmini onayla" })).toBeInTheDocument();
  expect(within(card).getByRole("button", { name: "Düzenle" })).toBeInTheDocument();
});

// --- EN -----------------------------------------------------------------------------------

test("W18c EN", async () => {
  const v = sample("run_p01_ready");
  const card = await showCard(v, "EN");
  expect(within(card).getByTestId("alloc-summary")).toHaveTextContent(
    "By the estimate, most of the client's money is in nakit benzeri (%75; from the client file). In the Muhafazakâr target this share is %10–20.",
  );
  expect(within(card).getByTestId("alloc-stack")).toHaveTextContent("Estimated current portfolio");
  expect(screen.getAllByTestId("stack-legend")[1]).toHaveTextContent("Borçlanma %8,1 · estimate");
  expect(row(v, "borclanma")).toHaveTextContent("Best option in this class");
  expect(within(row(v, "nakit_benzeri")).getByTestId("alloc-source")).toHaveTextContent('Source: client file, "mevduat ağırlıklı" → %60–90');
  expect(within(card).getByTestId("alloc-legend")).toHaveTextContent("ⓘ Target allocation: the target band of every class");
  await userEvent.click(screen.getByRole("button", { name: "ⓘ Target allocation (Muhafazakâr)" }));
  const note = screen.getByRole("dialog", { name: /Target allocation/ });
  expect(note).toHaveTextContent("Indicative strategic band; not an ING model portfolio.");
  expect(within(note).getAllByTestId("note-row")[1]).toHaveTextContent("%8,1 (estimate)");
  expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
});

test("W18c EN summary sentences for the ranking", async () => {
  const card = await showCard(sample("run_p02_ready"), "EN");
  expect(within(card).getByTestId("alloc-summary")).toHaveTextContent(
    "This estimate does not change the ranking; ask the client for the real split.",
  );
});
