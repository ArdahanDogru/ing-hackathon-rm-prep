"""Criteria, weights, penalties, the risk_ceiling rule and the display order
(docs/decision.md sections 2 and 4).

`option_features` computes everything that does not depend on the weights and
penalty maxima (criterion values, penalty factors = intensity x violation, the
hard rule); `rank` combines features with weights and maxima. Stability
(section 5) calls `rank` again with changed weights and maxima.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from rmprep.contracts import ConstraintResult, DataPoint, ProductOption, RejectedOption
from rmprep.decision.config import CRITERIA, PENALTY_RULES, DecisionConfig
from rmprep.decision.persona import LEVEL_ATTR, Levels
from rmprep.decision.universe import Candidate, Universe

RISK_MIN, RISK_MAX = 1, 7
_RISK_Q = "fund_risk_level"
_SIZE_Q = "fund_total_value"
_INVESTORS_Q = "fund_investor_count"


def percentile_rank(x: float, values: Sequence[float]) -> float:
    """(count below + 0.5 x count equal other) / (n - 1); n = 1 -> 1."""
    n = len(values)
    if n <= 1:
        return 1.0
    below = sum(1 for v in values if v < x)
    equal_other = sum(1 for v in values if v == x) - 1
    return (below + 0.5 * equal_other) / (n - 1)


def annualize(percent: float, years: float) -> float:
    """Total return in % over `years` -> annual return as a fraction."""
    return (1 + percent / 100) ** (1 / years) - 1


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# --- weights ----------------------------------------------------------------------

def raw_weights(levels: Levels, config: DecisionConfig) -> dict[str, float]:
    c = config.raw
    out = {}
    for crit in CRITERIA:
        w = c["weights"][crit]
        raw = w["base"] + w.get("appetite", 0.0) * levels.appetite
        if "level" in w:
            raw += w["per_level"] * getattr(levels, LEVEL_ATTR[w["level"]])
        raw += c["priority_boost"] * levels.boosts.get(crit, 0)
        if crit == "liquidity" and levels.liquidity_weight is not None:
            raw = levels.liquidity_weight
        out[crit] = float(raw)
    return out


def normalize_weights(raw: Mapping[str, float]) -> dict[str, float]:
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("the raw weights add up to 0")
    return {k: v / total for k, v in raw.items()}


def penalty_maxima(config: DecisionConfig) -> dict[str, float]:
    return {r: float(config.raw["penalties"][r]) for r in PENALTY_RULES}


# --- features ---------------------------------------------------------------------

@dataclass(frozen=True)
class Features:
    option: ProductOption
    values: Mapping[str, float]         # criterion -> 0..1
    factors: Mapping[str, float]        # penalty rule -> intensity x violation (x factor)
    fields: Mapping[str, Any]           # names for the reason templates
    evidence_ids: tuple[str, ...]
    constraint: ConstraintResult        # risk_ceiling, passed
    risk: int                           # known or estimated
    risk_estimated: bool
    period: str | None                  # return period used; None = no return
    shorter_period: bool                # a shorter period than the horizon was used
    annual_return: float | None
    rows: Mapping[str, DataPoint] = field(default_factory=dict)   # quantity -> row used


def _risk_of(cand: Candidate) -> int | None:
    if cand.option.kind == "deposit":
        return RISK_MIN
    row = cand.values.get(_RISK_Q)
    return None if row is None else int(round(row.value))


def _return_of(cand: Candidate, levels: Levels, config: DecisionConfig
               ) -> tuple[float | None, str | None, DataPoint | None]:
    """(annual return, period, row) of the horizon period or the next shorter one."""
    h = config.raw["horizon"]
    if cand.option.kind == "deposit":
        row = next(iter(cand.values.values()))
        return row.value / 100, "1y", row
    fallback = h["fallback"]
    start = fallback.index(levels.period) if levels.period in fallback else 0
    for period in fallback[start:]:
        row = cand.values.get(f"fund_return_{period}")
        if row is not None:
            return annualize(row.value, h["years"][period]), period, row
    return None, None, None


def option_features(universe: Universe, levels: Levels, config: DecisionConfig
                    ) -> tuple[list[Features], list[RejectedOption]]:
    c = config.raw
    texts = c["texts"]
    kept: list[tuple[Candidate, int | None]] = []
    rejected: list[RejectedOption] = []
    for cand in universe.candidates:
        risk = _risk_of(cand)
        if risk is not None and risk > levels.ceiling:
            row = cand.values[_RISK_Q]
            rejected.append(RejectedOption(cand.option, (ConstraintResult(
                rule_id="risk_ceiling", passed=False,
                reason=texts["constraint"]["failed"].format(risk=risk, ceiling=levels.ceiling),
                evidence_ids=(row.id,)),)))
        else:
            kept.append((cand, risk))

    # risk estimate per fund_kind: highest known risk among the scored funds
    known_by_kind: dict[str, int] = {}
    for cand, risk in kept:
        if cand.option.kind == "fund" and risk is not None:
            k = cand.option.fund_kind
            known_by_kind[k] = max(known_by_kind.get(k, RISK_MIN), risk)

    returns = {cand.option.option_id: _return_of(cand, levels, config) for cand, _ in kept}
    all_returns = [r[0] for r in returns.values() if r[0] is not None]
    funds = [cand for cand, _ in kept if cand.option.kind == "fund"]
    sizes = [f.values[_SIZE_Q].value for f in funds if _SIZE_Q in f.values]
    investors = [f.values[_INVESTORS_Q].value for f in funds if _INVESTORS_Q in f.values]

    pv = c["principal_value"]
    smin = c["fund_size_min"]
    out: list[Features] = []
    for cand, known in kept:
        opt = cand.option
        is_fund = opt.kind == "fund"
        kind_row = c["kinds"][opt.fund_kind if is_fund else "deposit"]
        estimated = known is None
        risk = known_by_kind.get(opt.fund_kind, RISK_MAX) if estimated else known
        annual, period, ret_row = returns[opt.option_id]

        size_row = cand.values.get(_SIZE_Q)
        inv_row = cand.values.get(_INVESTORS_Q)
        if is_fund:
            q_size = percentile_rank(size_row.value, sizes) if size_row else 0.0
            q_inv = percentile_rank(inv_row.value, investors) if inv_row else 0.0
            quality = (q_size + q_inv) / 2
            principal = max(0.0, pv["fund_base"] - pv["fund_step"] * (risk - 1))
        else:
            quality = 1.0
            principal = pv["deposit"]
        values = {
            "return": percentile_rank(annual, all_returns) if annual is not None else 0.0,
            "low_risk": 1 - (_clamp(risk, RISK_MIN, RISK_MAX) - 1) / 6,
            "liquidity": kind_row["liquidity"],
            "income": kind_row["income"],
            "principal": principal,
            "simplicity": kind_row["simplicity"],
            "quality": quality,
        }

        horizon_missing = is_fund and period != levels.period
        if not is_fund:
            size_violation = 0.0
        elif size_row is None or inv_row is None:
            size_violation = 1.0
        else:
            size_violation = _clamp(max(1 - size_row.value / smin["total_value_try"],
                                        1 - inv_row.value / smin["investors"]))
        above = estimated and risk > levels.ceiling
        factors = {
            "principal": levels.principal * _clamp((risk - 2) / 3),
            "liquidity": levels.liquidity_intensity * (1 - values["liquidity"]),
            "fx_exposure": levels.fx_intensity * (1.0 if opt.fx else 0.0),
            "risk_unknown": (c["penalties"]["risk_unknown_above_ceiling_factor"] if above
                             else 1.0) if estimated else 0.0,
            "track_record": 1.0 if horizon_missing else 0.0,
            "fund_size": size_violation,
        }

        rows = {q: d for q, d in cand.values.items()
                if q in (_RISK_Q, _SIZE_Q, _INVESTORS_Q, "deposit_rate")}
        if ret_row is not None:
            rows[ret_row.quantity] = ret_row
        fields = {
            "risk": risk, "ceiling": levels.ceiling,
            "annual": (annual or 0.0) * 100, "period": period or levels.period,
            "horizon": levels.period,
            "size_m": size_row.value / 1e6 if size_row else 0.0,
            "investors": inv_row.value if inv_row else 0.0,
        }
        if estimated:
            reason = texts["reasons"]["penalty:risk_unknown"].format(**fields)
            risk_ids: tuple[str, ...] = ()
        else:
            reason = texts["constraint"]["passed"].format(**fields)
            risk_ids = (rows[_RISK_Q].id,) if _RISK_Q in rows else ()
        out.append(Features(
            option=opt, values=values, factors=factors, fields=fields,
            evidence_ids=tuple(sorted(d.id for d in rows.values())),
            constraint=ConstraintResult(rule_id="risk_ceiling", passed=True, reason=reason,
                                        evidence_ids=risk_ids),
            risk=risk, risk_estimated=estimated, period=period,
            shorter_period=is_fund and period is not None and period != levels.period,
            annual_return=annual, rows=rows))
    return out, rejected


# --- score, parts, reasons -----------------------------------------------------------

@dataclass(frozen=True)
class Row:
    features: Features
    score: float
    parts: Mapping[str, float]
    reasons: Mapping[str, str]

    def __getattr__(self, name: str) -> Any:
        # option, risk, period, ... come from the features
        if name == "features":      # not set yet (copy, pickle): no recursion
            raise AttributeError(name)
        return getattr(self.features, name)


def _reasons(f: Features, parts: Mapping[str, float], config: DecisionConfig) -> dict[str, str]:
    tpl = config.raw["texts"]["reasons"]
    out = {}
    for key in parts:
        if key == "return" and f.annual_return is None:
            out[key] = tpl["return_missing"].format(**{**f.fields, "period": f.fields["horizon"]})
            continue
        v = f.values.get(key, 0.0)
        out[key] = tpl[key].format(**f.fields, value=v, pct=v * 100)
    if "penalty:track_record" in out:
        out["penalty:track_record"] = tpl["penalty:track_record"].format(
            **{**f.fields, "period": f.fields["horizon"]})
    return out


def score_row(f: Features, weights: Mapping[str, float], maxima: Mapping[str, float],
              config: DecisionConfig | None = None) -> Row:
    parts: dict[str, float] = {}
    for crit in CRITERIA:
        if weights[crit] > 0:
            parts[crit] = weights[crit] * f.values[crit]
    for rule in PENALTY_RULES:
        p = maxima[rule] * f.factors[rule]
        if p > 0:
            parts[f"penalty:{rule}"] = -p
    reasons = _reasons(f, parts, config) if config is not None else {}
    return Row(f, sum(parts.values()), parts, reasons)


# --- display order ---------------------------------------------------------------------

class _Ranked(Protocol):
    option: ProductOption
    score: float


@dataclass(frozen=True)
class DisplayOrder:
    rows: tuple[Any, ...]                       # deposit first, then funds in display order
    concentration: tuple[tuple[str, int], ...] = ()   # (fund_kind, count) over the cap
    concentration_n: int = 0                    # 3 or 10: the range the counts are about


def display_order(rows: Sequence[_Ranked], *, diversity: bool,
                  config: DecisionConfig) -> DisplayOrder:
    d = config.raw["display"]
    cap = d["diversity_cap"] if diversity else d["cap"]
    ranked = sorted(rows, key=lambda r: (-r.score, r.option.option_id))
    deposits = [r for r in ranked if r.option.kind == "deposit"]
    remaining = [r for r in ranked if r.option.kind != "deposit"]
    chosen: list[Any] = []
    counts: Counter[str] = Counter()
    filled = {"first": False, "shortlist": False}

    def take(limit: int, per_kind: int, phase: str) -> None:
        for r in list(remaining):
            if len(chosen) >= limit:
                return
            if counts[r.option.fund_kind] < per_kind:
                chosen.append(r)
                counts[r.option.fund_kind] += 1
                remaining.remove(r)
        while remaining and len(chosen) < limit:     # caps leave places empty
            r = remaining.pop(0)
            chosen.append(r)
            counts[r.option.fund_kind] += 1
            filled[phase] = True

    take(d["first"], d["first_cap"], "first")
    first_counts = Counter(r.option.fund_kind for r in chosen)
    take(d["shortlist"], cap, "shortlist")

    concentration: list[tuple[str, int]] = []
    n = 0
    if filled["first"] or filled["shortlist"]:
        concentration = sorted((k, v) for k, v in counts.items() if v > cap)
        n = d["shortlist"]
        if not concentration:
            concentration = sorted((k, v) for k, v in first_counts.items() if v > d["first_cap"])
            n = d["first"]
    return DisplayOrder(tuple(deposits[:1] + chosen + remaining + deposits[1:]),
                        tuple(concentration), n)


# --- all together ------------------------------------------------------------------------

@dataclass(frozen=True)
class Scoring:
    scored: tuple[Row, ...]             # display order
    rejected: tuple[RejectedOption, ...]
    order: DisplayOrder
    features: tuple[Features, ...]
    weights: Mapping[str, float]


def rank(features: Sequence[Features], weights: Mapping[str, float],
         maxima: Mapping[str, float], levels: Levels, config: DecisionConfig,
         *, with_reasons: bool = True) -> DisplayOrder:
    rows = [score_row(f, weights, maxima, config if with_reasons else None) for f in features]
    return display_order(rows, diversity=levels.diversity, config=config)


def score_options(universe: Universe, levels: Levels, config: DecisionConfig) -> Scoring:
    features, rejected = option_features(universe, levels, config)
    weights = normalize_weights(raw_weights(levels, config))
    order = rank(features, weights, penalty_maxima(config), levels, config)
    return Scoring(order.rows, tuple(rejected), order, tuple(features), weights)
