"""Returns of periods shorter than 1 year are not annualised; 5-year share data
(docs/decision.md section 16, D26c)."""

import copy

import pytest

from rmprep.decision.config import parse_config
from rmprep.decision.display import display_facts
from rmprep.decision.engine import decide
from rmprep.decision.exchange import stock_risk
from rmprep.decision.persona import read_persona
from rmprep.decision.scoring import option_features
from rmprep.decision.universe import build_universe
from tests.decision.conftest import CPI, T0, d9_rows, dp, load_persona, make_evidence, market_row
from tests.decision.test_exchange import _ev, add_d26, stock
from tests.decision.test_holdings_class import add_d23

PERIOD_TEXTS = {
    "return_period": "{months} aylık getiri %{nominal:.1f} (yıllıklandırılmadı) ({period}); "
                     "adayların %{pct:.0f}'inden iyi.",
    "return_period_net": "{months} aylık getiri %{nominal:.1f} (yıllıklandırılmadı), stopaj "
                         "sonrası %{net:.1f}; reel getiri hesaplanmadı (TÜFE yok); adayların "
                         "%{pct:.0f}'inden iyi.",
    "return_period_real": "{months} aylık getiri %{nominal:.1f} (yıllıklandırılmadı), stopaj "
                          "sonrası %{net:.1f}, aynı dönemin enflasyonu sonrası reel "
                          "%{real:+.1f}; adayların %{pct:.0f}'inden iyi.",
}
STOCK_RISK_5Y = ("Risk değeri {risk}/7: 5 yıllık oynaklıktan (%{volatility:.1f}) SPK "
                 "yöntemiyle; tek şirket payı için en az {floor}. Sınır {ceiling}/7.")
FULL = dict(size=2e8, investors=500)
CPI_Y = 1.2973 ** 0.5           # 6-month share of the yearly TÜFE (29.73 %)


def add_d26c(raw: dict) -> dict:
    raw["texts"]["reasons"].update(PERIOD_TEXTS)
    raw["texts"]["constraint"]["stock_risk_5y"] = STOCK_RISK_5Y
    return raw


@pytest.fixture
def c_raw(d19_raw) -> dict:
    return add_d26c(add_d26(add_d23(d19_raw)))


@pytest.fixture
def c_config(c_raw):
    return parse_config(c_raw)


def _features(cfg, funds, pid="P01", extra=()):
    ev = make_evidence(funds, extra=[*d9_rows(), *extra])
    lv = read_persona(load_persona(pid), cfg).levels
    feats, _ = option_features(build_universe(ev, cfg), lv, cfg)
    return {f.option.option_id: f for f in feats}


# --- (1) no annualising below 1 year ----------------------------------------------------------

def test_a_6_month_return_is_not_annualised(c_config):
    f = _features(c_config, {"NW": dict(kind="debt", risk=2, returns={"6m": 20.0}, **FULL)})
    nw = f["fund:NW"]
    assert nw.period == "6m" and nw.annual_return == pytest.approx(0.20)   # not 0.44
    assert nw.shorter_period and nw.factors["track_record"] == 1.0
    assert nw.period_years == 0.5
    # stopaj 10 % (fund_default), then the 6-month share of the yearly TÜFE
    assert nw.net_return == pytest.approx(0.18)
    assert nw.real_return == pytest.approx(1.18 / CPI_Y - 1)


def test_a_year_or_longer_is_still_annualised(c_config):
    f = _features(c_config, {"OLD": dict(kind="debt", risk=2, returns={"3y": 100.0}, **FULL),
                             "ONE": dict(kind="debt", risk=2, returns={"1y": 30.0}, **FULL)},
                  pid="P03")
    assert f["fund:OLD"].annual_return == pytest.approx(2 ** (1 / 3) - 1)
    assert f["fund:OLD"].period_years == 1.0
    assert f["fund:ONE"].annual_return == pytest.approx(0.30)          # 1y fallback for 3y
    assert f["fund:ONE"].shorter_period and f["fund:ONE"].period_years == 1.0
    assert f["fund:ONE"].real_return == pytest.approx(1.27 / 1.2973 - 1)


def test_the_horizon_period_itself_is_used_when_it_exists(c_config):
    f = _features(c_config, {"F": dict(kind="debt", risk=2,
                                       returns={"3m": 9.0, "6m": 20.0, "1y": 45.0}, **FULL)})
    assert f["fund:F"].period == "1y" and not f["fund:F"].shorter_period


def test_real_loss_of_a_short_period_is_scaled_to_the_period(c_config):
    # 6m raw 10 %, net 9 %: real = 1.09 / 1.1390 - 1 = -4.30 % over 6 months;
    # P01 principal level 1: factor = 0.0430 / (loss_scale 0.10 x 0.5) = 0.860
    f = _features(c_config, {"L": dict(kind="debt", risk=2, returns={"6m": 10.0}, **FULL)})
    real = 1.09 / CPI_Y - 1
    assert f["fund:L"].factors["real_loss"] == pytest.approx(-real / 0.05)


def test_underperformance_against_the_same_period_of_the_benchmark(c_config):
    # benchmark: market rate 43.82 % net of 17.5 % stopaj, 6-month share
    f = _features(c_config, {"U": dict(kind="debt", risk=2, returns={"6m": 10.0}, **FULL)},
                  pid="P03", extra=[market_row()])
    bench = (1 + 0.4382 * 0.825) ** 0.5 - 1
    u = f["fund:U"]
    assert u.factors["underperformance"] == pytest.approx((bench - 0.09) / (0.20 * 0.5))
    assert u.fields["benchmark"] == pytest.approx(bench * 100)


def test_fees_of_a_short_period_are_the_period_share(d19_raw):
    cfg = parse_config(add_d26c(add_d26(add_d23(d19_raw))))
    f = _features(cfg, {"FE": dict(kind="debt", risk=2, returns={"6m": 20.0}, entry_fee=1.0,
                                   exit_fee=1.0, **FULL)})
    # 2 % over a 1-year horizon = 2 % a year -> 1 % for the 6 months
    assert f["fund:FE"].net_return == pytest.approx(0.18 - 0.01)


def test_the_reason_says_not_annualised(c_config):
    ev = make_evidence({"NW": dict(kind="debt", risk=2, returns={"6m": 20.0}, **FULL),
                        "OK": dict(kind="debt", risk=2, returns={"1y": 40.0}, **FULL)},
                       extra=d9_rows())
    r = decide(ev, load_persona("P01"), c_config, created_at=T0)
    by_id = {o.option.option_id: o for o in r.options}
    text = by_id["fund:NW"].reasons["return"]
    assert text.startswith("6 aylık getiri %20.0 (yıllıklandırılmadı), stopaj sonrası %18.0")
    assert "aynı dönemin enflasyonu sonrası reel %+3.6" in text
    assert by_id["fund:OK"].reasons["return"].startswith("Yıllık getiri %40.0")


def test_the_reason_without_tufe_and_without_real_return(c_raw):
    ev = make_evidence({"NW": dict(kind="debt", risk=2, returns={"3m": 6.0}, **FULL)},
                       extra=d9_rows(cpi=None))
    r = decide(ev, load_persona("P01"), parse_config(c_raw), created_at=T0)
    o = next(o for o in r.options if o.option.option_id == "fund:NW")
    assert o.reasons["return"].startswith("3 aylık getiri %6.0 (yıllıklandırılmadı), stopaj")
    assert "TÜFE yok" in o.reasons["return"]


def test_the_reason_without_the_period_texts_keeps_the_old_text(c_raw):
    for key in PERIOD_TEXTS:
        del c_raw["texts"]["reasons"][key]
    ev = make_evidence({"NW": dict(kind="debt", risk=2, returns={"6m": 20.0}, **FULL)},
                       extra=d9_rows())
    r = decide(ev, load_persona("P01"), parse_config(c_raw), created_at=T0)
    o = next(o for o in r.options if o.option.option_id == "fund:NW")
    assert o.reasons["return"].startswith("Yıllık getiri %20.0")       # no crash


def test_a_share_with_only_6_months_is_not_annualised(c_config):
    # the EFOR case of 2026-10-14: +217 % over 6 months was shown as +906 % a year
    rows, ents = stock("EFOR", returns={"1m": 30.0, "3m": 90.0, "6m": 217.0})
    lv = read_persona(load_persona("P03"), c_config).levels
    feats, _ = option_features(build_universe(_ev((rows, ents)), c_config), lv, c_config)
    f = next(x for x in feats if x.option.option_id == "stock:EFOR")
    assert f.period == "6m" and f.annual_return == pytest.approx(2.17)


def test_the_deposit_is_unchanged(c_config):
    f = _features(c_config, {})
    d = f["deposit:ing_turuncu"]
    assert d.annual_return == pytest.approx(0.23) and d.period_years == 1.0


# --- (2) 5 years of share data ------------------------------------------------------------------

def _stock5(code, vol5=None, ret3y=None, **kw):
    rows, ents = stock(code, **kw)
    if vol5 is not None:
        rows.append(dp("stock_volatility_5y", code, vol5, source="bist_bulletin"))
    if ret3y is not None:
        rows.append(dp("stock_return_3y", code, ret3y, source="bist_bulletin"))
    return rows, ents


def test_stock_return_3y_is_used_for_a_3_year_horizon(c_config):
    ev = _ev(_stock5("THYAO", ret3y=200.0))
    lv = read_persona(load_persona("P03"), c_config).levels
    feats, _ = option_features(build_universe(ev, c_config), lv, c_config)
    f = next(x for x in feats if x.option.option_id == "stock:THYAO")
    assert f.period == "3y" and not f.shorter_period
    assert f.annual_return == pytest.approx(3 ** (1 / 3) - 1)


def test_five_year_volatility_is_used_without_the_estimate_factor(c_config):
    ev = _ev(_stock5("THYAO", vol5=17.0, vol=35.0, ret3y=200.0))
    r = decide(ev, load_persona("P03"), c_config, created_at=T0)
    o = next(o for o in r.options if o.option.option_id == "stock:THYAO")
    [c] = [c for c in o.constraints if c.rule_id == "risk_ceiling"]
    vol5 = next(d for d in ev.datapoints if d.quantity == "stock_volatility_5y")
    assert c.evidence_ids == (vol5.id,)
    assert c.reason == STOCK_RISK_5Y.format(risk=6, volatility=17.0, floor=6, ceiling=7)
    assert o.confidence == pytest.approx(1.0)           # 5-year SPK method, 3y return
    facts = display_facts(r, ev, c_config)["stock:THYAO"]
    assert (facts.risk.value, facts.risk.evidence_id) == (6, vol5.id)


def test_five_year_volatility_keeps_the_floor_and_the_bands(c_config):
    v5 = dp("stock_volatility_5y", "S", 32.0, source="bist_bulletin")
    v1 = dp("stock_volatility_1y", "S", 3.0, source="bist_bulletin")
    assert stock_risk(v1, c_config, v5) == 7               # the 5-year band decides
    assert stock_risk(v1, c_config, dp("stock_volatility_5y", "S", 3.0,
                                       source="bist_bulletin")) == 6   # floor
    assert stock_risk(v1, c_config) == 6


def test_without_five_year_rows_the_one_year_estimate_stays(c_config):
    r = decide(_ev(_stock5("THYAO", vol=25.0)), load_persona("P03"), c_config, created_at=T0)
    o = next(o for o in r.options if o.option.option_id == "stock:THYAO")
    assert o.confidence == pytest.approx(0.7 * 0.8)
    [c] = [c for c in o.constraints if c.rule_id == "risk_ceiling"]
    assert "1 yıllık oynaklıktan" in c.reason


def test_without_the_5y_text_the_1y_text_is_used(c_raw):
    del c_raw["texts"]["constraint"]["stock_risk_5y"]
    r = decide(_ev(_stock5("THYAO", vol5=17.0)), load_persona("P03"), parse_config(c_raw),
               created_at=T0)
    o = next(o for o in r.options if o.option.option_id == "stock:THYAO")
    assert o.confidence == pytest.approx(0.8)               # 1y return for a 3y client


def test_bad_period_text_is_an_error(c_raw):
    c_raw["texts"]["reasons"]["return_period"] = "{weeks} haftalık"
    with pytest.raises(Exception, match="return_period"):
        parse_config(copy.deepcopy(c_raw))
