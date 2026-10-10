"""config/decision.yaml: loader and checks (docs/decision.md section 7)."""

import pytest

from rmprep.decision.config import ConfigError, parse_config


def test_project_config_is_valid(config):
    assert config.raw["deposit"]["option_id"] == "deposit:ing_turuncu"
    assert config.fund_kind("Serbest Şemsiye Fonu") is None
    assert config.fund_kind("Para Piyasası Şemsiye Fonu") == "money_market"


def test_config_is_a_copy_of_the_input(raw):
    cfg = parse_config(raw)
    raw["deposit"]["tier"] = "changed"
    assert cfg.raw["deposit"]["tier"] == "100.000-249.999 TL"


def test_unknown_top_level_key_is_an_error(raw):
    raw["extra"] = 1
    with pytest.raises(ConfigError, match="extra"):
        parse_config(raw)


def test_missing_top_level_key_is_an_error(raw):
    del raw["penalties"]
    with pytest.raises(ConfigError, match="penalties"):
        parse_config(raw)


def test_unknown_nested_key_is_an_error(raw):
    raw["display"]["firstt"] = 3
    with pytest.raises(ConfigError, match="display"):
        parse_config(raw)


def test_fund_kind_without_kind_row_is_an_error(raw):
    del raw["kinds"]["equity"]
    with pytest.raises(ConfigError, match="equity"):
        parse_config(raw)


def test_deposit_kind_row_is_required(raw):
    del raw["kinds"]["deposit"]
    with pytest.raises(ConfigError, match="deposit"):
        parse_config(raw)


def test_kind_value_out_of_range_is_an_error(raw):
    raw["kinds"]["debt"]["liquidity"] = 1.5
    with pytest.raises(ConfigError, match="kinds.debt.liquidity"):
        parse_config(raw)


@pytest.mark.parametrize("criterion,key,value", [
    ("quality", "base", -0.1),
    ("income", "per_level", -2.0),
    ("low_risk", "appetite", -1.5),   # raw weight 1 - 1.5 < 0 for an Agresif persona
])
def test_negative_weight_is_an_error(raw, criterion, key, value):
    raw["weights"][criterion][key] = value
    with pytest.raises(ConfigError, match=f"weights.{criterion}"):
        parse_config(raw)


def test_missing_criterion_weight_is_an_error(raw):
    del raw["weights"]["simplicity"]
    with pytest.raises(ConfigError, match="simplicity"):
        parse_config(raw)


def test_weight_level_must_be_a_level_field(raw):
    raw["weights"]["income"]["level"] = "yas"
    with pytest.raises(ConfigError, match="weights.income.level"):
        parse_config(raw)


def test_negative_penalty_is_an_error(raw):
    raw["penalties"]["fund_size"] = -0.1
    with pytest.raises(ConfigError, match="penalties.fund_size"):
        parse_config(raw)


def test_constraint_with_unknown_effect_is_an_error(raw):
    raw["constraints"]["yeni kısıt"] = "no_such_effect"
    with pytest.raises(ConfigError, match="no_such_effect"):
        parse_config(raw)


def test_effect_without_label_is_an_error(raw):
    del raw["texts"]["effect_labels"]["fx_limit"]
    with pytest.raises(ConfigError, match="fx_limit"):
        parse_config(raw)


@pytest.mark.parametrize("effect", ["boost:nothing", "note:nothing", "other"])
def test_priority_with_unknown_effect_is_an_error(raw, effect):
    raw["priorities"]["düzenli gelir"] = effect
    with pytest.raises(ConfigError, match="priorities"):
        parse_config(raw)


def test_risk_ceiling_out_of_range_is_an_error(raw):
    raw["risk_profiles"]["Agresif"]["ceiling"] = 8
    with pytest.raises(ConfigError, match="risk_profiles"):
        parse_config(raw)


def test_safe_level_must_be_a_known_level(raw):
    raw["safe_levels"]["likidite_ihtiyaci"] = "Çok yüksek"
    with pytest.raises(ConfigError, match="safe_levels.likidite_ihtiyaci"):
        parse_config(raw)


def test_horizon_period_must_have_years(raw):
    raw["horizon"]["periods"][0]["period"] = "2y"
    with pytest.raises(ConfigError, match="horizon"):
        parse_config(raw)


def test_unknown_confidence_flag_is_an_error(raw):
    raw["confidence"]["flags"]["wobbly"] = 0.5
    with pytest.raises(ConfigError, match="wobbly"):
        parse_config(raw)


def test_table_keys_that_normalize_alike_are_an_error(raw):
    raw["priorities"]["Düzenli  Gelir."] = "boost:income"
    with pytest.raises(ConfigError, match="priorities"):
        parse_config(raw)


@pytest.mark.parametrize("key", ["return_missing", "penalty:fund_size", "quality"])
def test_missing_reason_text_is_an_error(raw, key):
    del raw["texts"]["reasons"][key]
    with pytest.raises(ConfigError, match="texts.reasons"):
        parse_config(raw)


def test_missing_constraint_text_is_an_error(raw):
    del raw["texts"]["constraint"]["failed"]
    with pytest.raises(ConfigError, match="texts.constraint"):
        parse_config(raw)


def test_stability_size_is_optional(raw):
    raw["stability"].pop("size", None)
    parse_config(raw)
    raw["stability"]["size"] = 20
    assert parse_config(raw).raw["stability"]["size"] == 20


@pytest.mark.parametrize("value", [0, -1, 2.5, True, "20"])
def test_bad_stability_size_is_an_error(raw, value):
    raw["stability"]["size"] = value
    with pytest.raises(ConfigError, match="stability.size"):
        parse_config(raw)
