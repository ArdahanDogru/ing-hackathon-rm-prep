import copy

import pytest
import yaml

from rmprep.research.config import DEFAULT_PATH, ConfigError, load_config, parse_config

RAW = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))


def test_the_repo_config_loads():
    c = load_config()
    assert c.providers == ("exa", "claude")
    assert c.exa.exclude_domains == ("kap.org.tr",)
    assert c.exa.query["fund"].format(label="X", code="PPN") == "X (PPN) fonu ve yöneten portföy yönetim şirketi"
    assert c.claude is not None and c.claude.max_uses == 3
    assert c.max_cost_usd_per_day == 5.0      # the user, 2026-10-15 (agent: 10 candidates per run)
    assert set(c.system_prompt) == {"TR", "EN"}


def test_the_v2_keys_load():
    c = load_config()
    assert (c.shape.news_days, c.shape.news_max, c.shape.highlights_max) == (90, 3, 4)
    assert (c.shape.bullet_max_words, c.shape.repeat_jaccard) == (20, 0.6)
    assert "saklayıcı" in c.shape.known_terms
    assert set(c.highlights_prompt) == {"TR", "EN"}
    assert set(c.news_prompt) == {"TR", "EN"} and "olay" in c.news_prompt["TR"]
    assert c.exa.news_query.format(name="Ak Portföy", code="AIS") == "Ak Portföy AIS haber"
    assert c.exa.news_type == "auto"


def _broken(path: str, value):
    raw = copy.deepcopy(RAW)
    node = raw
    *parents, last = path.split(".")
    for p in parents:
        node = node[p]
    if value is None:
        del node[last]
    else:
        node[last] = value
    return raw


@pytest.mark.parametrize("path,value,starts", [
    ("exa.api_key_env", None, "exa.api_key_env"),
    ("providers", ["bing"], "providers"),
    ("providers", [], "providers"),
    ("max_cost_usd_per_day", 0, "max_cost_usd_per_day"),
    ("system_prompt.EN", None, "system_prompt.EN"),
    ("exa.query.etf", None, "exa.query.etf"),
    ("claude.max_uses", "three", "claude.max_uses"),
    ("shape.repeat_jaccard", 0, "shape.repeat_jaccard"),
    ("shape.repeat_jaccard", 1.5, "shape.repeat_jaccard"),
    ("shape.news_days", 0, "shape.news_days"),
    ("shape.known_terms", "x", "shape.known_terms"),
    ("highlights_prompt.EN", None, "highlights_prompt.EN"),
    ("news_prompt.EN", None, "news_prompt.EN"),
    ("exa.news_query", None, "exa.news_query"),
])
def test_bad_values_name_their_path(path, value, starts):
    with pytest.raises(ConfigError) as e:
        parse_config(_broken(path, value))
    assert str(e.value).startswith(starts)


def test_claude_section_only_needed_when_listed():
    raw = _broken("providers", ["exa"])
    del raw["claude"]
    assert parse_config(raw).claude is None


def test_over_100k_prices_are_read_and_default_to_the_base_prices():
    c = load_config().claude
    assert (c.price_input_per_mtok_over_100k, c.price_output_per_mtok_over_100k) == (0.50, 2.50)
    raw = copy.deepcopy(RAW)
    del raw["claude"]["price_input_per_mtok_over_100k"]
    del raw["claude"]["price_output_per_mtok_over_100k"]
    c = parse_config(raw).claude
    assert c.price_input_per_mtok_over_100k == c.price_input_per_mtok == 0.10
    assert c.price_output_per_mtok_over_100k == c.price_output_per_mtok == 0.50


def test_a_bad_over_100k_price_names_its_path():
    with pytest.raises(ConfigError) as e:
        parse_config(_broken("claude.price_input_per_mtok_over_100k", -1))
    assert str(e.value).startswith("claude.price_input_per_mtok_over_100k")
