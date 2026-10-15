"""Load and check config/research.yaml (docs/research.md)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "research.yaml"
PROVIDERS = ("exa", "claude")
LANGS = ("TR", "EN")
QUERY_KINDS = ("fund", "etf", "stock")


class ConfigError(ValueError):
    """Invalid research config. The message starts with the path of the bad key."""


@dataclass(frozen=True)
class ExaConfig:
    api_key_env: str
    product_type: str
    question_type: str
    exclude_domains: tuple[str, ...]
    query: Mapping[str, str]          # option kind -> template with {label} and {code}
    news_query: str                   # template with {name} and {code}
    news_type: str
    base_url: str = "https://api.exa.ai"
    timeout_s: float = 60.0


@dataclass(frozen=True)
class ShapeConfig:
    news_days: int
    news_max: int
    highlights_max: int
    bullet_max_words: int
    repeat_jaccard: float             # in (0, 1]
    known_terms: tuple[str, ...]      # a highlight with one of these is dropped (the RM has the fact)


@dataclass(frozen=True)
class ClaudeSearchConfig:
    model: str
    max_uses: int
    max_tokens: int
    price_input_per_mtok: float
    price_output_per_mtok: float
    price_per_search: float
    api_key_env: str = "ANTHROPIC_API_KEY"
    workspace_id_env: str = "ANTHROPIC_WORKSPACE_ID"  # the key is org-level (as the narrator)
    # prices of a reply whose prompt is over 100K tokens; None: the base prices
    price_input_per_mtok_over_100k: float | None = None
    price_output_per_mtok_over_100k: float | None = None

    def __post_init__(self) -> None:
        if self.price_input_per_mtok_over_100k is None:
            object.__setattr__(self, "price_input_per_mtok_over_100k", self.price_input_per_mtok)
        if self.price_output_per_mtok_over_100k is None:
            object.__setattr__(self, "price_output_per_mtok_over_100k", self.price_output_per_mtok)


@dataclass(frozen=True)
class ResearchConfig:
    providers: tuple[str, ...]         # the fallback order
    exa: ExaConfig
    claude: ClaudeSearchConfig | None  # None: "claude" is not in providers
    max_cost_usd_per_day: float
    question_max_chars: int
    client_words: tuple[str, ...]
    system_prompt: Mapping[str, str]   # per language
    cache_dir: str
    shape: ShapeConfig
    highlights_prompt: Mapping[str, str]   # per language
    news_prompt: Mapping[str, str]         # per language; added to the system prompt of the news call


def _get(raw: Mapping, path: str):
    node = raw
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            raise ConfigError(f"{path}: missing")
        node = node[part]
    return node


def _num(raw: Mapping, path: str, kind=float):
    v = _get(raw, path)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        raise ConfigError(f"{path}: must be a positive number, got {v!r}")
    return kind(v)


def _opt_num(raw: Mapping, path: str) -> float | None:
    """A positive number, or None when the key is not there."""
    try:
        _get(raw, path)
    except ConfigError:
        return None
    return _num(raw, path)


def _str(raw: Mapping, path: str) -> str:
    v = _get(raw, path)
    if not isinstance(v, str) or not v.strip():
        raise ConfigError(f"{path}: must be a non-empty string, got {v!r}")
    return v


def _str_list(raw: Mapping, path: str) -> tuple[str, ...]:
    v = _get(raw, path)
    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
        raise ConfigError(f"{path}: must be a list of non-empty strings, got {v!r}")
    return tuple(v)


def parse_config(raw: Mapping) -> ResearchConfig:
    if not isinstance(raw, Mapping):
        raise ConfigError("(root): must be a mapping")
    providers = _str_list(raw, "providers")
    if not providers or any(p not in PROVIDERS for p in providers):
        raise ConfigError(f"providers: must be a non-empty list of {PROVIDERS}, got {list(providers)}")
    exa = ExaConfig(
        api_key_env=_str(raw, "exa.api_key_env"),
        product_type=_str(raw, "exa.product_type"),
        question_type=_str(raw, "exa.question_type"),
        exclude_domains=_str_list(raw, "exa.exclude_domains"),
        query={k: _str(raw, f"exa.query.{k}") for k in QUERY_KINDS},
        news_query=_str(raw, "exa.news_query"),
        news_type=_str(raw, "exa.news_type"))
    claude = None
    if "claude" in providers:
        claude = ClaudeSearchConfig(
            model=_str(raw, "claude.model"),
            max_uses=_num(raw, "claude.max_uses", int),
            max_tokens=_num(raw, "claude.max_tokens", int),
            price_input_per_mtok=_num(raw, "claude.price_input_per_mtok"),
            price_output_per_mtok=_num(raw, "claude.price_output_per_mtok"),
            price_per_search=_num(raw, "claude.price_per_search"),
            price_input_per_mtok_over_100k=_opt_num(raw, "claude.price_input_per_mtok_over_100k"),
            price_output_per_mtok_over_100k=_opt_num(raw, "claude.price_output_per_mtok_over_100k"))
    jaccard = _num(raw, "shape.repeat_jaccard")
    if jaccard > 1:
        raise ConfigError(f"shape.repeat_jaccard: must be in (0, 1], got {jaccard!r}")
    shape = ShapeConfig(
        news_days=_num(raw, "shape.news_days", int),
        news_max=_num(raw, "shape.news_max", int),
        highlights_max=_num(raw, "shape.highlights_max", int),
        bullet_max_words=_num(raw, "shape.bullet_max_words", int),
        repeat_jaccard=jaccard,
        known_terms=_str_list(raw, "shape.known_terms"))
    return ResearchConfig(
        providers=providers, exa=exa, claude=claude,
        max_cost_usd_per_day=_num(raw, "max_cost_usd_per_day"),
        question_max_chars=_num(raw, "question_max_chars", int),
        client_words=_str_list(raw, "client_words"),
        system_prompt={lang: _str(raw, f"system_prompt.{lang}") for lang in LANGS},
        cache_dir=_str(raw, "cache_dir"),
        shape=shape,
        highlights_prompt={lang: _str(raw, f"highlights_prompt.{lang}") for lang in LANGS},
        news_prompt={lang: _str(raw, f"news_prompt.{lang}") for lang in LANGS})


def load_config(path: Path | str = DEFAULT_PATH) -> ResearchConfig:
    return parse_config(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
