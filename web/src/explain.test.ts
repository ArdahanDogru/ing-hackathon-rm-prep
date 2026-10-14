import { sample } from "./test/samples";
import { confidenceLevel, explain, stabilityLevel } from "./explain";

const view = () => sample("run_p01_ready");

test("rank, total and parts come from the engine; parts add up to the score", () => {
  const v = view();
  const x = explain(v, "fund:PPN")!;
  expect(x.position).toBe(1);
  expect(x.of).toBe(v.result.options.length);
  const sum = [...x.criteria, ...x.penalties].reduce((s, r) => s + r.value, 0);
  expect(sum).toBeCloseTo(x.score, 6);
  expect(x.criteria[0].key).toBe("risk_fit"); // highest part first
  expect(x.criteria.every((r) => !r.penalty && r.reason !== "")).toBe(true);
});

test("criteria carry the client's priorities that boost them", () => {
  const x = explain(view(), "fund:PPN")!;
  const tags = Object.fromEntries(x.criteria.map((r) => [r.key, r.priorities]));
  expect(tags.income).toEqual(["düzenli gelir"]);
  expect(tags.liquidity).toEqual(["likiditeyi koruma"]);
  expect(tags.risk_fit).toEqual(["sınırlı dalgalanma"]);
  expect(tags.return).toEqual([]);
});

test("penalties are separate, largest first", () => {
  const v = view();
  const o = v.result.options.find((x) => x.option.option_id === "fund:PPN")!;
  o.score_parts = { ...o.score_parts, "penalty:a": -0.05, "penalty:b": -0.1 };
  o.reasons = { ...o.reasons, "penalty:a": "A", "penalty:b": "B" };
  const x = explain(v, "fund:PPN")!;
  expect(x.penalties.map((r) => r.key)).toEqual(["penalty:b", "penalty:a"]);
  expect(x.criteria.some((r) => r.penalty)).toBe(false);
});

test("a recommended option gets the best other option of its group as the alternative", () => {
  const v = view();
  const x = explain(v, "fund:IST")!;
  expect(x.recommended).toBe(true);
  const alt = x.alternative!;
  const o = v.result.options.find((y) => y.option.option_id === alt.option_id)!;
  expect(o.option.fund_kind).toBe("debt");
  expect(v.result.recommended).not.toContain(alt.option_id);
  const better = v.result.options.filter(
    (y) => y.option.fund_kind === "debt" && !v.result.recommended.includes(y.option.option_id) && y.score > alt.score,
  );
  expect(better).toEqual([]);
});

test("an option that is not recommended has no alternative; an unknown id gives null", () => {
  const v = view();
  const other = v.result.options.find((o) => !v.result.recommended.includes(o.option.option_id))!;
  expect(explain(v, other.option.option_id)!.alternative).toBeNull();
  expect(explain(v, "fund:NOPE")).toBeNull();
});

test("stability and confidence levels", () => {
  expect([stabilityLevel(1), stabilityLevel(0.6), stabilityLevel(0.4)]).toEqual(["good", "neutral", "bad"]);
  expect([confidenceLevel(0.9), confidenceLevel(0.64), confidenceLevel(0.5)]).toEqual(["good", "neutral", "bad"]);
});
