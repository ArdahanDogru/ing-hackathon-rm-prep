"""Load and check config/decision.yaml (docs/decision.md section 7).

`load_raw` reads the YAML; `parse_config` checks a plain dict and wraps a deep
copy of it. The engine reads the tables from `DecisionConfig.raw`; stability
(section 5) builds changed copies of the raw dict and parses them again.
"""

from __future__ import annotations

import copy
import dataclasses
import string
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from rmprep.contracts import (
    ACTIVE_HOLDINGS_SOURCES,
    ALLOCATION_CLASSES,
    WARNING_AUDIENCES,
    Flag,
    Persona,
)
from rmprep.decision.text import fold, normalize

CONFIG_VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "decision.yaml"

# option kinds scored from a rate row (risk 1, quality 1); not fund kinds
DEPOSIT_KINDS = ("deposit", "time_deposit")
CRITERIA = ("return", "low_risk", "liquidity", "income", "principal", "simplicity", "quality")


def criteria(c: Mapping[str, Any]) -> tuple[str, ...]:
    """The criteria of a config: with the risk_fit section (D19) risk_fit replaces
    low_risk."""
    if "risk_fit" in c:
        return tuple("risk_fit" if k == "low_risk" else k for k in CRITERIA)
    return CRITERIA
LEVEL_FIELDS = ("likidite_ihtiyaci", "gelir_nakit_akisi_ihtiyaci", "anapara_koruma_tercihi")
SAFE_LEVEL_FIELDS = ("yatirim_ufku", *LEVEL_FIELDS, "doviz_maruz_kalma_tercihi")
PENALTY_RULES = ("principal", "liquidity", "fx_exposure", "risk_unknown", "track_record",
                 "fund_size")
PENALTIES = (*PENALTY_RULES, "risk_unknown_above_ceiling_factor")
EFFECT_KEYS = ("max_ceiling", "min_fx_intensity", "liquidity_weight", "liquidity_intensity",
               "min_liquidity_intensity", "diversity")
TEXT_SECTIONS = ("reasons", "constraint", "questions", "effect_labels", "assumptions",
                 "warnings", "data_quality")

# optional sections of D9 (real return after tax); without them: nominal returns
WARNING_CODES = ("concentration", "fx_exposure", "risk_estimate", "low_stability",
                 "deposit_vs_market", "no_fx_deposit_data", "stale_tax_input",
                 "single_stock", "stock_crash")
RM_ONLY_WARNINGS = ("stale_tax_input", "single_stock", "stock_crash")   # never for the client (D22, D26)
TALKING_CODES = ("deposit_real", "best_alternative", "access", "risk_fit")
_D9_SECTIONS = ("holdings", "allocation_gap", "etf", "stock", "risk_estimate", "allocation", "asset_classes", "risk_fit", "recommend", "talking_points", "to_confirm", "real_return", "long_horizon", "quality_value", "underperformance",
                "fund_detail", "constraint_rules", "short_history")
_TOP = ("version", "deposit", "fund_kinds", "fx_name_words", "risk_profiles", "horizon",
        "levels", "fx_levels", "safe_levels", "priorities", "priority_boost", "constraints",
        "constraint_effects", "kinds", "principal_value", "weights", "penalties",
        "fund_size_min", "display", "confidence", "stability", "warnings", "texts")


class ConfigError(ValueError):
    """Invalid decision config. The message starts with the path of the bad key."""


@dataclass(frozen=True)
class DecisionConfig:
    raw: Mapping[str, Any]      # the checked config, as parsed (do not change it)

    @property
    def criteria(self) -> tuple[str, ...]:
        return criteria(self.raw)

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
    _keys(c, "config", _TOP, ("time_deposit", *_D9_SECTIONS))
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
        if kind is not None and (kind in DEPOSIT_KINDS or kind not in kinds):
            raise ConfigError(f"fund_kinds.{category}: kind {kind!r} has no row in kinds")
    if "time_deposit" in c:      # optional section (D8)
        _keys(c["time_deposit"], "time_deposit", ("option_id", "label", "source", "quantity",
                                                  "entity_prefix", "term", "tier"),
              ("term_days",))
        days = c["time_deposit"].get("term_days", 1)
        if not isinstance(days, int) or isinstance(days, bool) or days < 1:
            raise ConfigError(f"time_deposit.term_days: must be an integer >= 1, got {days!r}")
        if "time_deposit" not in kinds:
            raise ConfigError("kinds: the time_deposit section needs a time_deposit row")
        if "time_deposit_missing" not in c["texts"]["data_quality"]:
            raise ConfigError("texts.data_quality: the time_deposit section needs "
                              "time_deposit_missing")
    if not isinstance(c["fx_name_words"], list) or not all(
            isinstance(w, str) and w for w in c["fx_name_words"]):
        raise ConfigError("fx_name_words: must be a list of non-empty strings")

    _check_persona_tables(c)
    _check_scoring(c)

    _keys(c["texts"], "texts", TEXT_SECTIONS, ("holdings",))       # D27
    _keys(c["texts"]["reasons"], "texts.reasons",
          (*criteria(c), *(f"penalty:{p}" for p in PENALTY_RULES), "return_missing"),
          ("low_risk", "risk_fit", "class_rule", "return_real", "return_net",
           "penalty:risk_unknown_class", "holdings_class",
           "return_period", "return_period_net", "return_period_real",
           "allocation_gap", "allocation_gap_inactive", "allocation_gap_no_band",
           "penalty:real_loss", "penalty:underperformance", "liquidity_valor", "fees"))
    if "real_loss" in c["penalties"] and "penalty:real_loss" not in c["texts"]["reasons"]:
        raise ConfigError("texts.reasons: penalties.real_loss needs penalty:real_loss")
    _check_d9(c)
    _check_exchange(c)
    _check_holdings(c)
    _keys(c["texts"]["constraint"], "texts.constraint", ("passed", "failed"),
          ("not_buyable", "buyable", "fx_limit", "liquidity_need_valor",
           "liquidity_need_lock", "short_history", "stock_risk", "stock_risk_missing",
           "stock_risk_5y"))
    # D26c: returns of a period shorter than 1 year (not annualised)
    for key in ("return_period", "return_period_net", "return_period_real"):
        text = c["texts"]["reasons"].get(key)
        if text is None:
            continue
        allowed = {"months", "period", "horizon", "nominal", "net", "real", "loss",
                   "benchmark", "value", "pct", "fees", "years"}
        if not isinstance(text, str) or not text.strip() or not {
                f for _, f, _, _ in string.Formatter().parse(text) if f} <= allowed:
            raise ConfigError(f"texts.reasons.{key}: a text with only the fields "
                              f"{sorted(allowed)}")
    _keys(c["texts"]["questions"], "texts.questions",
          ("risk_profili", "acik_kisitlar", *SAFE_LEVEL_FIELDS, "reason"),
          ("override_fx_limit", "override_reason"))
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
        ok = ((kind == "boost" and arg in criteria(c)) or (effect == "diversity")
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
    _keys(pv, "principal_value", ("deposit", "fund_base", "fund_step"), ("time_deposit",))
    for k, v in pv.items():
        _num(v, f"principal_value.{k}", 0, 1)

    weights = c["weights"]
    _keys(weights, "weights", criteria(c), ("allocation_gap",))      # D27
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

    _keys(c["penalties"], "penalties", PENALTIES, ("real_loss", "underperformance"))
    for k, v in c["penalties"].items():
        _num(v, f"penalties.{k}", 0)
    _keys(c["fund_size_min"], "fund_size_min", ("total_value_try", "investors"))
    for k, v in c["fund_size_min"].items():
        _num(v, f"fund_size_min.{k}", 0)
        if v == 0:
            raise ConfigError(f"fund_size_min.{k}: must be > 0")

    d = c["display"]
    _keys(d, "display", ("first", "first_cap", "shortlist", "cap", "diversity_cap"),
          ("pool", "diversity_pool_cap", "why", "access"))
    if ("pool" in d) != ("diversity_pool_cap" in d):
        raise ConfigError("display: pool and diversity_pool_cap go together")
    _check_display_texts(d, criteria(c))
    for k, v in d.items():
        if k in ("why", "access"):
            continue
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise ConfigError(f"display.{k}: must be an integer >= 1")
    if d["first"] > d["shortlist"]:
        raise ConfigError("display.first: must be <= display.shortlist")
    if d.get("pool", d["shortlist"]) < d["shortlist"]:
        raise ConfigError("display.pool: must be >= display.shortlist")

    conf = c["confidence"]
    _keys(conf, "confidence", ("flags", "risk_estimate", "shorter_period"),
          ("liquidity_proxy", "real_return_missing"))
    known = {f.value for f in Flag}
    for flag, v in conf["flags"].items():
        if flag not in known:
            raise ConfigError(f"confidence.flags.{flag}: unknown flag")
        _num(v, f"confidence.flags.{flag}", 0, 1)
    _num(conf["risk_estimate"], "confidence.risk_estimate", 0, 1)
    _num(conf["shorter_period"], "confidence.shorter_period", 0, 1)
    _num(conf.get("liquidity_proxy", 1.0), "confidence.liquidity_proxy", 0, 1)
    _num(conf.get("real_return_missing", 1.0), "confidence.real_return_missing", 0, 1)   # D24

    _keys(c["stability"], "stability", ("step",), ("size",))
    _num(c["stability"]["step"], "stability.step", 0, 1)
    size = c["stability"].get("size", d["shortlist"])     # optional; default display.shortlist
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ConfigError(f"stability.size: must be an integer >= 1, got {size!r}")
    _keys(c["warnings"], "warnings", ("low_stability_below", "deposit_vs_market_points"),
          ("audience",))
    audience = c["warnings"].get("audience", {})
    if not isinstance(audience, Mapping):
        raise ConfigError("warnings.audience: must be a mapping code -> client|rm")
    for code, who in audience.items():
        if code not in WARNING_CODES or who not in WARNING_AUDIENCES:
            raise ConfigError(f"warnings.audience.{code}: a code of {WARNING_CODES} -> "
                              f"one of {WARNING_AUDIENCES}")
        if code in RM_ONLY_WARNINGS and who != "rm":
            raise ConfigError(f"warnings.audience.{code}: this warning is for the RM only")
    stale = c["texts"]["warnings"].get("stale_tax_input")      # D22, optional
    if stale is not None:
        if not isinstance(stale, str) or not stale.strip():
            raise ConfigError("texts.warnings.stale_tax_input: must be a non-empty text")
        if not {f for _, f, _, _ in string.Formatter().parse(stale) if f} <= {"entities"}:
            raise ConfigError("texts.warnings.stale_tax_input: only the field {entities} "
                              "is filled")
    _num(c["warnings"]["low_stability_below"], "warnings.low_stability_below", 0, 1)
    _num(c["warnings"]["deposit_vs_market_points"], "warnings.deposit_vs_market_points", 0)


HOLDINGS_GROUPS = ("fon", "ignore")     # by_holdings.labels groups that are not classes


def _fields(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def _check_by_holdings(c: dict, fund_kinds: set[str]) -> set[str]:
    """Optional D23 section asset_classes.by_holdings; returns its classes."""
    bh = c["asset_classes"]["by_holdings"]
    path = "asset_classes.by_holdings"
    _keys(bh, path, ("kinds", "fx_debt_kinds", "min_share", "labels", "class_labels"))
    for key in ("kinds", "fx_debt_kinds"):
        if not isinstance(bh[key], list) or not set(bh[key]) <= fund_kinds:
            raise ConfigError(f"{path}.{key}: a list of fund kinds of {sorted(fund_kinds)}")
    _num(bh["min_share"], f"{path}.min_share", 0, 100)
    if bh["min_share"] <= 0:
        raise ConfigError(f"{path}.min_share: must be > 0")
    labels = bh["labels"]
    if not isinstance(labels, Mapping):
        raise ConfigError(f"{path}.labels: a mapping class -> list of kiymetTip texts")
    seen: dict[str, str] = {}
    for cls, texts in labels.items():
        if not isinstance(texts, list) or not texts:
            raise ConfigError(f"{path}.labels.{cls}: a non-empty list of texts")
        for text in texts:
            key = fold(text) if isinstance(text, str) else ""
            if not key:
                raise ConfigError(f"{path}.labels.{cls}: {text!r} has no letter or digit")
            if key in seen:
                raise ConfigError(f"{path}.labels: {text!r} and {seen[key]!r} match the "
                                  "same texts")
            seen[key] = text
    classes = set(labels) - set(HOLDINGS_GROUPS)
    _keys(bh["class_labels"], f"{path}.class_labels", sorted(classes))
    for cls, label in bh["class_labels"].items():
        if not isinstance(label, str) or not label.strip():
            raise ConfigError(f"{path}.class_labels.{cls}: must be a non-empty text")
    for section, key, allowed in (("reasons", "holdings_class", {"share", "label"}),
                                  ("data_quality", "unknown_holding_type", {"text", "count"})):
        text = c["texts"][section].get(key)
        if not isinstance(text, str) or not text.strip():
            raise ConfigError(f"texts.{section}.{key}: {path} needs this text")
        if not _fields(text) <= allowed:
            raise ConfigError(f"texts.{section}.{key}: only the fields {sorted(allowed)}")
    return classes


def _check_d19(c: dict) -> None:
    """Optional D19 sections: asset_classes, risk_fit, recommend."""
    classes: set[str] = set()
    if "asset_classes" in c:
        ac = c["asset_classes"]
        _keys(ac, "asset_classes", ("by_name", "by_kind", "fx"), ("by_risk", "by_holdings"))
        kinds = {"deposit", "time_deposit", *(k for k in c["fund_kinds"].values() if k)}
        by_kind = ac["by_kind"]
        _keys(by_kind, "asset_classes.by_kind", sorted(kinds))
        for path, table in (("asset_classes.by_name", ac["by_name"]),
                            ("asset_classes.by_kind", by_kind)):
            if not isinstance(table, Mapping):
                raise ConfigError(f"{path}: must be a mapping")
            for k, v in table.items():
                if not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v:
                    raise ConfigError(f"{path}.{k}: a non-empty text -> a class name")
        if not isinstance(ac["fx"], str) or not ac["fx"]:
            raise ConfigError("asset_classes.fx: must be a class name")
        classes = {*by_kind.values(), *ac["by_name"].values(), ac["fx"]}
        by_risk = ac.get("by_risk", {})         # D19c: fund_kind -> [{min_risk, class}]
        if not isinstance(by_risk, Mapping):
            raise ConfigError("asset_classes.by_risk: must be a mapping fund_kind -> list")
        for kind, rules in by_risk.items():
            path = f"asset_classes.by_risk.{kind}"
            if kind not in kinds - {"deposit", "time_deposit"} or not isinstance(rules, list):
                raise ConfigError(f"{path}: a fund kind with a list of rules")
            for i, rule in enumerate(rules):
                _keys(rule, f"{path}[{i}]", ("min_risk", "class"))
                v = rule["min_risk"]
                if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 7:
                    raise ConfigError(f"{path}[{i}].min_risk: an integer 1..7")
                if not isinstance(rule["class"], str) or not rule["class"]:
                    raise ConfigError(f"{path}[{i}].class: a class name")
                classes.add(rule["class"])
        if "by_holdings" in ac:
            classes |= _check_by_holdings(c, kinds - {"deposit", "time_deposit"})

    if "risk_fit" in c:
        rf = c["risk_fit"]
        _keys(rf, "risk_fit", ("bands", "per_step"))
        _keys(rf["bands"], "risk_fit.bands", tuple(c["risk_profiles"]))
        for name, band in rf["bands"].items():
            ok = (isinstance(band, list) and len(band) == 2
                  and all(isinstance(x, int) and not isinstance(x, bool) for x in band)
                  and 1 <= band[0] <= band[1] <= 7)
            if not ok:
                raise ConfigError(f"risk_fit.bands.{name}: [low, high] with 1 <= low <= high <= 7")
        _num(rf["per_step"], "risk_fit.per_step", 0, 1)

    if "recommend" in c:
        rec = c["recommend"]
        _keys(rec, "recommend", ("max_per_class", "max_cash_like", "cash_like", "profiles"),
              ("min_real_return",))
        if "min_real_return" in rec:        # D19b: percent, e.g. 0.0
            _num(rec["min_real_return"], "recommend.min_real_return")
        for key in ("max_per_class", "max_cash_like"):
            v = rec[key]
            if not isinstance(v, int) or isinstance(v, bool) or v < 1:
                raise ConfigError(f"recommend.{key}: must be an integer >= 1")
        if "asset_classes" not in c:
            raise ConfigError("recommend: needs the asset_classes section")
        if rec["cash_like"] not in classes:
            raise ConfigError(f"recommend.cash_like: {rec['cash_like']!r} is not a class of "
                              "asset_classes")
        if not isinstance(rec["profiles"], list) or not set(rec["profiles"]) <= set(
                c["risk_profiles"]):
            raise ConfigError("recommend.profiles: a list of risk_profiles names")
        _text(c, "reasons", "class_rule", "the recommend section")
        _text(c, "assumptions", "class_rule", "the recommend section")

    if "risk_estimate" in c:        # D21: risk estimate by asset class
        re_ = c["risk_estimate"]
        _keys(re_, "risk_estimate", (), ("by_class_quantile", "min_known"))
        q = re_.get("by_class_quantile", 0.75)
        if _num(q, "risk_estimate.by_class_quantile", 0, 1) <= 0:
            raise ConfigError("risk_estimate.by_class_quantile: must be > 0")
        n = re_.get("min_known", 5)
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ConfigError("risk_estimate.min_known: must be an integer >= 1")

    if "allocation" in c:           # D20: model allocation bands
        if "asset_classes" not in c:
            raise ConfigError("allocation: needs the asset_classes section")
        _check_allocation(c, classes)


def _check_allocation(c: dict, classes: set[str]) -> None:
    al = c["allocation"]
    _keys(al, "allocation", ("classes", "profiles", "note_texts", "holding_hints",
                             "holding_confirm"))
    order = al["classes"]
    if (not isinstance(order, list) or not order or len(set(order)) != len(order)
            or not set(order) <= classes):
        raise ConfigError(f"allocation.classes: different classes of asset_classes {sorted(classes)}")
    _keys(al["profiles"], "allocation.profiles", tuple(c["risk_profiles"]))
    for name, p in al["profiles"].items():
        path = f"allocation.profiles.{name}"
        _keys(p, path, ("source", "inferred", "bands"))
        if not isinstance(p["source"], str) or not p["source"].strip():
            raise ConfigError(f"{path}.source: a non-empty text")
        if not isinstance(p["inferred"], bool):
            raise ConfigError(f"{path}.inferred: true or false")
        if not isinstance(p["bands"], Mapping):
            raise ConfigError(f"{path}.bands: a mapping class -> [low, high]")
        for cls, band in p["bands"].items():
            ok = (cls in order and isinstance(band, list) and len(band) == 2
                  and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in band)
                  and 0 <= band[0] <= band[1] <= 100)
            if not ok:
                raise ConfigError(f"{path}.bands.{cls}: a class of allocation.classes -> "
                                  "[low, high] with 0 <= low <= high <= 100")
    _keys(al["note_texts"], "allocation.note_texts", ("ceiling", "none", "negative_real"))
    hints = al["holding_hints"]
    if not isinstance(hints, Mapping) or not all(
            isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
            for k, v in hints.items()):
        raise ConfigError("allocation.holding_hints: a mapping keyword -> text")
    for key in ("holding_confirm",):
        if not isinstance(al[key], str) or not al[key].strip():
            raise ConfigError(f"allocation.{key}: a non-empty text")
    for key, text in al["note_texts"].items():
        if not isinstance(text, str) or not text.strip():
            raise ConfigError(f"allocation.note_texts.{key}: a non-empty text")


def _check_display_texts(d: Mapping[str, Any], crits: tuple[str, ...]) -> None:
    """Optional web UI texts (D17): display.why (criterion -> text) needs
    display.access (texts of the "Paraya erişim" value)."""
    if "why" in d:
        why = d["why"]
        if not isinstance(why, Mapping):
            raise ConfigError("display.why: must be a mapping criterion -> text")
        for crit, text in why.items():
            if crit not in crits or not isinstance(text, str) or not text.strip():
                raise ConfigError(f"display.why.{crit}: a criterion of {crits} with a text")
        if "access" not in d:
            raise ConfigError("display.access: display.why needs the access texts")
    if "access" in d:
        _keys(d["access"], "display.access", ("same_day", "days", "term"), ("exchange",))
        for k, v in d["access"].items():
            if k == "exchange":         # D26: ETFs and shares, a text per language
                _keys(v, "display.access.exchange", ("TR", "EN"))
                texts = list(v.values())
            else:
                texts = [v]
            if not all(isinstance(t, str) and t.strip() for t in texts):
                raise ConfigError(f"display.access.{k}: must be a non-empty text")


def _shares(d: Any, path: str) -> None:
    """A split over ALLOCATION_CLASSES: every class, each 0..100, total 100."""
    _keys(d, path, ALLOCATION_CLASSES)
    for k, v in d.items():
        _num(v, f"{path}.{k}", 0, 100)
    if abs(sum(d.values()) - 100) > 1e-6:
        raise ConfigError(f"{path}: the shares must add up to 100, got {sum(d.values())}")


def _fields_of(text: Any) -> set[str] | None:
    if not isinstance(text, str) or not text.strip():
        return None
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def _check_holdings(c: dict) -> None:
    """Optional D27 sections holdings and allocation_gap (docs/decision.md section 17)."""
    if "holdings" not in c:
        for key in ("allocation_gap",):
            if key in c:
                raise ConfigError(f"{key}: needs the holdings section")
        if "allocation_gap" in c["weights"]:
            raise ConfigError("weights.allocation_gap: needs the holdings section")
        return
    for key in ("allocation", "asset_classes"):
        if key not in c:
            raise ConfigError(f"{key}: the holdings section needs it")
    if tuple(c["allocation"]["classes"]) != ALLOCATION_CLASSES:
        raise ConfigError(f"allocation.classes: must be {ALLOCATION_CLASSES} for holdings")
    h = c["holdings"]
    _keys(h, "holdings", ("national", "profiles", "text_rules", "spread"))
    _keys(h["national"], "holdings.national", ("label", "source", "url", "shares"))
    _shares(h["national"]["shares"], "holdings.national.shares")
    if not isinstance(h["profiles"], list):
        raise ConfigError("holdings.profiles: a list of rows")
    for i, row in enumerate(h["profiles"]):
        path = f"holdings.profiles[{i}]"
        _keys(row, path, ("match", "label", "rule", "source", "shares"))
        if not isinstance(row["match"], list) or not row["match"] or not all(
                isinstance(w, str) and w.strip() for w in row["match"]):
            raise ConfigError(f"{path}.match: a non-empty list of words")
        _shares(row["shares"], f"{path}.shares")
    persona_fields = {f.name for f in dataclasses.fields(Persona)}
    if not isinstance(h["text_rules"], list):
        raise ConfigError("holdings.text_rules: a list of rules")
    ids: set[str] = set()
    for i, rule in enumerate(h["text_rules"]):
        path = f"holdings.text_rules[{i}]"
        _keys(rule, path, ("id", "fields", "match", "class", "range"), ("note",))
        if not isinstance(rule["id"], str) or not rule["id"] or rule["id"] in ids:
            raise ConfigError(f"{path}.id: a unique non-empty id")
        ids.add(rule["id"])
        if (not isinstance(rule["fields"], list) or not rule["fields"]
                or not set(rule["fields"]) <= persona_fields):
            raise ConfigError(f"{path}.fields: persona fields")
        if not isinstance(rule["match"], str) or not rule["match"].strip():
            raise ConfigError(f"{path}.match: a non-empty phrase")
        if rule["class"] not in ALLOCATION_CLASSES:
            raise ConfigError(f"{path}.class: one of {ALLOCATION_CLASSES}")
        rg = rule["range"]
        if not (isinstance(rg, list) and len(rg) == 2 and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) for x in rg)
                and 0 <= rg[0] <= rg[1] <= 100):
            raise ConfigError(f"{path}.range: [low, high] with 0 <= low <= high <= 100")
    _num(h["spread"], "holdings.spread", 0, 100)

    th = c["texts"].get("holdings")
    _keys(th, "texts.holdings", ("source_labels", "class_labels", "to_confirm"))
    _keys(th["source_labels"], "texts.holdings.source_labels", ACTIVE_HOLDINGS_SOURCES)
    _keys(th["class_labels"], "texts.holdings.class_labels", ALLOCATION_CLASSES)
    for k, v in (*th["source_labels"].items(), *th["class_labels"].items(),
                 ("to_confirm", th["to_confirm"])):
        if _fields_of(v) is None:
            raise ConfigError(f"texts.holdings.{k}: must be a non-empty text")

    if "allocation_gap" not in c:
        return
    ag = c["allocation_gap"]
    _keys(ag, "allocation_gap", ("scale", "overweight_factor", "per_signal", "max_signals",
                                 "source_factor", "signals"))
    if _num(ag["scale"], "allocation_gap.scale", 0) <= 0:
        raise ConfigError("allocation_gap.scale: must be > 0")
    _num(ag["overweight_factor"], "allocation_gap.overweight_factor", 0)
    _num(ag["per_signal"], "allocation_gap.per_signal", 0)
    v = ag["max_signals"]
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        raise ConfigError("allocation_gap.max_signals: an integer >= 0")
    _keys(ag["source_factor"], "allocation_gap.source_factor", ACTIVE_HOLDINGS_SOURCES)
    for k, f in ag["source_factor"].items():
        _num(f, f"allocation_gap.source_factor.{k}", 0)
    if not isinstance(ag["signals"], list) or not all(
            isinstance(x, str) and x.strip() for x in ag["signals"]):
        raise ConfigError("allocation_gap.signals: a list of phrases")
    if "allocation_gap" not in c["weights"]:
        raise ConfigError("weights.allocation_gap: the allocation_gap section needs it")
    why = "the allocation_gap section"
    allowed = {"allocation_gap": {"class_label", "source_label", "current", "profile", "low",
                                  "high"},
               "allocation_gap_inactive": {"class_label"},
               "allocation_gap_no_band": {"class_label"}}
    for key, ok in allowed.items():
        _text(c, "reasons", key, why)
        fields = _fields_of(c["texts"]["reasons"][key])
        if fields is None or not fields <= ok:
            raise ConfigError(f"texts.reasons.{key}: only the fields {sorted(ok)}")


def _check_exchange(c: dict) -> None:
    """Optional D26 sections etf and stock (docs/decision.md section 16)."""
    for kind in ("etf", "stock"):
        if kind not in c:
            continue
        if kind not in c["kinds"]:
            raise ConfigError(f"kinds: the {kind} section needs a {kind} row")
        if not isinstance(c[kind], Mapping):
            raise ConfigError(f"{kind}: must be a mapping")
        src = c[kind].get("source")
        if not isinstance(src, str) or not src:
            raise ConfigError(f"{kind}.source: must be a source name")
        _text(c, "data_quality", "excluded_exchange_groups", f"the {kind} section")
    if "etf" in c:
        et = c["etf"]
        _keys(et, "etf", ("source", "by_name", "default_class"))
        if not isinstance(et["by_name"], Mapping) or not all(
                isinstance(k, str) and k.strip() and isinstance(v, str) and v
                for k, v in et["by_name"].items()):
            raise ConfigError("etf.by_name: a mapping name phrase -> class name")
        if not isinstance(et["default_class"], str) or not et["default_class"]:
            raise ConfigError("etf.default_class: must be a class name")
    if "stock" in c:
        st = c["stock"]
        _keys(st, "stock", ("source", "risk_floor", "min_turnover_try", "max_in_top3",
                            "spk_bands", "asset_class"), ("exclude_markets", "crash_1m_pct"))
        if "crash_1m_pct" in st:        # 2026-10-14: a warning for a share in a crash
            v = st["crash_1m_pct"]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not -100 < v < 0:
                raise ConfigError("stock.crash_1m_pct: a 1-month return in % between -100 and 0")
            _text(c, "warnings", "stock_crash", "stock.crash_1m_pct")
            text = c["texts"]["warnings"]["stock_crash"]
            if not {f for _, f, _, _ in string.Formatter().parse(text) if f} <= {"name", "ret"}:
                raise ConfigError("texts.warnings.stock_crash: only the fields {name} {ret}")
        if "exclude_markets" in st:     # D26b: PAZAR codes of EntityInfo.category
            em = st["exclude_markets"]
            if not isinstance(em, list) or not all(isinstance(m, str) and m.strip()
                                                    for m in em):
                raise ConfigError("stock.exclude_markets: a list of market codes")
            _text(c, "data_quality", "removed_stock_market", "stock.exclude_markets")
            text = c["texts"]["data_quality"]["removed_stock_market"]
            if not {f for _, f, _, _ in string.Formatter().parse(text) if f} <= {
                    "count", "markets"}:
                raise ConfigError("texts.data_quality.removed_stock_market: only the fields "
                                  "{count} {markets}")
        for key, lo, hi in (("risk_floor", 1, 7), ("max_in_top3", 0, 3)):
            v = st[key]
            if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
                raise ConfigError(f"stock.{key}: an integer {lo}..{hi}")
        _num(st["min_turnover_try"], "stock.min_turnover_try", 0)
        bands = st["spk_bands"]
        ok = isinstance(bands, list) and bands and all(
            isinstance(b, list) and len(b) == 2 and not isinstance(b[0], bool)
            and isinstance(b[0], (int, float)) and b[0] > 0
            and isinstance(b[1], int) and not isinstance(b[1], bool) and 1 <= b[1] <= 6
            for b in bands)
        if ok:
            ok = all(a[0] < b[0] and a[1] < b[1] for a, b in zip(bands, bands[1:]))
        if not ok:
            raise ConfigError("stock.spk_bands: [[upper volatility %, risk 1..6], ...] with "
                              "both rising; above the last band the risk is 7")
        if not isinstance(st["asset_class"], str) or not st["asset_class"]:
            raise ConfigError("stock.asset_class: must be a class name")
        why = "the stock section"
        _text(c, "warnings", "single_stock", why)
        for key in ("stock_risk", "stock_risk_missing", "stock_risk_5y"):
            if key == "stock_risk_5y" and key not in c["texts"]["constraint"]:
                continue                # optional (D26c)
            _text(c, "constraint", key, why)
            text = c["texts"]["constraint"][key]
            fields = {f for _, f, _, _ in string.Formatter().parse(text) if f}
            allowed = {"risk", "ceiling", "volatility", "floor"}
            if not fields <= allowed:
                raise ConfigError(f"texts.constraint.{key}: only the fields {sorted(allowed)}")


def _text(c: dict, section: str, key: str, why: str) -> None:
    if key not in c["texts"][section]:
        raise ConfigError(f"texts.{section}: {why} needs {key}")


def _check_d9(c: dict) -> None:
    """Optional D9 sections: real_return, long_horizon, quality_value."""
    if "real_return" in c:
        rr = c["real_return"]
        _keys(rr, "real_return", ("cpi", "stopaj", "loss_scale"))
        _keys(rr["cpi"], "real_return.cpi", ("source", "quantity", "entity"))
        st = rr["stopaj"]
        _keys(st, "real_return.stopaj", ("source", "quantity", "deposit", "time_deposit",
                                         "fund_default"), ("fund_by_kind", "etf", "stock"))
        for path, d in (("real_return.cpi", rr["cpi"]), ("real_return.stopaj", st)):
            for k, v in d.items():
                if k != "fund_by_kind" and (not isinstance(v, str) or not v):
                    raise ConfigError(f"{path}.{k}: must be a non-empty string")
        by_kind = st.get("fund_by_kind", {})
        if not isinstance(by_kind, Mapping):
            raise ConfigError("real_return.stopaj.fund_by_kind: must be a mapping")
        fund_kinds = {k for k in c["fund_kinds"].values() if k is not None}
        for kind, entity in by_kind.items():
            if kind not in fund_kinds or not isinstance(entity, str) or not entity:
                raise ConfigError(f"real_return.stopaj.fund_by_kind.{kind}: unknown fund kind "
                                  "or empty entity")
        if _num(rr["loss_scale"], "real_return.loss_scale", 0) <= 0:
            raise ConfigError("real_return.loss_scale: must be > 0")
        why = "the real_return section"
        for key in ("return_real", "return_net"):
            _text(c, "reasons", key, why)
        for key in ("real_return_cpi", "real_return_no_cpi", "stopaj_equity",
                    "time_deposit_renewal"):
            _text(c, "assumptions", key, why)
        for key in ("cpi_missing", "stopaj_missing"):
            _text(c, "data_quality", key, why)

    if "long_horizon" in c:
        lh = c["long_horizon"]
        _keys(lh, "long_horizon", ("period", "liquidity_factor", "return_add"))
        periods = {p["period"] for p in c["horizon"]["periods"]}
        if lh["period"] not in periods:
            raise ConfigError(f"long_horizon.period: {lh['period']!r} is not a horizon period")
        _num(lh["liquidity_factor"], "long_horizon.liquidity_factor", 0)
        _num(lh["return_add"], "long_horizon.return_add", 0)

    if "underperformance" in c:
        _keys(c["underperformance"], "underperformance", ("scale",))
        if _num(c["underperformance"]["scale"], "underperformance.scale", 0) <= 0:
            raise ConfigError("underperformance.scale: must be > 0")
    if "underperformance" in c["penalties"]:
        why = "penalties.underperformance"
        if "underperformance" not in c:
            raise ConfigError(f"underperformance: {why} needs the underperformance section")
        _text(c, "reasons", "penalty:underperformance", why)
        _text(c, "data_quality", "benchmark_missing", why)

    if "fund_detail" in c:
        fd = c["fund_detail"]
        _keys(fd, "fund_detail", ("buyable_quantity", "sell_valor_quantity", "entry_fee_quantity",
                                  "exit_fee_quantity", "liquidity_by_sell_valor"))
        table = fd["liquidity_by_sell_valor"]
        path = "fund_detail.liquidity_by_sell_valor"
        if not isinstance(table, list) or not table or table[-1].get("max_days") is not None:
            raise ConfigError(f"{path}: a list whose last entry has max_days null")
        last = -1
        for i, row in enumerate(table):
            _keys(row, f"{path}[{i}]", ("max_days", "value"))
            _num(row["value"], f"{path}[{i}].value", 0, 1)
            days = row["max_days"]
            if i < len(table) - 1:
                if not isinstance(days, int) or isinstance(days, bool) or days <= last:
                    raise ConfigError(f"{path}[{i}].max_days: integers, increasing, >= 0")
                last = days
        why = "the fund_detail section"
        for section, key in (("constraint", "not_buyable"), ("constraint", "buyable"),
                             ("reasons", "liquidity_valor"), ("reasons", "fees"),
                             ("assumptions", "kind_proxy_valor"),
                             ("data_quality", "buyable_missing")):
            _text(c, section, key, why)

    if "constraint_rules" in c:     # D13: explicit constraints as hard rules
        cr = c["constraint_rules"]
        _keys(cr, "constraint_rules", (), ("fx_limit", "liquidity_need"))
        why = "constraint_rules"
        if "fx_limit" in cr:
            fx = cr["fx_limit"]
            _keys(fx, "constraint_rules.fx_limit", ("override_choices", "override_lifts"))
            choices = fx["override_choices"]
            if (not isinstance(choices, list) or len(choices) < 2
                    or len(set(choices)) != len(choices)
                    or not all(isinstance(x, str) and x for x in choices)):
                raise ConfigError("constraint_rules.fx_limit.override_choices: at least 2 "
                                  "different non-empty strings")
            if fx["override_lifts"] not in choices:
                raise ConfigError("constraint_rules.fx_limit.override_lifts: must be one of "
                                  "the override_choices")
            for section, key in (("constraint", "fx_limit"), ("questions", "override_fx_limit"),
                                 ("questions", "override_reason"),
                                 ("assumptions", "fx_override")):
                _text(c, section, key, why + ".fx_limit")
        if "liquidity_need" in cr:
            ln = cr["liquidity_need"]
            path = "constraint_rules.liquidity_need"
            _keys(ln, path, ("max_sell_valor_days", "max_lock_days"))
            for key, low in (("max_sell_valor_days", 0), ("max_lock_days", 1)):
                v = ln[key]
                if not isinstance(v, int) or isinstance(v, bool) or v < low:
                    raise ConfigError(f"{path}.{key}: must be an integer >= {low}")
            if "fund_detail" not in c:
                raise ConfigError(f"{path}: needs the fund_detail section (sell valör)")
            for section, key in (("constraint", "liquidity_need_valor"),
                                 ("constraint", "liquidity_need_lock"),
                                 ("data_quality", "valor_missing")):
                _text(c, section, key, why + ".liquidity_need")

    if "short_history" in c:        # D15
        sh = c["short_history"]
        _keys(sh, "short_history", ("min_period", "allow_appetite"))
        if sh["min_period"] not in c["horizon"]["years"]:
            raise ConfigError(f"short_history.min_period: {sh['min_period']!r} is not in "
                              "horizon.years")
        _num(sh["allow_appetite"], "short_history.allow_appetite", 0, 1)
        for section, key in (("constraint", "short_history"),
                             ("data_quality", "removed_no_data")):
            _text(c, section, key, "the short_history section")

    _check_d19(c)

    if "talking_points" in c:       # D18
        tp = c["talking_points"]
        _keys(tp, "talking_points", ("order", "deposit_keywords", "texts"))
        order = tp["order"]
        if (not isinstance(order, list) or not order or len(set(order)) != len(order)
                or not set(order) <= set(TALKING_CODES)):
            raise ConfigError(f"talking_points.order: different codes of {TALKING_CODES}")
        kw = tp["deposit_keywords"]
        if not isinstance(kw, list) or not all(isinstance(k, str) and k.strip() for k in kw):
            raise ConfigError("talking_points.deposit_keywords: a list of non-empty texts")
        texts = tp["texts"]
        _keys(texts, "talking_points.texts", order, tuple(TALKING_CODES))
        for code, t in texts.items():
            path = f"talking_points.texts.{code}"
            _keys(t, path, ("label", "text", *(("figure",) if code == "risk_fit" else ())))
            for k, v in t.items():
                if not isinstance(v, str) or not v.strip():
                    raise ConfigError(f"{path}.{k}: must be a non-empty text")
        if "access" in order and "access" not in c["display"]:
            raise ConfigError("display.access: talking_points access needs the access texts")

    if "to_confirm" in c:           # D16: assumption key (D22: or warning code) -> command
        table = c["to_confirm"]
        if not isinstance(table, Mapping):
            raise ConfigError("to_confirm: must be a mapping assumption key -> text")
        for key, text in table.items():
            if key not in c["texts"]["assumptions"] and key not in WARNING_CODES:
                raise ConfigError(f"to_confirm.{key}: not a key of texts.assumptions "
                                  "or a warning code")
            if not isinstance(text, str) or not text.strip():
                raise ConfigError(f"to_confirm.{key}: must be a non-empty text")
            fields = {f for _, f, _, _ in string.Formatter().parse(text) if f}
            if not fields <= {"tier"}:
                raise ConfigError(f"to_confirm.{key}: only the field {{tier}} is filled")

    if "quality_value" in c:
        qv = c["quality_value"]
        _keys(qv, "quality_value", ("deposit",), ("time_deposit",))
        for k, v in qv.items():
            _num(v, f"quality_value.{k}", 0, 1)
