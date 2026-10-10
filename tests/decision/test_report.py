"""Text report: baseline, fund_kind groups like the UI, the rest in short
(docs/decision.md section 4.5, milestone D7; docs/ui.md section 1)."""

import dataclasses

import pytest

from rmprep.contracts import (
    ConstraintResult,
    DecisionResult,
    DecisionState,
    ProductOption,
    RejectedOption,
    ScoredOption,
)
from rmprep.decision.engine import decide
from rmprep.decision.report import fund_groups, render
from tests.decision.conftest import T0, load_evidence, load_persona


def _opt(oid, kind, score):
    if kind == "deposit":
        option = ProductOption(option_id=oid, kind="deposit", label=f"label {oid}")
    else:
        option = ProductOption(option_id=oid, kind="fund", label=f"label {oid}", fund_kind=kind)
    return ScoredOption(option=option, score=score, score_parts={"return": score},
                        constraints=(), confidence=0.9, stability=1.0,
                        reasons={"return": "r"})


def _rejected(i):
    option = ProductOption(option_id=f"fund:R{i:02d}", kind="fund", label="x", fund_kind="equity")
    return RejectedOption(option, (ConstraintResult("risk_ceiling", False, "no"),))


def _result(options, rejected=()):
    return DecisionResult(run_id="R0123456789", config_hash="abcdef012345", created_at=T0,
                          persona=load_persona("P04"), snapshot_id="S-test",
                          excluded_sources=frozenset(), state=DecisionState.READY,
                          options=tuple(options), rejected=tuple(rejected))


# display order (caps applied): the first fund of each kind leads, so the
# order is not the plain score order.
SIX_KINDS = [
    _opt("deposit:d", "deposit", 0.5),
    _opt("fund:debt1", "debt", 0.9),
    _opt("fund:eq1", "equity", 0.8),
    _opt("fund:mix1", "mixed", 0.7),
    _opt("fund:debt2", "debt", 0.85),
    _opt("fund:mix2", "mixed", 0.6),
    _opt("fund:var1", "variable", 0.4),
    _opt("fund:fof1", "fund_of_funds", 0.3),
    _opt("fund:par1", "participation", 0.2),
    _opt("fund:debt3", "debt", 0.1),
]


def _ids(group):
    return [o.option.option_id for o in group[1]]


def test_groups_are_ordered_by_their_best_score_and_at_most_5():
    groups = fund_groups(_result(SIX_KINDS))
    assert [g[0] for g in groups] == ["debt", "equity", "mixed", "variable", "fund_of_funds"]
    assert _ids(groups[0]) == ["fund:debt1", "fund:debt2", "fund:debt3"]
    assert _ids(groups[2]) == ["fund:mix1", "fund:mix2"]
    assert "participation" not in [g[0] for g in groups]


def test_group_members_are_in_score_order():
    options = [_opt("fund:a", "debt", 0.5), _opt("fund:b", "equity", 0.4),
               _opt("fund:c", "debt", 0.7)]
    [debt, _] = fund_groups(_result(options))
    assert _ids(debt) == ["fund:c", "fund:a"]


def test_tie_of_the_best_score_breaks_by_option_id():
    options = [_opt("fund:z", "debt", 0.5), _opt("fund:a", "equity", 0.5)]
    assert [g[0] for g in fund_groups(_result(options))] == ["equity", "debt"]


def test_pool_is_the_first_20_funds():
    options = [_opt("deposit:d", "deposit", 0.1)]
    options += [_opt(f"fund:d{i:02d}", "debt", 1 - i / 100) for i in range(25)]
    [debt] = fund_groups(_result(options))
    assert _ids(debt) == [f"fund:d{i:02d}" for i in range(20)]
    text = render(_result(options))
    assert "fund:d19" in text and "fund:d20" not in text
    assert "5 more scored options outside the groups" in text


def test_render_shows_baseline_then_groups_with_head_and_alternatives():
    text = render(_result(SIX_KINDS))
    assert text.index("label deposit:d") < text.index("debt")
    order = ["fund:debt1", "fund:debt2", "fund:debt3", "fund:eq1", "fund:mix1", "fund:mix2",
             "fund:var1", "fund:fof1"]
    positions = [text.index(oid) for oid in order]
    assert positions == sorted(positions)
    assert "fund:par1" not in text.split("rejected")[0].split("more")[0]
    # every group header shows its fund_kind and count
    assert "debt (3)" in text and "mixed (2)" in text and "equity (1)" in text


def test_head_shows_parts_and_alternatives_are_marked():
    lines = render(_result(SIX_KINDS)).splitlines()
    head = next(i for i, ln in enumerate(lines) if "fund:debt1" in ln)
    assert "return" in lines[head + 1]
    alt = next(ln for ln in lines if "fund:debt2" in ln)
    assert alt.lstrip().startswith("-")


def test_long_rejected_list_is_cut_to_10_ids():
    text = render(_result(SIX_KINDS, [_rejected(i) for i in range(15)]))
    assert "rejected: 15" in text
    assert "fund:R09" in text and "fund:R10" not in text


def test_short_rejected_list_is_complete():
    text = render(_result(SIX_KINDS, [_rejected(i) for i in range(3)]))
    assert "rejected: 3" in text and "fund:R02" in text and "..." not in text.split("rejected")[1]


# --- on evidence_medium ----------------------------------------------------------------

@pytest.fixture(scope="module")
def medium():
    return load_evidence()


def test_report_on_real_rows(config, medium):
    r = decide(medium, load_persona("P04"), config, created_at=T0)
    text = render(r)
    assert r.run_id in text and "P04" in text
    assert "ING Turuncu Hesap (standart)" in text
    assert r.options[1].option.label in text          # best fund heads the first group
    groups = fund_groups(r)
    assert 1 <= len(groups) <= 5
    assert groups[0][1][0] == r.options[1]
    for w in r.warnings:
        assert w.code in text


def test_report_of_a_blocked_result_shows_the_questions(config, medium):
    p = dataclasses.replace(load_persona("P01"), acik_kisitlar=("bilinmeyen bir kısıt",))
    text = render(decide(medium, p, config, created_at=T0))
    assert "needs_rm_input" in text
    assert "q:acik_kisitlar[0]" in text and "bilinmeyen bir kısıt" in text
