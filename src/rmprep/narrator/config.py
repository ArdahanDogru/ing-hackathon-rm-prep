"""Load and check config/narrator.yaml (docs/narrator.md)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from rmprep.contracts import NARRATIVE_LANGS, NARRATIVE_SECTIONS, NARRATIVE_SECTIONS_V13

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "narrator.yaml"


class ConfigError(ValueError):
    """Invalid narrator config. The message starts with the path of the bad key."""


@dataclass(frozen=True)
class BriefConfig:
    """v1.4 dashboard brief (config section `brief`; narrator N10)."""
    model: str
    max_chars: int
    prompt_version: str
    price_input_per_mtok: float     # missing in the config -> the llm prices (over-states)
    price_output_per_mtok: float
    effort: str = "low"             # 1-2 sentences: low effort (claude-api skill)
    max_tokens: int = 4000          # room for adaptive thinking; the text itself is short


@dataclass(frozen=True)
class NarratorConfig:
    model: str
    effort: str
    max_tokens: int
    price_input_per_mtok: float
    price_output_per_mtok: float
    api_key_env: str
    max_cost_usd_per_day: float
    prompt_version: str
    cache_dir: str
    langs: tuple[str, ...]
    sections: tuple[str, ...]
    forbidden_phrases: Mapping[str, tuple[str, ...]]
    disclaimer: Mapping[str, str]
    workspace_id_env: str | None = None  # env var of the workspace id (org-level keys)
    brief: BriefConfig | None = None     # None: no `brief` section -> the plain sentence


def _get(raw: Mapping, path: str):
    node = raw
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            raise ConfigError(f"{path}: missing")
        node = node[part]
    return node


def _str(raw: Mapping, path: str) -> str:
    v = _get(raw, path)
    if not isinstance(v, str) or not v.strip():
        raise ConfigError(f"{path}: must be a non-empty string, got {v!r}")
    return v


def _num(raw: Mapping, path: str) -> float:
    v = _get(raw, path)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        raise ConfigError(f"{path}: must be a number >= 0, got {v!r}")
    return float(v)


def _per_lang(raw: Mapping, path: str) -> dict:
    v = _get(raw, path)
    if not isinstance(v, Mapping) or set(v) != set(NARRATIVE_LANGS):
        raise ConfigError(f"{path}: needs exactly the languages {NARRATIVE_LANGS}")
    return dict(v)


def parse_config(raw: Mapping) -> NarratorConfig:
    langs = tuple(_get(raw, "langs"))
    if langs != NARRATIVE_LANGS:
        raise ConfigError(f"langs: must be {list(NARRATIVE_LANGS)}, got {list(langs)}")
    sections = tuple(_get(raw, "sections"))
    # N9: v1.3 adds talking_points; the v1.2 list is accepted until the config has it
    if sections not in (NARRATIVE_SECTIONS, NARRATIVE_SECTIONS_V13):
        raise ConfigError(f"sections: must be {list(NARRATIVE_SECTIONS_V13)}, got {list(sections)}")
    sections = NARRATIVE_SECTIONS_V13
    forbidden = _per_lang(raw, "forbidden_phrases")
    for lang, phrases in forbidden.items():
        if not phrases or not all(isinstance(p, str) and p.strip() for p in phrases):
            raise ConfigError(f"forbidden_phrases.{lang}: must be a list of non-empty strings")
    disclaimer = _per_lang(raw, "disclaimer")
    for lang in disclaimer:
        _str(raw, f"disclaimer.{lang}")
    max_tokens = _get(raw, "llm.max_tokens")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ConfigError(f"llm.max_tokens: must be a positive integer, got {max_tokens!r}")
    return NarratorConfig(
        model=_str(raw, "llm.model"),
        effort=_str(raw, "llm.effort"),
        max_tokens=max_tokens,
        price_input_per_mtok=_num(raw, "llm.price_input_per_mtok"),
        price_output_per_mtok=_num(raw, "llm.price_output_per_mtok"),
        api_key_env=_str(raw, "llm.api_key_env"),
        max_cost_usd_per_day=_num(raw, "max_cost_usd_per_day"),
        prompt_version=_str(raw, "prompt_version"),
        cache_dir=_str(raw, "cache_dir"),
        langs=langs,
        sections=sections,
        forbidden_phrases={k: tuple(v) for k, v in forbidden.items()},
        disclaimer=disclaimer,
        workspace_id_env=(_str(raw, "llm.workspace_id_env")
                          if "workspace_id_env" in raw.get("llm", {}) else None),
        brief=_brief(raw) if "brief" in raw else None,
    )


def _brief(raw: Mapping) -> BriefConfig:
    max_chars = _get(raw, "brief.max_chars")
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars <= 0:
        raise ConfigError(f"brief.max_chars: must be a positive integer, got {max_chars!r}")
    b = raw["brief"]

    def price(key: str) -> float:
        return _num(raw, f"brief.{key}") if key in b else _num(raw, f"llm.{key}")

    extra = {}
    if "effort" in b:
        extra["effort"] = _str(raw, "brief.effort")
    if "max_tokens" in b:
        extra["max_tokens"] = int(_num(raw, "brief.max_tokens"))
    return BriefConfig(model=_str(raw, "brief.model"), max_chars=max_chars,
                       prompt_version=_str(raw, "brief.prompt_version"),
                       price_input_per_mtok=price("price_input_per_mtok"),
                       price_output_per_mtok=price("price_output_per_mtok"), **extra)


def load_config(path: Path | str = DEFAULT_PATH) -> NarratorConfig:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, Mapping):
        raise ConfigError("(root): must be a mapping")
    return parse_config(raw)
