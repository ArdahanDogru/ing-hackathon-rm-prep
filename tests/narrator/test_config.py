import pytest
import yaml

from rmprep.contracts import NARRATIVE_LANGS, NARRATIVE_SECTIONS, NARRATIVE_SECTIONS_V13
from rmprep.narrator.config import DEFAULT_PATH, ConfigError, load_config


def test_real_config_loads(config):
    assert config.model == "claude-sonnet-5-5"
    assert config.sections == NARRATIVE_SECTIONS_V13
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


def test_workspace_id_env_is_optional(tmp_path):
    raw = _raw()
    raw["llm"].pop("workspace_id_env", None)
    assert load_config(_write(tmp_path, raw)).workspace_id_env is None
    raw["llm"]["workspace_id_env"] = "ANTHROPIC_WORKSPACE_ID"
    assert load_config(_write(tmp_path, raw)).workspace_id_env == "ANTHROPIC_WORKSPACE_ID"
    raw["llm"]["workspace_id_env"] = ""
    with pytest.raises(ConfigError, match="llm.workspace_id_env"):
        load_config(_write(tmp_path, raw))


def test_sections_v12_or_v13(tmp_path):
    """N9: the lead adds talking_points to config/narrator.yaml on merge; both
    lists load until then; the narrator always writes the v1.3 sections."""
    from rmprep.contracts import NARRATIVE_SECTIONS_V13

    raw = _raw()
    raw["sections"] = list(NARRATIVE_SECTIONS_V13)
    assert load_config(_write(tmp_path, raw)).sections == NARRATIVE_SECTIONS_V13
    raw["sections"] = list(NARRATIVE_SECTIONS)
    assert load_config(_write(tmp_path, raw)).sections == NARRATIVE_SECTIONS_V13
