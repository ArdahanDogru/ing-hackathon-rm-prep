"""Load and check config/eval.yaml (docs/eval.md)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml


class ConfigError(ValueError):
    """Invalid eval config. The message starts with the path of the bad key."""


@dataclass(frozen=True)
class RubricItem:
    id: str
    question: str


@dataclass(frozen=True)
class JudgeConfig:
    model: str
    effort: str
    max_tokens: int
    price_input_per_mtok: float
    price_output_per_mtok: float
    api_key_env: str
    workspace_id_env: str | None
    rubric: tuple[RubricItem, ...]


@dataclass(frozen=True)
class SecondAbJudgeConfig:
    """E13: a second, independent A/B judge from another vendor (only "gemini" now)."""
    provider: str
    model: str
    max_tokens: int
    thinking_level: str | None      # Gemini 3 thinkingLevel ("low", ...); None = model default
    price_input_per_mtok: float
    price_output_per_mtok: float
    api_key_env: str
    min_interval_s: float           # pause between two new calls (free-tier rate limit)


@dataclass(frozen=True)
class Targets:
    rule_checks: float
    narrator_pass_rate: float
    forbidden_phrases: int


@dataclass(frozen=True)
class EvalConfig:
    snapshot: str | None            # the frozen eval snapshot; None = not set yet
    max_cost_usd_per_run: float
    report_dir: str
    judge: JudgeConfig
    targets: Targets
    judge_repeats: int = 1          # E10: grades per text (mean and spread in the report)
    second_ab_judge: SecondAbJudgeConfig | None = None   # E13; None = not configured


_TOP = {"version", "snapshot", "max_cost_usd_per_run", "report_dir", "judge", "targets"}
_TOP_OPTIONAL = {"judge_repeats", "second_ab_judge"}
_JUDGE = {"model", "effort", "max_tokens", "price_input_per_mtok", "price_output_per_mtok",
          "api_key_env", "workspace_id_env", "rubric"}
_TARGETS = {"rule_checks", "narrator_pass_rate", "forbidden_phrases"}
_SECOND_AB = {"provider", "model", "max_tokens", "thinking_level", "price_input_per_mtok",
              "price_output_per_mtok", "api_key_env", "min_interval_s"}
SECOND_AB_PROVIDERS = ("gemini",)


def _keys(node, path: str, allowed: set[str], optional: set[str] = frozenset()) -> Mapping:
    if not isinstance(node, Mapping):
        raise ConfigError(f"{path or '<root>'}: must be a mapping")
    unknown = sorted(set(node) - allowed)
    if unknown:
        raise ConfigError(f"{path or '<root>'}: unknown keys {unknown}")
    missing = sorted(allowed - set(node) - set(optional))
    if missing:
        raise ConfigError(f"{path or '<root>'}: missing keys {missing}")
    return node


def _str(node: Mapping, key: str, path: str) -> str:
    v = node[key]
    if not isinstance(v, str) or not v.strip():
        raise ConfigError(f"{path}{key}: must be a non-empty string, got {v!r}")
    return v


def _num(node: Mapping, key: str, path: str) -> float:
    v = node[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        raise ConfigError(f"{path}{key}: must be a number >= 0, got {v!r}")
    return float(v)


def _int(node: Mapping, key: str, path: str) -> int:
    v = node[key]
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise ConfigError(f"{path}{key}: must be an integer >= 0, got {v!r}")
    return v


def parse_config(raw) -> EvalConfig:
    raw = _keys(raw, "", _TOP | _TOP_OPTIONAL, _TOP_OPTIONAL)
    repeats = raw.get("judge_repeats", 1)
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1:
        raise ConfigError(f"judge_repeats: must be an integer >= 1, got {repeats!r}")
    if raw["version"] != 1:
        raise ConfigError(f"version: must be 1, got {raw['version']!r}")
    snapshot = raw["snapshot"]
    if snapshot is not None and (not isinstance(snapshot, str) or not snapshot.strip()):
        raise ConfigError(f"snapshot: must be null or a snapshot id, got {snapshot!r}")

    j = _keys(raw["judge"], "judge", _JUDGE)
    if not isinstance(j["rubric"], list) or not j["rubric"]:
        raise ConfigError("judge.rubric: must be a non-empty list")
    rubric = []
    for i, item in enumerate(j["rubric"]):
        item = _keys(item, f"judge.rubric[{i}]", {"id", "question"})
        rubric.append(RubricItem(_str(item, "id", f"judge.rubric[{i}]."),
                                 _str(item, "question", f"judge.rubric[{i}].")))
    ids = [r.id for r in rubric]
    if len(ids) != len(set(ids)):
        raise ConfigError(f"judge.rubric: duplicate ids in {ids}")
    workspace = j["workspace_id_env"]
    if workspace is not None and (not isinstance(workspace, str) or not workspace.strip()):
        raise ConfigError(f"judge.workspace_id_env: must be null or a name, got {workspace!r}")
    judge = JudgeConfig(
        model=_str(j, "model", "judge."), effort=_str(j, "effort", "judge."),
        max_tokens=_int(j, "max_tokens", "judge."),
        price_input_per_mtok=_num(j, "price_input_per_mtok", "judge."),
        price_output_per_mtok=_num(j, "price_output_per_mtok", "judge."),
        api_key_env=_str(j, "api_key_env", "judge."), workspace_id_env=workspace,
        rubric=tuple(rubric))

    second = None
    if raw.get("second_ab_judge") is not None:
        a = _keys(raw["second_ab_judge"], "second_ab_judge", _SECOND_AB)
        if a["provider"] not in SECOND_AB_PROVIDERS:
            raise ConfigError(f"second_ab_judge.provider: must be one of {list(SECOND_AB_PROVIDERS)}, "
                              f"got {a['provider']!r}")
        level = a["thinking_level"]
        if level is not None and (not isinstance(level, str) or not level.strip()):
            raise ConfigError(f"second_ab_judge.thinking_level: must be null or a level, got {level!r}")
        path = "second_ab_judge."
        second = SecondAbJudgeConfig(
            provider=a["provider"], model=_str(a, "model", path),
            max_tokens=_int(a, "max_tokens", path), thinking_level=level,
            price_input_per_mtok=_num(a, "price_input_per_mtok", path),
            price_output_per_mtok=_num(a, "price_output_per_mtok", path),
            api_key_env=_str(a, "api_key_env", path), min_interval_s=_num(a, "min_interval_s", path))

    t = _keys(raw["targets"], "targets", _TARGETS)
    targets = Targets(rule_checks=_num(t, "rule_checks", "targets."),
                      narrator_pass_rate=_num(t, "narrator_pass_rate", "targets."),
                      forbidden_phrases=_int(t, "forbidden_phrases", "targets."))
    return EvalConfig(judge_repeats=repeats, snapshot=snapshot, max_cost_usd_per_run=_num(raw, "max_cost_usd_per_run", ""),
                      report_dir=_str(raw, "report_dir", ""), judge=judge, targets=targets,
                      second_ab_judge=second)


def load_config(path: Path | str) -> EvalConfig:
    return parse_config(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
