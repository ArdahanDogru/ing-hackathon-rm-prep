"""decide(): warnings, data-quality notes, config_hash, run_id and the text
report (docs/decision.md sections 6 and 7)."""

import dataclasses
import re

import pytest

from rmprep.contracts import DecisionResult, DecisionState, SourceStatus
from rmprep.decision.config import parse_config
from rmprep.decision.engine import config_hash, decide, run_id
from rmprep.decision.notes import build_warnings
from rmprep.decision.persona import read_persona
from rmprep.decision.report import render
from tests.decision.conftest import (
    PERSONA_IDS,
    T0,
    load_evidence,
    load_persona,
    make_evidence,
)


@pytest.fixture(scope="module")
def medium():
    return load_evidence()


def _edit(pid, **changes):
    return dataclasses.replace(load_persona(pid), **changes)


def _codes(result):
    return [w.code for w in result.warnings]


def _warning(result, code):
    [w] = [w for w in result.warnings if w.code == code]
    return w


# --- valid results on evidence_medium --------------------------------------------------

@pytest.mark.parametrize("pid", PERSONA_IDS)
def test_valid_result_for_every_persona(config, medium, pid):
    r = decide(medium, load_persona(pid), config, created_at=T0)
    assert isinstance(r, DecisionResult)
    assert r.state == DecisionState.READY
    assert r.options[0].option.option_id == "deposit:ing_turuncu"
    assert len(r.options) > 10
    assert r.persona == load_persona(pid)
    assert r.snapshot_id == medium.snapshot_id
    assert re.fullmatch(r"R[0-9a-f]{10}", r.run_id)
    assert re.fullmatch(r"[0-9a-f]{12}", r.config_hash)
    assert DecisionResult.from_dict(r.to_dict()) == r
    for o in r.options:
        assert 0 < o.confidence <= 1 and 0 <= o.stability <= 1
        assert o.evidence_ids
    assert r.options[0].stability == 1.0


def test_p01_rejects_funds_above_its_ceiling(config, medium):
    r = decide(medium, load_persona("P01"), config, created_at=T0)
    assert r.rejected
    assert all(c.rule_id == "risk_ceiling" for x in r.rejected for c in x.failed)
    scored = {o.option.option_id for o in r.options}
    assert not scored & {x.option.option_id for x in r.rejected}


def test_p02_has_one_open_non_blocking_question(config, medium):
    r = decide(medium, load_persona("P02"), config, created_at=T0)
    assert r.state == DecisionState.READY
    [q] = r.questions
    assert q.question_id == "q:doviz_maruz_kalma_tercihi" and q.answer is None


def test_assumptions(config, medium):
    r = decide(medium, load_persona("P02"), config, created_at=T0)
    a = config.raw["texts"]["assumptions"]
    for key in ("past_returns", "pre_tax", "no_real_returns", "kind_proxy"):
        assert a[key] in r.assumptions
    assert a["deposit_tier"].format(tier="100.000-249.999 TL") in r.assumptions
    assert a["fx_priority"] in r.assumptions                       # from the persona
    assert any("güvenli düzey" in x for x in r.assumptions)


# --- needs_rm_input and answers ---------------------------------------------------------

def test_unknown_constraint_needs_rm_input(config, medium):
    p = _edit("P01", acik_kisitlar=("bilinmeyen bir kısıt",))
    r = decide(medium, p, config, created_at=T0)
    assert r.state == DecisionState.NEEDS_RM_INPUT
    assert r.options == () and r.rejected == ()
    assert r.questions[0].question_id == "q:acik_kisitlar[0]"
    assert config.raw["texts"]["assumptions"]["pre_tax"] in r.assumptions


def test_answer_makes_it_ready(config, medium):
    p = _edit("P01", acik_kisitlar=("bilinmeyen bir kısıt",))
    r = decide(medium, p, config, {"q:acik_kisitlar[0]": "Risk tavanını 4 ile sınırla"},
               created_at=T0)
    assert r.state == DecisionState.READY and r.options


def test_bad_answer_is_an_error(config, medium):
    with pytest.raises(ValueError):
        decide(medium, load_persona("P02"), config, {"q:doviz_maruz_kalma_tercihi": "x"},
               created_at=T0)


# --- identity ----------------------------------------------------------------------------

def test_same_inputs_give_the_same_result(config, medium):
    a = decide(medium, load_persona("P04"), config, created_at=T0)
    b = decide(medium, load_persona("P04"), config, created_at=T0)
    assert a.to_dict() == b.to_dict()


def test_created_at_is_not_part_of_the_run_id(config, medium):
    a = decide(medium, load_persona("P04"), config, created_at=T0)
    b = decide(medium, load_persona("P04"), config,
               created_at=T0.replace(hour=17))
    assert a.run_id == b.run_id and a.created_at != b.created_at


def test_answer_persona_edit_and_exclusion_give_a_new_run_id(config, medium):
    base = decide(medium, load_persona("P02"), config, created_at=T0).run_id
    answered = decide(medium, load_persona("P02"), config,
                      {"q:doviz_maruz_kalma_tercihi": "Açık"}, created_at=T0).run_id
    edited = decide(medium, _edit("P02", rm_notu="başka"), config, created_at=T0).run_id
    excluded = decide(dataclasses.replace(medium, excluded_sources=frozenset({"tefas"})),
                      load_persona("P02"), config, created_at=T0).run_id
    assert len({base, answered, edited, excluded}) == 4


def test_run_id_formula(config):
    p = load_persona("P01")
    rid = run_id(config_hash(config), p, "S1", frozenset({"b", "a"}), {"q:x": "1"})
    assert rid == run_id(config_hash(config), p, "S1", frozenset({"a", "b"}), {"q:x": "1"})
    assert rid != run_id(config_hash(config), p, "S2", frozenset({"a", "b"}), {"q:x": "1"})


def test_config_hash(config, raw):
    assert config_hash(config) == config_hash(parse_config(raw))
    raw["penalties"]["fund_size"] = 0.2
    assert config_hash(parse_config(raw)) != config_hash(config)


# --- warnings ------------------------------------------------------------------------------

FULL = dict(returns={"3y": 100.0}, size=2e8, investors=500)


def test_concentration_warning(config):
    funds = {f"D{i}": dict(kind="debt", risk=2, **FULL) for i in range(5)}
    r = decide(make_evidence(funds), load_persona("P04"), config, created_at=T0)
    w = _warning(r, "concentration")
    assert set(w.option_ids) == {f"fund:D{i}" for i in range(5)}
    assert "debt" in w.message


def test_no_concentration_warning_with_enough_kinds(config):
    funds = {"A": dict(kind="debt", risk=2, **FULL), "B": dict(kind="equity", risk=3, **FULL)}
    r = decide(make_evidence(funds), load_persona("P04"), config, created_at=T0)
    assert "concentration" not in _codes(r)


def test_fx_exposure_warning(config):
    funds = {"FX": dict(kind="debt", risk=2, name="X EUROBOND FONU", **FULL),
             "TL": dict(kind="money_market", risk=1, **FULL)}
    r = decide(make_evidence(funds), load_persona("P05"), config, created_at=T0)  # Sınırlı
    assert _warning(r, "fx_exposure").option_ids == ("fund:FX",)
    r3 = decide(make_evidence(funds), load_persona("P03"), config, created_at=T0)  # Açık
    assert "fx_exposure" not in _codes(r3)


def test_risk_estimate_warning(config):
    funds = {"NR": dict(kind="equity", **FULL), "MM": dict(kind="money_market", risk=1, **FULL)}
    r = decide(make_evidence(funds), load_persona("P05"), config, created_at=T0)  # ceiling 3
    assert _warning(r, "risk_estimate").option_ids == ("fund:NR",)
    r3 = decide(make_evidence(funds), load_persona("P03"), config, created_at=T0)  # ceiling 7
    assert "risk_estimate" not in _codes(r3)


def test_low_stability_warning(config, medium):
    r = decide(medium, load_persona("P04"), config, created_at=T0)
    shaky = dataclasses.replace(r.options[2], stability=0.3)
    options = (*r.options[:2], shaky, *r.options[3:])
    lv = read_persona(load_persona("P04"), config).levels
    ws = build_warnings(options, lv, r.questions, medium, config)
    [w] = [w for w in ws if w.code == "low_stability"]
    assert w.option_ids == (shaky.option.option_id,)
    assert "0.30" in w.message


def test_deposit_vs_market_warning(config, medium):
    r = decide(medium, load_persona("P01"), config, created_at=T0)
    w = _warning(r, "deposit_vs_market")
    rows = {d.id: d for d in medium.datapoints}
    assert sorted(rows[i].source for i in w.evidence_ids) == ["evds", "manual"]
    assert w.option_ids == ("deposit:ing_turuncu",)
    assert "20.8" in w.message                              # 43.82 - 23.00


def test_no_deposit_vs_market_warning_when_close(config, medium):
    rows = tuple(d if d.entity != "ING Turuncu Hesap standart, 100.000-249.999 TL"
                 else dataclasses.replace(d, value=40.0) for d in medium.datapoints)
    r = decide(dataclasses.replace(medium, datapoints=rows), load_persona("P01"), config,
               created_at=T0)
    assert "deposit_vs_market" not in _codes(r)


@pytest.mark.parametrize("pid,expected", [
    ("P01", False), ("P02", True), ("P03", True), ("P04", True), ("P05", False)])
def test_no_fx_deposit_data_warning(config, medium, pid, expected):
    r = decide(medium, load_persona(pid), config, created_at=T0)
    assert ("no_fx_deposit_data" in _codes(r)) is expected


# --- data-quality notes ---------------------------------------------------------------------

def _note(result, contains):
    return [n for n in result.data_quality if contains in n.message]


def test_flag_count_notes(config, medium):
    r = decide(medium, load_persona("P04"), config, created_at=T0)
    [manual] = _note(r, "manual:")
    assert manual.flags == ("manual_entry",) and manual.sources == ("manual",)
    assert len(manual.evidence_ids) == 1 and "1 değer" in manual.message
    [web] = _note(r, "tefas_web:")
    assert web.flags == ("needs_check",)
    used = r.evidence_ids()
    assert set(web.evidence_ids) <= used


def test_out_of_range_and_removed_notes(config, medium):
    r = decide(medium, load_persona("P04"), config, created_at=T0)
    [oor] = _note(r, "aralık dışında")
    assert oor.evidence_ids == ("Ea1b6ffd1",) and oor.flags == ("out_of_range",)
    assert _note(r, "2 serbest fon")
    assert _note(r, "1 fon, adı ve türü bilinmediği")
    assert not _note(r, "tanımsız şemsiye")


def test_source_notes(config, medium):
    status = dict(medium.source_status)
    status["evds"] = SourceStatus(status="failed", error="timeout")
    status["tefas"] = SourceStatus(status="ok", fallback_from="20261009-000000-aaaa")
    ev = dataclasses.replace(medium, source_status=status,
                             excluded_sources=frozenset({"tefas_web"}))
    r = decide(ev, load_persona("P04"), config, created_at=T0)
    assert _note(r, "tefas_web kaynağı olmadan")[0].sources == ("tefas_web",)
    assert _note(r, "evds alınamadı: timeout")
    assert _note(r, "20261009-000000-aaaa")


def test_source_notes_also_when_blocked(config, medium):
    ev = dataclasses.replace(medium, excluded_sources=frozenset({"tefas"}))
    r = decide(ev, _edit("P01", risk_profili="?"), config, created_at=T0)
    assert r.state == DecisionState.NEEDS_RM_INPUT
    assert _note(r, "tefas kaynağı olmadan")


# --- report ----------------------------------------------------------------------------------

def test_report_shows_baseline_and_positions_1_to_10(config, medium):
    r = decide(medium, load_persona("P04"), config, created_at=T0)
    text = render(r)
    assert r.run_id in text and "P04" in text
    assert "ING Turuncu Hesap (standart)" in text
    for i in range(1, 11):
        assert re.search(rf"^\s*{i}\. ", text, re.M)
    assert not re.search(r"^\s*11\. ", text, re.M)
    assert r.options[1].option.label in text
    assert "penalty:" in text or "return" in text
    for w in r.warnings:
        assert w.code in text


def test_report_of_a_blocked_result_shows_the_questions(config, medium):
    p = _edit("P01", acik_kisitlar=("bilinmeyen bir kısıt",))
    text = render(decide(medium, p, config, created_at=T0))
    assert "needs_rm_input" in text
    assert "q:acik_kisitlar[0]" in text and "bilinmeyen bir kısıt" in text
