"""Warning audience and to_confirm (contract v1.3; docs/decision.md D16)."""

import dataclasses

import pytest

from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.engine import decide
from tests.decision.conftest import T0, load_evidence, load_persona, make_evidence

AUDIENCE = {"concentration": "client", "fx_exposure": "client"}
TIER_TEXT = "Yatırım tutarını sorun: {tier} dilimi varsayıldı."
FULL = dict(returns={"3y": 100.0}, size=2e8, investors=500)


@pytest.fixture
def d16_raw(raw):
    raw["warnings"]["audience"] = dict(AUDIENCE)
    raw["to_confirm"] = {"deposit_tier": TIER_TEXT}
    return raw


@pytest.fixture
def d16_config(d16_raw):
    return parse_config(d16_raw)


def _codes(r):
    return {w.code: w.audience for w in r.warnings}


# --- audience ---------------------------------------------------------------------------------

def test_fx_exposure_is_for_the_client(d16_config):
    funds = {"FX": dict(kind="debt", risk=2, name="X EUROBOND FONU", **FULL),
             "TL": dict(kind="money_market", risk=1, **FULL)}
    r = decide(make_evidence(funds), load_persona("P05"), d16_config, created_at=T0)
    assert _codes(r)["fx_exposure"] == "client"


def test_concentration_is_for_the_client(d16_config):
    funds = {f"D{i}": dict(kind="debt", risk=2, **FULL) for i in range(5)}
    r = decide(make_evidence(funds), load_persona("P04"), d16_config, created_at=T0)
    assert _codes(r)["concentration"] == "client"


def test_deposit_vs_market_is_rm_only(d16_config):
    r = decide(load_evidence(), load_persona("P01"), d16_config, created_at=T0)
    assert _codes(r)["deposit_vs_market"] == "rm"


def test_a_code_not_in_the_table_is_rm(d16_config):
    funds = {"NR": dict(kind="equity", **FULL), "MM": dict(kind="money_market", risk=1, **FULL)}
    r = decide(make_evidence(funds), load_persona("P05"), d16_config, created_at=T0)
    assert _codes(r)["risk_estimate"] == "rm"


# --- to_confirm -------------------------------------------------------------------------------

def test_to_confirm_for_the_deposit_tier(d16_config):
    r = decide(load_evidence(), load_persona("P01"), d16_config, created_at=T0)
    tier = d16_config.raw["deposit"]["tier"]
    assert r.to_confirm == (f"Yatırım tutarını sorun: {tier} dilimi varsayıldı.",)


def test_to_confirm_follows_the_emit_order(d16_raw):
    d16_raw["to_confirm"]["fx_priority"] = "Kur riskinin nasıl yönetileceğini sorun."
    d16_raw["to_confirm"] = {"fx_priority": d16_raw["to_confirm"]["fx_priority"],
                             "deposit_tier": TIER_TEXT}           # table order does not count
    cfg = parse_config(d16_raw)
    r = decide(load_evidence(), load_persona("P02"), cfg, created_at=T0)
    tier = cfg.raw["deposit"]["tier"]
    assert r.to_confirm == (TIER_TEXT.format(tier=tier),       # standard assumption first
                            "Kur riskinin nasıl yönetileceğini sorun.")   # then the persona's


def test_to_confirm_only_for_emitted_keys(d16_raw):
    d16_raw["to_confirm"]["fx_priority"] = "Kur riskini sorun."
    cfg = parse_config(d16_raw)
    r = decide(load_evidence(), load_persona("P01"), cfg, created_at=T0)   # P01: no fx priority
    assert "Kur riskini sorun." not in r.to_confirm


def test_blocked_result_has_to_confirm_too(d16_config):
    p = dataclasses.replace(load_persona("P01"), risk_profili="?")
    r = decide(load_evidence(), p, d16_config, created_at=T0)
    assert r.to_confirm and r.options == ()


# --- without config ---------------------------------------------------------------------------

def test_without_config_all_rm_and_nothing_to_confirm(config):
    r = decide(load_evidence(), load_persona("P01"), config, created_at=T0)
    assert r.warnings and {w.audience for w in r.warnings} == {"rm"}
    assert r.to_confirm == ()


def test_same_config_same_run_id(d16_config):
    a = decide(load_evidence(), load_persona("P01"), d16_config, created_at=T0)
    b = decide(load_evidence(), load_persona("P01"), d16_config, created_at=T0)
    assert a.run_id == b.run_id and a.to_dict() == b.to_dict()


@pytest.mark.parametrize("edit,match", [
    (lambda r: r["warnings"]["audience"].update(fx_exposure="everyone"), "warnings.audience"),
    (lambda r: r["warnings"]["audience"].update(unknown_code="rm"), "warnings.audience"),
    (lambda r: r["to_confirm"].update(no_such_assumption="x"), "to_confirm"),
    (lambda r: r["to_confirm"].update(deposit_tier=""), "to_confirm"),
    (lambda r: r["to_confirm"].update(deposit_tier="Tutar {amount}"), "to_confirm"),
])
def test_bad_d16_config_is_an_error(d16_raw, edit, match):
    edit(d16_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(d16_raw)
