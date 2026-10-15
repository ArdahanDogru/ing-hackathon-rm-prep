"""A1: config/agent.yaml (docs/agent.md; test copy in fixtures/)."""

import pytest
import yaml

from rmprep.agent.config import ConfigError, load_agent_config, parse_agent_config
from tests.agent.conftest import FIXTURES


def _raw() -> dict:
    return yaml.safe_load((FIXTURES / "agent.yaml").read_text(encoding="utf-8"))


def test_loads_the_test_copy(cfg):
    assert cfg.model == "claude-sonnet-5-5"
    assert cfg.effort == "medium"
    assert cfg.max_tool_calls == {"karsilastir": 4, "arastir": 2}
    assert cfg.timeout_s == 90 and cfg.max_cost_usd_per_day == 3.0
    assert cfg.candidates == 10 and cfg.prompt_version == "a3"
    assert cfg.max_candidates == 20
    assert cfg.words == {"reason": 30, "summary": 40, "amac": 20}
    assert cfg.labels["estimate"]["TR"] == "(tahmini dağılıma göre)"
    assert cfg.labels["web"]["EN"] == "(web, not verified)"
    assert cfg.labels["web_confirmed"]["TR"] == "(web, RM doğruladı)"
    assert "{reason}" in cfg.fallback_texts["TR"]


def test_config_strict_keys():
    raw = _raw() | {"surprise": 1}
    with pytest.raises(ConfigError, match="surprise"):
        parse_agent_config(raw)
    raw = _raw()
    del raw["timeout_s"]
    with pytest.raises(ConfigError, match="timeout_s"):
        parse_agent_config(raw)
    raw = _raw()
    raw["max_tool_calls"] = {"karsilastir": 4, "arastir": 2, "sil": 1}
    with pytest.raises(ConfigError, match="max_tool_calls"):
        parse_agent_config(raw)


def test_config_values_are_checked():
    for key, value in (("candidates", 2), ("timeout_s", 0), ("max_cost_usd_per_day", -1),
                       ("effort", "huge"), ("prompt_version", "zz")):
        raw = _raw() | {key: value}
        with pytest.raises(ConfigError, match=key):
            parse_agent_config(raw)
    raw = _raw()
    raw["labels"]["web"] = {"TR": "(web)"}
    with pytest.raises(ConfigError, match="labels.web"):
        parse_agent_config(raw)
    raw = _raw()
    raw["fallback_texts"]["EN"] = "no field"
    with pytest.raises(ConfigError, match="fallback_texts"):
        parse_agent_config(raw)


def test_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="agent.yaml"):
        load_agent_config(tmp_path / "agent.yaml")


def test_an_a1_config_gets_the_a2_defaults():
    """config/agent.yaml of A1 has no max_candidates and no labels.web_confirmed."""
    raw = _raw()
    del raw["max_candidates"]
    del raw["labels"]["web_confirmed"]
    cfg = parse_agent_config(raw)
    assert cfg.max_candidates == 20
    assert cfg.labels["web_confirmed"] == {"TR": "(web, RM doğruladı)",
                                           "EN": "(web, confirmed by the RM)"}
    with pytest.raises(ConfigError, match="max_candidates"):
        parse_agent_config(_raw() | {"max_candidates": 5})        # below candidates (10)
    with pytest.raises(ConfigError, match="max_candidates"):
        parse_agent_config(_raw() | {"max_candidates": 51})
