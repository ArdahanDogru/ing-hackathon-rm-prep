"""confidence and stability of the scored options (docs/decision.md section 5)."""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from typing import Any

from rmprep.decision.config import DecisionConfig
from rmprep.decision.persona import Levels
from rmprep.decision.scoring import (
    Features,
    normalize_weights,
    penalty_maxima,
    rank,
    raw_weights,
)


def confidence(f: Features, config: DecisionConfig) -> float:
    """Factor of the weakest row the option uses x the factor of each estimate."""
    c = config.raw["confidence"]
    weakest = 1.0
    for row in f.rows.values():
        for flag in row.flags:
            weakest = min(weakest, c["flags"].get(flag.value, 1.0))
    if f.risk_estimated:
        weakest *= c["risk_estimate"]
    if f.shorter_period:
        weakest *= c["shorter_period"]
    if f.liquidity_proxy:           # D14: no sell valör row, liquidity from the kind table
        weakest *= c.get("liquidity_proxy", 1.0)
    # D24: real return configured (net_return set) but not computable: no TÜFE row,
    # or no stopaj row for the option's product type (stopaj taken as 0)
    if f.net_return is not None and (f.real_return is None or f.stopaj_missing):
        weakest *= c.get("real_return_missing", 1.0)
    return weakest


def stability(features: Sequence[Features], levels: Levels, config: DecisionConfig,
              recommended: Collection[str] = (),
              pick: Callable[[Sequence[Any]], Collection[str]] | None = None,
              ) -> dict[str, float]:
    """Share of the perturbed display orders (each raw weight and each penalty
    maximum x (1 - step) and x (1 + step), one at a time) in which the option is
    in positions 1..stability.size (default: display.shortlist). The deposit
    baseline counts as always in. D25: an option of `recommended` gets instead
    the share of the runs in which pick (the recommendation rule applied to the
    rows of that run's order) recommends it again."""
    step = config.raw["stability"]["step"]
    size = config.raw["stability"].get("size", config.raw["display"]["shortlist"])
    raw = raw_weights(levels, config)
    maxima = penalty_maxima(config)
    runs: list[tuple[dict[str, float], dict[str, float]]] = []
    for factor in (1 - step, 1 + step):
        for crit in raw:
            runs.append(({**raw, crit: raw[crit] * factor}, maxima))
        for rule in maxima:
            runs.append((raw, {**maxima, rule: maxima[rule] * factor}))

    hits = {f.option.option_id: 0 for f in features}
    again = {oid: 0 for oid in recommended} if pick is not None else {}
    for w, m in runs:
        order = rank(features, normalize_weights(w), m, levels, config, with_reasons=False)
        funds = [r for r in order.rows if r.option.kind != "deposit"]
        for r in funds[:size]:
            hits[r.option.option_id] += 1
        if again:
            for oid in set(pick(order.rows)) & again.keys():
                again[oid] += 1
    out = {f.option.option_id: 1.0 if f.option.kind == "deposit"
           else hits[f.option.option_id] / len(runs) for f in features}
    out.update({oid: n / len(runs) for oid, n in again.items()})
    return out
