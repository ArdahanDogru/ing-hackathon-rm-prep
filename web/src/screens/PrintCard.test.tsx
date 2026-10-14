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
  // a template draft has no model: the footer says "şablon metin" instead
  expect(screen.getByTestId("print-footer")).toHaveTextContent(n.source === "template" ? "şablon metin" : n.model);
});

test("an approved edited text prints as formatted Markdown", () => {
  const n = { ...sample("narrative_p01_tr"), status: "approved" as const, rm_text: "## Düzenlenmiş başlık\n\nMetin.", markdown: "## Düzenlenmiş başlık\n\nMetin." };
  renderPrint(sample("run_p01_approved"), n);
  expect(screen.getByRole("heading", { name: "Düzenlenmiş başlık" })).toBeInTheDocument();
});

test("an approved unedited text prints the sections", () => {
  const d = sample("narrative_p01_tr");
  const n = { ...d, status: "approved" as const, rm_text: d.draft_markdown, markdown: d.draft_markdown };
  renderPrint(sample("run_p01_approved"), n);
  expect(document.body).toHaveTextContent(d.sections.find((s) => s.key === "teklif_metni")!.sentences[0].text);
});

test("print card leaves deleted blocks out and prints edited ones", () => {
  const v = sample("run_p01_approved");
  const n = sample("narrative_p01_tr");
  const [first, second] = v.result.rm_selected;
  const text = (key: string) => n.sections.find((s) => s.key === key)!.sentences[0].text;
  const firstSentence = n.sections.find((s) => s.key === "oneriler")!.sentences.find((s) => s.option_ids[0] === first)!.text;
  renderPrint(v, { ...n, rm_edits: { ozet: "", dikkat: "", [`oneriler:${first}`]: "", [`oneriler:${second}`]: "Kendi cümlem." } });
  expect(document.body).not.toHaveTextContent(text("ozet"));
  expect(document.body).not.toHaveTextContent(text("dikkat"));
  expect(document.body).not.toHaveTextContent(firstSentence);
  expect(document.body).not.toHaveTextContent(v.options[first].label.replace(/\s+/g, " "));
  expect(document.body).toHaveTextContent("Kendi cümlem.");
  expect(document.body).toHaveTextContent(text("teklif_metni"));
});
