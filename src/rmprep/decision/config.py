"""Load and check config/decision.yaml (docs/decision.md section 7).

`load_raw` reads the YAML; `parse_config` checks a plain dict and wraps a deep
copy of it. The engine reads the tables from `DecisionConfig.raw`; stability
(section 5) builds changed copies of the raw dict and parses them again.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from rmprep.contracts import Flag
from rmprep.decision.text import normalize

CONFIG_VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "decision.yaml"

CRITERIA = ("return", "low_risk", "liquidity", "income", "principal", "simplicity", "quality")
LEVEL_FIELDS = ("likidite_ihtiyaci", "gelir_nakit_akisi_ihtiyaci", "anapara_koruma_tercihi")
SAFE_LEVEL_FIELDS = ("yatirim_ufku", *LEVEL_FIELDS, "doviz_maruz_kalma_tercihi")
PENALTY_RULES = ("principal", "liquidity", "fx_exposure", "risk_unknown", "track_record",
                 "fund_size")
PENALTIES = (*PENALTY_RULES, "risk_unknown_above_ceiling_factor")
EFFECT_KEYS = ("max_ceiling", "min_fx_intensity", "liquidity_weight", "liquidity_intensity",
               "min_liquidity_intensity", "diversity")
TEXT_SECTIONS = ("reasons", "constraint", "questions", "effect_labels", "assumptions",
                 "warnings", "data_quality")

_TOP = ("version", "deposit", "fund_kinds", "fx_name_words", "risk_profiles", "horizon",
        "levels", "fx_levels", "safe_levels", "priorities", "priority_boost", "constraints",
        "constraint_effects", "kinds", "principal_value", "weights", "penalties",
        "fund_size_min", "display", "confidence", "stability", "warnings", "texts")


class ConfigError(ValueError):
    """Invalid decision config. The message starts with the path of the bad key."""


@dataclass(frozen=True)
class DecisionConfig:
    raw: Mapping[str, Any]      # the checked config, as parsed (do not change it)

    def fund_kind(self, category: str) -> str | None:
        """fund_kind of an umbrella type; None if not in the universe or unknown."""
        return self.raw["fund_kinds"].get(category)


def load_raw(path: Path | str = DEFAULT_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: the top level must be a mapping")
    return data


def load_config(path: Path | str = DEFAULT_PATH) -> DecisionConfig:
    return parse_config(load_raw(path))


def parse_config(raw: Mapping[str, Any]) -> DecisionConfig:
    data = copy.deepcopy(dict(raw))
    _check(data)
    return DecisionConfig(raw=data)


# --- checks ------------------------------------------------------------------------

def _keys(d: Any, path: str, required: tuple[str, ...] | list[str],
          optional: tuple[str, ...] = ()) -> None:
    if not isinstance(d, Mapping):
        raise ConfigError(f"{path}: must be a mapping")
    missing = [k for k in required if k not in d]
    unknown = sorted(set(d) - set(required) - set(optional))
    if missing or unknown:
        raise ConfigError(f"{path}: missing keys {missing}, unknown keys {unknown}")


def _num(v: Any, path: str, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigError(f"{path}: must be a number, got {v!r}")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise ConfigError(f"{path}: {v!r} is not in [{lo}, {hi}]")
    return float(v)


def _table_keys(d: Mapping, path: str) -> None:
    """Persona text tables: two keys must not normalize to the same text."""
    seen: dict[str, str] = {}
    for k in d:
        n = normalize(k)
        if not n or n in seen:
            raise ConfigError(f"{path}: key {k!r} normalizes like {seen.get(n)!r}")
        seen[n] = k


def _check(c: dict) -> None:
    _keys(c, "config", _TOP)
    if c["version"] != CONFIG_VERSION:
        raise ConfigError(f"version: expected {CONFIG_VERSION}, got {c['version']!r}")

    _keys(c["deposit"], "deposit", ("option_id", "label", "source", "quantity",
                                    "entity_prefix", "tier", "market_entity"))

    kinds = c["kinds"]
    _keys(kinds, "kinds", ["deposit"], tuple(kinds))
    for kind, row in kinds.items():
        _keys(row, f"kinds.{kind}", ("liquidity", "income", "simplicity"))
        for name, v in row.items():
            _num(v, f"kinds.{kind}.{name}", 0, 1)
    if not isinstance(c["fund_kinds"], Mapping):
        raise ConfigError("fund_kinds: must be a mapping")
    for category, kind in c["fund_kinds"].items():
        if kind is not None and (kind == "deposit" or kind not in kinds):
            raise ConfigError(f"fund_kinds.{category}: kind {kind!r} has no row in kinds")
    if not isinstance(c["fx_name_words"], list) or not all(
            isinstance(w, str) and w for w in c["fx_name_words"]):
        raise ConfigError("fx_name_words: must be a list of non-empty strings")

    _check_persona_tables(c)
    _check_scoring(c)

    _keys(c["texts"], "texts", TEXT_SECTIONS)
    _keys(c["texts"]["reasons"], "texts.reasons",
          (*CRITERIA, *(f"penalty:{p}" for p in PENALTY_RULES), "return_missing"))
    _keys(c["texts"]["constraint"], "texts.constraint", ("passed", "failed"))
    _keys(c["texts"]["questions"], "texts.questions",
          ("risk_profili", "acik_kisitlar", *SAFE_LEVEL_FIELDS, "reason"))
    _keys(c["texts"]["effect_labels"], "texts.effect_labels", tuple(c["constraint_effects"]))
    labels = list(c["texts"]["effect_labels"].values())
    if len(set(labels)) != len(labels):
        raise ConfigError("texts.effect_labels: labels must be unique")


def _check_persona_tables(c: dict) -> None:
    profiles = c["risk_profiles"]
    _table_keys(profiles, "risk_profiles")
    for name, p in profiles.items():
        _keys(p, f"risk_profiles.{name}", ("ceiling", "appetite"))
        if not isinstance(p["ceiling"], int) or not 1 <= p["ceiling"] <= 7:
            raise ConfigError(f"risk_profiles.{name}.ceiling: must be an integer 1..7")
        _num(p["appetite"], f"risk_profiles.{name}.appetite", 0, 1)

    h = c["horizon"]
    _keys(h, "horizon", ("periods", "years", "fallback"))
    years = h["years"]
    for k, v in years.items():
        _num(v, f"horizon.years.{k}", 0)
    periods = h["periods"]
    if not periods or periods[-1].get("max_years") is not None:
        raise ConfigError("horizon.periods: the last entry must have max_years null")
    for i, p in enumerate(periods):
        _keys(p, f"horizon.periods[{i}]", ("max_years", "period"))
        if p["period"] not in years:
            raise ConfigError(f"horizon.periods[{i}]: period {p['period']!r} not in years")
    for p in h["fallback"]:
        if p not in years:
            raise ConfigError(f"horizon.fallback: period {p!r} not in years")

    for table in ("levels", "fx_levels"):
        _table_keys(c[table], table)
        for k, v in c[table].items():
            _num(v, f"{table}.{k}", 0, 1)

    safe = c["safe_levels"]
    _keys(safe, "safe_levels", SAFE_LEVEL_FIELDS)
    for field, v in safe.items():
        allowed = (years if field == "yatirim_ufku"
                   else c["fx_levels"] if field == "doviz_maruz_kalma_tercihi"
                   else c["levels"])
        if v not in allowed:
            raise ConfigError(f"safe_levels.{field}: {v!r} is not a known level")

    _table_keys(c["priorities"], "priorities")
    for phrase, effect in c["priorities"].items():
        kind, _, arg = str(effect).partition(":")
        ok = ((kind == "boost" and arg in CRITERIA) or (effect == "diversity")
              or (kind == "note" and arg in c["texts"]["assumptions"]))
        if not ok:
            raise ConfigError(f"priorities.{phrase}: unknown effect {effect!r}")
    _num(c["priority_boost"], "priority_boost", 0)

    effects = c["constraint_effects"]
    if "ignore" not in effects:
        raise ConfigError("constraint_effects: an 'ignore' entry is required")
    for name, e in effects.items():
        _keys(e, f"constraint_effects.{name}", (), EFFECT_KEYS)
        for k, v in e.items():
            if k == "diversity":
                if v is not True:
                    raise ConfigError(f"constraint_effects.{name}.diversity: must be true")
            elif k == "max_ceiling":
                if not isinstance(v, int) or not 1 <= v <= 7:
                    raise ConfigError(f"constraint_effects.{name}.max_ceiling: must be 1..7")
            else:
                _num(v, f"constraint_effects.{name}.{k}", 0, 1)
    _table_keys(c["constraints"], "constraints")
    for phrase, effect in c["constraints"].items():
        if effect not in effects:
            raise ConfigError(f"constraints.{phrase}: unknown effect {effect!r}")


def _check_scoring(c: dict) -> None:
    pv = c["principal_value"]
    _keys(pv, "principal_value", ("deposit", "fund_base", "fund_step"))
    for k, v in pv.items():
        _num(v, f"principal_value.{k}", 0, 1)

    weights = c["weights"]
    _keys(weights, "weights", CRITERIA)
    for crit, w in weights.items():
        path = f"weights.{crit}"
        _keys(w, path, ("base",), ("appetite", "level", "per_level"))
        if ("level" in w) != ("per_level" in w):
            raise ConfigError(f"{path}: level and per_level go together")
        if "level" in w and w["level"] not in LEVEL_FIELDS:
            raise ConfigError(f"{path}.level: {w['level']!r} is not one of {LEVEL_FIELDS}")
        base = _num(w["base"], f"{path}.base", 0)
        _num(w.get("per_level", 0), f"{path}.per_level", 0)
        appetite = _num(w.get("appetite", 0), f"{path}.appetite")
        # appetite is 0..1, so the lowest raw weight is base + min(0, appetite).
        if base + min(0.0, appetite) < 0:
            raise ConfigError(f"{path}: the raw weight is < 0 for some appetite")

    _keys(c["penalties"], "penalties", PENALTIES)
    for k, v in c["penalties"].items():
        _num(v, f"penalties.{k}", 0)
    _keys(c["fund_size_min"], "fund_size_min", ("total_value_try", "investors"))
    for k, v in c["fund_size_min"].items():
        _num(v, f"fund_size_min.{k}", 0)
        if v == 0:
            raise ConfigError(f"fund_size_min.{k}: must be > 0")

    d = c["display"]
    _keys(d, "display", ("first", "first_cap", "shortlist", "cap", "diversity_cap"))
    for k, v in d.items():
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise ConfigError(f"display.{k}: must be an integer >= 1")
    if d["first"] > d["shortlist"]:
        raise ConfigError("display.first: must be <= display.shortlist")

    conf = c["confidence"]
    _keys(conf, "confidence", ("flags", "risk_estimate", "shorter_period"))
    known = {f.value for f in Flag}
    for flag, v in conf["flags"].items():
        if flag not in known:
            raise ConfigError(f"confidence.flags.{flag}: unknown flag")
        _num(v, f"confidence.flags.{flag}", 0, 1)
    _num(conf["risk_estimate"], "confidence.risk_estimate", 0, 1)
    _num(conf["shorter_period"], "confidence.shorter_period", 0, 1)

    _keys(c["stability"], "stability", ("step",))
    _num(c["stability"]["step"], "stability.step", 0, 1)
    _keys(c["warnings"], "warnings", ("low_stability_below", "deposit_vs_market_points"))
    _num(c["warnings"]["low_stability_below"], "warnings.low_stability_below", 0, 1)
    _num(c["warnings"]["deposit_vs_market_points"], "warnings.deposit_vs_market_points", 0)
