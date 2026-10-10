"""decide(): one EvidenceSet + one Persona -> one DecisionResult
(docs/decision.md, "Entry point" and section 7). Pure: no I/O, no clock."""

from __future__ import annotations

import hashlib
import json
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
from rmprep.decision.universe import build_universe

_STANDARD_ASSUMPTIONS = ("past_returns", "pre_tax", "deposit_tier", "no_real_returns",
                         "kind_proxy")


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def config_hash(config: DecisionConfig) -> str:
    return hashlib.sha256(_canonical(config.raw)).hexdigest()[:12]


def run_id(cfg_hash: str, persona: Persona, snapshot_id: str,
           excluded_sources: frozenset[str], answers: Mapping[str, str]) -> str:
    key = [cfg_hash, persona.to_dict(), snapshot_id, sorted(excluded_sources),
           sorted(answers.items())]
    return "R" + hashlib.sha1(_canonical(key), usedforsecurity=False).hexdigest()[:10]


def standard_assumptions(config: DecisionConfig) -> tuple[str, ...]:
    a = config.raw["texts"]["assumptions"]
    tier = config.raw["deposit"]["tier"]
    return tuple(a[k].format(tier=tier) for k in _STANDARD_ASSUMPTIONS)


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
        assumptions=standard_assumptions(config) + reading.assumptions,
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
                     constraints=(r.constraint,), confidence=confidence(r.features, config),
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
    notes = build_notes(frozenset(used), universe, evidence, config)
    return DecisionResult(state=DecisionState.READY, options=options, rejected=scoring.rejected,
                          warnings=warnings, data_quality=notes, **common)
