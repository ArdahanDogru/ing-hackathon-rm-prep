"""Fund detail rows (TEFAS detail page): hard rule not_buyable, liquidity from the
sell valör, entry and exit fees in the net return (docs/decision.md section 2
and the D12 row of section 8)."""

import copy
import dataclasses
import math

import pytest

from rmprep.contracts import DecisionResult, DecisionState
from rmprep.decision.confidence import confidence
from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.engine import decide
from rmprep.decision.persona import read_persona
from rmprep.decision.scoring import option_features, score_options
from rmprep.decision.universe import build_universe
from tests.decision.conftest import (
    D12_TEXTS,
    PERSONA_IDS,
    T0,
    add_d9,
    add_d10,
    d9_rows,
    load_persona,
    make_evidence,
    market_row,
)

BASE = dict(size=2e8, investors=500)
FUNDS = {
    "MMF": dict(kind="money_market", risk=1, returns={"1y": 50.0, "3y": 200.0}, buyable=1,
                sell_valor=0, **BASE),
    "CLO": dict(kind="debt", risk=2, returns={"1y": 30.0, "3y": 100.0}, buyable=0,
                sell_valor=1, **BASE),
    "NOS": dict(kind="debt", risk=2, returns={"1y": 30.0, "3y": 100.0}, **BASE),   # no detail
    "EQ4": dict(kind="equity", risk=5, returns={"1y": 40.0, "3y": 150.0}, buyable=1,
                sell_valor=4, **BASE),
    "FEE": dict(kind="money_market", risk=1, returns={"1y": 50.0, "3y": 200.0}, buyable=1,
                sell_valor=1, entry_fee=1.0, exit_fee=2.0, **BASE),
}


def _ev(funds=FUNDS):
    return make_evidence(funds, time_deposit=35.0, extra=d9_rows() + [market_row()])


def _scoring(cfg, pid="P04", funds=FUNDS):
    lv = read_persona(load_persona(pid), cfg).levels
    return score_options(build_universe(_ev(funds), cfg), lv, cfg)


def _features(cfg, pid="P04", funds=FUNDS):
    lv = read_persona(load_persona(pid), cfg).levels
    feats, rejected = option_features(build_universe(_ev(funds), cfg), lv, cfg)
    return {f.option.option_id: f for f in feats}, {r.option.option_id: r for r in rejected}


def _row_id(quantity, code):
    return next(d.id for d in _ev().datapoints if d.quantity == quantity and d.entity == code)


# --- config -------------------------------------------------------------------------------

def test_d12_config_is_valid_and_optional(d12_config, config):
    assert d12_config.raw["fund_detail"]["buyable_quantity"] == "fund_buyable"
    assert "fund_detail" not in config.raw


@pytest.mark.parametrize("edit,match", [
    (lambda r: r["fund_detail"].pop("sell_valor_quantity"), "fund_detail"),
    (lambda r: r["fund_detail"].update(other=1), "fund_detail"),
    (lambda r: r["fund_detail"]["liquidity_by_sell_valor"][-1].update(max_days=20),
     "liquidity_by_sell_valor"),
    (lambda r: r["fund_detail"]["liquidity_by_sell_valor"][1].update(max_days=0),
     "liquidity_by_sell_valor"),
    (lambda r: r["fund_detail"]["liquidity_by_sell_valor"][0].update(value=1.5),
     "liquidity_by_sell_valor"),
    (lambda r: r["texts"]["constraint"].pop("not_buyable"), "not_buyable"),
    (lambda r: r["texts"]["reasons"].pop("liquidity_valor"), "liquidity_valor"),
    (lambda r: r["texts"]["reasons"].pop("fees"), "fees"),
    (lambda r: r["texts"]["data_quality"].pop("buyable_missing"), "buyable_missing"),
])
def test_bad_d12_config_is_an_error(d12_raw, edit, match):
    edit(d12_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(d12_raw)


# --- (a) not_buyable ------------------------------------------------------------------------

def test_not_buyable_fund_is_rejected(d12_config):
    r = _scoring(d12_config)
    rejected = {x.option.option_id: x for x in r.rejected}
    [c] = rejected["fund:CLO"].failed
    assert c.rule_id == "not_buyable" and not c.passed
    assert c.reason == D12_TEXTS["constraint"]["not_buyable"]
    assert c.evidence_ids == (_row_id("fund_buyable", "CLO"),)
    assert "fund:CLO" not in {s.option.option_id for s in r.scored}


def test_a_fund_can_fail_both_rules(d12_config):
    r = _scoring(d12_config, "P01", {**FUNDS, "EQ4": {**FUNDS["EQ4"], "buyable": 0}})
    [eq] = [x for x in r.rejected if x.option.option_id == "fund:EQ4"]
    assert [c.rule_id for c in eq.failed] == ["not_buyable", "risk_ceiling"]


def test_buyable_fund_carries_the_passed_rule(d12_config):
    r = _scoring(d12_config)
    mmf = next(s for s in r.scored if s.option.option_id == "fund:MMF")
    assert [c.rule_id for c in mmf.constraints] == ["not_buyable", "risk_ceiling"]
    assert mmf.constraints[0].passed
    assert mmf.constraints[0].evidence_ids == (_row_id("fund_buyable", "MMF"),)


def test_missing_status_is_not_rejected_and_counted(d12_config):
    r = _scoring(d12_config)
    nos = next(s for s in r.scored if s.option.option_id == "fund:NOS")
    assert [c.rule_id for c in nos.constraints] == ["risk_ceiling"]
    res = decide(_ev(), load_persona("P04"), d12_config, created_at=T0)
    msg = D12_TEXTS["data_quality"]["buyable_missing"].format(count=1)
    assert msg in [n.message for n in res.data_quality]


def test_without_config_nothing_is_rejected_for_status(d10_config):
    r = _scoring(d10_config)
    assert "fund:CLO" in {s.option.option_id for s in r.scored}


# --- (b) liquidity from the sell valör ---------------------------------------------------------

@pytest.mark.parametrize("days,value", [
    (0, 1.0), (1, 0.9), (2, 0.8), (3, 0.7), (4, 0.6), (5, 0.6), (6, 0.4), (10, 0.4), (11, 0.2),
])
def test_valor_table(d12_config, days, value):
    funds = {"V": dict(kind="equity", risk=3, returns={"3y": 100.0}, buyable=1,
                       sell_valor=days, **BASE)}
    f, _ = _features(d12_config, funds=funds)
    assert f["fund:V"].values["liquidity"] == value


def test_missing_valor_uses_the_kind_table(d12_config):
    f, _ = _features(d12_config)
    assert f["fund:NOS"].values["liquidity"] == d12_config.raw["kinds"]["debt"]["liquidity"]


def test_valor_reason_and_penalty(d12_config):
    rows = {s.option.option_id: s for s in _scoring(d12_config, "P05").scored}  # liquidity 1
    fee = rows["fund:FEE"]
    assert fee.reasons["liquidity"] == "Satış valörü 1 gün; likidite 0.9."
    assert fee.parts["penalty:liquidity"] == pytest.approx(-0.3 * 1.0 * (1 - 0.9))
    nos = rows["fund:NOS"]
    assert nos.reasons["liquidity"].startswith("Likidite (ürün türüne göre)")


def test_valor_row_is_evidence(d12_config):
    f, _ = _features(d12_config)
    assert _row_id("fund_sell_valor_days", "MMF") in f["fund:MMF"].evidence_ids


def test_deposits_keep_the_kind_table(d12_config):
    f, _ = _features(d12_config)
    assert f["deposit:ing_turuncu"].values["liquidity"] == 1.0
    assert f["time_deposit:ing_e_vadeli"].values["liquidity"] == 0.6


# --- (c) fees ----------------------------------------------------------------------------------

def test_fees_reduce_n_over_the_horizon_years(d12_config):
    f1, _ = _features(d12_config, "P01")                 # 1y horizon
    assert f1["fund:FEE"].net_return == pytest.approx(0.5 * 0.825 - 0.03)
    assert f1["fund:MMF"].net_return == pytest.approx(0.5 * 0.825)
    f3, _ = _features(d12_config, "P04")                 # 3y horizon
    annual = 3 ** (1 / 3) - 1
    assert f3["fund:FEE"].net_return == pytest.approx(annual * 0.825 - 0.03 / 3)


def test_fees_reach_the_real_return(d12_config):
    f, _ = _features(d12_config, "P01")
    n = 0.5 * 0.825 - 0.03
    assert f["fund:FEE"].real_return == pytest.approx((1 + n) / 1.2973 - 1)


def test_fee_reason_and_evidence(d12_config):
    rows = {s.option.option_id: s for s in _scoring(d12_config, "P01").scored}
    assert rows["fund:FEE"].reasons["return"].endswith(
        "Giriş + çıkış komisyonu %3.00, 1 yıla yayılarak getiriden düşüldü.")
    assert "komisyon" not in rows["fund:MMF"].reasons["return"]
    assert _row_id("fund_entry_fee", "FEE") in rows["fund:FEE"].evidence_ids
    assert _row_id("fund_exit_fee", "FEE") in rows["fund:FEE"].evidence_ids


def test_parts_add_up(d12_config):
    for s in _scoring(d12_config, "P05").scored:
        assert math.isclose(sum(s.parts.values()), s.score, abs_tol=1e-12)
        assert set(s.reasons) == set(s.parts)


@pytest.mark.parametrize("pid", PERSONA_IDS)
def test_valid_results(d12_config, pid):
    r = decide(_ev(), load_persona(pid), d12_config, created_at=T0)
    assert isinstance(r, DecisionResult) and r.state == DecisionState.READY
    assert DecisionResult.from_dict(r.to_dict()) == r
    assert "fund:CLO" not in {o.option.option_id for o in r.options}


def test_kind_proxy_assumption_is_replaced(d12_config, raw_config):
    a = d12_config.raw["texts"]["assumptions"]
    r = decide(_ev(), load_persona("P04"), d12_config, created_at=T0)
    assert a["kind_proxy_valor"] in r.assumptions and a["kind_proxy"] not in r.assumptions
    d10 = parse_config(add_d10(add_d9(copy.deepcopy(raw_config))))      # its own copy
    r10 = decide(_ev(), load_persona("P04"), d10, created_at=T0)
    assert a["kind_proxy"] in r10.assumptions


# --- D14: confidence of a fund whose liquidity is the kind proxy --------------------------------

@pytest.fixture
def d14_config(d12_raw):
    d12_raw["confidence"]["liquidity_proxy"] = 0.8
    return parse_config(d12_raw)


def test_liquidity_proxy_factor(d14_config):
    f, _ = _features(d14_config)
    # MMF: valör row (needs_check 0.9), no factor; NOS: no detail rows, unflagged rows
    # (1.0), liquidity from the kind table -> x 0.8
    assert confidence(f["fund:MMF"], d14_config) == pytest.approx(0.9)
    assert confidence(f["fund:NOS"], d14_config) == pytest.approx(0.8)


def test_liquidity_proxy_is_optional(d12_config):
    f, _ = _features(d12_config)
    assert confidence(f["fund:NOS"], d12_config) == pytest.approx(1.0)


@pytest.mark.parametrize("value", [-0.1, 1.5, "x"])
def test_bad_liquidity_proxy_is_an_error(d12_raw, value):
    d12_raw["confidence"]["liquidity_proxy"] = value
    with pytest.raises(ConfigError, match="confidence.liquidity_proxy"):
        parse_config(d12_raw)


@pytest.mark.parametrize("pid", PERSONA_IDS)
def test_excluding_tefas_detail_never_raises_a_confidence(d14_config, pid):
    ev = _ev()
    full = decide(ev, load_persona(pid), d14_config, created_at=T0)
    without = decide(dataclasses.replace(ev, excluded_sources=frozenset({"tefas_detail"})),
                     load_persona(pid), d14_config, created_at=T0)
    before = {o.option.option_id: o.confidence for o in full.options}
    compared = 0
    for o in without.options:
        if o.option.option_id in before:
            assert o.confidence <= before[o.option.option_id] + 1e-12, o.option.option_id
            compared += 1
    assert compared >= 3
