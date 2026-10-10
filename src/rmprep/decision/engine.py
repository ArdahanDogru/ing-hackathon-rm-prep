"""decide(): one EvidenceSet + one Persona -> one DecisionResult
(docs/decision.md, "Entry point" and section 7). Pure: no I/O, no clock."""

from __future__ import annotations

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
from rmprep.decision.confidence import confidence, stability
from rmprep.decision.config import DecisionConfig
from rmprep.decision.notes import build_notes, build_warnings, source_notes
from rmprep.decision.persona import read_persona
from rmprep.decision.scoring import score_options
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


def standard_assumptions(config: DecisionConfig, evidence: EvidenceSet) -> tuple[str, ...]:
    c = config.raw
    a = c["texts"]["assumptions"]
    tier = c["deposit"]["tier"]
    rr = c.get("real_return")
    # with fund_detail (D12) the liquidity of a fund comes from its sell valör
    proxy = "kind_proxy_valor" if "fund_detail" in c else "kind_proxy"
    keys = _STANDARD_ASSUMPTIONS if rr is None else _REAL_ASSUMPTIONS
    keys = tuple(proxy if k == "kind_proxy" else k for k in keys)
    if rr is None:
        return tuple(a[k].format(tier=tier) for k in keys)
    out = []
    for key in keys:
        if key == "real_return":
            cpi = EvidenceIndex(evidence).get(rr["cpi"]["quantity"], rr["cpi"]["entity"])
            out.append(a["real_return_no_cpi"] if cpi is None else
                       a["real_return_cpi"].format(cpi=cpi.value, cpi_date=cpi.as_of.isoformat()))
        elif key == "time_deposit_renewal":
            days = c.get("time_deposit", {}).get("term_days")
            if days:
                out.append(a[key].format(term_days=days))
        else:
            out.append(a[key].format(tier=tier))
    return tuple(out)


def decide(evidence: EvidenceSet, persona: Persona, config: DecisionConfig,
           answers: Mapping[str, str] = {}, *, created_at: datetime) -> DecisionResult:
    reading = read_persona(persona, config, answers)
    cfg_hash = config_hash(config)
    common = dict(
        run_id=run_id(cfg_hash, persona, evidence.snapshot_id, evidence.excluded_sources,
                      answers),
        config_hash=cfg_hash, created_at=created_at, persona=persona,
        snapshot_id=evidence.snapshot_id, excluded_sources=evidence.excluded_sources,
        questions=reading.questions,
        assumptions=standard_assumptions(config, evidence) + reading.assumptions,
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
    estimates = {f.option.option_id: f.risk for f in scoring.features if f.risk_estimated}
    warnings = build_warnings(options, levels, reading.questions, evidence, config, estimates)

    used: set[str] = set()
    for o in options:
        used.update(o.evidence_ids)
    for rej in scoring.rejected:
        for c in rej.failed:
            used.update(c.evidence_ids)
    for w in warnings:
        used.update(w.evidence_ids)
    stopaj_missing = Counter(f.stopaj_entity for f in scoring.features if f.stopaj_missing)
    notes = build_notes(frozenset(used), universe, evidence, config, stopaj_missing)
    return DecisionResult(state=DecisionState.READY, options=options, rejected=scoring.rejected,
                          warnings=warnings, data_quality=notes, **common)
