// "Neden bu öneri?" of the fund card (docs/web-ui.md W16): the engine's own score
// parts, reasons, rules, stability and confidence of one option, plus its rank and
// the closest alternative. Pure; every value comes from the RunView.
import type { ConstraintResult, RunView, ScoredOption } from "./api/types";

export interface ScoreRow {
  key: string; // score_parts key: "return", "risk_fit", … or "penalty:<rule>"
  value: number;
  reason: string; // engine text (Turkish)
  penalty: boolean;
  priorities: string[]; // the client's priorities (as written) that boost this criterion
}

export interface Alternative {
  option_id: string;
  label: string;
  score: number;
  /** The criterion with the largest score difference; null when the parts are equal. */
  diff: { key: string; mine: number; theirs: number; reason: string } | null;
}

export interface Explanation {
  position: number; // 1 = the highest score of all scored options
  of: number;
  score: number;
  criteria: ScoreRow[]; // highest part first
  penalties: ScoreRow[]; // largest penalty first
  constraints: ConstraintResult[];
  recommended: boolean;
  stability: number; // 0..1
  confidence: number; // 0..1
  alternative: Alternative | null; // only for a recommended option
}

const byScore = (a: ScoredOption, b: ScoredOption) =>
  b.score - a.score || a.option.option_id.localeCompare(b.option.option_id);

/** fund_kind for a fund, else the option kind: the engine's group (grouping.group_key). */
const groupOf = (o: ScoredOption) => o.option.fund_kind || o.option.kind;

/** Score differences below this are rounding noise. */
const EPS = 0.0005;

function biggestDiff(mine: ScoredOption, theirs: ScoredOption): Alternative["diff"] {
  const keys = new Set([...Object.keys(mine.score_parts), ...Object.keys(theirs.score_parts)]);
  let best: Alternative["diff"] = null;
  for (const key of keys) {
    const m = mine.score_parts[key] ?? 0;
    const t = theirs.score_parts[key] ?? 0;
    if (Math.abs(m - t) >= EPS && (best === null || Math.abs(m - t) > Math.abs(best.mine - best.theirs))) {
      best = { key, mine: m, theirs: t, reason: theirs.reasons[key] ?? "" };
    }
  }
  return best;
}

export function explain(view: RunView, optionId: string): Explanation | null {
  const r = view.result;
  const ranked = [...r.options].sort(byScore);
  const index = ranked.findIndex((o) => o.option.option_id === optionId);
  if (index < 0) return null;
  const o = ranked[index];
  const rows: ScoreRow[] = Object.entries(o.score_parts)
    .filter(([key, value]) => value !== 0 || key in o.reasons)
    .map(([key, value]) => ({
      key,
      value,
      reason: o.reasons[key] ?? "",
      penalty: key.startsWith("penalty:"),
      priorities: view.priority_criteria?.[key] ?? [],
    }));
  const recommended = r.recommended.includes(optionId);
  let alternative: Alternative | null = null;
  if (recommended) {
    const alt = ranked.find((x) => x !== o && groupOf(x) === groupOf(o) && !r.recommended.includes(x.option.option_id));
    if (alt) {
      alternative = { option_id: alt.option.option_id, label: alt.option.label, score: alt.score, diff: biggestDiff(o, alt) };
    }
  }
  return {
    position: index + 1,
    of: ranked.length,
    score: o.score,
    criteria: rows.filter((x) => !x.penalty).sort((a, b) => b.value - a.value),
    penalties: rows.filter((x) => x.penalty).sort((a, b) => a.value - b.value),
    constraints: o.constraints,
    recommended,
    stability: o.stability,
    confidence: o.confidence,
    alternative,
  };
}

export type Level = "good" | "neutral" | "bad";

/** Stability: config warnings.low_stability_below is 0.5. */
export const stabilityLevel = (s: number): Level => (s >= 0.8 ? "good" : s >= 0.5 ? "neutral" : "bad");

/** Data confidence: 1 = no flag; each flag multiplies it down (config confidence). */
export const confidenceLevel = (c: number): Level => (c >= 0.8 ? "good" : c >= 0.6 ? "neutral" : "bad");
