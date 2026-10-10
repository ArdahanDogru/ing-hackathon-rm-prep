"""Criteria, weights, penalties, risk_ceiling, score_parts + reasons and the
display order (docs/decision.md sections 2 and 4)."""

import dataclasses
import math
from types import SimpleNamespace

import pytest

from rmprep.contracts import ProductOption
from rmprep.decision.persona import read_persona
from rmprep.decision.scoring import (
    annualize,
    display_order,
    normalize_weights,
    percentile_rank,
    raw_weights,
    score_options,
)
from rmprep.decision.universe import build_universe
from tests.decision.conftest import (
    PERSONA_IDS,
    load_evidence,
    load_persona,
    make_evidence,
)

SMALL = {
    "MMF": dict(kind="money_market", risk=1, returns={"3y": 100.0, "1y": 30.0},
                size=1e9, investors=5000),
    "EQF": dict(kind="equity", risk=5, returns={"3y": 300.0, "1y": 50.0},
                size=2e8, investors=200),
    "DBF": dict(kind="debt", returns={"1y": 30.0}, size=5e7, investors=50),
}


def _levels(config, pid="P04", **changes):
    lv = read_persona(load_persona(pid), config).levels
    return dataclasses.replace(lv, **changes)


def _score(config, funds=SMALL, levels=None, **kw):
    u = build_universe(make_evidence(funds, **kw), config)
    return score_options(u, levels or _levels(config), config)


# --- helpers ------------------------------------------------------------------------

def test_percentile_rank():
    vals = [1.0, 2.0, 2.0, 3.0]
    assert percentile_rank(1.0, vals) == 0.0
    assert percentile_rank(2.0, vals) == pytest.approx((1 + 0.5) / 3)
    assert percentile_rank(3.0, vals) == 1.0
    assert percentile_rank(5.0, [5.0]) == 1.0


def test_annualize():
    assert annualize(100.0, 3) == pytest.approx(2 ** (1 / 3) - 1)
    assert annualize(10.0, 0.5) == pytest.approx(1.1 ** 2 - 1)


def test_p01_weights_match_the_design_example(config):
    w = normalize_weights(raw_weights(_levels(config, "P01"), config))
    assert {k: round(v, 2) for k, v in w.items()} == {
        "income": 0.29, "low_risk": 0.19, "liquidity": 0.19, "principal": 0.19,
        "return": 0.10, "simplicity": 0.0, "quality": 0.05}
    assert sum(w.values()) == pytest.approx(1.0)


def test_no_liquidity_need_sets_the_liquidity_weight_to_0(config):
    raw = raw_weights(_levels(config, "P03"), config)
    assert raw["liquidity"] == 0.0
    assert raw["return"] == pytest.approx(2.0 + 2.0)     # 1 + appetite 1, two boosts


def test_simplicity_boost(config):
    assert raw_weights(_levels(config, "P05"), config)["simplicity"] == 1.0


# --- hand-computed scores (P04 levels) -------------------------------------------------
# raw weights: return 1+2/3, low_risk 1-2/3+1 (boost), liquidity 1, income 1,
# principal 1, simplicity 0, quality 0.5; sum 6.5.
W = {"return": 5 / 3, "low_risk": 4 / 3, "liquidity": 1.0, "income": 1.0, "principal": 1.0,
     "quality": 0.5}
S = 6.5


def _by_id(result):
    return {s.option.option_id: s for s in result.scored}


def test_equity_fund_score_by_hand(config):
    eq = _by_id(_score(config))["fund:EQF"]
    # returns: deposit .23, MMF 2^(1/3)-1, DBF .30 (1y), EQF 4^(1/3)-1 -> EQF best
    values = {"return": 1.0, "low_risk": 1 - 4 / 6, "liquidity": 0.5, "income": 0.2,
              "principal": 0.8 - 0.15 * 4, "quality": 0.5}
    for k, v in values.items():
        assert eq.parts[k] == pytest.approx(W[k] / S * v), k
    assert eq.parts["penalty:principal"] == pytest.approx(-0.3 * 0.5 * 1.0)
    assert eq.parts["penalty:liquidity"] == pytest.approx(-0.3 * 0.5 * 0.5)
    assert set(eq.parts) == set(values) | {"penalty:principal", "penalty:liquidity"}
    expected = sum(W[k] / S * v for k, v in values.items()) - 0.15 - 0.075
    assert eq.score == pytest.approx(expected)
    assert math.isclose(sum(eq.parts.values()), eq.score, abs_tol=1e-12)


def test_fund_without_risk_and_track_record_by_hand(config):
    db = _by_id(_score(config))["fund:DBF"]
    # no debt fund with a known risk -> estimate 7 (> ceiling 5 -> risk_unknown x 2)
    assert db.risk == 7 and db.risk_estimated
    assert db.parts["return"] == pytest.approx(W["return"] / S * 2 / 3)
    assert "low_risk" not in db.parts or db.parts["low_risk"] == 0.0
    assert db.parts["penalty:risk_unknown"] == pytest.approx(-0.6)
    assert db.parts["penalty:track_record"] == pytest.approx(-0.2)
    assert db.parts["penalty:fund_size"] == pytest.approx(-0.1 * 0.5)
    assert db.parts["penalty:principal"] == pytest.approx(-0.15)
    assert db.parts["penalty:liquidity"] == pytest.approx(-0.3 * 0.5 * 0.3)
    assert db.period == "1y" and db.shorter_period


def test_deposit_by_hand(config):
    d = _by_id(_score(config))["deposit:ing_turuncu"]
    values = {"return": 0.0, "low_risk": 1.0, "liquidity": 1.0, "income": 1.0,
              "principal": 1.0, "quality": 1.0}
    assert d.score == pytest.approx(sum(W[k] / S * v for k, v in values.items()))
    assert not [k for k in d.parts if k.startswith("penalty:")]
    assert d.risk == 1 and not d.risk_estimated


def test_risk_estimate_uses_the_highest_known_risk_of_the_kind(config):
    funds = dict(SMALL, DB2=dict(kind="debt", risk=3, returns={"3y": 50.0}, size=2e8,
                                 investors=500),
                 DB3=dict(kind="debt", risk=2, returns={"3y": 50.0}, size=2e8, investors=500))
    db = _by_id(_score(config, funds))["fund:DBF"]
    assert db.risk == 3 and db.risk_estimated
    assert db.parts["penalty:risk_unknown"] == pytest.approx(-0.3)     # 3 <= ceiling 5


def test_risk_estimate_ignores_rejected_funds(config):
    funds = dict(SMALL, DB2=dict(kind="debt", risk=6, returns={"3y": 50.0}))
    r = _score(config, funds)
    assert "fund:DB2" in {x.option.option_id for x in r.rejected}
    assert _by_id(r)["fund:DBF"].risk == 7


def test_fx_penalty(config):
    funds = dict(SMALL, FXF=dict(kind="debt", risk=3, name="X EUROBOND (DOLAR) FONU",
                                 returns={"3y": 100.0}, size=2e8, investors=500))
    fx = _by_id(_score(config, funds, levels=_levels(config, "P01", ceiling=5)))["fund:FXF"]
    assert fx.parts["penalty:fx_exposure"] == pytest.approx(-0.3)
    no = _by_id(_score(config, funds))["fund:FXF"]          # P04: FX level Çeşitlendirilmiş
    assert "penalty:fx_exposure" not in no.parts


def test_shorter_period_for_a_6m_horizon(config):
    funds = {"MMF": dict(kind="money_market", risk=1, returns={"3m": 10.0}, size=1e9,
                         investors=1000)}
    m = _by_id(_score(config, funds, levels=_levels(config, period="6m")))["fund:MMF"]
    assert m.period == "3m" and m.shorter_period
    assert m.annual_return == pytest.approx(1.1 ** 4 - 1)
    assert m.parts["penalty:track_record"] == pytest.approx(-0.2)


def test_fund_without_any_return(config):
    funds = dict(SMALL, NRF=dict(kind="money_market", risk=1, size=1e9, investors=1000))
    n = _by_id(_score(config, funds))["fund:NRF"]
    assert n.period is None and n.annual_return is None
    assert n.parts["return"] == 0.0
    assert n.parts["penalty:track_record"] == pytest.approx(-0.2)
    assert n.reasons["return"] == "Getiri verisi yok (3y ve daha kısa dönemler)."


# --- risk_ceiling -----------------------------------------------------------------------

def test_risk_above_ceiling_is_rejected(config):
    r = _score(config, levels=_levels(config, "P01"))     # ceiling 2
    [rej] = r.rejected
    assert rej.option.option_id == "fund:EQF"
    [c] = rej.failed
    assert c.rule_id == "risk_ceiling" and not c.passed
    assert c.reason == "Risk değeri 5, müşterinin risk tavanı 2 üzerinde."
    risk_row = next(d for d in make_evidence(SMALL).datapoints
                    if d.quantity == "fund_risk_level" and d.entity == "EQF")
    assert c.evidence_ids == (risk_row.id,)
    assert "fund:EQF" not in _by_id(r)


def test_unknown_risk_is_never_rejected(config):
    r = _score(config, levels=_levels(config, "P01"))
    assert "fund:DBF" in _by_id(r)


def test_scored_options_pass_the_risk_ceiling(config):
    for s in _score(config).scored:
        assert s.constraint.rule_id == "risk_ceiling" and s.constraint.passed
    eq = _by_id(_score(config))["fund:EQF"]
    assert eq.constraint.reason == "Risk değeri 5, müşterinin tavanı 5 içinde."


def test_evidence_ids_are_the_rows_used(config):
    ev = make_evidence(SMALL)
    u = build_universe(ev, config)
    eq = _by_id(score_options(u, _levels(config), config))["fund:EQF"]
    used = {d.id for d in ev.datapoints if d.entity == "EQF" and d.quantity in (
        "fund_risk_level", "fund_return_3y", "fund_total_value", "fund_investor_count")}
    assert set(eq.evidence_ids) == used


# --- on evidence_medium -----------------------------------------------------------------

@pytest.mark.parametrize("pid", PERSONA_IDS)
def test_parts_add_up_and_reasons_match_on_real_rows(config, pid):
    lv = read_persona(load_persona(pid), config).levels
    r = score_options(build_universe(load_evidence(), config), lv, config)
    assert r.scored
    for s in r.scored:
        assert math.isclose(sum(s.parts.values()), s.score, abs_tol=1e-9)
        assert set(s.reasons) == set(s.parts)
        assert all(v < 0 for k, v in s.parts.items() if k.startswith("penalty:"))
        assert all(isinstance(t, str) and t for t in s.reasons.values())
    for rej in r.rejected:
        assert rej.failed[0].rule_id == "risk_ceiling"


# --- display order ------------------------------------------------------------------------

def _row(oid, kind, score):
    if kind == "deposit":
        opt = ProductOption(option_id=oid, kind="deposit", label=oid)
    else:
        opt = ProductOption(option_id=oid, kind="fund", label=oid, fund_kind=kind)
    return SimpleNamespace(option=opt, score=score)


def _ids(order):
    return [r.option.option_id for r in order.rows]


def test_deposit_is_first_even_with_a_low_score(config):
    rows = [_row("f:a", "debt", 0.9), _row("d", "deposit", 0.1), _row("f:b", "equity", 0.5)]
    o = display_order(rows, diversity=False, config=config)
    assert _ids(o) == ["d", "f:a", "f:b"]
    assert o.concentration == ()


def test_first_three_have_one_option_per_kind(config):
    rows = [_row("f:a1", "debt", 0.9), _row("f:a2", "debt", 0.8), _row("f:b1", "equity", 0.7),
            _row("f:c1", "mixed", 0.6)]
    assert _ids(display_order(rows, diversity=False, config=config)) == [
        "f:a1", "f:b1", "f:c1", "f:a2"]


def test_positions_1_to_10_have_at_most_3_per_kind(config):
    rows = [_row(f"f:a{i}", "debt", 1 - i / 100) for i in range(6)]
    rows += [_row(f"f:b{i}", "equity", 0.5 - i / 100) for i in range(6)]
    rows += [_row(f"f:c{i}", "mixed", 0.2 - i / 100) for i in range(6)]
    rows += [_row(f"f:d{i}", "variable", 0.1 - i / 100) for i in range(6)]
    o = display_order(rows, diversity=False, config=config)
    ids = _ids(o)
    assert ids[:3] == ["f:a0", "f:b0", "f:c0"]
    assert ids[3:10] == ["f:a1", "f:a2", "f:b1", "f:b2", "f:c1", "f:c2", "f:d0"]
    assert ids[10:13] == ["f:a3", "f:a4", "f:a5"]      # after 10: by score
    assert o.concentration == ()


def test_diversity_cap_is_2(config):
    rows = [_row(f"f:a{i}", "debt", 1 - i / 100) for i in range(6)]
    rows += [_row(f"f:b{i}", "equity", 0.5 - i / 100) for i in range(6)]
    rows += [_row(f"f:c{i}", "mixed", 0.2 - i / 100) for i in range(6)]
    rows += [_row(f"f:d{i}", "variable", 0.1 - i / 100) for i in range(6)]
    rows += [_row(f"f:e{i}", "fund_of_funds", 0.05 - i / 100) for i in range(6)]
    ids = _ids(display_order(rows, diversity=True, config=config))
    assert ids[:10] == ["f:a0", "f:b0", "f:c0", "f:a1", "f:b1", "f:c1", "f:d0", "f:d1",
                        "f:e0", "f:e1"]


def test_too_few_kinds_fill_by_score_and_raise_concentration(config):
    rows = [_row(f"f:a{i}", "debt", 1 - i / 100) for i in range(8)]
    rows += [_row("f:b0", "equity", 0.1)]
    o = display_order(rows, diversity=False, config=config)
    ids = _ids(o)
    assert ids[:2] == ["f:a0", "f:b0"]
    assert ids[2:9] == [f"f:a{i}" for i in range(1, 8)]
    assert dict(o.concentration) == {"debt": 8}


def test_ties_break_by_option_id(config):
    rows = [_row("f:b", "debt", 0.5), _row("f:a", "equity", 0.5), _row("f:c", "mixed", 0.5)]
    assert _ids(display_order(rows, diversity=False, config=config)) == ["f:a", "f:b", "f:c"]


def test_result_rows_follow_the_display_order(config):
    r = _score(config)
    assert r.order.rows[0].option.kind == "deposit"
    assert [s.option.option_id for s in r.order.rows] == _ids(r.order)
    assert len(r.order.rows) == len(r.scored)
