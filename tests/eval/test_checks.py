"""Each check passes on a clean run and catches a hand-made violation
(fixture evidence, project decision config with D12/D13, fake narrator)."""

import dataclasses
from datetime import date

import pytest

from rmprep import decision
from rmprep.contracts import (
    DataPoint, DecisionState, NarrativeDraft, NarrativeSection, NarrativeSentence, ScoredOption,
)
from rmprep.eval.checks import (
    FAIL, NA, PASS, Context, check_bad_data_handled, check_consistency,
    check_explicit_constraints, check_forbidden_phrases, check_missing_data_shown,
    check_narrator_valid, check_no_invented_data, check_not_buyable, check_questions,
    check_risk_ceiling, check_rule5, check_sensitivity, check_traceability, expect_errors,
    run_checks,
)
from rmprep.eval.scenario import EvidenceEdit, Scenario
from rmprep.narrator.config import load_config as load_narrator_config
from tests.eval.conftest import PROJECT, T0
from tests.eval.test_runner import one, runner

DCFG = decision.load_config(PROJECT / "config" / "decision.yaml").raw
PHRASES = load_narrator_config(PROJECT / "config" / "narrator.yaml").forbidden_phrases


def ctx(sr, k=0, compare=None) -> Context:
    return Context(sr.scenario, sr.runs[k], DCFG, PHRASES, compare)


def with_result(run, **changes):
    return dataclasses.replace(run, result=dataclasses.replace(run.result, **changes))


def as_scored(rej) -> ScoredOption:
    return ScoredOption(option=rej.option, score=0.0, score_parts={}, constraints=(),
                        confidence=0.5, stability=0.5, evidence_ids=tuple(
                            i for c in rej.failed for i in c.evidence_ids))


def text(run, *sentences, source="llm", checks=()):
    return NarrativeDraft(run.result.run_id, "TR", (NarrativeSection("oneriler", tuple(sentences)),),
                          source, "" if source == "template" else "m", "p", checks, T0)


def first_rejected(run, rule):
    return next(x for x in run.result.rejected if any(c.rule_id == rule for c in x.failed))


def add_row(run, quantity, entity, value, source="tefas_detail"):
    dp = DataPoint.create(quantity=quantity, entity=entity, value=value, unit="x",
                          as_of=date(2026, 10, 9), source=source, source_url="u",
                          fetched_at=T0, snapshot_id=run.evidence.snapshot_id, raw_ref="r")
    ev = dataclasses.replace(run.evidence, datapoints=run.evidence.datapoints + (dp,))
    return dataclasses.replace(run, evidence=ev), dp


@pytest.fixture
def p01(root):
    return one(root, Scenario(id="base-p01", group="base", persona="P01"))


def test_clean_runs_pass_or_are_na(root):
    from rmprep.eval.scenario import load_scenarios, packaged_scenario_files
    runs = runner(root).run([s for s in load_scenarios(packaged_scenario_files())
                             if "tefas_detail" not in s.exclude_sources
                             and s.group != "regression"])   # test_regression.py adds their rows
    for sc in run_checks(runs, DCFG, PHRASES):
        for c in sc.all():
            assert c.status in (PASS, NA), (sc.scenario.id, c)


def test_rule5_catches_a_bad_option_in_the_short_list_the_selection_and_the_text(p01):
    run = p01.runs[0]
    assert check_rule5(ctx(p01)).status == PASS
    rej = first_rejected(run, "risk_ceiling")
    bad = as_scored(rej)
    opts = run.result.options
    run2 = with_result(run, options=opts[:1] + (bad,) + opts[1:])
    run2 = dataclasses.replace(run2, approved=dataclasses.replace(
        run.approved, options=run2.result.options, rm_selected=(bad.option.option_id,)),
        narratives={"TR": text(run, NarrativeSentence(f"Öneri: {rej.option.label}."))})
    c = check_rule5(Context(p01.scenario, run2, DCFG, PHRASES))
    assert c.status == FAIL
    joined = " ".join(c.details)
    assert "short list" in joined and "selection" in joined and "text TR" in joined


def test_rule5_catches_a_rejected_option_named_in_the_text(p01):
    run = p01.runs[0]
    rej = first_rejected(run, "risk_ceiling")
    run2 = dataclasses.replace(run, narratives={"TR": text(
        run, NarrativeSentence(f"Bir de {rej.option.entity} var."))})
    c = check_rule5(Context(p01.scenario, run2, DCFG, PHRASES))
    assert c.status == FAIL and "rejected" in c.details[0]


def test_risk_ceiling_catches_a_listed_fund_above_the_ceiling(p01):
    run = p01.runs[0]
    assert check_risk_ceiling(ctx(p01)).status == PASS
    bad = as_scored(first_rejected(run, "risk_ceiling"))
    run2 = with_result(run, options=run.result.options + (bad,))
    c = check_risk_ceiling(Context(p01.scenario, run2, DCFG, PHRASES))
    assert c.status == FAIL and bad.option.option_id in c.details[0]


def test_not_buyable_catches_a_listed_closed_fund_and_is_na_before_d12(p01):
    run = p01.runs[0]
    assert check_not_buyable(ctx(p01)).status == PASS
    fund = next(o for o in run.result.options if o.option.kind == "fund")
    run2, _ = add_row(run, "fund_buyable", fund.option.entity, 0.0)
    c = check_not_buyable(Context(p01.scenario, run2, DCFG, PHRASES))
    assert c.status == FAIL and fund.option.option_id in c.details[0]
    no_d12 = {k: v for k, v in DCFG.items() if k not in ("fund_detail", "constraint_rules")}
    c = check_not_buyable(Context(p01.scenario, run2, no_d12, PHRASES))
    assert c.status == NA and c.needs == "D12"


def test_explicit_constraints_fx_limit(root):
    sr = one(root, Scenario(id="p02", group="base", persona="P02"))
    run = sr.runs[0]
    assert check_explicit_constraints(ctx(sr)).status == PASS
    fx = first_rejected(run, "fx_limit")
    run2 = with_result(run, options=run.result.options + (as_scored(fx),))
    c = check_explicit_constraints(Context(sr.scenario, run2, DCFG, PHRASES))
    assert c.status == FAIL and "fx_limit" in c.details[0]
    no_d13 = {k: v for k, v in DCFG.items() if k != "constraint_rules"}
    c = check_explicit_constraints(Context(sr.scenario, run2, no_d13, PHRASES))
    assert c.status == NA and c.needs == "D13"


def test_explicit_constraints_fx_override_lifts_the_rule(root):
    sr = one(root, Scenario(id="p02o", group="g", persona="P02",
                            answers=(("q:override:fx_limit", "gerekçeyle kaldır"),)))
    assert any(o.option.fx for o in sr.runs[0].result.options)
    assert check_explicit_constraints(ctx(sr)).status == NA


def test_explicit_constraints_liquidity_need(root):
    sr = one(root, Scenario(id="p05", group="base", persona="P05"))
    run = sr.runs[0]
    fund = next(o for o in run.result.options if o.option.kind == "fund")
    run2, _ = add_row(run, "fund_sell_valor_days", fund.option.entity, 5.0)
    c = check_explicit_constraints(Context(sr.scenario, run2, DCFG, PHRASES))
    assert c.status == FAIL and "liquidity_need" in c.details[0]


def test_no_invented_data_catches_a_made_up_number_and_an_excluded_source(root):
    sr = one(root, Scenario(id="x", group="data_access", persona="P01",
                            exclude_sources=frozenset({"manual"})))
    run = sr.runs[0]
    assert check_no_invented_data(ctx(sr)).status == PASS
    run2 = dataclasses.replace(run, narratives={"TR": text(
        run, NarrativeSentence("Getiri %987,6 olur.", (run.approved.rm_selected[0],)))})
    c = check_no_invented_data(Context(sr.scenario, run2, DCFG, PHRASES))
    assert c.status == FAIL and "987,6" in c.details[0]
    manual = next(d for d in run.evidence.datapoints if d.source == "manual")
    run3 = dataclasses.replace(run, narratives={"TR": text(
        run, NarrativeSentence("Mevduat.", evidence_ids=(manual.id,)))})
    c = check_no_invented_data(Context(sr.scenario, run3, DCFG, PHRASES))
    assert c.status == FAIL and "excluded source manual" in c.details[0]


def test_missing_data_shown_catches_a_hidden_exclusion(root):
    base = one(root, Scenario(id="b", group="base", persona="P01")).runs[0]
    sr = one(root, Scenario(id="x", group="data_access", persona="P01",
                            exclude_sources=frozenset({"manual"}), compare_to="b"))
    assert check_missing_data_shown(ctx(sr, compare=base)).status == PASS
    run2 = with_result(sr.runs[0], data_quality=())
    c = check_missing_data_shown(Context(sr.scenario, run2, DCFG, PHRASES, base))
    assert c.status == FAIL and "manual" in c.details[0]
    assert check_missing_data_shown(Context(sr.scenario, base, DCFG, PHRASES)).status == NA


def test_missing_data_shown_catches_a_confidence_rise(root):
    base = one(root, Scenario(id="b", group="base", persona="P01")).runs[0]
    sr = one(root, Scenario(id="x", group="data_access", persona="P01",
                            exclude_sources=frozenset({"tefas_web"})))
    run = sr.runs[0]
    fund_base = next(o for o in base.result.options if o.option.kind == "fund")
    higher = dataclasses.replace(fund_base, confidence=min(1.0, fund_base.confidence + 0.05))
    run2 = with_result(run, options=run.result.options + (higher,))
    c = check_missing_data_shown(Context(sr.scenario, run2, DCFG, PHRASES, base))
    assert c.status == FAIL and "confidence" in " ".join(c.details)


def test_bad_data_handled_catches_a_conflict_row_with_full_confidence(root):
    s = Scenario(id="c", group="bad_data", persona="P04", evidence_edits=(
        EvidenceEdit(quantity="fund_risk_level", entity="@top1", add_flags=("conflict",)),))
    sr = one(root, s)
    run = sr.runs[0]
    assert check_bad_data_handled(ctx(sr)).status == PASS
    entity = run.evidence_edits[0].entity
    opts = tuple(dataclasses.replace(o, confidence=0.9) if o.option.entity == entity else o
                 for o in run.result.options)
    c = check_bad_data_handled(Context(sr.scenario, with_result(run, options=opts), DCFG, PHRASES))
    assert c.status == FAIL and "conflict" in c.details[0]


def test_bad_data_handled_catches_a_used_out_of_range_row(root):
    s = Scenario(id="o", group="bad_data", persona="P04", evidence_edits=(
        EvidenceEdit(quantity="fund_risk_level", entity="@top1", value=9,
                     add_flags=("out_of_range",)),))
    sr = one(root, s)
    run = sr.runs[0]
    assert check_bad_data_handled(ctx(sr)).status == PASS
    row = next(d for d in run.evidence.datapoints if d.quantity == "fund_risk_level"
               and d.entity == run.evidence_edits[0].entity)
    opts = tuple(dataclasses.replace(o, evidence_ids=o.evidence_ids + (row.id,))
                 if o.option.entity == row.entity else o for o in run.result.options)
    c = check_bad_data_handled(Context(sr.scenario, with_result(run, options=opts), DCFG, PHRASES))
    assert c.status == FAIL and "out_of_range" in c.details[0]


def test_questions_catch_a_guess(p01, root):
    assert check_questions(ctx(p01)).status == NA
    asks = one(root, Scenario(id="a", group="constraint", persona="P01",
                              add_constraints=("kripto istemiyor",)))
    assert check_questions(ctx(asks)).status == PASS
    run = p01.runs[0]
    guessed = dataclasses.replace(run.result.persona, acik_kisitlar=run.result.persona.acik_kisitlar
                                  + ("kripto istemiyor",))
    c = check_questions(Context(p01.scenario, with_result(run, persona=guessed), DCFG, PHRASES))
    assert c.status == FAIL and "ready" in c.details[0]


def test_narrator_valid(p01):
    run = p01.runs[0]
    assert check_narrator_valid(ctx(p01)).status == PASS
    for d in (text(run, NarrativeSentence("x"), source="template", checks=("llm: no key",)),
              text(run, NarrativeSentence("x"), checks=("number: ...",))):
        c = check_narrator_valid(Context(p01.scenario, dataclasses.replace(
            run, narratives={"TR": d}), DCFG, PHRASES))
        assert c.status == FAIL


def test_forbidden_phrases_but_not_inside_a_fund_name(p01):
    run = p01.runs[0]
    bad = dataclasses.replace(run, narratives={"TR": text(run, NarrativeSentence("Garantili getiri."))})
    c = check_forbidden_phrases(Context(p01.scenario, bad, DCFG, PHRASES))
    assert c.status == FAIL and "garanti" in c.details[0]
    fund = run.result.options[1]
    named = dataclasses.replace(fund.option, label="GARANTİ PORTFÖY PARA PİYASASI FONU")
    run2 = with_result(run, options=(run.result.options[0], dataclasses.replace(fund, option=named))
                       + run.result.options[2:])
    run2 = dataclasses.replace(run2, narratives={"TR": text(
        run, NarrativeSentence("Seçenek: GARANTİ PORTFÖY PARA PİYASASI FONU."))})
    assert check_forbidden_phrases(Context(p01.scenario, run2, DCFG, PHRASES)).status == PASS


def test_forbidden_phrases_skip_short_fund_names(p01):
    """n8 texts name funds by their screen names ("Garanti Portföy Blockchain ...")."""
    run = p01.runs[0]
    fund = run.result.options[1]
    named = dataclasses.replace(fund.option, label="GARANTİ PORTFÖY BLOCKCHAİN TEKNOLOJİLERİ DEĞİŞKEN FON")
    run2 = with_result(run, options=(run.result.options[0], dataclasses.replace(fund, option=named))
                       + run.result.options[2:])
    for sentence in ("Garanti Portföy Blockchain Teknolojileri Değişken fonun riski 6 / 7'dir.",
                     "Garanti Portföy fonunda paraya erişim 3 iş günüdür."):
        run3 = dataclasses.replace(run2, narratives={"TR": text(run, NarrativeSentence(sentence))})
        assert check_forbidden_phrases(Context(p01.scenario, run3, DCFG, PHRASES)).status == PASS
    run4 = dataclasses.replace(run2, narratives={"TR": text(run, NarrativeSentence("Getiri garantilidir."))})
    assert check_forbidden_phrases(Context(p01.scenario, run4, DCFG, PHRASES)).status == FAIL


def test_traceability(p01):
    run = p01.runs[0]
    assert check_traceability(ctx(p01)).status == PASS
    o = run.result.options[1]
    run2 = with_result(run, options=(run.result.options[0], dataclasses.replace(o, evidence_ids=()))
                       + run.result.options[2:])
    c = check_traceability(Context(p01.scenario, run2, DCFG, PHRASES))
    assert c.status == FAIL and "no evidence id" in c.details[0]
    run3 = dataclasses.replace(run, narratives={"TR": text(
        run, NarrativeSentence("Kaynaksız cümle."), NarrativeSentence("y", evidence_ids=("Edeadbeef",)))})
    c = check_traceability(Context(p01.scenario, run3, DCFG, PHRASES))
    assert c.status == FAIL
    assert "without citation" in c.details[0] and "Edeadbeef" in c.details[1]


def test_consistency(root):
    sr = one(root, Scenario(id="r", group="base", persona="P02", repeat=2))
    assert check_consistency(sr).status == PASS
    a, b = sr.runs
    sr.runs[1] = dataclasses.replace(b, result=dataclasses.replace(b.result, assumptions=("x",)))
    assert check_consistency(sr).status == FAIL
    sr.runs[1] = dataclasses.replace(b, narratives={"TR": text(b, NarrativeSentence("other"))})
    c = check_consistency(sr)
    assert c.status == FAIL and "TR text" in c.details[0]
    assert check_consistency(one(root, Scenario(id="o", group="g", persona="P02"))).status == NA


def test_sensitivity_directions_and_absolute_values(root):
    base = one(root, Scenario(id="base-p03", group="base", persona="P03"))
    s = Scenario(id="e", group="persona_edit", persona="P03", edit={"risk_profili": "Muhafazakâr"},
                 compare_to="base-p03", expect={"avg_risk": "lower", "max_risk": {"at_most": 2},
                                                "state": "ready"})
    sr = one(root, s)
    assert check_sensitivity(sr, base, DCFG).status == PASS
    wrong = dataclasses.replace(s, expect={"avg_risk": "higher", "options": {"at_least": 10 ** 6}})
    sr.scenario = wrong
    c = check_sensitivity(sr, base, DCFG)
    assert c.status == FAIL and len(c.details) == 2


def test_expect_errors():
    assert expect_errors(Scenario(id="a", group="g", persona="P01", expect={"colour": 1}))
    assert expect_errors(Scenario(id="a", group="g", persona="P01", expect={"avg_risk": "lower"}))
    assert expect_errors(Scenario(id="a", group="g", persona="P01",
                                  expect={"avg_risk": {"about": 2}}))
    assert not expect_errors(Scenario(id="a", group="g", persona="P01", compare_to="b",
                                      expect={"avg_risk": "lower", "fx_in_options": {"equals": 0}}))


def test_a_scenario_that_did_not_run_fails(root):
    runs = runner(root).run([Scenario(id="p", group="g", persona="P99")])
    [sc] = run_checks(runs, DCFG, PHRASES)
    assert sc.scenario_checks[0].check == "scenario_runs" and sc.scenario_checks[0].status == FAIL


def test_packaged_expectations_are_valid():
    from rmprep.eval.scenario import load_scenarios, packaged_scenario_files
    for s in load_scenarios(packaged_scenario_files()):
        assert expect_errors(s) == [], s.id
    assert DecisionState.READY  # import used


def test_a_template_without_an_llm_try_is_not_a_narrator_finding(p01):
    run = p01.runs[0]
    for checks in (("llm: no API key (ANTHROPIC_API_KEY)",), ("budget: daily limit $5.00 reached",)):
        d = text(run, NarrativeSentence("x"), source="template", checks=checks)
        c = check_narrator_valid(Context(p01.scenario, dataclasses.replace(
            run, narratives={"TR": d}), DCFG, PHRASES))
        assert c.status == NA


# --- E8: the display facts of the run (decision.display) count as known numbers

def _display(run):
    from rmprep.decision.config import DecisionConfig
    from rmprep.decision.display import display_facts
    return display_facts(run.result, run.evidence, DecisionConfig(raw=DCFG))


def _tr1(x: float) -> str:
    return f"{abs(x):.1f}".replace(".", ",")


def _uncited(run, numbers):
    """(option_id, value) of a display-facts number the result does not hold."""
    from rmprep.eval.checks import _matches, allowed_numbers
    from rmprep.narrator.validator import numbers_in
    nums, _ = allowed_numbers(run.result, {d.id: d for d in run.evidence.datapoints})
    for oid, value in numbers:
        if not _matches(numbers_in(_tr1(value)), nums):
            return oid, value
    pytest.skip("every display number is also in the result on this fixture")


def test_a_display_facts_return_passes(root):
    sr = one(root, Scenario(id="p03", group="base", persona="P03"))   # horizon 3y: cites 3y rows
    run = sr.runs[0]
    shown = {o.option.option_id for o in run.result.options}
    oid, value = _uncited(run, [(oid, f.value) for oid, d in _display(run).items() if oid in shown
                                for f in d.returns.values()])
    run2 = dataclasses.replace(run, narratives={"TR": text(
        run, NarrativeSentence(f"Getiri %{_tr1(value)} oldu.", (oid,)))})
    assert check_no_invented_data(Context(sr.scenario, run2, DCFG, PHRASES)).status == PASS


def test_a_real_1y_return_passes(root, extra_rows):
    from tests.eval.test_regression import d9_rows
    extra_rows += d9_rows()                       # CPI and stopaj rows: real returns exist
    # P03 (horizon 3y): its reasons show the 3-year real return, not the 1-year one
    sr = one(root, Scenario(id="p03", group="base", persona="P03"))
    run = sr.runs[0]
    shown = {o.option.option_id for o in run.result.options}
    oid, value = _uncited(run, [(oid, d.real_1y.value) for oid, d in _display(run).items()
                                if oid in shown and d.real_1y is not None])
    run2 = dataclasses.replace(run, narratives={"TR": text(
        run, NarrativeSentence(f"Reel getiri −%{_tr1(value)}.", (oid,)))})
    assert check_no_invented_data(Context(sr.scenario, run2, DCFG, PHRASES)).status == PASS


def test_a_number_in_neither_the_result_nor_the_display_facts_still_fails(root):
    sr = one(root, Scenario(id="p03", group="base", persona="P03"))
    run = sr.runs[0]
    oid = run.result.options[1].option.option_id
    run2 = dataclasses.replace(run, narratives={"TR": text(
        run, NarrativeSentence("Getiri %4321,7 oldu.", (oid,)))})
    c = check_no_invented_data(Context(sr.scenario, run2, DCFG, PHRASES))
    assert c.status == FAIL and "4321,7" in c.details[0]


def test_display_facts_of_rejected_options_do_not_count(root):
    sr = one(root, Scenario(id="p01", group="base", persona="P01"))
    run = sr.runs[0]
    rejected = {x.option.option_id for x in run.result.rejected}
    shown = {o.option.option_id for o in run.result.options}
    facts = _display(run)
    shown_values = {round(f.value, 1) for oid, d in facts.items() if oid in shown
                    for f in d.returns.values()}
    oid, value = _uncited(run, [(oid, f.value) for oid, d in facts.items() if oid in rejected
                                for f in d.returns.values()
                                if round(f.value, 1) not in shown_values])
    run2 = dataclasses.replace(run, narratives={"TR": text(
        run, NarrativeSentence(f"Getiri %{_tr1(value)}.", (run.result.options[1].option.option_id,)))})
    assert check_no_invented_data(Context(sr.scenario, run2, DCFG, PHRASES)).status == FAIL


# --- E9: diverse recommendations (D19, docs/decision.md section 10)

def _diverse(sr, run=None):
    from rmprep.eval.checks import check_diverse_recommendations
    return check_diverse_recommendations(Context(sr.scenario, run or sr.runs[0], DCFG, PHRASES))


def test_diverse_recommendations_pass_for_a_dengeli_persona(root):
    sr = one(root, Scenario(id="p02", group="base", persona="P02"))
    assert sr.runs[0].result.recommended
    assert _diverse(sr).status == PASS


def test_diverse_recommendations_do_not_apply_to_a_muhafazakar_persona(root):
    sr = one(root, Scenario(id="p01", group="base", persona="P01"))
    c = _diverse(sr)
    assert c.status == NA and "Muhafazakâr" in c.details[0]


def test_two_cash_like_recommendations_fail(root):
    sr = one(root, Scenario(id="p02", group="base", persona="P02"))
    run = sr.runs[0]
    cash = [o.option.option_id for o in run.result.options
            if o.option.asset_class == "nakit_benzeri" and o.option.kind != "deposit"]
    assert len(cash) >= 2
    other = [o.option.option_id for o in run.result.options
             if o.option.asset_class not in ("nakit_benzeri", "") and o.option.kind != "deposit"]
    bad = with_result(run, recommended=(cash[0], cash[1], other[0]))
    c = _diverse(sr, bad)
    assert c.status == FAIL and "nakit_benzeri" in c.details[0]


def test_one_class_only_fails_when_the_result_has_more(root):
    sr = one(root, Scenario(id="p04", group="base", persona="P04"))
    run = sr.runs[0]
    by_class = {}
    for o in run.result.options:
        if o.option.kind != "deposit":
            by_class.setdefault(o.option.asset_class, []).append(o.option.option_id)
    cls, ids = next((k, v) for k, v in by_class.items() if k != "nakit_benzeri" and len(v) >= 3)
    c = _diverse(sr, with_result(run, recommended=tuple(ids[:3])))
    assert c.status == FAIL and "asset class" in " ".join(c.details)


def test_a_recommendation_above_the_risk_ceiling_fails(root):
    sr = one(root, Scenario(id="p02", group="base", persona="P02"))
    run = sr.runs[0]
    rej = next(x for x in run.result.rejected if any(c.rule_id == "risk_ceiling" for c in x.failed))
    bad_opt = ScoredOption(option=rej.option, score=0.0, score_parts={}, constraints=(),
                           confidence=0.5, stability=0.5, evidence_ids=tuple(
                               i for c in rej.failed for i in c.evidence_ids))
    run2 = with_result(run, options=run.result.options + (bad_opt,),
                       recommended=run.result.recommended[:2] + (rej.option.option_id,))
    c = _diverse(sr, run2)
    assert c.status == FAIL and "risk ceiling" in " ".join(c.details)


def test_a_class_rule_pick_with_a_negative_real_return_fails(root, extra_rows):
    from tests.eval.test_regression import d9_rows
    extra_rows += d9_rows()
    sr = one(root, Scenario(id="p02", group="base", persona="P02"))
    run = sr.runs[0]
    facts = _display(run)
    plain = {o.option.option_id for o in __import__("rmprep.grouping", fromlist=["x"])
             .top_heads(run.result.options, 3)}
    neg = [o.option.option_id for o in run.result.options
           if o.option.kind != "deposit" and o.option.option_id not in plain
           and facts[o.option.option_id].real_1y is not None
           and facts[o.option.option_id].real_1y.value < 0]
    if not neg:
        pytest.skip("no option with a negative real return on this fixture")
    keep = [i for i in run.result.recommended if i != neg[0]][:2]
    c = _diverse(sr, with_result(run, recommended=tuple(keep) + (neg[0],)))
    assert c.status == FAIL and "real" in " ".join(c.details)


def test_recommendation_metrics(root):
    from rmprep.eval.checks import metric_values
    sr = one(root, Scenario(id="p01", group="base", persona="P01"))
    m = metric_values(sr.runs[0], DCFG)
    assert m["recommended_plain_order"] is True
    assert m["recommended_cash_like"] >= 0 and m["recommended_classes"] >= 1


# --- the code-written market note (N14) cites its own EVDS rows (lead, 2026-10-15) ---------

def test_a_sentence_may_use_the_rows_it_cites_itself(root):
    """Eval 20261014-full: every LLM text failed rule 3 on piyasa_notu ("49,28",
    "2026-08-31"): the market note cites EVDS rows that the decision result does not
    reference. A sentence may use the value and date of a row it cites itself; the same
    figure without the citation still fails."""
    sr = one(root, Scenario(id="p01", group="base", persona="P01"))
    run = sr.runs[0]
    used = run.result.evidence_ids()
    for row in run.evidence.datapoints:
        if row.id in used or row.value is None or abs(row.value) < 100:
            continue
        figure = f"{row.value:.2f}".replace(".", ",")
        said = f"Değer {figure} ({row.as_of:%d.%m.%Y})."
        bare = dataclasses.replace(run, narratives={"TR": text(run, NarrativeSentence(said, ()))})
        if check_no_invented_data(Context(sr.scenario, bare, DCFG, PHRASES)).status != FAIL:
            continue                          # the figure is allowed anyway: try another row
        cited = dataclasses.replace(run, narratives={"TR": text(
            run, NarrativeSentence(said, (), (row.id,)))})
        assert check_no_invented_data(Context(sr.scenario, cited, DCFG, PHRASES)).status == PASS
        return
    pytest.skip("no evidence row outside the result with a figure that is not allowed anyway")


# --- E10: the current split and the allocation gap (D27, lead 2026-10-15) ------------------

def test_allocation_projection_passes_on_a_real_run(root):
    from rmprep.eval.checks import check_allocation_projection
    for pid in ("P01", "P02"):
        sr = one(root, Scenario(id=pid.lower(), group="base", persona=pid))
        assert check_allocation_projection(ctx(sr)).status == PASS


def test_allocation_projection_catches_a_bad_total_a_wrong_gap_and_a_bad_criterion(root):
    from rmprep.eval.checks import check_allocation_projection
    sr = one(root, Scenario(id="p02", group="base", persona="P02"))    # estimate only
    run = sr.runs[0]
    r = run.result
    bands = list(r.allocation)
    i = next(k for k, b in enumerate(bands) if b.current is not None and b.low is not None)
    b = bands[i]
    bands[i] = dataclasses.replace(b, current=b.current + 5, current_high=max(b.current_high, b.current + 5))
    bad_total = dataclasses.replace(run, result=dataclasses.replace(r, allocation=tuple(bands)))
    c = check_allocation_projection(Context(sr.scenario, bad_total, DCFG, PHRASES))
    assert c.status == FAIL and any("adds up" in d for d in c.details)
    bands = list(r.allocation)
    bands[i] = dataclasses.replace(b, gap=(b.gap or 0) + 7)
    wrong_gap = dataclasses.replace(run, result=dataclasses.replace(r, allocation=tuple(bands)))
    c = check_allocation_projection(Context(sr.scenario, wrong_gap, DCFG, PHRASES))
    assert c.status == FAIL and any("gap" in d for d in c.details)
    o = r.options[1]
    parts = dict(o.score_parts) | {"allocation_gap": 0.05}
    reasons = (dict(o.reasons) | {"allocation_gap": "test"}) if o.reasons else o.reasons
    options = (r.options[0], dataclasses.replace(o, score_parts=parts, score=o.score + 0.05,
                                                 reasons=reasons), *r.options[2:])
    criterion = dataclasses.replace(run, result=dataclasses.replace(r, options=options))
    c = check_allocation_projection(Context(sr.scenario, criterion, DCFG, PHRASES))
    assert c.status == FAIL and any("no active class" in d for d in c.details)
