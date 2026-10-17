"""Conflicting client information (W42, asked by the user 2026-10-17; lead-owned).

Fixed rules over the engine's own reading of the profile (`read_persona`: the risk
profile, the levels of liquidity, income and principal protection, the FX level,
the priority boosts and the constraint effects), so the check sees the profile
exactly as the scoring does. A finding names its fields; kind "conflict" (two
fields contradict each other) or "confirm" (a tension worth a question). The
texts are in config/profile_checks.yaml. Display only: the engine and the scores
do not change; the findings also go into "Teyit edin".
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from rmprep.contracts import DecisionResult, Persona
from rmprep.decision.config import DecisionConfig
from rmprep.decision.persona import read_persona

LOW, HIGH = 0.0, 1.0
CAUTIOUS = ("Muhafazakâr", "Temkinli")
RULE_IDS = ("risk_vs_growth", "aggressive_vs_protection", "liquidity_low_vs_need",
            "liquidity_high_vs_no_need", "income_low_vs_priority", "fx_open_vs_limit",
            "long_horizon_high_liquidity", "short_horizon_growth")


def load_texts(path: Path | str) -> dict:
    """config/profile_checks.yaml: rule id -> {kind, fields, TR, EN}; strict keys."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rules = raw.get("rules") if isinstance(raw, Mapping) else None
    if not isinstance(rules, Mapping) or set(rules) != set(RULE_IDS):
        raise ValueError(f"profile_checks: rules must be exactly {sorted(RULE_IDS)}")
    for rid, r in rules.items():
        if set(r) != {"kind", "fields", "TR", "EN"} or r["kind"] not in ("conflict", "confirm"):
            raise ValueError(f"profile_checks.rules.{rid}: keys kind, fields, TR, EN; kind conflict|confirm")
    return dict(rules)


def _priorities(persona: Persona, config: DecisionConfig, target: str) -> list[str]:
    """The client's priorities that the config maps to `target` (e.g. "boost:return")."""
    table = {k.casefold(): v for k, v in config.raw["priorities"].items()}
    return [p for p in persona.oncelikler if table.get(p.casefold()) == target]


def _constraints(persona: Persona, config: DecisionConfig, effect: str) -> list[str]:
    table = {k.casefold(): v for k, v in config.raw["constraints"].items()}
    return [c for c in persona.acik_kisitlar if table.get(c.casefold()) == effect]


def check(persona: Persona, config: DecisionConfig, texts: Mapping, lang: str = "TR",
          answers: Mapping[str, str] | None = None) -> list[dict]:
    """The findings of one profile, in RULE_IDS order: [{id, kind, fields, text}]."""
    reading = read_persona(persona, config, dict(answers or {}))
    lv = reading.levels
    if lv is None:                       # a blocking question is open: nothing to compare yet
        return []
    p = persona
    found: list[tuple[str, dict]] = []
    growth = _priorities(p, config, "boost:return")
    if lv.risk_profile in CAUTIOUS and growth:
        found.append(("risk_vs_growth", {"risk": p.risk_profili, "ceiling": lv.ceiling,
                                         "items": ", ".join(growth)}))
    protect = [*_priorities(p, config, "boost:principal"), *_constraints(p, config, "risk_cap")]
    if lv.principal >= HIGH:
        protect.insert(0, f"anapara koruma tercihi {p.anapara_koruma_tercihi}")
    if lv.risk_profile == "Agresif" and protect:
        found.append(("aggressive_vs_protection", {"risk": p.risk_profili, "items": ", ".join(protect)}))
    wants_cash = [*_priorities(p, config, "boost:liquidity"), *_constraints(p, config, "liquidity_need")]
    if lv.liquidity <= LOW and wants_cash:
        found.append(("liquidity_low_vs_need", {"level": p.likidite_ihtiyaci, "items": ", ".join(wants_cash)}))
    no_need = _constraints(p, config, "no_liquidity_need")
    if lv.liquidity >= HIGH and no_need:
        found.append(("liquidity_high_vs_no_need", {"level": p.likidite_ihtiyaci, "items": ", ".join(no_need)}))
    income = _priorities(p, config, "boost:income")
    if lv.income <= LOW and income:
        found.append(("income_low_vs_priority", {"level": p.gelir_nakit_akisi_ihtiyaci, "items": ", ".join(income)}))
    fx_limit = _constraints(p, config, "fx_limit")
    if lv.fx_level == "Açık" and fx_limit:
        found.append(("fx_open_vs_limit", {"fx": p.doviz_maruz_kalma_tercihi, "items": ", ".join(fx_limit)}))
    if lv.period == "3y" and lv.liquidity >= HIGH:
        found.append(("long_horizon_high_liquidity", {"horizon": p.yatirim_ufku, "level": p.likidite_ihtiyaci}))
    if lv.period == "6m" and growth:
        found.append(("short_horizon_growth", {"horizon": p.yatirim_ufku, "items": ", ".join(growth)}))
    out = []
    for rid, values in found:
        t = texts[rid]
        out.append({"id": rid, "kind": t["kind"], "fields": list(t["fields"]),
                    "text": t[lang].format(**values)})
    return out


def check_run(r: DecisionResult, config: DecisionConfig, texts: Mapping, lang: str = "TR") -> list[dict]:
    """The findings of a run's profile, with the RM's answers of the run."""
    answers = {q.question_id: q.answer for q in r.questions if q.answer is not None}
    return check(r.persona, config, texts, lang, answers)
