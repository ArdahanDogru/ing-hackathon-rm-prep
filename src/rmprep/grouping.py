"""The grouping rule of the short list: one implementation for the UI, the text
report and the display caps. Ground truth: docs/decision.md section 4.6; change
the rule there first, then here (lead-owned)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rmprep.contracts import DecisionResult, ProductOption, RejectedOption, ScoredOption


@dataclass(frozen=True)
class GroupingRule:
    pool: int = 20                  # groups are made from the first `pool` non-deposit options
    max_groups: int = 5
    visible_alternatives: int = 3   # the rest open with "Daha fazla"


DEFAULT_RULE = GroupingRule()


@dataclass(frozen=True)
class Group:
    key: str                                    # group_key of its members
    head: ScoredOption                          # the best option of the group
    alternatives: tuple[ScoredOption, ...]      # the others, best first


def group_key(o: ProductOption | ScoredOption | RejectedOption) -> str:
    """fund_kind for a fund, else the option kind (deposit, time_deposit)."""
    option = o if isinstance(o, ProductOption) else o.option
    return option.fund_kind or option.kind


def _best_first(o: ScoredOption) -> tuple[float, str]:
    return (-o.score, o.option.option_id)


def groups(options: Sequence[ScoredOption], rule: GroupingRule = DEFAULT_RULE) -> list[Group]:
    """Groups of the first rule.pool non-deposit options (display order), at most
    rule.max_groups, ordered by the score of their head (ties: option_id)."""
    pool = [o for o in options if o.option.kind != "deposit"][:rule.pool]
    by_key: dict[str, list[ScoredOption]] = {}
    for o in pool:
        by_key.setdefault(group_key(o), []).append(o)
    out = []
    for key, members in by_key.items():
        best = sorted(members, key=_best_first)
        out.append(Group(key, best[0], tuple(best[1:])))
    out.sort(key=lambda g: _best_first(g.head))
    return out[:rule.max_groups]


def top_heads(options: Sequence[ScoredOption], n: int = 3,
              rule: GroupingRule = DEFAULT_RULE) -> tuple[ScoredOption, ...]:
    """The recommendations of the web dashboard: the heads of the first n groups."""
    return tuple(g.head for g in groups(options, rule)[:n])


def recommended(result: DecisionResult, n: int = 3) -> tuple[ScoredOption, ...]:
    """The recommendations of a result: the engine's choice (v1.6, D19), else
    the heads of the first n groups."""
    if result.recommended:
        by_id = {o.option.option_id: o for o in result.options}
        return tuple(by_id[i] for i in result.recommended[:n])
    return top_heads(result.options, n)


def visible_alternatives(g: Group, opened: bool,
                         rule: GroupingRule = DEFAULT_RULE) -> tuple[ScoredOption, ...]:
    return g.alternatives if opened else g.alternatives[:rule.visible_alternatives]
