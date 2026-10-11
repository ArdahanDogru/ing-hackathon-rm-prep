// Test access to the API samples: the lead's (tests/contracts/fixtures/api/)
// when they exist, else the hand-made ones in src/test/fixtures/.
import type { EvidenceItem, GlossaryTerm, NarrativeView, Persona, RunView, SourceStatus } from "../api/types";

const lead = import.meta.glob("../../../tests/contracts/fixtures/api/*.json", { eager: true, import: "default" });
const local = import.meta.glob("./fixtures/*.json", { eager: true, import: "default" });

interface Samples {
  personas: Persona[];
  snapshots: string[];
  sources: Record<string, SourceStatus>;
  run_p01_ready: RunView;
  run_p01_approved: RunView;
  run_needs_input: RunView;
  run_test: RunView;
  narrative_p01_tr: NarrativeView;
  narrative_p01_en: NarrativeView;
  glossary: GlossaryTerm[];
  evidence_item: EvidenceItem;
}

function find(name: string): unknown {
  const pick = (files: Record<string, unknown>) =>
    Object.entries(files).find(([path]) => path.endsWith(`/${name}.json`))?.[1];
  const v = pick(lead) ?? pick(local);
  if (v === undefined) throw new Error(`no sample ${name}`);
  return v;
}

/** A deep copy of a sample, so a test may change it. */
export function sample<K extends keyof Samples>(name: K): Samples[K] {
  return structuredClone(find(name)) as Samples[K];
}
