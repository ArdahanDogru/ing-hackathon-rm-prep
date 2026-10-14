// Types of the JSON API (docs/web-ui.md section 6). Contract objects are their
// to_dict() (src/rmprep/contracts.py v1.3). Check them against the samples in
// ../tests/contracts/fixtures/api/ when they change.

export type Lang = "TR" | "EN";

// --- contract types (as JSON) ---------------------------------------------------

export interface Persona {
  persona_id: string;
  profil: string;
  yas: number;
  risk_profili: string;
  durum: string;
  yatirim_amaci: string;
  yatirim_ufku: string;
  likidite_ihtiyaci: string;
  doviz_maruz_kalma_tercihi: string;
  gelir_nakit_akisi_ihtiyaci: string;
  anapara_koruma_tercihi: string;
  oncelikler: string[];
  acik_kisitlar: string[];
  rm_notu: string;
}

export type OptionKind = "deposit" | "time_deposit" | "fund";

export interface ProductOption {
  option_id: string;
  kind: OptionKind;
  label: string;
  entity: string;
  fund_kind: string;
  fx: boolean;
  asset_class: string; // v1.6: nakit_benzeri | borclanma | dengeli | hisse | altin_doviz ("" = not set)
}

export interface ConstraintResult {
  rule_id: string;
  passed: boolean;
  reason: string;
  evidence_ids: string[];
}

export interface ScoredOption {
  option: ProductOption;
  score: number;
  score_parts: Record<string, number>;
  constraints: ConstraintResult[];
  confidence: number;
  stability: number;
  evidence_ids: string[];
  reasons: Record<string, string>;
}

export interface RejectedOption {
  option: ProductOption;
  failed: ConstraintResult[];
}

export interface ClarificationQuestion {
  question_id: string;
  text: string;
  reason: string;
  about: string;
  choices: string[];
  answer: string | null;
  blocking: boolean;
}

export type Audience = "client" | "rm";

export interface Warning {
  code: string;
  message: string;
  evidence_ids: string[];
  option_ids: string[];
  audience: Audience;
}

export interface TalkingPoint {
  code: string;
  label: string;
  figure: string;
  text: string;
  evidence_ids: string[];
  option_ids: string[];
}

export interface DataNote {
  message: string;
  flags: string[];
  sources: string[];
  evidence_ids: string[];
}

export type DecisionState = "ready" | "needs_rm_input";
export type RmStatus = "pending" | "approved" | "rejected";

export interface DecisionResult {
  run_id: string;
  config_hash: string;
  created_at: string;
  persona: Persona;
  snapshot_id: string;
  excluded_sources: string[];
  state: DecisionState;
  options: ScoredOption[];
  rejected: RejectedOption[];
  questions: ClarificationQuestion[];
  assumptions: string[];
  warnings: Warning[];
  data_quality: DataNote[];
  rm_status: RmStatus;
  rm_note: string;
  rm_selected: string[];
  rm_option_notes: Record<string, string>;
  talking_points: TalkingPoint[];
  to_confirm: string[];
  recommended: string[]; // v1.6: the engine's top 3 (option ids, in order)
  rm_decided_at: string | null; // v1.7: when the RM approved or rejected (ISO, +03:00)
  allocation: AllocationBand[]; // v1.8, D20: strategic model allocation bands, in class order
  allocation_notes: string[]; // v1.8: holding hints from the persona text
}

/** v1.8 (D20): one asset class of the strategic model allocation. No current shares, no amounts. */
export interface AllocationBand {
  asset_class: string;
  low: number | null; // % of the portfolio; null = no band (dengeli funds)
  high: number | null;
  source: string;
  inferred: boolean; // our inference, not a source value
  option_id: string | null; // the best scored option of the class for this client
  note: "" | "ceiling" | "none" | "negative_real";
}

/** The API's allocation row: the band plus the class label and the note text. */
export interface AllocationRow extends AllocationBand {
  label: string;
  note_text: string;
}

export type SectionKey =
  | "ozet"
  | "oneriler"
  | "alternatifler"
  | "dikkat"
  | "sorular"
  | "teklif_metni"
  | "varsayimlar"
  | "talking_points"
  | "piyasa_notu";

export interface NarrativeSentence {
  text: string;
  option_ids: string[];
  evidence_ids: string[];
  title: string;
}

export interface NarrativeSection {
  key: SectionKey;
  sentences: NarrativeSentence[];
}

export interface NarrativeDraft {
  run_id: string;
  lang: Lang;
  sections: NarrativeSection[];
  source: "llm" | "template";
  model: string;
  prompt_version: string;
  checks: string[];
  created_at: string;
  cost_usd: number;
  status: "draft" | "approved";
  rm_text: string;
  need_tags: Record<string, string[]>;
  /** v1.5: block id → the RM's edited text of that block. */
  rm_edits: Record<string, string>;
  /** v1.5: block id → findings "<kind>: <message>"; kinds in BLOCKING_CHECK_KINDS stop the approval. */
  edit_checks: Record<string, string[]>;
  approved_at: string | null; // v1.7: when the text was approved (ISO, +03:00)
}

/** Finding kinds that block "Metni onayla" (contract v1.5); "number" only warns. */
export const BLOCKING_CHECK_KINDS = ["phrase", "option", "internal", "label"] as const;

/** GET /runs/{id}/narrative: the draft plus its Markdown (the approved text when approved)
 * and the unedited draft's Markdown. */
export interface NarrativeView extends NarrativeDraft {
  markdown: string;
  draft_markdown: string;
}

export interface SourceStatus {
  status: "ok" | "failed" | "skipped";
  error: string | null;
  fallback_from: string | null;
  excluded: boolean;
}

/** GET /evidence/{snapshot}/{id}: one DataPoint plus the fund name. */
export interface EvidenceItem {
  id: string;
  quantity: string;
  entity: string;
  value: number | null;
  unit: string;
  as_of: string;
  source: string;
  source_url: string;
  fetched_at: string;
  snapshot_id: string;
  raw_ref: string;
  flags: string[];
  note: string;
  entity_name: string;
}

/** GET /runs/{id}/brief (contract v1.4): 1–2 sentences for the RM, never in the card. */
export interface NarrativeBrief {
  run_id: string;
  lang: Lang;
  text: string;
  source: "llm" | "template";
  model: string;
  prompt_version: string;
  checks: string[];
  created_at: string;
  cost_usd: number;
  cite: string[];
}

export interface GlossaryTerm {
  term: string;
  form: string;
  explanation: string;
}

// --- view models (API section 6) -----------------------------------------------

export type Fact = { value: number; evidence_id: string } | null;

export interface OptionView {
  option_id: string;
  label: string; // the full official name (hover, fund card, evidence, meeting text)
  issuer: string; // "Nurol Portföy"; "" when the label has no "PORTFÖY"
  short_label: string; // "Para Piyasası (TL)"; the whole label when there is no issuer
  kind: OptionKind;
  category_key: string;
  category_label: string;
  fx: boolean;
  returns: { "3m": Fact; "6m": Fact; "1y": Fact; real_1y: Fact };
  category_avg: { "3m": number | null; "6m": number | null; "1y": number | null; real_1y: number | null } | null;
  rank: { position: number; of: number } | null;
  stars: number | null;
  better_than_pct: number | null;
  risk: { level: number; evidence_id: string } | null;
  access: { days: number | null; lock_days: number | null; label: string | null; evidence_id: string };
  match: number | null;
  why: [string, string][];
  warnings: Warning[];
  data_notes: DataNote[];
  selected: boolean;
  rm_note: string;
}

export interface Category {
  key: string;
  label: string;
  count: number;
  best_return_1y: number | null;
  option_ids: string[];
}

export interface ConfirmItem {
  text: string;
  question_id: string | null;
  choices: string[];
}

export interface RejectedByRule {
  rule_id: string;
  label: string;
  count: number;
  options: { label: string; reasons: string[] }[];
}

export interface RunView {
  result: DecisionResult;
  /** The client's SPK fund risk ceiling 1..7; null while a blocking question is open. */
  risk_ceiling: number | null;
  test_run: boolean;
  persona_changes: { field: string; original: unknown; edited: unknown }[];
  baseline: OptionView | null;
  top: string[];
  categories: Category[];
  options: Record<string, OptionView>;
  talking_points: TalkingPoint[];
  to_confirm: ConfirmItem[];
  assumptions: string[];
  data_notes: DataNote[];
  client_warnings: Warning[];
  rm_warnings: Warning[];
  rejected_by_rule: RejectedByRule[];
  allocation: AllocationRow[];
  allocation_notes: string[];
  /** W15: policy rate, USD/TRY, TCMB funding cost (EVDS); missing ones left out, [] when none. */
  market_note: MarketNoteItem[];
}

/** One value of the market note ("Piyasa notu · TCMB EVDS"). */
export interface MarketNoteItem {
  key: string; // policy_rate | usd_try | funding_cost
  label: string;
  value: number;
  unit: "pct" | "TRY";
  /** a plain date "2026-10-09" */
  as_of: string;
  evidence_id: string;
}

export interface RunInputs {
  persona: Persona;
  snapshot_id?: string;
  exclude_sources?: string[];
}

/** GET /api/ingest (and the 202 answer of POST): the data freshness and the ingest job (W14). */
export interface IngestStatus {
  latest_snapshot: string | null;
  /** ISO time of the latest snapshot, Europe/Istanbul */
  created_at: string | null;
  age_hours: number | null;
  /** age_hours >= 24 */
  stale: boolean;
  running: boolean;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}
