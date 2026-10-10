"""Penalty underperformance and the positions 11-20 cap with diversity
(docs/decision.md 4.3 and 4.5; milestone D10)."""

import dataclasses
import math
from types import SimpleNamespace

import pytest

from rmprep.contracts import DecisionResult, DecisionState, ProductOption, ScoredOption
from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.confidence import stability
from rmprep.decision.engine import decide
from rmprep.decision.notes import build_warnings
from rmprep.decision.persona import read_persona
from rmprep.decision.scoring import (
    display_order,
    option_features,
    penalty_maxima,
    score_options,
)
from rmprep.decision.universe import build_universe
from tests.decision.conftest import (
    D10_TEXTS,
    MARKET,
    PERSONA_IDS,
    T0,
    add_d10,
    d9_rows,
    load_evidence,
    load_persona,
    make_evidence,
    market_row,
)

B_NET = 0.4382 * (1 - 0.175)            # market rate net of the deposit stopaj: 36.15 %
FUNDS = {
    # 3y 33.1 % = 10 % a year; 1y 10 %: N = 10 % x (1 - 10 % stopaj) = 9 %
    "TEN": dict(kind="debt", risk=2, returns={"1y": 10.0, "3y": 33.1}, size=2e8, investors=500),
    # about 30 % a year (3y 119.7 %), money market stopaj 17.5 %: N about 24.8 %
    "THR": dict(kind="money_market", risk=1, returns={"1y": 30.0, "3y": 119.7},
                size=2e8, investors=500),
}


def _ev(market=43.82, **kw):
    extra = d9_rows(**kw) + ([market_row(market)] if market is not None else [])
    return make_evidence(FUNDS, extra=extra)


def _features(cfg, pid, **kw):
    lv = read_persona(load_persona(pid), cfg).levels
    feats, _ = option_features(build_universe(_ev(**kw), cfg), lv, cfg)
    return {f.option.option_id: f for f in feats}


def _rows(cfg, pid, **kw):
    lv = read_persona(load_persona(pid), cfg).levels
    return {s.option.option_id: s for s in
            score_options(build_universe(_ev(**kw), cfg), lv, cfg).scored}


# --- config ---------------------------------------------------------------------------

def test_d10_config_is_valid(d10_config):
    assert d10_config.raw["underperformance"]["scale"] == 0.20


def test_d10_config_is_optional(config):
    assert "underperformance" not in config.raw["penalties"]
    assert "pool" not in config.raw["display"]


@pytest.mark.parametrize("edit,match", [
    (lambda r: r.pop("underperformance"), "underperformance"),
    (lambda r: r["underperformance"].update(scale=0), "underperformance.scale"),
    (lambda r: r["underperformance"].update(other=1), "underperformance"),
    (lambda r: r["penalties"].update(underperformance=-1), "penalties.underperformance"),
    (lambda r: r["texts"]["reasons"].pop("penalty:underperformance"), "underperformance"),
    (lambda r: r["texts"]["data_quality"].pop("benchmark_missing"), "benchmark_missing"),
    (lambda r: r["display"].update(pool=5), "display.pool"),
    (lambda r: r["display"].update(diversity_pool_cap=0), "diversity_pool_cap"),
    (lambda r: r["display"].pop("diversity_pool_cap"), "display"),
])
def test_bad_d10_config_is_an_error(d10_raw, edit, match):
    edit(d10_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(d10_raw)


# --- the penalty by hand -----------------------------------------------------------------

def test_p03_fund_at_10_percent_gets_the_full_penalty(d10_config):
    f = _features(d10_config, "P03")["fund:TEN"]               # Agresif: appetite 1
    assert f.net_return == pytest.approx(0.09)
    assert f.factors["underperformance"] == pytest.approx(1.0)  # (36.15 - 9) / 20 > 1
    row = _rows(d10_config, "P03")["fund:TEN"]
    assert row.parts["penalty:underperformance"] == pytest.approx(-0.3)


def test_p02_gets_two_thirds(d10_config):
    row = _rows(d10_config, "P02")["fund:TEN"]                 # Dengeli: appetite 2/3
    assert row.parts["penalty:underperformance"] == pytest.approx(-0.2)


def test_muhafazakar_gets_no_penalty(d10_config):
    row = _rows(d10_config, "P01")["fund:TEN"]                 # appetite 0
    assert "penalty:underperformance" not in row.parts


def test_partial_violation(d10_config):
    f = _features(d10_config, "P03")["fund:THR"]
    n = f.net_return
    assert f.factors["underperformance"] == pytest.approx((B_NET - n) / 0.20)
    assert 0 < f.factors["underperformance"] < 1


def test_option_above_the_benchmark_has_no_penalty(d10_config):
    f = _features(d10_config, "P03")
    # the Turuncu deposit (23 % -> 18.98 %) is below the benchmark; nothing is above
    # it in FUNDS, so check with a lower market rate
    low = _features(d10_config, "P03", market=10.0)
    assert low["fund:TEN"].factors["underperformance"] == 0.0
    assert f["deposit:ing_turuncu"].factors["underperformance"] > 0


def test_benchmark_without_real_return_is_the_gross_rate(raw):
    cfg = parse_config(add_d10(raw))                           # no D9: nominal returns
    f = _features(cfg, "P02")["fund:TEN"]                      # 1y: annual 10 %
    assert f.factors["underperformance"] == pytest.approx(
        (2 / 3) * min(1.0, (0.4382 - 0.10) / 0.20))


def test_missing_deposit_stopaj_uses_the_gross_benchmark(d10_config):
    f = _features(d10_config, "P03", deposit=None)["fund:THR"]
    assert f.factors["underperformance"] == pytest.approx((0.4382 - f.net_return) / 0.20)


def test_reason_and_parts(d10_config):
    row = _rows(d10_config, "P03")["fund:TEN"]
    assert row.reasons["penalty:underperformance"].startswith(
        "Stopaj sonrası getiri %9.0, piyasa mevduat ortalamasının (stopaj sonrası %36.2)")
    assert math.isclose(sum(row.parts.values()), row.score, abs_tol=1e-12)
    assert list(penalty_maxima(d10_config))[-3:] == ["real_loss", "underperformance",
                                                      "fund_size"]


def test_benchmark_row_is_evidence(d10_config):
    f = _features(d10_config, "P03")["fund:TEN"]
    market = market_row()
    assert market.id in f.evidence_ids


def test_missing_benchmark_no_penalty_and_a_note(d10_config):
    f = _features(d10_config, "P03", market=None)["fund:TEN"]
    assert f.factors["underperformance"] == 0.0
    r = decide(_ev(market=None), load_persona("P03"), d10_config, created_at=T0)
    msg = D10_TEXTS["data_quality"]["benchmark_missing"].format(entity=MARKET)
    assert msg in [n.message for n in r.data_quality]
    r2 = decide(_ev(), load_persona("P03"), d10_config, created_at=T0)
    assert msg not in [n.message for n in r2.data_quality]


def test_stability_counts_the_new_penalty(d10_config):
    lv = read_persona(load_persona("P03"), d10_config).levels
    feats, _ = option_features(build_universe(_ev(), d10_config), lv, d10_config)
    for v in stability(feats, lv, d10_config).values():     # 2 x (7 + 8) runs
        assert v * 30 == pytest.approx(round(v * 30))


@pytest.mark.parametrize("pid", PERSONA_IDS)
def test_valid_results(d10_config, pid):
    ev = load_evidence()
    ev = dataclasses.replace(ev, datapoints=tuple(ev.datapoints) + tuple(d9_rows()))
    r = decide(ev, load_persona(pid), d10_config, created_at=T0)
    assert isinstance(r, DecisionResult) and r.state == DecisionState.READY
    assert DecisionResult.from_dict(r.to_dict()) == r


# --- positions 11-20 with diversity ---------------------------------------------------------

def _row(oid, kind, score):
    return SimpleNamespace(option=ProductOption(option_id=oid, kind="fund", label=oid,
                                                fund_kind=kind), score=score)


def _rows_by_kind(counts):
    """kinds a, b, c, ... with the given counts; every option of a kind scores
    higher than every option of the next kind."""
    rows = []
    for k, (kind, n) in enumerate(zip(["debt", "equity", "mixed", "variable",
                                       "fund_of_funds", "participation"], counts)):
        rows += [_row(f"f:{kind}{i}", kind, 1 - k / 10 - i / 100) for i in range(n)]
    return rows


def _ids(order):
    return [r.option.option_id for r in order.rows]


def test_diversity_caps_positions_11_to_20_at_4(d10_config):
    o = display_order(_rows_by_kind([6, 6, 6, 6, 6]), diversity=True, config=d10_config)
    ids = _ids(o)
    assert ids[10:20] == ["f:debt2", "f:debt3", "f:equity2", "f:equity3", "f:mixed2",
                          "f:mixed3", "f:variable2", "f:variable3", "f:fund_of_funds2",
                          "f:fund_of_funds3"]
    assert ids[20:22] == ["f:debt4", "f:debt5"]
    for kind in ("debt", "equity", "mixed", "variable", "fund_of_funds"):
        assert sum(1 for i in ids[:20] if i.startswith(f"f:{kind}")) <= 4
    assert o.concentration == ()


def test_without_diversity_the_order_does_not_change(d10_config, config):
    rows = _rows_by_kind([6, 6, 6, 6, 6])
    assert _ids(display_order(rows, diversity=False, config=d10_config)) == \
        _ids(display_order(rows, diversity=False, config=config))


def test_without_pool_config_diversity_is_as_before(config):
    ids = _ids(display_order(_rows_by_kind([6, 6, 6, 6, 6]), diversity=True, config=config))
    assert ids[10:14] == ["f:debt2", "f:debt3", "f:debt4", "f:debt5"]


def test_pool_cap_that_cannot_be_met_raises_concentration(d10_config):
    o = display_order(_rows_by_kind([6, 6, 6, 2, 2]), diversity=True, config=d10_config)
    ids = _ids(o)
    assert ids[:10] == ["f:debt0", "f:equity0", "f:mixed0", "f:debt1", "f:equity1",
                        "f:mixed1", "f:variable0", "f:variable1", "f:fund_of_funds0",
                        "f:fund_of_funds1"]
    assert ids[10:16] == ["f:debt2", "f:debt3", "f:equity2", "f:equity3", "f:mixed2",
                          "f:mixed3"]
    assert ids[16:20] == ["f:debt4", "f:debt5", "f:equity4", "f:equity5"]
    assert dict(o.concentration) == {"debt": 6, "equity": 6}
    assert o.concentration_n == 20


def _scored(row):
    return ScoredOption(option=row.option, score=row.score, score_parts={"return": row.score},
                        constraints=(), confidence=0.9, stability=1.0,
                        reasons={"return": "r"})


def test_pool_concentration_warning(d10_config):
    order = display_order(_rows_by_kind([6, 6, 6, 2, 2]), diversity=True, config=d10_config)
    options = tuple(_scored(r) for r in order.rows)
    lv = read_persona(load_persona("P04"), d10_config).levels          # diversity
    ws = [w for w in build_warnings(options, lv, (), load_evidence(), d10_config)
          if w.code == "concentration"]
    assert {w.message.split(":")[0] for w in ws} == {"İlk 20 seçenek yeterince "
                                                     "çeşitlendirilemedi"}
    assert {o for w in ws for o in w.option_ids} == {
        *(f"f:debt{i}" for i in range(6)), *(f"f:equity{i}" for i in range(6))}
