"""Explicit constraints as hard rules: fx_limit with the RM override and
liquidity_need (docs/decision.md section 2, D13)."""

import dataclasses

import pytest

from rmprep.contracts import DecisionResult, DecisionState
from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.engine import decide
from rmprep.decision.persona import read_persona
from tests.decision.conftest import (
    D13_TEXTS,
    PERSONA_IDS,
    T0,
    d9_rows,
    load_persona,
    make_evidence,
    market_row,
)

LIFT = "gerekçeyle kaldır"
BASE = dict(size=2e8, investors=500, buyable=1)
FUNDS = {
    "MMF": dict(kind="money_market", risk=1, returns={"1y": 50.0, "3y": 200.0}, sell_valor=0,
                **BASE),
    "FXF": dict(kind="debt", risk=3, name="X PORTFÖY EUROBOND (DOLAR) FONU",
                returns={"1y": 30.0, "3y": 100.0}, sell_valor=1, **BASE),
    "V3": dict(kind="equity", risk=3, returns={"1y": 40.0, "3y": 150.0}, sell_valor=3, **BASE),
    "V4": dict(kind="equity", risk=3, returns={"1y": 40.0, "3y": 150.0}, sell_valor=4, **BASE),
    "NOV": dict(kind="mixed", risk=3, returns={"1y": 40.0, "3y": 150.0}, **BASE),   # no valör
}


def _ev(funds=FUNDS):
    return make_evidence(funds, time_deposit=35.0, extra=d9_rows() + [market_row()])


def _decide(cfg, pid, answers={}, persona=None, funds=FUNDS):
    return decide(_ev(funds), persona or load_persona(pid), cfg, answers, created_at=T0)


def _ids(r):
    return {o.option.option_id for o in r.options}


def _rejected(r):
    return {x.option.option_id: x for x in r.rejected}


# --- config -------------------------------------------------------------------------------

def test_d13_config_is_valid_and_optional(d13_config, config):
    assert d13_config.raw["constraint_rules"]["liquidity_need"]["max_lock_days"] == 91
    assert "constraint_rules" not in config.raw


@pytest.mark.parametrize("edit,match", [
    (lambda r: r["constraint_rules"].update(risk_cap={}), "constraint_rules"),
    (lambda r: r["constraint_rules"]["liquidity_need"].pop("max_lock_days"), "liquidity_need"),
    (lambda r: r["constraint_rules"]["liquidity_need"].update(max_sell_valor_days=-1),
     "max_sell_valor_days"),
    (lambda r: r["constraint_rules"]["fx_limit"].update(override_lifts="x"), "override_lifts"),
    (lambda r: r.pop("fund_detail"), "fund_detail"),
    (lambda r: r["texts"]["constraint"].pop("fx_limit"), "fx_limit"),
    (lambda r: r["texts"]["questions"].pop("override_fx_limit"), "override_fx_limit"),
    (lambda r: r["texts"]["assumptions"].pop("fx_override"), "fx_override"),
    (lambda r: r["texts"]["data_quality"].pop("valor_missing"), "valor_missing"),
])
def test_bad_d13_config_is_an_error(d13_raw, edit, match):
    edit(d13_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(d13_raw)


# --- fx_limit --------------------------------------------------------------------------------

def test_p02_fx_fund_is_rejected(d13_config):
    r = _decide(d13_config, "P02")
    assert "fund:FXF" not in _ids(r)
    [c] = _rejected(r)["fund:FXF"].failed
    assert c.rule_id == "fx_limit" and not c.passed
    assert c.reason == D13_TEXTS["constraint"]["fx_limit"]


def test_p02_gets_the_non_blocking_override_question(d13_config):
    r = _decide(d13_config, "P02")
    assert r.state == DecisionState.READY
    q = next(q for q in r.questions if q.question_id == "q:override:fx_limit")
    assert not q.blocking and q.answer is None
    assert q.choices == ("uygula", LIFT)
    assert q.about == "acik_kisitlar[0]"
    assert q.text == D13_TEXTS["questions"]["override_fx_limit"]


def test_override_brings_the_fx_funds_back_with_the_penalty(d13_config):
    r = _decide(d13_config, "P02", {"q:override:fx_limit": LIFT})
    assert "fund:FXF" in _ids(r) and "fund:FXF" not in _rejected(r)
    fxf = next(o for o in r.options if o.option.option_id == "fund:FXF")
    assert fxf.score_parts["penalty:fx_exposure"] < 0
    assert D13_TEXTS["assumptions"]["fx_override"] in r.assumptions


def test_apply_answer_keeps_the_rule(d13_config):
    r = _decide(d13_config, "P02", {"q:override:fx_limit": "uygula"})
    assert "fund:FXF" in _rejected(r)
    assert D13_TEXTS["assumptions"]["fx_override"] not in r.assumptions


def test_bad_override_answer_is_an_error(d13_config):
    with pytest.raises(ValueError, match="choices"):
        _decide(d13_config, "P02", {"q:override:fx_limit": "belki"})


def test_no_override_question_without_fx_limit(d13_config):
    r = _decide(d13_config, "P03")
    assert not [q for q in r.questions if q.question_id == "q:override:fx_limit"]
    with pytest.raises(ValueError):
        _decide(d13_config, "P03", {"q:override:fx_limit": LIFT})


def test_without_the_config_fx_limit_stays_a_penalty(d12_config):
    r = _decide(d12_config, "P02")
    assert "fund:FXF" in _ids(r)
    assert not [q for q in r.questions if q.question_id.startswith("q:override")]


def test_answered_unknown_constraint_is_enforced_too(d13_config):
    p = dataclasses.replace(load_persona("P03"), acik_kisitlar=("bilinmeyen bir kısıt",))
    r = _decide(d13_config, "P03", {"q:acik_kisitlar[0]": "Döviz maruziyetini sınırla"},
                persona=p)
    assert _rejected(r)["fund:FXF"].failed[0].rule_id == "fx_limit"
    q = next(q for q in r.questions if q.question_id == "q:override:fx_limit")
    assert q.about == "acik_kisitlar[0]"


# --- liquidity_need -----------------------------------------------------------------------------

def test_p05_valor_above_3_is_rejected(d13_config):
    r = _decide(d13_config, "P05")
    assert "fund:V4" not in _ids(r)
    [c] = _rejected(r)["fund:V4"].failed
    assert c.rule_id == "liquidity_need"
    assert c.reason == ("Satış valörü 4 gün, üst sınır 3 gün (müşterinin açık kısıtı: düşük "
                        "likiditeden kaçınma).")
    valor_row = next(d for d in _ev().datapoints
                     if d.entity == "V4" and d.quantity == "fund_sell_valor_days")
    assert c.evidence_ids == (valor_row.id,)


def test_p05_valor_3_and_missing_valor_are_kept(d13_config):
    r = _decide(d13_config, "P05")
    assert {"fund:V3", "fund:NOV", "fund:MMF"} <= _ids(r)
    msg = D13_TEXTS["data_quality"]["valor_missing"].format(count=1)
    assert msg in [n.message for n in r.data_quality]


def test_p05_32_day_time_deposit_is_kept(d13_config):
    assert "time_deposit:ing_e_vadeli" in _ids(_decide(d13_config, "P05"))


def test_p05_120_day_time_deposit_is_rejected(d13_raw):
    d13_raw["time_deposit"]["term_days"] = 120
    r = _decide(parse_config(d13_raw), "P05")
    [c] = _rejected(r)["time_deposit:ing_e_vadeli"].failed
    assert c.rule_id == "liquidity_need"
    assert c.reason.startswith("Vade 120 gün, üst sınır 91 gün")


def test_liquidity_need_only_for_its_persona(d13_config):
    r = _decide(d13_config, "P04")
    assert "fund:V4" in _ids(r)
    assert not [n for n in r.data_quality if "satış valörü kanıtlarda yok" in n.message]


def test_order_of_the_failed_rules(d13_config):
    funds = {**FUNDS, "V4": {**FUNDS["V4"], "buyable": 0, "risk": 4}}
    r = _decide(d13_config, "P05", funds=funds)                     # ceiling 3
    assert [c.rule_id for c in _rejected(r)["fund:V4"].failed] == [
        "not_buyable", "risk_ceiling", "liquidity_need"]


@pytest.mark.parametrize("pid", PERSONA_IDS)
def test_valid_results_and_rejected_never_listed(d13_config, pid):
    r = _decide(d13_config, pid)
    assert isinstance(r, DecisionResult) and r.state == DecisionState.READY
    assert DecisionResult.from_dict(r.to_dict()) == r
    assert not _ids(r) & set(_rejected(r))
