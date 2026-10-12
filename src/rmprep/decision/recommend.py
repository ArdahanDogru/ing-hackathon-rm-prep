"""The recommended top 3 with the asset-class rule (docs/decision.md section 10,
D19)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence

from rmprep.contracts import ScoredOption
from rmprep.decision.config import DecisionConfig
from rmprep.decision.persona import Levels
from rmprep.grouping import groups

N = 3


def class_rule_applies(levels: Levels, config: DecisionConfig) -> bool:
    """The class rule is for the profiles of recommend.profiles (Dengeli, Agresif)
    and for a client with the diversity priority or constraint."""
    rec = config.raw.get("recommend")
    return rec is not None and (levels.risk_profile in rec["profiles"] or levels.diversity)


def choose(options: Sequence[ScoredOption], levels: Levels, config: DecisionConfig,
           real_of: Callable[[ScoredOption], float | None] = lambda o: None,
           ) -> tuple[tuple[str, ...], frozenset[str]]:
    """(recommended option ids in score order, the ids the class rule moved up).

    Without the rule: the first three group heads. With it: from all ranked
    (non-deposit) options in score order, at most max_per_class per asset class
    and at most max_cash_like cash-like options; with fewer than 3 classes the
    rule relaxes in that order (first the class cap, then the cash cap). The
    class rule never picks an option whose real 1-year return (real_of, percent)
    is below recommend.min_real_return (D19b; no value -> not blocked); the last
    step fills by plain score order without caps and without the floor. All
    options and not only the group heads: the groups are made by fund_kind, so
    a head can hide another class (a long-term debt fund behind a short-term
    one)."""
    plain = tuple(g.head.option.option_id for g in groups(options)[:N])
    if not class_rule_applies(levels, config):
        return plain, frozenset()
    rec = config.raw["recommend"]
    ranked = sorted((o for o in options if o.option.kind != "deposit"),
                    key=lambda o: (-o.score, o.option.option_id))
    stages = ((rec["max_per_class"], rec["max_cash_like"]), (None, rec["max_cash_like"]),
              (None, None))
    floor = rec.get("min_real_return")
    chosen: dict[str, ScoredOption] = {}
    for per_class, cash in stages:
        rule = per_class is not None or cash is not None
        for o in ranked:
            if len(chosen) == N:
                break
            if o.option.option_id in chosen:
                continue
            counts = Counter(x.option.asset_class for x in chosen.values())
            cls = o.option.asset_class
            if per_class is not None and counts[cls] >= per_class:
                continue
            if cash is not None and cls == rec["cash_like"] and counts[cls] >= cash:
                continue
            if rule and floor is not None:
                real = real_of(o)
                if real is not None and real < floor:
                    continue
            chosen[o.option.option_id] = o
    ids = tuple(o.option.option_id for o in ranked if o.option.option_id in chosen)
    return ids, frozenset(ids) - frozenset(plain)
