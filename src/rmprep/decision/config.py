"""Load and check config/decision.yaml (docs/decision.md section 7).

`load_raw` reads the YAML; `parse_config` checks a plain dict and wraps a deep
copy of it. The engine reads the tables from `DecisionConfig.raw`; stability
(section 5) builds changed copies of the raw dict and parses them again.
"""

from __future__ import annotations

import copy
import string
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from rmprep.contracts import WARNING_AUDIENCES, Flag
from rmprep.decision.text import normalize

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
                 "deposit_vs_market", "no_fx_deposit_data", "stale_tax_input")
RM_ONLY_WARNINGS = ("stale_tax_input",)     # never for the client (D22)
TALKING_CODES = ("deposit_real", "best_alternative", "access", "risk_fit")
_D9_SECTIONS = ("risk_estimate", "allocation", "asset_classes", "risk_fit", "recommend", "talking_points", "to_confirm", "real_return", "long_horizon", "quality_value", "underperformance",
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

    _keys(c["texts"], "texts", TEXT_SECTIONS)
    _keys(c["texts"]["reasons"], "texts.reasons",
          (*criteria(c), *(f"penalty:{p}" for p in PENALTY_RULES), "return_missing"),
          ("low_risk", "risk_fit", "class_rule", "return_real", "return_net",
           "penalty:risk_unknown_class",
           "penalty:real_loss", "penalty:underperformance", "liquidity_valor", "fees"))
    if "real_loss" in c["penalties"] and "penalty:real_loss" not in c["texts"]["reasons"]:
        raise ConfigError("texts.reasons: penalties.real_loss needs penalty:real_loss")
    _check_d9(c)
    _keys(c["texts"]["constraint"], "texts.constraint", ("passed", "failed"),
          ("not_buyable", "buyable", "fx_limit", "liquidity_need_valor",
           "liquidity_need_lock", "short_history"))
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
    _keys(weights, "weights", criteria(c))
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
          ("liquidity_proxy",))
    known = {f.value for f in Flag}
    for flag, v in conf["flags"].items():
        if flag not in known:
            raise ConfigError(f"confidence.flags.{flag}: unknown flag")
        _num(v, f"confidence.flags.{flag}", 0, 1)
    _num(conf["risk_estimate"], "confidence.risk_estimate", 0, 1)
    _num(conf["shorter_period"], "confidence.shorter_period", 0, 1)
    _num(conf.get("liquidity_proxy", 1.0), "confidence.liquidity_proxy", 0, 1)

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


def _check_d19(c: dict) -> None:
    """Optional D19 sections: asset_classes, risk_fit, recommend."""
    classes: set[str] = set()
    if "asset_classes" in c:
        ac = c["asset_classes"]
        _keys(ac, "asset_classes", ("by_name", "by_kind", "fx"), ("by_risk",))
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
        _keys(d["access"], "display.access", ("same_day", "days", "term"))
        for k, v in d["access"].items():
            if not isinstance(v, str) or not v.strip():
                raise ConfigError(f"display.access.{k}: must be a non-empty text")


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
                                         "fund_default"), ("fund_by_kind",))
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
