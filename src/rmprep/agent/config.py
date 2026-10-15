"""config/agent.yaml (docs/agent.md): the model, its limits and the texts of the
agentic top-3 decision. Strict: an unknown or a missing key is a ConfigError."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "agent.yaml"
LANGS = ("TR", "EN")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
PROMPT_VERSIONS = ("a1", "a2")                # the known prompts (service.PROMPTS)
TOOL_NAMES = ("karsilastir", "arastir")
WORD_KEYS = ("reason", "summary", "amac")
LABEL_KEYS = ("estimate", "web")
KEYS = ("version", "model", "effort", "max_tokens", "price_input_per_mtok",
        "price_output_per_mtok", "api_key_env", "workspace_id_env", "prompt_version",
        "candidates", "max_tool_calls", "timeout_s", "max_cost_usd_per_day", "cache_dir",
        "words", "labels", "fallback_texts")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class AgentConfig:
    model: str
    effort: str
    max_tokens: int
    price_input_per_mtok: float
    price_output_per_mtok: float
    api_key_env: str
    workspace_id_env: str
    prompt_version: str
    candidates: int
    max_tool_calls: Mapping[str, int]          # karsilastir, arastir
    timeout_s: float
    max_cost_usd_per_day: float
    cache_dir: str
    words: Mapping[str, int]                   # reason, summary, amac
    labels: Mapping[str, Mapping[str, str]]    # estimate | web -> language -> label
    fallback_texts: Mapping[str, str]          # language -> text with {reason}


def _exact(d: Any, path: str, keys: tuple[str, ...]) -> Mapping:
    if not isinstance(d, Mapping):
        raise ConfigError(f"{path}: must be a mapping")
    unknown, missing = sorted(set(d) - set(keys)), [k for k in keys if k not in d]
    if unknown or missing:
        raise ConfigError(f"{path}: unknown keys {unknown}, missing keys {missing}")
    return d


def _int(v: Any, path: str, lo: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < lo:
        raise ConfigError(f"{path}: an integer >= {lo}, got {v!r}")
    return v


def _num(v: Any, path: str, positive: bool = True) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (positive and v <= 0):
        raise ConfigError(f"{path}: a number > 0, got {v!r}")
    return float(v)


def _str(v: Any, path: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ConfigError(f"{path}: a non-empty text, got {v!r}")
    return v


def _per_lang(d: Any, path: str) -> dict[str, str]:
    d = _exact(d, path, LANGS)
    return {lang: _str(d[lang], f"{path}.{lang}") for lang in LANGS}


def parse_agent_config(raw: Mapping[str, Any]) -> AgentConfig:
    raw = _exact(raw, "agent.yaml", KEYS)
    if raw["version"] != 1:
        raise ConfigError(f"version: 1, got {raw['version']!r}")
    if raw["effort"] not in EFFORTS:
        raise ConfigError(f"effort: one of {EFFORTS}, got {raw['effort']!r}")
    if raw["prompt_version"] not in PROMPT_VERSIONS:
        raise ConfigError(f"prompt_version: one of {PROMPT_VERSIONS}, got {raw['prompt_version']!r}")
    tools = _exact(raw["max_tool_calls"], "max_tool_calls", TOOL_NAMES)
    words = _exact(raw["words"], "words", WORD_KEYS)
    labels = _exact(raw["labels"], "labels", LABEL_KEYS)
    fallback = _per_lang(raw["fallback_texts"], "fallback_texts")
    if any("{reason}" not in t for t in fallback.values()):
        raise ConfigError("fallback_texts: every text needs the field {reason}")
    return AgentConfig(
        model=_str(raw["model"], "model"),
        effort=raw["effort"],
        max_tokens=_int(raw["max_tokens"], "max_tokens", 256),
        price_input_per_mtok=_num(raw["price_input_per_mtok"], "price_input_per_mtok"),
        price_output_per_mtok=_num(raw["price_output_per_mtok"], "price_output_per_mtok"),
        api_key_env=_str(raw["api_key_env"], "api_key_env"),
        workspace_id_env=_str(raw["workspace_id_env"], "workspace_id_env"),
        prompt_version=raw["prompt_version"],
        candidates=_int(raw["candidates"], "candidates", 3),
        max_tool_calls={k: _int(tools[k], f"max_tool_calls.{k}", 0) for k in TOOL_NAMES},
        timeout_s=_num(raw["timeout_s"], "timeout_s"),
        max_cost_usd_per_day=_num(raw["max_cost_usd_per_day"], "max_cost_usd_per_day"),
        cache_dir=_str(raw["cache_dir"], "cache_dir"),
        words={k: _int(words[k], f"words.{k}", 1) for k in WORD_KEYS},
        labels={k: _per_lang(labels[k], f"labels.{k}") for k in LABEL_KEYS},
        fallback_texts=fallback,
    )


def load_agent_config(path: Path | str = DEFAULT_PATH) -> AgentConfig:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ConfigError(f"{path}: cannot read ({e})") from e
    return parse_agent_config(raw)
