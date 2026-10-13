"""decide(): one EvidenceSet + one Persona -> one DecisionResult
(docs/decision.md, "Entry point" and section 7). Pure: no I/O, no clock."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime

from rmprep.contracts import (
    DecisionResult,
    DecisionState,
    EvidenceSet,
    Persona,
    ScoredOption,
)
from rmprep.decision.allocation import allocation, holding_notes
from rmprep.decision.confidence import confidence, stability
from rmprep.decision.config import DecisionConfig
from rmprep.decision.notes import build_notes, build_warnings, source_notes
from rmprep.decision.persona import read_persona
from rmprep.decision.scoring import score_options
from rmprep.decision.display import facts_of
from rmprep.decision.recommend import class_rule_applies, choose
from rmprep.decision.talking import talking_points
from rmprep.decision.universe import EvidenceIndex, build_universe

_STANDARD_ASSUMPTIONS = ("past_returns", "pre_tax", "deposit_tier", "no_real_returns",
                         "kind_proxy")
# with real_return (D9): pre_tax and no_real_returns are replaced (docs/decision.md 4.1b)
_REAL_ASSUMPTIONS = ("past_returns", "real_return", "deposit_tier", "kind_proxy",
                     "stopaj_equity", "time_deposit_renewal")


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def config_hash(config: DecisionConfig) -> str:
    return hashlib.sha256(_canonical(config.raw)).hexdigest()[:12]


def run_id(cfg_hash: str, persona: Persona, snapshot_id: str,
           excluded_sources: frozenset[str], answers: Mapping[str, str]) -> str:
    key = [cfg_hash, persona.to_dict(), snapshot_id, sorted(excluded_sources),
           sorted(answers.items())]
    return "R" + hashlib.sha1(_canonical(key), usedforsecurity=False).hexdigest()[:10]


def standard_assumption_items(config: DecisionConfig,
                              evidence: EvidenceSet) -> list[tuple[str, str]]:
    """(texts.assumptions key, text) of the assumptions every run has."""
    c = config.raw
    a = c["texts"]["assumptions"]
    tier = c["deposit"]["tier"]
    rr = c.get("real_return")
    # with fund_detail (D12) the liquidity of a fund comes from its sell valör
    proxy = "kind_proxy_valor" if "fund_detail" in c else "kind_proxy"
    keys = _STANDARD_ASSUMPTIONS if rr is None else _REAL_ASSUMPTIONS
    keys = tuple(proxy if k == "kind_proxy" else k for k in keys)
    if rr is None:
        return [(k, a[k].format(tier=tier)) for k in keys]
    out = []
    for key in keys:
        if key == "real_return":
            cpi = EvidenceIndex(evidence).get(rr["cpi"]["quantity"], rr["cpi"]["entity"])
            if cpi is None:
                out.append(("real_return_no_cpi", a["real_return_no_cpi"]))
            else:
                out.append(("real_return_cpi", a["real_return_cpi"].format(
                    cpi=cpi.value, cpi_date=cpi.as_of.isoformat())))
        elif key == "time_deposit_renewal":
            days = c.get("time_deposit", {}).get("term_days")
            if days:
                out.append((key, a[key].format(term_days=days)))
        else:
            out.append((key, a[key].format(tier=tier)))
    return out


def standard_assumptions(config: DecisionConfig, evidence: EvidenceSet) -> tuple[str, ...]:
    return tuple(text for _, text in standard_assumption_items(config, evidence))


def to_confirm(config: DecisionConfig, keys: tuple[str, ...]) -> tuple[str, ...]:
    """Commands for the RM (config to_confirm) of the emitted assumption keys,
    in emit order, each once (D16)."""
    table = config.raw.get("to_confirm", {})
    tier = config.raw["deposit"]["tier"]
    return tuple(table[k].format(tier=tier) for k in dict.fromkeys(keys) if k in table)


def _with_class_reason(o: ScoredOption, text: str) -> ScoredOption:
    """Append the class-rule text to the return reason (else the first reason):
    the reason keys must stay the keys of score_parts."""
    key = "return" if "return" in o.reasons else next(iter(o.reasons))
    reasons = {**o.reasons, key: f"{o.reasons[key]} {text}"}
    return dataclasses.replace(o, reasons=reasons)


def decide(evidence: EvidenceSet, persona: Persona, config: DecisionConfig,
           answers: Mapping[str, str] = {}, *, created_at: datetime) -> DecisionResult:
    reading = read_persona(persona, config, answers)
    cfg_hash = config_hash(config)
    standard = standard_assumption_items(config, evidence)
    keys = tuple(k for k, _ in standard) + reading.assumption_keys
    hints = holding_notes(persona, config)

    def confirm(keys: tuple[str, ...]) -> tuple[str, ...]:
        """to_confirm of the assumption keys, then the holding question (D20)."""
        holding = (config.raw["allocation"]["holding_confirm"],) if hints else ()
        return to_confirm(config, keys) + holding

    common = dict(
        run_id=run_id(cfg_hash, persona, evidence.snapshot_id, evidence.excluded_sources,
                      answers),
        config_hash=cfg_hash, created_at=created_at, persona=persona,
        snapshot_id=evidence.snapshot_id, excluded_sources=evidence.excluded_sources,
        questions=reading.questions,
        assumptions=tuple(text for _, text in standard) + reading.assumptions,
        to_confirm=confirm(keys),
        allocation_notes=hints,
    )
    if reading.levels is None:
        return DecisionResult(state=DecisionState.NEEDS_RM_INPUT,
                              data_quality=tuple(source_notes(evidence, config)), **common)

    levels = reading.levels
    universe = build_universe(evidence, config)
    scoring = score_options(universe, levels, config)
    stab = stability(scoring.features, levels, config)
    options = tuple(
        ScoredOption(option=r.option, score=r.score, score_parts=r.parts,
                     constraints=r.constraints, confidence=confidence(r.features, config),
                     stability=stab[r.option.option_id], evidence_ids=r.evidence_ids,
                     reasons=r.reasons)
        for r in scoring.scored)
    # recommended top 3 with the class rule (D19); the reason of an option the rule
    # moved up says so
    idx = EvidenceIndex(evidence)
    nets = {f.option.option_id: f.net_return for f in scoring.features}

    def real_of(o: ScoredOption) -> float | None:
        """Real 1-year return (percent; display facts), else the net return."""
        real = facts_of(o.option, idx, config).real_1y
        if real is not None:
            return real.value
        net = nets.get(o.option.option_id)
        return net * 100 if net is not None else None

    # D21: the assumption names the class rule of the risk estimate when a fund uses it
    extra_keys: list[str] = []
    a_texts = config.raw["texts"]["assumptions"]
    if "risk_estimate_class" in a_texts and any(
            f.risk_by_class for f in scoring.features):
        common["assumptions"] += (a_texts["risk_estimate_class"],)
        extra_keys.append("risk_estimate_class")

    rec_ids, moved = choose(options, levels, config, real_of)
    if moved:
        text = config.raw["texts"]["reasons"]["class_rule"]
        options = tuple(_with_class_reason(o, text) if o.option.option_id in moved else o
                        for o in options)
    if class_rule_applies(levels, config):
        texts = config.raw["texts"]["assumptions"]
        common["assumptions"] += (texts["class_rule"],)
        extra_keys.append("class_rule")
    by_id = {o.option.option_id: o for o in options}
    estimates = {f.option.option_id: f.risk for f in scoring.features if f.risk_estimated}
    # D22: the stopaj and CPI rows of the scored options' real (net) returns
    rr = config.raw.get("real_return")
    real_inputs = [] if rr is None else [
        f.rows[q] for f in scoring.features if f.net_return is not None
        for q in (rr["stopaj"]["quantity"], rr["cpi"]["quantity"]) if q in f.rows]
    warnings = build_warnings(options, levels, reading.questions, evidence, config, estimates,
                              real_inputs)
    # to_confirm: assumption keys, then warning codes with an entry (D22)
    common["to_confirm"] = confirm(keys + tuple(extra_keys) + tuple(w.code for w in warnings))

    used: set[str] = set()
    for o in options:
        used.update(o.evidence_ids)
    for rej in scoring.rejected:
        for c in rej.failed:
            used.update(c.evidence_ids)
    for w in warnings:
        used.update(w.evidence_ids)
    stopaj_missing = Counter(f.stopaj_entity for f in scoring.features if f.stopaj_missing)
    valor_missing = 0
    if "liquidity_need" in levels.hard_rules:
        quantity = config.raw["fund_detail"]["sell_valor_quantity"]
        valor_missing = sum(1 for f in scoring.features       # listed funds only
                            if f.option.kind == "fund" and quantity not in f.rows)
    notes = build_notes(frozenset(used), universe, evidence, config, stopaj_missing,
                        valor_missing)
    return DecisionResult(state=DecisionState.READY, options=options, rejected=scoring.rejected,
                          warnings=warnings, data_quality=notes,
                          talking_points=talking_points(
                              options, persona, levels, evidence, config,
                              top=[by_id[i] for i in rec_ids]),
                          recommended=rec_ids,
                          allocation=allocation(options, scoring.rejected, levels, config,
                                                real_of, estimates),
                          **common)
