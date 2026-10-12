// Test access to the API samples (tests/contracts/fixtures/api/, written by the
// lead with `python -m rmprep.api.samples`): the contract between API and web.
import type { EvidenceItem, GlossaryTerm, NarrativeBrief, NarrativeView, Persona, RunView, SourceStatus } from "../api/types";

const files = import.meta.glob("../../../tests/contracts/fixtures/api/*.json", { eager: true, import: "default" });

interface Samples {
  personas: Persona[];
  snapshots: string[];
  sources: Record<string, SourceStatus>;
  run_p01_ready: RunView;
  run_p01_approved: RunView;
  run_p02_ready: RunView;
  run_needs_input: RunView;
  run_test: RunView;
  narrative_p01_tr: NarrativeView;
  narrative_p01_en: NarrativeView;
  glossary: GlossaryTerm[];
  evidence_item: EvidenceItem;
  brief_p01_tr: NarrativeBrief;
}

function find(name: string): unknown {
  const v = Object.entries(files).find(([path]) => path.endsWith(`/${name}.json`))?.[1];
  if (v === undefined) throw new Error(`no sample ${name}`);
  return v;
}

/** A deep copy of a sample, so a test may change it. */
export function sample<K extends keyof Samples>(name: K): Samples[K] {
  return structuredClone(find(name)) as Samples[K];
}
