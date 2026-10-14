// Test access to the API samples (tests/contracts/fixtures/api/, written by the
// lead with `python -m rmprep.api.samples`): the contract between API and web.
import type { EvidenceItem, GlossaryTerm, IngestStatus, NarrativeBrief, NarrativeView, OptionView, Persona, RunView, SourceStatus } from "../api/types";

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


// Option kinds etf and stock (contract v1.9, D26): the API samples have none yet, so
// a fund of a sample becomes one, with the access of a T+2 exchange trade.
/** The fund option as an ETF ("BYF") or a share ("Pay"). */
export function asKind(o: OptionView, kind: "etf" | "stock"): OptionView {
  const code = o.option_id.split(":")[1] ?? o.option_id;
  const stock = kind === "stock";
  return {
    ...structuredClone(o),
    option_id: `${kind}:${code}`,
    kind,
    issuer: stock ? "" : o.issuer,
    short_label: stock ? `${code} Pay` : o.short_label,
    label: stock ? `${code} Pay Senedi` : o.label,
    access: { ...o.access, days: 2, label: "2 iş günü (borsa takası)" },
    rank: stock ? null : o.rank,
    stars: stock ? null : o.stars,
  };
}

// W18: the current split (RunView.allocation current fields, RunView.holdings). The lead's
// API (Task 4) is built in parallel; until its fixtures have them, the numbers of spec
// docs/superpowers/specs/2026-10-14-portfolio-projection-design.md section 4.
type HoldingsState = "estimate" | "persona_text" | "rm" | "rm_confirmed";
type Current = [current: number, low: number, high: number, source: string, ref: string];

const NATIONAL = { id: "national", label: "TCMB Finansal İstikrar Raporu 2026-I, Tablo III.1.2", url: "https://www.tcmb.gov.tr/", date: "2026-03-31" };
const CURRENT: Record<HoldingsState, Record<string, Current>> = {
  // the national default, point ± 5
  estimate: {
    nakit_benzeri: [39, 34, 44, "national", "national"],
    borclanma: [10, 5, 15, "national", "national"],
    hisse: [10, 5, 15, "national", "national"],
    altin_doviz: [30, 25, 35, "national", "national"],
    dengeli: [11, 6, 16, "national", "national"],
  },
  // P01 "mevduat ağırlıklı" → nakit 60–90; the rest in the national proportions
  persona_text: {
    nakit_benzeri: [75, 60, 90, "persona_text", "mevduat_agirlikli"],
    borclanma: [4.1, 0, 9.1, "national", "national"],
    hisse: [4.1, 0, 9.1, "national", "national"],
    altin_doviz: [12.3, 7.3, 17.3, "national", "national"],
    dengeli: [4.5, 0, 9.5, "national", "national"],
  },
  rm: {
    nakit_benzeri: [50, 50, 50, "rm", ""],
    borclanma: [20, 20, 20, "rm", ""],
    hisse: [15, 15, 15, "rm", ""],
    altin_doviz: [10, 10, 10, "rm", ""],
    dengeli: [5, 5, 5, "rm", ""],
  },
  rm_confirmed: {
    nakit_benzeri: [39, 39, 39, "rm_confirmed", ""],
    borclanma: [10, 10, 10, "rm_confirmed", ""],
    hisse: [10, 10, 10, "rm_confirmed", ""],
    altin_doviz: [30, 30, 30, "rm_confirmed", ""],
    dengeli: [11, 11, 11, "rm_confirmed", ""],
  },
};
const ACTIVE = new Set(["rm", "rm_confirmed", "persona_text"]);

/** The gap of spec section 5: + under the band, − over it, 0 inside, null without a band. */
const gapOf = (low: number | null, high: number | null, x: number) =>
  low === null || high === null ? null : x < low ? low - x : x > high ? high - x : 0;

/** A run sample with the current split of one holdings state. */
export function withHoldings(view: RunView, status: HoldingsState): RunView {
  const rows = CURRENT[status];
  return {
    ...view,
    allocation: view.allocation.map((a) => {
      const [current, current_low, current_high, current_source, current_ref] = rows[a.asset_class];
      const gap = gapOf(a.low, a.high, current);
      return { ...a, current, current_low, current_high, current_source, current_ref, gap: gap === null ? null : Math.round(gap * 10) / 10, active: ACTIVE.has(current_source) } as typeof a;
    }),
    holdings: { status, sources: status === "estimate" || status === "persona_text" ? [NATIONAL] : [] },
    effective_weights: { return: 1, liquidity: 1, allocation_gap: ACTIVE.has(status) ? 0.75 : 0 },
  };
}
