// W42: bigger codes, readable units, conflicting client information.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "../api/client";
import type { ProfileCheck, RunView } from "../api/types";
import { fmtUnit } from "../format";
import { CodeBadge } from "../product";
import { renderDashboard } from "../test/render";
import { sample } from "../test/samples";
import { EvidencePopup } from "./EvidencePopup";
import { PersonaPanel } from "./PersonaPanel";

afterEach(() => vi.restoreAllMocks());

// --- 1. the code badge ---------------------------------------------------------------

test("the code badge takes about 0.85 em of its text, at least 11 px, monospace with a border", () => {
  render(<CodeBadge optionId="fund:PPN" />);
  const b = screen.getByTestId("code-badge");
  expect(b).toHaveClass("text-[max(11px,0.85em)]", "font-mono", "border");
  expect(b.className).not.toMatch(/text-\[11px\]/);
});

// --- 2. one unit formatter ---------------------------------------------------------------

test("fmtUnit: every unit in TR", () => {
  expect(fmtUnit(34.5, "pct", "TR")).toBe("%34,5");
  expect(fmtUnit(47.6037, "pct", "TR")).toBe("%47,6");
  expect(fmtUnit(-8.25, "pct", "TR")).toBe("−%8,25");
  expect(fmtUnit(49.1267, "TRY", "TR")).toBe("49,13 TL");
  expect(fmtUnit(4123.5, "TRY/kg", "TR")).toBe("4.123,5 TL/kg");
  expect(fmtUnit(3, "days", "TR")).toBe("3 gün");
  expect(fmtUnit(1250, "count", "TR")).toBe("1.250");
  expect(fmtUnit(1, "flag", "TR")).toBe("evet");
  expect(fmtUnit(0, "flag", "TR")).toBe("hayır");
  expect(fmtUnit(102.4, "index", "TR")).toBe("102,4");
  expect(fmtUnit(3, "level", "TR")).toBe("3 / 7");
  expect(fmtUnit(2, "parsec", "TR")).toBe("2 parsec");
});

test("fmtUnit: every unit in EN", () => {
  expect(fmtUnit(34.5, "pct", "EN")).toBe("34.5 %");
  expect(fmtUnit(49.1267, "TRY", "EN")).toBe("49.13 TL");
  expect(fmtUnit(4123.5, "TRY/kg", "EN")).toBe("4,123.5 TL/kg");
  expect(fmtUnit(1, "days", "EN")).toBe("1 day");
  expect(fmtUnit(3, "days", "EN")).toBe("3 days");
  expect(fmtUnit(1, "flag", "EN")).toBe("yes");
  expect(fmtUnit(0, "flag", "EN")).toBe("no");
  expect(fmtUnit(3, "level", "EN")).toBe("3 / 7");
});

test("the evidence pop-up shows %47,6, never pct", async () => {
  vi.spyOn(api, "evidence").mockResolvedValue(sample("evidence_item"));
  render(<EvidencePopup snapshotId="S" evidenceId="E1" open onClose={vi.fn()} />);
  const dialog = await screen.findByRole("dialog");
  await within(dialog).findByText("%47,6");
  expect(dialog).not.toHaveTextContent(/pct/);
});

test("the market note uses the same formatter (EN '37 %')", () => {
  renderDashboard(sample("run_p01_ready"), () => {}, "EN");
  const items = screen.getAllByTestId("market-item");
  expect(items[0]).toHaveTextContent("37 %");
  expect(screen.getByTestId("market-note")).not.toHaveTextContent(/pct/);
});

// --- 3. conflicting client information --------------------------------------------------

const testRun = (): RunView => sample("run_test");

test("the client card: an amber block 'Profilde çelişki (1)' with the finding's text", () => {
  const v = testRun();
  expect(v.profile_checks).toHaveLength(1);
  renderDashboard(v);
  const block = within(screen.getByTestId("brief-card")).getByTestId("profile-checks");
  expect(block).toHaveTextContent("Profilde çelişki (1)");
  expect(block).toHaveTextContent(v.profile_checks![0].text);
  expect(within(block).getAllByTestId("profile-check")[0]).toHaveAttribute("data-kind", "conflict");
});

test("a confirm finding: a softer item with the title Sorulacak; only confirms: the block is 'Sorulacak (n)'", () => {
  const confirm: ProfileCheck = { id: "long_but_liquid", kind: "confirm", fields: ["yatirim_ufku", "likidite_ihtiyaci"], text: "Uzun vade ama yüksek likidite: sorun." };
  const v = { ...testRun(), profile_checks: [...testRun().profile_checks!, confirm] };
  const { unmount } = renderDashboard(v);
  const items = screen.getAllByTestId("profile-check");
  expect(items[1]).toHaveAttribute("data-kind", "confirm");
  expect(items[1]).toHaveTextContent("Sorulacak");
  expect(items[1].className).not.toEqual(items[0].className);
  expect(screen.getByTestId("profile-checks")).toHaveTextContent("Profilde çelişki (2)");
  unmount();
  renderDashboard({ ...testRun(), profile_checks: [confirm] });
  expect(screen.getByTestId("profile-checks")).toHaveTextContent("Sorulacak (1)");
});

test("nothing for an empty list", () => {
  renderDashboard(sample("run_p01_ready"));
  expect(screen.queryByTestId("profile-checks")).toBeNull();
});

test("the profile panel: the fields of a finding get an amber mark and its text", () => {
  const v = testRun();
  render(<PersonaPanel persona={v.result.persona} checks={v.profile_checks} onApply={vi.fn()} onClose={vi.fn()} />);
  for (const f of v.profile_checks![0].fields) {
    const mark = screen.getByTestId(`field-check-${f}`);
    expect(mark).toHaveTextContent(v.profile_checks![0].text);
  }
  expect(screen.queryByTestId("field-check-yas")).toBeNull();
  expect(screen.getByLabelText("risk profili")).toHaveClass("border-[#F79009]");
});

test("the dashboard passes the findings to the panel", async () => {
  const v = testRun();
  // renderDashboard has no onPersona: render the Dashboard with onPersona, so "Profili düzenle" shows
  const { Dashboard } = await import("../screens/Dashboard");
  const { renderWith } = await import("../test/render");
  renderWith(<Dashboard view={v} onView={() => {}} onPersona={() => {}} />);
  await userEvent.click(screen.getAllByRole("button", { name: "Profili düzenle" })[0]);
  expect(screen.getByTestId("field-check-risk_profili")).toBeInTheDocument();
});

test("W42 EN block", () => {
  renderDashboard(testRun(), () => {}, "EN");
  expect(screen.getByTestId("profile-checks")).toHaveTextContent("Conflicting profile information (1)");
});
