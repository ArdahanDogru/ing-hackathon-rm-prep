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
    assert c.max_cost_usd_per_day == 2.0
    assert set(c.system_prompt) == {"TR", "EN"}


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
])
def test_bad_values_name_their_path(path, value, starts):
    with pytest.raises(ConfigError) as e:
        parse_config(_broken(path, value))
    assert str(e.value).startswith(starts)


def test_claude_section_only_needed_when_listed():
    raw = _broken("providers", ["exa"])
    del raw["claude"]
    assert parse_config(raw).claude is None
