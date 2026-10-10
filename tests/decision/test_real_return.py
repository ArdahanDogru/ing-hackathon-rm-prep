"""Real return after tax, real_loss, long horizon and deposit quality
(docs/decision.md 4.1b, 4.2, 4.3; milestone D9)."""

import math

import pytest

from rmprep.contracts import DecisionResult, DecisionState
from rmprep.decision.confidence import stability
from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.engine import decide
from rmprep.decision.persona import read_persona
from rmprep.decision.scoring import (
    normalize_weights,
    option_features,
    percentile_rank,
    raw_weights,
    score_options,
)
from rmprep.decision.universe import build_universe
from tests.decision.conftest import (
    CPI,
    D9_TEXTS,
    PERSONA_IDS,
    STOPAJ,
    T0,
    d9_rows,
    load_persona,
    make_evidence,
)

DEP_ID = "deposit:ing_turuncu"
TD_ID = "time_deposit:ing_e_vadeli"
FUNDS = {
    "MMF": dict(kind="money_market", risk=1, returns={"1y": 50.0, "3y": 200.0},
                size=2e8, investors=500),
    "DBF": dict(kind="debt", risk=2, returns={"1y": 20.0, "3y": 80.0}, size=2e8, investors=500),
    "NEG": dict(kind="mixed", risk=2, returns={"1y": -10.0, "3y": 10.0}, size=2e8,
                investors=500),
}
CPI_V = 0.2973


def _ev(**kw):
    rows = kw.pop("rows", None)
    return make_evidence(FUNDS, time_deposit=35.0, extra=d9_rows(**kw) if rows is None else rows)


def _features(cfg, pid="P01", **kw):
    lv = read_persona(load_persona(pid), cfg).levels
    feats, _ = option_features(build_universe(_ev(**kw), cfg), lv, cfg)
    return {f.option.option_id: f for f in feats}


def _rows(cfg, pid="P01", **kw):
    lv = read_persona(load_persona(pid), cfg).levels
    r = score_options(build_universe(_ev(**kw), cfg), lv, cfg)
    return {s.option.option_id: s for s in r.scored}


# --- config ---------------------------------------------------------------------------

def test_d9_config_is_valid(d9_config):
    assert d9_config.raw["real_return"]["loss_scale"] == 0.10


def test_d9_config_is_optional(config):
    for key in ("real_return", "long_horizon", "quality_value"):
        assert key not in config.raw
    assert "real_loss" not in config.raw["penalties"]


@pytest.mark.parametrize("path", [
    ("real_return", "cpi", "entity"),
    ("real_return", "stopaj", "fund_default"),
    ("real_return", "loss_scale"),
    ("long_horizon", "return_add"),
    ("quality_value", "deposit"),
])
def test_missing_key_is_an_error(d9_raw, path):
    d = d9_raw
    for k in path[:-1]:
        d = d[k]
    del d[path[-1]]
    with pytest.raises(ConfigError, match=path[-2] if len(path) > 1 else path[0]):
        parse_config(d9_raw)


@pytest.mark.parametrize("edit,match", [
    (lambda r: r["real_return"]["stopaj"]["fund_by_kind"].update(gold="x"), "fund_by_kind"),
    (lambda r: r["real_return"].update(loss_scale=0), "loss_scale"),
    (lambda r: r["long_horizon"].update(period="10y"), "long_horizon"),
    (lambda r: r["long_horizon"].update(liquidity_factor=-1), "long_horizon"),
    (lambda r: r["quality_value"].update(deposit=1.5), "quality_value"),
    (lambda r: r["time_deposit"].update(term_days=0), "term_days"),
    (lambda r: r["penalties"].update(real_loss=-0.1), "real_loss"),
    (lambda r: r["texts"]["reasons"].pop("return_real"), "return_real"),
    (lambda r: r["texts"]["reasons"].pop("penalty:real_loss"), "real_loss"),
    (lambda r: r["texts"]["data_quality"].pop("stopaj_missing"), "stopaj_missing"),
    (lambda r: r["texts"]["assumptions"].pop("real_return_cpi"), "real_return_cpi"),
])
def test_bad_d9_config_is_an_error(d9_raw, edit, match):
    edit(d9_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(d9_raw)


# --- net and real return by hand --------------------------------------------------------

def test_turuncu_is_minus_8_3_percent_real(d9_config):
    f = _features(d9_config)[DEP_ID]
    assert f.net_return == pytest.approx(0.23 * (1 - 0.175))
    r = (1 + 0.23 * 0.825) / (1 + CPI_V) - 1
    assert f.real_return == pytest.approx(r)
    assert round(r * 100, 1) == -8.3
    # P01: principal level 1 -> real_loss = 0.3 x 1 x 0.829
    assert f.factors["real_loss"] == pytest.approx(-r / 0.10)
    row = _rows(d9_config)[DEP_ID]
    assert row.parts["penalty:real_loss"] == pytest.approx(-0.3 * 1.0 * (-r / 0.10))
    assert row.parts["penalty:real_loss"] == pytest.approx(-0.3 * 0.829, abs=1e-3)


def test_real_loss_intensity_is_the_principal_level(d9_config):
    f = _features(d9_config, "P02")[DEP_ID]          # anapara Orta -> 0.5
    r = (1 + 0.23 * 0.825) / (1 + CPI_V) - 1
    assert f.factors["real_loss"] == pytest.approx(0.5 * -r / 0.10)


def test_time_deposit_compounds_every_term(d9_config):
    f = _features(d9_config)[TD_ID]
    d = 32
    n = (1 + 0.35 * 0.85 * d / 365) ** (365 / d) - 1
    assert f.net_return == pytest.approx(n)
    assert f.real_return == pytest.approx((1 + n) / (1 + CPI_V) - 1)


def test_fund_stopaj_by_kind_and_default(d9_config):
    f = _features(d9_config)
    assert f["fund:MMF"].net_return == pytest.approx(0.5 * (1 - 0.175))
    assert f["fund:DBF"].net_return == pytest.approx(0.2 * (1 - 0.10))
    assert f["fund:DBF"].real_return == pytest.approx(1.18 / (1 + CPI_V) - 1)


def test_no_stopaj_on_a_loss(d9_config):
    f = _features(d9_config)["fund:NEG"]
    assert f.net_return == pytest.approx(-0.10)
    assert f.real_return == pytest.approx(0.9 / (1 + CPI_V) - 1)
    assert f.factors["real_loss"] == 1.0                 # -r > loss_scale -> clamped


def test_positive_real_return_has_no_real_loss(d9_config):
    row = _rows(d9_config)["fund:MMF"]
    assert "penalty:real_loss" not in row.parts


def test_return_value_is_the_percentile_of_the_real_return(d9_config):
    f = _features(d9_config)
    reals = [x.real_return for x in f.values() if x.real_return is not None]
    for x in f.values():
        assert x.values["return"] == pytest.approx(percentile_rank(x.real_return, reals))


def test_return_reason_shows_r_n_and_real(d9_config):
    row = _rows(d9_config)[DEP_ID]
    assert row.reasons["return"].startswith("Yıllık getiri %23.0, stopaj sonrası %19.0, "
                                            "enflasyon sonrası reel %-8.3")
    assert row.reasons["penalty:real_loss"].startswith("Enflasyon sonrası reel kayıp %8.3")


def test_parts_add_up(d9_config):
    for row in _rows(d9_config).values():
        assert math.isclose(sum(row.parts.values()), row.score, abs_tol=1e-12)
        assert set(row.reasons) == set(row.parts)


# --- missing CPI / stopaj ------------------------------------------------------------------

def test_missing_cpi_uses_the_net_return_and_no_real_loss(d9_config):
    f = _features(d9_config, cpi=None)
    dep = f[DEP_ID]
    assert dep.real_return is None
    assert dep.net_return == pytest.approx(0.23 * 0.825)
    assert dep.factors["real_loss"] == 0.0
    nets = [x.net_return for x in f.values()]
    assert dep.values["return"] == pytest.approx(percentile_rank(dep.net_return, nets))
    row = _rows(d9_config, cpi=None)[DEP_ID]
    assert "penalty:real_loss" not in row.parts
    assert "reel getiri hesaplanmadı" in row.reasons["return"]


def test_missing_cpi_note_and_assumption(d9_config):
    r = decide(_ev(cpi=None), load_persona("P01"), d9_config, created_at=T0)
    assert [n for n in r.data_quality if CPI in n.message]
    assert D9_TEXTS["assumptions"]["real_return_no_cpi"] in r.assumptions


def test_missing_stopaj_is_0_with_a_note(d9_config):
    f = _features(d9_config, fund_default=None)
    assert f["fund:DBF"].net_return == pytest.approx(0.20)
    assert f["fund:DBF"].stopaj_missing
    r = decide(_ev(fund_default=None), load_persona("P01"), d9_config, created_at=T0)
    [n] = [n for n in r.data_quality if STOPAJ["fund_default"] in n.message]
    assert "2 seçenek" in n.message                      # DBF and NEG (MMF has its own row)


def test_stopaj_and_cpi_rows_are_evidence(d9_config):
    f = _features(d9_config)[DEP_ID]
    quantities = {row.quantity for row in f.rows.values()}
    assert {"cpi_annual", "withholding_tax_rate", "deposit_rate"} <= quantities
    assert len(f.evidence_ids) == 3


# --- weights and quality ---------------------------------------------------------------------

def test_return_weight_2_plus_2_appetite(d9_config):
    raw = raw_weights(read_persona(load_persona("P01"), d9_config).levels, d9_config)
    assert raw["return"] == 2.0                          # appetite 0, horizon 1y


def test_long_horizon_weights(d9_config, config):
    lv = read_persona(load_persona("P04"), d9_config).levels      # 5+ yıl -> 3y
    raw = raw_weights(lv, d9_config)
    assert raw["liquidity"] == pytest.approx(2 * 0.5 * 0.5)       # 2 x Orta x 0.5
    assert raw["return"] == pytest.approx(2 + 2 * (2 / 3) + 1)
    assert raw_weights(lv, config)["liquidity"] == pytest.approx(1.0)    # no long_horizon
    assert sum(normalize_weights(raw).values()) == pytest.approx(1.0)


def test_long_horizon_not_for_shorter_periods(d9_config):
    lv = read_persona(load_persona("P05"), d9_config).levels      # 1-3 yıl -> 1y
    raw = raw_weights(lv, d9_config)
    assert raw["liquidity"] == pytest.approx(2 * 1.0 + 1)         # level Yüksek + boost


def test_deposit_quality_from_config(d9_config, config):
    assert _features(d9_config)[DEP_ID].values["quality"] == 0.5
    assert _features(d9_config)[TD_ID].values["quality"] == 0.5
    assert _features(config)[DEP_ID].values["quality"] == 1.0


# --- assumptions, stability, decide -----------------------------------------------------------

def test_assumptions_replace_pre_tax_and_no_real_returns(d9_config):
    r = decide(_ev(), load_persona("P01"), d9_config, created_at=T0)
    a = d9_config.raw["texts"]["assumptions"]
    assert a["pre_tax"] not in r.assumptions and a["no_real_returns"] not in r.assumptions
    assert a["real_return_cpi"].format(cpi=29.73, cpi_date="2026-09-30") in r.assumptions
    assert a["stopaj_equity"] in r.assumptions
    assert a["time_deposit_renewal"].format(term_days=32) in r.assumptions
    assert a["past_returns"] in r.assumptions


def test_old_assumptions_without_real_return(config):
    r = decide(_ev(), load_persona("P01"), config, created_at=T0)
    assert config.raw["texts"]["assumptions"]["pre_tax"] in r.assumptions


def test_real_loss_maximum_is_perturbed_too(d9_config):
    lv = read_persona(load_persona("P01"), d9_config).levels
    feats, _ = option_features(build_universe(_ev(), d9_config), lv, d9_config)
    s = stability(feats, lv, d9_config)
    for v in s.values():                                 # 2 x (7 weights + 7 maxima) runs
        assert v * 28 == pytest.approx(round(v * 28))


@pytest.mark.parametrize("pid", PERSONA_IDS)
def test_valid_results_with_the_new_rows(d9_config, pid):
    r = decide(_ev(), load_persona(pid), d9_config, created_at=T0)
    assert isinstance(r, DecisionResult) and r.state == DecisionState.READY
    assert DecisionResult.from_dict(r.to_dict()) == r
    assert not [n for n in r.data_quality if "TÜFE" in n.message or "Stopaj" in n.message]
