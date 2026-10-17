// W30: an edited profile (a test run) can be approved; screen 2 and the print card say so.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "../api/client";
import type { Lang, RunView } from "../api/types";
import { LangContext } from "../i18n";
import { profileChanges } from "../profileChanges";
import { MeetingText } from "../screens/MeetingText";
import { PrintCard } from "../screens/PrintCard";
import { renderDashboard, renderWith } from "../test/render";
import { sample } from "../test/samples";

afterEach(() => vi.restoreAllMocks());

const testRun = (): RunView => sample("run_test");
const BANNER = "Düzenlenmiş profil: onaylanırsa metin ve kart bu profille hazırlanır; değişiklikler kartta gösterilir.";

test("the changes in one line with the profile panel's field labels; lists joined with ', '", () => {
  const v = testRun();
  expect(profileChanges(v.persona_changes, "TR")).toBe("yaş: 62 → 45");
  const many = [
    { field: "yas", original: 62, edited: 45 },
    { field: "oncelikler", original: ["düzenli gelir", "likidite"], edited: ["büyüme"] },
  ];
  expect(profileChanges(many, "TR")).toBe("yaş: 62 → 45; öncelikler: düzenli gelir, likidite → büyüme");
  expect(profileChanges(many, "EN")).toBe("age: 62 → 45; priorities: düzenli gelir, likidite → büyüme");
  expect(profileChanges([{ field: "unknown_field", original: "a", edited: "b" }], "TR")).toBe("unknown_field: a → b");
});

test("the banner of an edited profile and the approval works", async () => {
  const v = testRun();
  const approve = vi.spyOn(api, "approve").mockResolvedValue({ ...v, result: { ...v.result, rm_status: "approved" } });
  renderDashboard(v);
  expect(screen.getByText(BANNER)).toBeInTheDocument();
  expect(screen.queryByText(/Test çalıştırması onaylanamaz/)).toBeNull();
  const button = screen.getByRole("button", { name: "Onayla ve metni hazırla" });
  // W44: run_test has one profile conflict; it needs a reason first
  await userEvent.click(screen.getByRole("button", { name: "Müşteriyle teyit edildi" }));
  await userEvent.type(screen.getByRole("textbox", { name: "Neden" }), "uzun vade");
  await userEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  expect(button).toBeEnabled();
  await userEvent.click(button);
  expect(approve).toHaveBeenCalled();
  expect(approve.mock.calls[0][1]).toBe("approved");
  expect(approve.mock.calls[0][4]).toEqual([{ finding_id: "risk_vs_growth", note: "uzun vade" }]);
});

function meeting(v: RunView, lang: Lang = "TR") {
  vi.spyOn(api, "narrative").mockResolvedValue(sample(lang === "TR" ? "narrative_p01_tr" : "narrative_p01_en"));
  vi.spyOn(api, "glossary").mockResolvedValue([]);
  return renderWith(<MeetingText view={v} />, { lang });
}

test("screen 2 of an edited profile shows the line with the changes", async () => {
  meeting(testRun());
  expect(await screen.findByTestId("edited-profile")).toHaveTextContent("Düzenlenmiş profil ile hazırlandı: yaş: 62 → 45");
});

test("screen 2 of the original profile has no such line", async () => {
  meeting(sample("run_p01_approved"));
  await screen.findByTestId("presentation");      // the client page (Öykü's W27+)
  expect(screen.queryByTestId("edited-profile")).toBeNull();
});

test("the print card shows the line in the client section", () => {
  render(
    <LangContext.Provider value="TR">
      <PrintCard view={testRun()} narrative={sample("narrative_p01_tr")} />
    </LangContext.Provider>,
  );
  expect(screen.getByTestId("print-edited-profile")).toHaveTextContent("Düzenlenmiş profil ile hazırlandı: yaş: 62 → 45");
});

test("W30 EN", async () => {
  renderDashboard(testRun(), () => {}, "EN");
  expect(screen.getByText("Edited profile: if you approve, the text and the card are prepared with this profile; the changes are shown on the card.")).toBeInTheDocument();
  vi.restoreAllMocks();
  meeting(testRun(), "EN");
  expect(await screen.findByTestId("edited-profile")).toHaveTextContent("Prepared with an edited profile: age: 62 → 45");
});
