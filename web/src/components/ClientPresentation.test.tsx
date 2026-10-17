import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "../api/client";
import type { NarrativeView } from "../api/types";
import { renderWith } from "../test/render";
import { sample } from "../test/samples";
import { MeetingText } from "../screens/MeetingText";
import { fundRoles, parseAmount, parseFigure, restatesFacts, withoutName } from "./ClientPresentation";

const narrative = () => sample("narrative_p01_tr");

function show(n: NarrativeView = narrative(), lang: "TR" | "EN" = "TR") {
  vi.spyOn(api, "narrative").mockResolvedValue(n);
  renderWith(<MeetingText view={sample("run_p01_approved")} />, { lang });
}

beforeEach(() => {
  vi.spyOn(api, "glossary").mockResolvedValue(sample("glossary"));
});
afterEach(() => vi.restoreAllMocks());

test("one page: the client presentation with the RM's boxes; no tabs", async () => {
  show();
  expect(await screen.findByTestId("presentation")).toBeInTheDocument();
  expect(screen.getByTestId("pres-goal")).toHaveTextContent("Düzenli gelir ve sermayenin korunmasını önceliklendirmek");
  expect(screen.getAllByTestId("rm-note").length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: "RM hazırlık notu" })).toBeNull();
});

test("the figures and the chart come from the run, the TL amounts follow the example amount", async () => {
  show();
  const figures = await screen.findAllByTestId("pres-figure");
  expect(figures[0]).toHaveTextContent("+%7,4");
  expect(figures[0]).toHaveTextContent("mevduat ortalaması +%4,9");
  expect(figures[1]).toHaveTextContent("Aynı gün");
  expect(figures[2]).toHaveTextContent("1 / 7");
  expect(figures[2]).toHaveTextContent("sınırınız 2");
  const bars = screen.getAllByTestId("pres-bar");
  expect(bars).toHaveLength(4);
  expect(bars[0]).toHaveTextContent("Mevduat");
  expect(bars[0]).toHaveTextContent("+49.000 TL");
  expect(bars[1]).toHaveTextContent("+73.561 TL");
  const amount = screen.getByRole("textbox", { name: "Örnek tutar" });
  await userEvent.clear(amount);
  await userEvent.type(amount, "100000");
  expect(screen.getAllByTestId("pres-bar")[0]).toHaveTextContent("+4.900 TL");
});

test("each fund has its own role from the client's priorities and its narrator block", async () => {
  show();
  const funds = await screen.findAllByTestId("pres-fund");
  expect(funds.map((f) => within(f).getAllByText(/./)[0].textContent)).toEqual(["DÜZENLİ GELİR", "SINIRLI DALGALANMA", "LİKİDİTEYİ KORUMA"]);
  // the sentences without the fund's name in front: the card's title is the name
  const items = within(funds[0]).getAllByRole("listitem").map((x) => x.textContent!);
  // the sentence that only restates the labels (real, nominal, risk) is left out (W31)
  expect(items).toHaveLength(2);
  items.forEach((x) => expect(x).not.toMatch(/^Nurol/));
  expect(items[0]).toMatch(/^Düzenli gelir ihtiyacınız/);
  expect(items[1]).toMatch(/^Getirisi faiz değişimine bağlıdır/);
});

test("labels: real and nominal; risk, access and the timeline only when the funds differ", async () => {
  show();
  const funds = await screen.findAllByTestId("pres-fund");
  expect(funds[0]).toHaveTextContent("+%7,4 reel");
  expect(funds[0]).toHaveTextContent("+%47,6 nominal");
  // P01: all three are risk 1 and same-day
  funds.forEach((f) => {
    expect(f).not.toHaveTextContent("risk 1/7");
    expect(f).not.toHaveTextContent("Aynı gün");
  });
  expect(screen.queryAllByTestId("pres-access")).toHaveLength(0);
  expect(screen.queryByText("Paranıza ne zaman ulaşırsınız?")).toBeNull();
});

test("funds with different risk and access show the labels and the timeline", async () => {
  const v = sample("run_p01_approved");
  const ist = v.options["fund:IST"];
  v.options["fund:IST"] = { ...ist, risk: { ...ist.risk!, level: 2 }, access: { ...ist.access, days: 2, label: "2 gün" } };
  vi.spyOn(api, "narrative").mockResolvedValue(narrative());
  renderWith(<MeetingText view={v} />);
  const funds = await screen.findAllByTestId("pres-fund");
  expect(funds[1]).toHaveTextContent("risk 2/7");
  expect(funds[1]).toHaveTextContent("2 gün");
  expect(screen.getAllByTestId("pres-access")).toHaveLength(3);
});

test("restatesFacts: both the real and the nominal figure", () => {
  const o = sample("run_p01_approved").options["fund:PPN"];
  expect(restatesFacts("X: enflasyon sonrası reel getirisi %7,36, nominal getirisi %47,60, risk düzeyi 1/7.", o)).toBe(true);
  expect(restatesFacts("X shows a real 1-year return of 7.36%, a nominal return of 47.60%.", o)).toBe(true);
  expect(restatesFacts("X son bir yılda %7,36 reel getiri sundu.", o)).toBe(false);
  // the live narrator rounds to one decimal
  expect(restatesFacts("X için reel getiri %7,4, nominal getiri %47,6 ve risk değeri 1/7'dir.", o)).toBe(true);
  expect(restatesFacts("X için reel getiri %7,4 ve risk değeri 1/7'dir.", o)).toBe(false);
});

test("withoutName: the joins of TR and EN, and texts it leaves alone", () => {
  const o = sample("run_p01_approved").options["fund:IST"];
  const n = "İstanbul Portföy KV Borçlanma (TL)";
  expect(withoutName(`${n}: reel getirisi %7,06.`, o, "TR")).toBe("Reel getirisi %7,06.");
  expect(withoutName(`${n}, 1-3 yıllık ufkunuza uygun.`, o, "TR")).toBe("1-3 yıllık ufkunuza uygun.");
  expect(withoutName(`${n} de faiz değişimine bağlı.`, o, "TR")).toBe("Faiz değişimine bağlı.");
  expect(withoutName(`${n} için getirisi faize bağlıdır.`, o, "TR")).toBe("Getirisi faize bağlıdır.");
  expect(withoutName(`${n} also follows interest rates.`, o, "EN")).toBe("Also follows interest rates.");
  expect(withoutName("Getirisi faize bağlıdır.", o, "TR")).toBe("Getirisi faize bağlıdır.");
  expect(withoutName(n, o, "TR")).toBe(n);
});

test("the risk scale marks the funds' level and the client's limit", async () => {
  show();
  const scale = await screen.findByTestId("pres-risk");
  expect(within(scale).getByText("1")).toHaveAttribute("data-own", "true");
  expect(within(scale).getByText("2")).not.toHaveAttribute("data-own");
  expect(screen.getByText("Sınırınız: 2")).toBeInTheDocument();
});

test("the RM sees ✎, a comment per fund, the hint and the general note; the client view none of them", async () => {
  show();
  await screen.findByTestId("presentation");
  expect(screen.getAllByRole("button", { name: /düzenle$/i }).length).toBeGreaterThan(0);
  expect(screen.getAllByTestId("pres-comment")).toHaveLength(3);
  expect(screen.getByTestId("pres-hint")).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Notlarım" })).toHaveValue("Müşteri aylık nakit akışını sordu.");
  await userEvent.click(screen.getByRole("button", { name: "👁 Müşteri görünümü" }));
  expect(screen.queryAllByRole("button", { name: /düzenle$/i })).toHaveLength(0);
  expect(screen.queryAllByTestId("pres-comment")).toHaveLength(0);
  expect(screen.queryByRole("textbox", { name: "Notlarım" })).toBeNull();
});

test("a fund comment is saved as the RM's option note", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const notes = vi.spyOn(api, "notes").mockResolvedValue(sample("run_p01_approved"));
  show();
  await screen.findByTestId("presentation");
  await userEvent.type(screen.getAllByRole("textbox", { name: "Yorum · yalnızca siz görürsünüz" })[1], "Faiz sorusu gelebilir");
  await vi.advanceTimersByTimeAsync(1000);
  await waitFor(() => expect(notes).toHaveBeenCalled());
  expect(notes.mock.lastCall![2]).toEqual({ "fund:IST": "Faiz sorusu gelebilir" });
  vi.useRealTimers();
});

test("editing a block in the presentation uses the same block edit", async () => {
  const edit = vi.spyOn(api, "editBlock").mockResolvedValue(narrative());
  show();
  await screen.findByTestId("presentation");
  await userEvent.click(screen.getByRole("button", { name: "Söyleyebileceğiniz düzenle" }));
  const box = screen.getByRole("textbox", { name: /Söyleyebileceğiniz/ });
  await userEvent.clear(box);
  await userEvent.type(box, "Aylık gelirinizi birlikte planlayalım.");
  await userEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  expect(edit).toHaveBeenCalledWith(expect.any(String), "TR", "teklif_metni", "Aylık gelirinizi birlikte planlayalım.");
});

test("the risks block can be edited but not deleted; other blocks can be deleted", async () => {
  show();
  await screen.findByTestId("presentation");
  expect(screen.getByRole("button", { name: "Dikkat düzenle" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Dikkat: Sil" })).toBeNull();
  expect(screen.getByRole("button", { name: "Söyleyebileceğiniz: Sil" })).toBeInTheDocument();
});

test("a deleted block is a Geri al line for the RM and gone in the client view", async () => {
  show({ ...narrative(), rm_edits: { teklif_metni: "" } });
  expect(await screen.findByTestId("deleted-block")).toHaveAttribute("data-block", "teklif_metni");
  await userEvent.click(screen.getByRole("button", { name: "👁 Müşteri görünümü" }));
  expect(screen.queryByTestId("deleted-block")).toBeNull();
});

test("an open rule finding disables the print", async () => {
  const n = { ...narrative(), rm_edits: { ozet: "Garanti getiri." }, edit_checks: { ozet: ["phrase: 'garanti' kullanılmamalı"] } };
  show(n);
  expect(await screen.findByRole("button", { name: "⤓ Yazdır / PDF" })).toBeDisabled();
});

test("EN labels", async () => {
  show(sample("narrative_p01_en"), "EN");
  expect(await screen.findByRole("button", { name: "👁 Client view" })).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByText("What does your money earn today?")).toBeInTheDocument();
  expect(screen.getByText("Your limit: 2")).toBeInTheDocument();
});

test("helpers: figures, amounts and roles", () => {
  expect(parseFigure("+%4,9")).toBe(4.9);
  expect(parseFigure("−%1,2")).toBe(-1.2);
  expect(parseFigure("Aynı gün")).toBeNull();
  expect(parseAmount("1.000.000 TL")).toBe(1000000);
  expect(parseAmount("abc")).toBe(0);
  const v = sample("run_p01_approved");
  const funds = ["fund:PPN", "fund:IST"].map((id) => v.options[id]);
  expect(fundRoles(funds, { "fund:PPN": ["a", "b"], "fund:IST": ["a"] })).toEqual({ "fund:PPN": "a", "fund:IST": "a" });
  expect(fundRoles(funds, { "fund:PPN": ["a", "b"], "fund:IST": ["a", "b"] })).toEqual({ "fund:PPN": "a", "fund:IST": "b" });
  expect(fundRoles(funds, {})["fund:PPN"]).toBe(v.options["fund:PPN"].category_label);
});
