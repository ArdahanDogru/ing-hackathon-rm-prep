import { render, screen } from "@testing-library/react";
import type { NarrativeView, RunView } from "../api/types";
import { LangContext } from "../i18n";
import { sample } from "../test/samples";
import { PrintCard } from "./PrintCard";

function renderPrint(view: RunView, narrative: NarrativeView) {
  return render(
    <LangContext.Provider value="TR">
      <PrintCard view={view} narrative={narrative} />
    </LangContext.Provider>,
  );
}

test("print card has no buttons and holds the selected options", () => {
  renderPrint(sample("run_p01_approved"), sample("narrative_p01_tr"));
  expect(screen.queryAllByRole("button")).toHaveLength(0);
  sample("run_p01_approved").result.rm_selected.forEach((id) =>
    expect(document.body).toHaveTextContent(sample("run_p01_approved").options[id].label.replace(/\s+/g, " ")),
  );
});

test("print card: aim, script, Dikkat, RM notes, footer", () => {
  const v = sample("run_p01_approved");
  const n = sample("narrative_p01_tr");
  renderPrint(v, n);
  const text = (key: string) => n.sections.find((s) => s.key === key)!.sentences[0].text;
  expect(document.body).toHaveTextContent(text("ozet"));
  expect(document.body).toHaveTextContent(text("teklif_metni"));
  expect(document.body).toHaveTextContent(text("dikkat"));
  v.rm_warnings.forEach((w) => expect(screen.getByTestId("print-rm-notes")).toHaveTextContent(w.message));
  expect(screen.getByTestId("print-footer")).toHaveTextContent(n.model);
});

test("an approved edited text prints as formatted Markdown", () => {
  const n = { ...sample("narrative_p01_tr"), status: "approved" as const, rm_text: "## Düzenlenmiş başlık\n\nMetin.", markdown: "## Düzenlenmiş başlık\n\nMetin." };
  renderPrint(sample("run_p01_approved"), n);
  expect(screen.getByRole("heading", { name: "Düzenlenmiş başlık" })).toBeInTheDocument();
});
