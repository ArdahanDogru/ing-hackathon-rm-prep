import pytest
import yaml

from rmprep.contracts import NARRATIVE_LANGS, NARRATIVE_SECTIONS
from rmprep.narrator.config import DEFAULT_PATH, ConfigError, load_config


def test_real_config_loads(config):
    assert config.model == "claude-sonnet-5-5"
    assert config.sections == NARRATIVE_SECTIONS
    assert config.langs == NARRATIVE_LANGS
    assert config.max_cost_usd_per_day == 5.0
    assert "garanti" in config.forbidden_phrases["TR"]
    assert "yatırım tavsiyesi değildir" in config.disclaimer["TR"]
    assert config.disclaimer["EN"]


def _write(tmp_path, raw):
    p = tmp_path / "narrator.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return p


def _raw():
    return yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("change, where", [
    (lambda r: r.pop("prompt_version"), "prompt_version"),
    (lambda r: r["llm"].pop("model"), "llm.model"),
    (lambda r: r.__setitem__("sections", ["ozet"]), "sections"),
    (lambda r: r["disclaimer"].pop("EN"), "disclaimer"),
    (lambda r: r["forbidden_phrases"].pop("TR"), "forbidden_phrases"),
    (lambda r: r.__setitem__("max_cost_usd_per_day", -1), "max_cost_usd_per_day"),
])
def test_bad_config_names_the_key(tmp_path, change, where):
    raw = _raw()
    change(raw)
    with pytest.raises(ConfigError, match=where):
        load_config(_write(tmp_path, raw))
