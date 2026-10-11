"""The grouping rule (docs/decision.md section 4.6) on hand-made results."""

import json
from pathlib import Path

from rmprep.contracts import DecisionResult, ProductOption, ScoredOption
from rmprep.grouping import DEFAULT_RULE, GroupingRule, group_key, groups, visible_alternatives

FIX = Path(__file__).resolve().parent / "fixtures"


def opt(oid, kind="fund", fund_kind="money_market"):
    return ProductOption(oid, kind, oid, fund_kind=fund_kind if kind == "fund" else "")


def scored(o, score):
    return ScoredOption(o, score, {"a": score}, (), 1, 1, reasons={"a": "r"})


def test_group_key_is_fund_kind_or_kind():
    assert group_key(opt("fund:A", fund_kind="debt")) == "debt"
    assert group_key(opt("time_deposit:t", kind="time_deposit")) == "time_deposit"
    assert group_key(scored(opt("deposit:d", kind="deposit"), 0.5)) == "deposit"


def test_groups_pool_order_heads_and_limit():
    dep = scored(opt("deposit:d", kind="deposit"), 0.99)
    rows = [scored(opt("fund:M1"), 0.9), scored(opt("fund:D1", fund_kind="debt"), 0.8),
            scored(opt("fund:M2"), 0.85), scored(opt("time_deposit:t", kind="time_deposit"), 0.7),
            scored(opt("fund:E1", fund_kind="equity"), 0.6)]
    rule = GroupingRule(pool=4, max_groups=2, visible_alternatives=1)
    gs = groups([dep, *rows], rule)
    # the pool is the first 4 non-deposit options; E1 is outside it
    assert [g.key for g in gs] == ["money_market", "debt"]          # max 2, by best score
    assert gs[0].head.option.option_id == "fund:M1"
    assert [o.option.option_id for o in gs[0].alternatives] == ["fund:M2"]
    assert visible_alternatives(gs[0], opened=False, rule=rule) == gs[0].alternatives[:1]


def test_ties_break_by_option_id():
    rows = [scored(opt("fund:B"), 0.5), scored(opt("fund:A", fund_kind="debt"), 0.5)]
    assert [g.key for g in groups(rows)] == ["debt", "money_market"]


def test_alternatives_beyond_the_visible_count_open_on_request():
    rows = [scored(opt(f"fund:M{i}"), 0.9 - i / 100) for i in range(6)]
    g = groups(rows)[0]
    assert len(g.alternatives) == 5
    assert len(visible_alternatives(g, opened=False)) == DEFAULT_RULE.visible_alternatives == 3
    assert len(visible_alternatives(g, opened=True)) == 5


def test_default_rule_on_a_fixture_result():
    r = DecisionResult.from_dict(json.loads((FIX / "decision_p02_ready.json").read_text(encoding="utf-8")))
    gs = groups(r.options)
    assert 1 <= len(gs) <= DEFAULT_RULE.max_groups
    pool = [o for o in r.options if o.option.kind != "deposit"][:DEFAULT_RULE.pool]
    members = [o for g in gs for o in (g.head, *g.alternatives)]
    assert all(m in pool for m in members)


def test_top_heads_are_the_first_group_heads():
    from rmprep.grouping import top_heads
    dep = scored(opt("deposit:d", kind="deposit"), 0.99)
    rows = [dep, scored(opt("fund:M1"), 0.9), scored(opt("fund:D1", fund_kind="debt"), 0.8),
            scored(opt("fund:M2"), 0.85), scored(opt("time_deposit:t", kind="time_deposit"), 0.7),
            scored(opt("fund:E1", fund_kind="equity"), 0.6)]
    assert [h.option.option_id for h in top_heads(rows, 3)] == ["fund:M1", "fund:D1", "time_deposit:t"]
    assert top_heads(rows, 3) == tuple(g.head for g in groups(rows))[:3]
    assert top_heads([dep], 3) == ()
