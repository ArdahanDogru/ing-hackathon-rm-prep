import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api, ApiError } from "../api/client";
import type { RunView } from "../api/types";
import { renderDashboard } from "../test/render";
import { sample, withHoldings } from "../test/samples";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

async function openAllocation() {
  await userEvent.click(screen.getByRole("button", { name: "Dağılım" }));
}

test("the switch has Dağılım; one row per class; the choice is remembered", async () => {
  const v = sample("run_p01_ready");
  const { unmount } = renderDashboard(v);
  await openAllocation();
  expect(screen.getAllByTestId("alloc-row")).toHaveLength(v.allocation.length);
  expect(localStorage.getItem("rmprep.view.oneriler")).toBe("allocation");
  unmount();
  renderDashboard(sample("run_p01_ready"));
  expect(screen.getAllByTestId("alloc-row")).toHaveLength(v.allocation.length);
});

test("without a current split (W13 view): label, band bar on 0-100 with the range; dengeli has no bar", async () => {
  const v = withoutHoldings(sample("run_p01_ready"));
  renderDashboard(v);
  await openAllocation();
  const rows = screen.getAllByTestId("alloc-row");
  v.allocation.forEach((a, i) => {
    expect(rows[i]).toHaveTextContent(a.label);
    const bar = within(rows[i]).queryByTestId("alloc-band");
    if (a.low === null || a.high === null) {
      expect(bar).toBeNull();
      expect(rows[i]).toHaveTextContent("hedef bant yok");
    } else {
      expect(bar!.style.left).toBe(`${a.low}%`);
      expect(bar!.style.width).toBe(`${a.high - a.low}%`);
      expect(rows[i]).toHaveTextContent(`%${a.low}–${a.high}`);
    }
  });
});

test("without a current split: an inferred band has an asterisk with the tooltip", async () => {
  const v = withoutHoldings(sample("run_p01_ready"));
  v.allocation[0] = { ...v.allocation[0], inferred: true, source: "çıkarım" };
  renderDashboard(v);
  await openAllocation();
  const mark = within(screen.getAllByTestId("alloc-row")[0]).getByText("*");
  expect(mark).toHaveAttribute("title", "Kaynak yok: Muhafazakâr–Dengeli arası çıkarım");
  expect(within(screen.getAllByTestId("alloc-row")[1]).queryByText("*")).toBeNull();
});

test("the best option: short name, real 1-year return, SPK risk; a click opens the fund card", async () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  await openAllocation();
  const i = v.allocation.findIndex((a) => a.option_id && !a.note);
  const o = v.options[v.allocation[i].option_id!];
  const row = screen.getAllByTestId("alloc-row")[i];
  const pick = within(row).getByRole("button", { name: new RegExp(o.short_label.replace(/[()]/g, "\\$&")) });
  expect(row).toHaveTextContent(`risk ${o.risk!.level}/7`);
  await userEvent.click(pick);
  expect(screen.getByRole("dialog")).toHaveTextContent(o.label.replace(/\s+/g, " "));
});

test("note texts: a class without an option, and a negative real return next to its option", async () => {
  const v = sample("run_p01_ready");
  renderDashboard(v);
  await openAllocation();
  const rows = screen.getAllByTestId("alloc-row");
  v.allocation.forEach((a, i) => {
    if (a.note_text) expect(rows[i]).toHaveTextContent(a.note_text);
    if (!a.option_id) expect(within(rows[i]).queryByRole("button")).toBeNull();
  });
  expect(v.allocation.some((a) => a.note === "ceiling" && !a.option_id)).toBe(true);
  expect(v.allocation.some((a) => a.note === "negative_real" && a.option_id)).toBe(true);
});

/** The sample as an API before W18 sent it: no current split. */
function withoutHoldings(view: RunView): RunView {
  const allocation = view.allocation.map((a) => {
    const row: Record<string, unknown> = { ...a };
    for (const k of ["current", "current_low", "current_high", "current_source", "current_ref", "gap", "active"]) {
      delete row[k];
    }
    return row as unknown as RunView["allocation"][number];
  });
  const out: RunView = { ...view, allocation };
  delete out.holdings;
  return out;
}

test("the holding hints above the rows and the footer with the source", async () => {
  const v = withoutHoldings(sample("run_p01_ready"));
  renderDashboard(v);
  await openAllocation();
  const view = screen.getByTestId("allocation");
  v.allocation_notes.forEach((n) => expect(within(view).getByTestId("alloc-notes")).toHaveTextContent(n));
  expect(within(view).getByTestId("alloc-footer")).toHaveTextContent(
    `Gösterge model dağılım (stratejik), tutar değildir. Kaynak: ${v.allocation[0].source}`,
  );
  // without the current split (an API before W18): no marker, badge, gap or buttons
  expect(within(view).queryAllByTestId("alloc-current")).toHaveLength(0);
  expect(within(view).queryAllByTestId("alloc-badge")).toHaveLength(0);
  expect(within(view).queryAllByTestId("alloc-gap")).toHaveLength(0);
  expect(within(view).queryByRole("button", { name: "Düzenle" })).toBeNull();
});

test("no allocation: no Dağılım button, a remembered choice falls back to the cards", () => {
  localStorage.setItem("rmprep.view.oneriler", "allocation");
  const v = sample("run_p01_ready");
  renderDashboard({ ...v, allocation: [], allocation_notes: [] });
  expect(screen.queryByRole("button", { name: "Dağılım" })).toBeNull();
  expect(screen.getAllByTestId("option-card").length).toBeGreaterThan(0);
});

test("EN labels", async () => {
  renderDashboard(withoutHoldings(sample("run_p01_ready")), () => {}, "EN");
  await userEvent.click(screen.getByRole("button", { name: "Allocation" }));
  expect(screen.getByTestId("alloc-footer")).toHaveTextContent("Indicative model allocation");
});

// --- W18: current and target split ----------------------------------------------------------

const BANNER = "Portföy dağılımı bilinmiyor; aşağıdaki değerler tahmini senaryodur ve sıralamayı etkilemez.";
const POINTS = { nakit_benzeri: 39, borclanma: 10, hisse: 10, altin_doviz: 30, dengeli: 11 };

async function showCard(v: RunView, onView: (v: RunView) => void = () => {}) {
  renderDashboard(v, onView);
  await openAllocation();
  return screen.getAllByTestId("alloc-row");
}

test("the card title and the estimate banner", async () => {
  await showCard(withHoldings(sample("run_p01_ready"), "estimate"));
  expect(screen.getByTestId("allocation")).toHaveTextContent("Mevcut ve hedef dağılım");
  expect(screen.getByTestId("alloc-banner")).toHaveTextContent(BANNER);
});

test("no banner for the RM's split", async () => {
  await showCard(withHoldings(sample("run_p01_ready"), "rm"));
  expect(screen.queryByTestId("alloc-banner")).toBeNull();
});

test("each row: the band, the current marker with its range, the badge and the gap", async () => {
  const v = withHoldings(sample("run_p01_ready"), "estimate");
  const rows = await showCard(v);
  v.allocation.forEach((a, i) => {
    const marker = within(rows[i]).getByTestId("alloc-current");
    expect(marker.style.left).toBe(`${a.current}%`);
    const range = within(rows[i]).getByTestId("alloc-current-range");
    expect(range.style.left).toBe(`${a.current_low}%`);
    expect(range.style.width).toBe(`${a.current_high! - a.current_low!}%`);
    expect(rows[i]).toHaveTextContent(`%${a.current} (${a.current_low}–${a.current_high})`);
    expect(within(rows[i]).getByTestId("alloc-badge")).toHaveTextContent("tahmini senaryo");
  });
  const gap = (cls: string) => within(rows[v.allocation.findIndex((a) => a.asset_class === cls)]).queryByTestId("alloc-gap");
  expect(gap("nakit_benzeri")).toHaveTextContent("−19 puan"); // 39 over the band 10–20
  expect(gap("borclanma")).toHaveTextContent("+50 puan"); // 10 under the band 60–70
  expect(gap("hisse")).toHaveTextContent("bandın içinde");
  expect(gap("dengeli")).toBeNull(); // no band, no gap
});

test("an RM value has no range text", async () => {
  const rows = await showCard(withHoldings(sample("run_p01_ready"), "rm"));
  expect(rows[0]).toHaveTextContent("%50");
  expect(rows[0]).not.toHaveTextContent("(50–50)");
});

test("badges: persona metni, RM, RM onaylı; the source in the tooltip", async () => {
  const { unmount } = renderDashboard(withHoldings(sample("run_p01_ready"), "persona_text"));
  await openAllocation();
  const badges = screen.getAllByTestId("alloc-badge");
  expect(badges[0]).toHaveTextContent("persona metni");
  expect(badges[1]).toHaveTextContent("tahmini senaryo");
  expect(badges[1].getAttribute("title")).toContain("TCMB Finansal İstikrar Raporu 2026-I");
  expect(badges[1].getAttribute("title")).toContain("31.03.2026");
  unmount();
  for (const [status, text] of [
    ["rm", "RM"],
    ["rm_confirmed", "RM onaylı"],
  ] as const) {
    const { unmount: u } = renderDashboard(withHoldings(sample("run_p01_ready"), status));
    expect(screen.getAllByTestId("alloc-badge")[0]).toHaveTextContent(new RegExp(`^${text}$`));
    u();
  }
});

test("Tahmini onayla sends the current points as rm_confirmed and shows the new run", async () => {
  const v = withHoldings(sample("run_p01_ready"), "estimate");
  const next = withHoldings(sample("run_p01_ready"), "rm_confirmed");
  const set = vi.spyOn(api, "setHoldings").mockResolvedValue(next);
  const onView = vi.fn();
  await showCard(v, onView);
  await userEvent.click(screen.getByRole("button", { name: "Tahmini onayla" }));
  expect(set).toHaveBeenCalledWith(v.result.run_id, POINTS, "rm_confirmed");
  expect(onView).toHaveBeenCalledWith(next);
});

test("Düzenle: five number inputs, the running total, Kaydet only at 100 ± 0,5", async () => {
  const v = withHoldings(sample("run_p01_ready"), "estimate");
  const set = vi.spyOn(api, "setHoldings").mockResolvedValue(withHoldings(sample("run_p01_ready"), "rm"));
  await showCard(v);
  await userEvent.click(screen.getByRole("button", { name: "Düzenle" }));
  const inputs = screen.getAllByRole("spinbutton");
  expect(inputs).toHaveLength(5);
  expect(screen.getByTestId("alloc-total")).toHaveTextContent("Toplam %100");
  const save = screen.getByRole("button", { name: "Kaydet" });
  expect(save).toBeEnabled();
  await userEvent.clear(inputs[0]);
  await userEvent.type(inputs[0], "38");
  expect(screen.getByTestId("alloc-total")).toHaveTextContent("Toplam %99");
  expect(save).toBeDisabled();
  await userEvent.clear(inputs[0]);
  await userEvent.type(inputs[0], "38.5");
  expect(save).toBeEnabled(); // 99,5 is inside 100 ± 0,5
  await userEvent.clear(inputs[0]);
  await userEvent.type(inputs[0], "39");
  await userEvent.click(save);
  expect(set).toHaveBeenCalledWith(v.result.run_id, POINTS, "rm");
});

test("a 422 shows the server detail under the inputs", async () => {
  vi.spyOn(api, "setHoldings").mockRejectedValue(new ApiError(422, "shares must add up to 100 ± 0.5, got 100.6"));
  await showCard(withHoldings(sample("run_p01_ready"), "estimate"));
  await userEvent.click(screen.getByRole("button", { name: "Düzenle" }));
  await userEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("shares must add up to 100 ± 0.5, got 100.6");
  expect(screen.getAllByRole("spinbutton")).toHaveLength(5); // the inputs stay open
});

test("Sıfırla removes the RM's split", async () => {
  const v = withHoldings(sample("run_p01_ready"), "rm");
  const set = vi.spyOn(api, "setHoldings").mockResolvedValue(withHoldings(sample("run_p01_ready"), "estimate"));
  await showCard(v);
  expect(screen.queryByRole("button", { name: "Tahmini onayla" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Sıfırla" }));
  expect(set).toHaveBeenCalledWith(v.result.run_id, null);
});

test("an estimate has no Sıfırla", async () => {
  await showCard(withHoldings(sample("run_p01_ready"), "estimate"));
  expect(screen.queryByRole("button", { name: "Sıfırla" })).toBeNull();
});

test("W18 EN labels", async () => {
  renderDashboard(withHoldings(sample("run_p01_ready"), "estimate"), () => {}, "EN");
  await userEvent.click(screen.getByRole("button", { name: "Allocation" }));
  expect(screen.getByTestId("allocation")).toHaveTextContent("Current and target split");
  expect(screen.getAllByTestId("alloc-badge")[0]).toHaveTextContent("estimate scenario");
  expect(screen.getByRole("button", { name: "Confirm the estimate" })).toBeInTheDocument();
});

// --- W18b: a split partly from the client file --------------------------------------------

const PARTLY = "Nakit benzeri payı müşteri dosyasından; diğer sınıflar tahmini senaryodur ve sıralamayı etkilemez.";

test("persona_text with estimated rows (the API sample of P01): the partial banner", async () => {
  const v = sample("run_p01_ready");
  expect(v.holdings?.status).toBe("persona_text");
  await showCard(v);
  expect(screen.getByTestId("alloc-banner")).toHaveTextContent(PARTLY);
  expect(screen.queryByText(BANNER)).toBeNull();
});

test("several active classes: their labels joined with a comma", async () => {
  const v = sample("run_p01_ready");
  const i = v.allocation.findIndex((a) => a.asset_class === "altin_doviz");
  v.allocation[i] = { ...v.allocation[i], current_source: "persona_text", active: true };
  await showCard(v);
  const labels = v.allocation.filter((a) => a.active).map((a) => a.label);
  expect(labels).toHaveLength(2);
  expect(screen.getByTestId("alloc-banner")).toHaveTextContent(
    `${labels.join(", ")} payları müşteri dosyasından; diğer sınıflar tahmini senaryodur ve sıralamayı etkilemez.`,
  );
});

test("persona_text with every row active: no banner", async () => {
  const v = sample("run_p01_ready");
  v.allocation = v.allocation.map((a) => ({ ...a, current_source: "persona_text", active: true }));
  await showCard(v);
  expect(screen.queryByTestId("alloc-banner")).toBeNull();
});

test("the estimate sample of P02 keeps the estimate banner", async () => {
  const v = sample("run_p02_ready");
  expect(v.holdings?.status).toBe("estimate");
  await showCard(v);
  expect(screen.getByTestId("alloc-banner")).toHaveTextContent(BANNER);
});

test("W18b EN partial banner", async () => {
  renderDashboard(sample("run_p01_ready"), () => {}, "EN");
  await userEvent.click(screen.getByRole("button", { name: "Allocation" }));
  expect(screen.getByTestId("alloc-banner")).toHaveTextContent(
    "Nakit benzeri share is from the client file; the other classes are an estimate and do not change the ranking.",
  );
});
