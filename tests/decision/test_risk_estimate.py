"""Risk estimate by asset class (the D21 row of docs/decision.md section 8)."""

import math

import pytest

from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.engine import decide
from rmprep.decision.persona import read_persona
from rmprep.decision.scoring import class_risk_estimates, option_features
from rmprep.decision.universe import build_universe
from tests.decision.conftest import T0, d9_rows, load_persona, make_evidence, market_row

BASE = dict(size=2e8, investors=500, buyable=1, sell_valor=1)
CLASS_TEXT = ("Risk değeri olmayan fonlarda aynı varlık sınıfındaki bilinen risk değerlerinin "
              "üst çeyreği (yukarı yuvarlanmış) kullanıldı.")
REASON_TEXT = "Risk değeri yok; varlık sınıfının üst çeyreği ({risk}) varsayıldı."


def _gold(code, risk, **kw):
    return dict(kind="precious_metals", name=f"{code} PORTFÖY ALTIN FONU", risk=risk,
                returns={"1y": 20.0, "3y": 100.0}, **BASE, **kw)


FUNDS = {
    # the gold class: known risks 4, 4, 5, 5, 6 -> upper quartile 5
    **{f"G{i}": _gold(f"G{i}", r) for i, r in enumerate([4, 4, 5, 5, 6])},
    # KZL-like: a gold PARTICIPATION fund without a risk row
    "KZL": dict(kind="participation", name="KZL PORTFÖY ALTIN KATILIM FONU",
                returns={"1y": 20.0, "3y": 100.0}, **BASE),
    # the participation umbrella has low risks (the old kind estimate: 2)
    "KP1": dict(kind="participation", name="KP1 PORTFÖY PARA PİYASASI KATILIM FONU", risk=1,
                returns={"1y": 40.0, "3y": 150.0}, **BASE),
    "KP2": dict(kind="participation", name="KP2 PORTFÖY KİRA SERTİFİKASI KATILIM FONU", risk=2,
                returns={"1y": 38.0, "3y": 140.0}, **BASE),
    "MMF": dict(kind="money_market", name="M PORTFÖY PARA PİYASASI FONU", risk=1,
                returns={"1y": 45.0, "3y": 160.0}, **BASE),
    # a debt fund without a risk row: borclanma has fewer than 5 known values
    "DNR": dict(kind="debt", name="D PORTFÖY BORÇLANMA ARAÇLARI FONU",
                returns={"1y": 30.0, "3y": 110.0}, **BASE),
    "DB3": dict(kind="debt", name="E PORTFÖY BORÇLANMA ARAÇLARI FONU", risk=3,
                returns={"1y": 31.0, "3y": 115.0}, **BASE),
}


def _raw(d19_raw, **estimate):
    d19_raw["asset_classes"]["by_name"]["ALTIN"] = "altin_doviz"
    if estimate:
        d19_raw["risk_estimate"] = estimate
    d19_raw["texts"]["assumptions"]["risk_estimate_class"] = CLASS_TEXT
    d19_raw["texts"]["reasons"]["penalty:risk_unknown_class"] = REASON_TEXT
    return d19_raw


@pytest.fixture
def cfg(d19_raw):
    return parse_config(_raw(d19_raw))


def _ev(funds=FUNDS):
    return make_evidence(funds, time_deposit=35.0, extra=d9_rows() + [market_row()])


def _features(config, pid):
    lv = read_persona(load_persona(pid), config).levels
    feats, _ = option_features(build_universe(_ev(), config), lv, config)
    return {f.option.option_id: f for f in feats}


# --- the estimate --------------------------------------------------------------------------------

def test_class_estimates_are_the_upper_quartile_rounded_up(cfg):
    est = class_risk_estimates(build_universe(_ev(), cfg), cfg)
    assert est["altin_doviz"] == 5                       # [4, 4, 5, 5, 6] -> 5
    assert "borclanma" not in est                        # 1 known value < 5: no class estimate


def test_quantile_from_config(d19_raw):
    config = parse_config(_raw(d19_raw, by_class_quantile=0.9))
    est = class_risk_estimates(build_universe(_ev(), config), config)
    assert est["altin_doviz"] == math.ceil(5 + 0.6 * 1)   # 0.9 x 4 = 3.6 -> 5.6 -> 6


def test_kzl_gets_the_class_estimate(cfg):
    f = _features(cfg, "P03")["fund:KZL"]
    assert f.option.asset_class == "altin_doviz"
    assert f.risk_estimated and f.risk == 5


def test_kzl_no_longer_passes_a_ceiling_of_2(cfg):
    r = decide(_ev(), load_persona("P01"), cfg, created_at=T0)
    kzl = next(o for o in r.options if o.option.option_id == "fund:KZL")
    assert kzl.score_parts["penalty:risk_unknown"] == pytest.approx(-0.3 * 2)   # 5 > 2
    assert kzl.reasons["penalty:risk_unknown"] == REASON_TEXT.format(risk=5)
    assert kzl.constraints[-1].reason == REASON_TEXT.format(risk=5)


def test_fallback_to_the_kind_rule_with_few_known_values(cfg):
    f = _features(cfg, "P03")["fund:DNR"]                # borclanma: 1 known value
    assert f.risk_estimated and f.risk == 3               # the old rule: highest known of "debt"


def test_funds_with_a_risk_row_are_unchanged(cfg, d19_config):
    new, old = _features(cfg, "P03"), _features(d19_config, "P03")
    for oid, f in new.items():
        if not f.risk_estimated:
            assert f.risk == old[oid].risk and not old[oid].risk_estimated


def test_estimate_does_not_depend_on_the_persona(cfg):
    assert _features(cfg, "P01")["fund:KZL"].risk == _features(cfg, "P03")["fund:KZL"].risk


def test_assumption_names_the_rule(cfg):
    r = decide(_ev(), load_persona("P03"), cfg, created_at=T0)
    assert CLASS_TEXT in r.assumptions


def test_no_assumption_when_no_fund_uses_it(cfg):
    funds = {k: v for k, v in FUNDS.items() if k not in ("KZL",)}
    funds["DNR"] = {**FUNDS["DNR"], "risk": 3}
    r = decide(_ev(funds), load_persona("P03"), cfg, created_at=T0)
    assert CLASS_TEXT not in r.assumptions


def test_without_asset_classes_the_old_rule_stays(d15_config):
    lv = read_persona(load_persona("P03"), d15_config).levels
    feats, _ = option_features(build_universe(_ev(), d15_config), lv, d15_config)
    kzl = next(f for f in feats if f.option.option_id == "fund:KZL")
    assert kzl.risk == 2                                  # highest known of "participation"


@pytest.mark.parametrize("value", [0, 1.5, "x"])
def test_bad_quantile_is_an_error(d19_raw, value):
    with pytest.raises(ConfigError, match="risk_estimate"):
        parse_config(_raw(d19_raw, by_class_quantile=value))
