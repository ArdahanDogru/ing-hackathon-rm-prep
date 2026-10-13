// Test access to the API samples (tests/contracts/fixtures/api/, written by the
// lead with `python -m rmprep.api.samples`): the contract between API and web.
import type { EvidenceItem, GlossaryTerm, IngestStatus, NarrativeBrief, NarrativeView, Persona, RunView, SourceStatus } from "../api/types";

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

// GET /api/ingest (W14): the lead's endpoint is not merged yet, so the states are
// written here, on the newest snapshot of the snapshots sample.
const IDLE: IngestStatus = {
  latest_snapshot: "20261010-183835-6813",
  created_at: "2026-10-10T18:38:35+03:00",
  age_hours: 5,
  stale: false,
  running: false,
  started_at: null,
  finished_at: null,
  error: null,
};

const INGEST = {
  fresh: IDLE,
  stale: { ...IDLE, age_hours: 75.5, stale: true },
  running: { ...IDLE, age_hours: 75.5, stale: true, running: true, started_at: "2026-10-14T07:30:04+03:00" },
  finished_newer: {
    ...IDLE,
    latest_snapshot: "20261014-074512-a1b2",
    created_at: "2026-10-14T07:45:12+03:00",
    age_hours: 0.1,
    started_at: "2026-10-14T07:30:04+03:00",
    finished_at: "2026-10-14T07:45:20+03:00",
  },
  error: {
    ...IDLE,
    age_hours: 75.5,
    stale: true,
    started_at: "2026-10-14T07:30:04+03:00",
    finished_at: "2026-10-14T07:31:10+03:00",
    error: "EVDS: HTTP 503",
  },
} satisfies Record<string, IngestStatus>;

/** A deep copy of one ingest status sample. */
export function ingestSample(state: keyof typeof INGEST): IngestStatus {
  return structuredClone(INGEST[state]);
}
