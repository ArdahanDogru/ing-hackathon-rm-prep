"""What the rules say about one run, computed again from the evidence, the
persona and config/decision.yaml - not with the decision code - so the checks
can catch a decision bug (docs/decision.md sections 1-3 are the reference).

- Evidence lookup (section 1): per (quantity, entity) the row with the latest
  as_of whose source is not excluded; a missing or out_of_range row counts as
  missing (an older row is then not used).
- Hard rules (section 2): risk_ceiling always; not_buyable with D12 (config
  section fund_detail); fx_limit and liquidity_need with D13 (config section
  constraint_rules), only when the persona carries that effect.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from rmprep.contracts import DecisionResult, DataPoint, EvidenceSet, Flag, ProductOption

_PUNCT = re.compile(r"[^\w\s+\-]")


def norm(text: str) -> str:
    """Normalized persona text (docs/decision.md section 3)."""
    t = text.replace("İ", "i").replace("I", "ı").lower()
    return " ".join(_PUNCT.sub("", t).split())


def _lookup(table: Mapping[str, Any], text: str):
    want = norm(text)
    return next((v for k, v in table.items() if norm(k) == want), None)


def _key(table: Mapping[str, Any], text: str) -> str | None:
    want = norm(text)
    return next((k for k in table if norm(k) == want), None)


class EvidenceView:
    def __init__(self, ev: EvidenceSet) -> None:
        self.ev = ev
        self.by_id = {d.id: d for d in ev.datapoints}
        latest: dict[tuple[str, str], DataPoint] = {}
        for d in ev.datapoints:
            if d.source in ev.excluded_sources:
                continue
            key = (d.quantity, d.entity)
            if key not in latest or d.as_of > latest[key].as_of:
                latest[key] = d
        self.latest = latest

    def value(self, quantity: str, entity: str) -> float | None:
        d = self.latest.get((quantity, entity))
        if d is None or Flag.MISSING in d.flags or Flag.OUT_OF_RANGE in d.flags:
            return None
        return d.value

    def name(self, entity: str) -> str:
        info = self.ev.entities.get(entity)
        if info is None or info.source in self.ev.excluded_sources:
            return ""
        return info.name


@dataclass(frozen=True)
class Rules:
    """The hard rules that apply to one persona (with its answers)."""

    ceiling: int | None             # None: the risk profile is unknown and not answered
    effects: tuple[str, ...]        # constraint effects of acik_kisitlar (table or answer)
    unknown_blocking: tuple[str, ...]   # question ids that must stay open (not answered)
    d12: bool
    d13: bool
    fx_hard: bool                   # D13 fx_limit applies (not lifted by the RM)
    liquidity_hard: bool            # D13 liquidity_need applies
    max_sell_valor_days: int | None
    max_lock_days: int | None
    profile: str | None = None      # the risk profile as a config key (table or answer)
    diversity: bool = False         # the diversity priority or a constraint with diversity


def rules_for(result: DecisionResult, config: Mapping[str, Any]) -> Rules:
    p = result.persona
    answers = {q.question_id: q.answer for q in result.questions if q.answer is not None}
    unknown: list[str] = []

    profile_name = _key(config["risk_profiles"], p.risk_profili)
    if profile_name is None and answers.get("q:risk_profili") in config["risk_profiles"]:
        profile_name = answers["q:risk_profili"]
    profile = None if profile_name is None else config["risk_profiles"][profile_name]
    if profile is None:
        unknown.append("q:risk_profili")
    ceiling = None if profile is None else int(profile["ceiling"])

    by_label = {label: effect for effect, label in config["texts"]["effect_labels"].items()}
    effects: list[str] = []
    for i, text in enumerate(p.acik_kisitlar):
        effect = _lookup(config["constraints"], text)
        qid = f"q:acik_kisitlar[{i}]"
        if effect is None and qid in answers:
            effect = by_label.get(answers[qid])
        if effect is None:
            unknown.append(qid)
        else:
            effects.append(effect)
    if ceiling is not None and "risk_cap" in effects:
        ceiling = min(ceiling, int(config["constraint_effects"]["risk_cap"]["max_ceiling"]))

    rules = config.get("constraint_rules", {})
    d13 = bool(rules)
    fx_hard = "fx_limit" in effects and "fx_limit" in rules
    if fx_hard and answers.get("q:override:fx_limit") == rules["fx_limit"]["override_lifts"]:
        fx_hard = False
    ln = rules.get("liquidity_need", {})
    diversity = (any(_lookup(config["priorities"], x) == "diversity" for x in p.oncelikler)
                 or any(config["constraint_effects"].get(e, {}).get("diversity") for e in effects))
    return Rules(ceiling=ceiling, effects=tuple(effects), unknown_blocking=tuple(unknown),
                 profile=profile_name, diversity=diversity,
                 d12="fund_detail" in config, d13=d13, fx_hard=fx_hard,
                 liquidity_hard="liquidity_need" in effects and bool(ln),
                 max_sell_valor_days=ln.get("max_sell_valor_days"),
                 max_lock_days=ln.get("max_lock_days"))


class Oracle:
    """Facts about the options of one run, from its evidence and the config."""

    def __init__(self, result: DecisionResult, ev: EvidenceSet, config: Mapping[str, Any]) -> None:
        self.result = result
        self.config = config
        self.view = EvidenceView(ev)
        self.rules = rules_for(result, config)
        self._fx_words = tuple(w.upper() for w in config["fx_name_words"])
        fd = config.get("fund_detail", {})
        self._buyable_q = fd.get("buyable_quantity")
        self._valor_q = fd.get("sell_valor_quantity")
        self._term_days = config.get("time_deposit", {}).get("term_days")

    def risk(self, o: ProductOption) -> float | None:
        if o.kind in ("deposit", "time_deposit"):
            return 1.0
        return self.view.value("fund_risk_level", o.entity)

    def fx(self, o: ProductOption) -> bool:
        if o.kind != "fund":
            return False
        name = (self.view.name(o.entity) or o.label).replace("i", "İ").upper()
        return any(w in name for w in self._fx_words)

    def sell_valor(self, o: ProductOption) -> float | None:
        if o.kind != "fund" or not self._valor_q:
            return None
        return self.view.value(self._valor_q, o.entity)

    def violations(self, o: ProductOption) -> list[str]:
        """The hard rules this option breaks (only the rules that are active)."""
        r, out = self.rules, []
        if o.kind == "fund" and r.d12 and self.view.value(self._buyable_q, o.entity) == 0:
            out.append("not_buyable")
        risk = self.risk(o)
        if r.ceiling is not None and risk is not None and risk > r.ceiling:
            out.append("risk_ceiling")
        if r.fx_hard and self.fx(o):
            out.append("fx_limit")
        if r.liquidity_hard:
            valor = self.sell_valor(o)
            if valor is not None and r.max_sell_valor_days is not None and valor > r.max_sell_valor_days:
                out.append("liquidity_need")
            if (o.kind == "time_deposit" and self._term_days is not None
                    and r.max_lock_days is not None and self._term_days > r.max_lock_days):
                out.append("liquidity_need")
        return out
