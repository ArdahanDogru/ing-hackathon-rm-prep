"""Run eval scenarios through RealBackend, the system under test (docs/eval.md
"Shape"): persona edits -> decide -> answers -> a fixed RM selection -> the
meeting text of each language.

- The RM approval is simulated in memory (dataclasses.replace on the result):
  RealBackend.approve saves to data/runs and refuses edited (test) personas, and
  the eval must not write RM runs. The narrator gets the approved copy.
- Repetition k runs on its own fresh RealBackend (one per k, shared by all
  scenarios), so "same inputs -> same result" is not answered from the session
  memory of one backend.
- Evidence edits (bad data) give the evidence a snapshot id of its own
  (`<snapshot>~<scenario id>`), so their runs never share a run_id (or a cached
  meeting text) with a run on the clean snapshot.
- The eval has its own cost limit per suite run (config/eval.yaml); over it, no
  new meeting text is asked for. The cost of a text is the growth of the
  narrator's cost ledger (a cached text costs nothing).
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from rmprep.backend import RealBackend
from rmprep.contracts import (
    TR_TZ, DecisionResult, DecisionState, EvidenceSet, NarrativeDraft, Persona, RmStatus,
)
from rmprep.eval.scenario import (
    Scenario, ScenarioError, apply_evidence_edits, edit_persona, resolve_top, top_placeholders,
)
from rmprep.grouping import groups

EDIT_SEP = "~"


class NarratorLike(Protocol):
    def draft(self, r: DecisionResult, ev: EvidenceSet, lang: str) -> NarrativeDraft: ...


class EvalBackend(RealBackend):
    """RealBackend plus registered evidence edits under derived snapshot ids.
    Everything else is the real code path (decide, answers, evidence lookup)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._edits: dict[str, tuple[str, tuple]] = {}
        self._edited: dict[tuple[str, frozenset[str]], EvidenceSet] = {}

    def register_edits(self, snapshot_id: str, scenario_id: str, edits: tuple) -> str:
        sid = f"{snapshot_id}{EDIT_SEP}{scenario_id}"
        self._edits[sid] = (snapshot_id, edits)
        self._edited = {k: v for k, v in self._edited.items() if k[0] != sid}
        return sid

    def evidence(self, snapshot_id: str,
                 exclude_sources: frozenset[str] = frozenset()) -> EvidenceSet:
        if snapshot_id not in self._edits:
            return super().evidence(snapshot_id, exclude_sources)
        key = (snapshot_id, frozenset(exclude_sources))
        if key not in self._edited:
            base, edits = self._edits[snapshot_id]
            self._edited[key] = apply_evidence_edits(
                super().evidence(base, exclude_sources), edits, snapshot_id)
        return self._edited[key]


@dataclass
class RunRecord:
    """One run of one scenario (repetition `repeat`)."""

    repeat: int
    backend: RealBackend
    persona: Persona
    evidence: EvidenceSet
    result: DecisionResult                  # after the answers
    approved: DecisionResult | None         # with the RM selection; None if not ready
    evidence_edits: tuple = ()              # the edits applied (placeholders resolved)
    narratives: dict[str, NarrativeDraft] = field(default_factory=dict)
    seconds_evidence: float = 0.0
    seconds_decide: float = 0.0             # decide + answers
    seconds_narrate: dict[str, float] = field(default_factory=dict)
    narrator_cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


@dataclass
class ScenarioRun:
    scenario: Scenario
    runs: list[RunRecord] = field(default_factory=list)
    error: str | None = None                # the scenario could not run at all


class Runner:
    def __init__(self, root: Path | str, *, personas_dir: Path | str | None = None,
                 narrator: NarratorLike | None = None, snapshot: str | None = None,
                 now: Callable[[], datetime] | None = None,
                 max_cost_usd: float | None = None) -> None:
        self.root = Path(root)
        self.personas_dir = personas_dir
        self.narrator = narrator
        self.max_cost_usd = max_cost_usd
        start = datetime.now(TR_TZ)
        self.now = now or (lambda: start)       # one fixed time per suite: identical results
        self.spent_usd = 0.0
        self._backends: list[EvalBackend] = []
        self.snapshot_id = snapshot or (self._backend(0).list_snapshots() or [None])[0]

    def _backend(self, k: int) -> EvalBackend:
        while len(self._backends) <= k:
            self._backends.append(EvalBackend(self.root, personas_dir=self.personas_dir,
                                              now=self.now))
        return self._backends[k]

    # --- public -----------------------------------------------------------------

    def budget_left(self) -> float:
        """USD left of the eval limit of this suite run (inf without a limit)."""
        return float("inf") if self.max_cost_usd is None else self.max_cost_usd - self.spent_usd

    def add_cost(self, usd: float) -> None:
        """Count a cost outside the narrator (the judge) against the limit."""
        self.spent_usd += usd

    def run(self, scenarios: Iterable[Scenario]) -> list[ScenarioRun]:
        return [self.run_one(s) for s in scenarios]

    def run_one(self, s: Scenario) -> ScenarioRun:
        out = ScenarioRun(s)
        for k in range(s.repeat):
            try:
                out.runs.append(self._run(s, k))
            except Exception as e:          # noqa: BLE001 - one bad scenario must not stop the suite
                out.error = f"{type(e).__name__}: {e}"
                out.runs = []
                break
        return out

    # --- one run ----------------------------------------------------------------

    def _run(self, s: Scenario, k: int) -> RunRecord:
        b = self._backend(k)
        persona = next((p for p in b.list_personas() if p.persona_id == s.persona), None)
        if persona is None:
            raise ScenarioError(f"scenario {s.id}: no persona {s.persona}")
        persona = edit_persona(persona, s)
        snapshot = s.snapshot or self.snapshot_id
        if snapshot is None:
            raise ScenarioError(f"scenario {s.id}: no snapshot")
        edits = s.evidence_edits
        if edits:
            if top_placeholders(edits):
                clean = self._answered(b, b.decide(persona, snapshot, s.exclude_sources), s, [])
                funds = [o.option.entity for o in clean.options if o.option.kind == "fund"]
                edits = resolve_top(edits, funds)
            snapshot = b.register_edits(snapshot, s.id, edits)

        t = time.perf_counter()
        ev = b.evidence(snapshot, s.exclude_sources)
        t_ev = time.perf_counter() - t

        errors: list[str] = []
        t = time.perf_counter()
        result = self._answered(b, b.decide(persona, snapshot, s.exclude_sources), s, errors)
        t_decide = time.perf_counter() - t

        rec = RunRecord(repeat=k, backend=b, persona=persona, evidence=ev, result=result,
                        approved=None, evidence_edits=edits, seconds_evidence=t_ev, seconds_decide=t_decide,
                        errors=errors)
        if result.state != DecisionState.READY:
            return rec
        rec.approved = self._approve(s, result, errors)
        if rec.approved is not None and s.narrate and self.narrator is not None:
            self._narrate(s, rec)
        return rec

    @staticmethod
    def _answered(b: RealBackend, result: DecisionResult, s: Scenario,
                  errors: list[str]) -> DecisionResult:
        for qid, answer in s.answers:
            if not any(q.question_id == qid for q in result.questions):
                errors.append(f"answer: the result has no question {qid}")
                continue
            try:
                result = b.answer_question(result.run_id, qid, answer)
            except ValueError as e:
                errors.append(f"answer {qid}: {e}")
        return result

    def _approve(self, s: Scenario, r: DecisionResult, errors: list[str]) -> DecisionResult | None:
        if s.select:
            known = {o.option.option_id for o in r.options}
            bad = [i for i in s.select if i not in known]
            if bad:
                errors.append(f"select: not a scored option {bad}")
                return None
            selected = s.select
        else:
            selected = tuple(g.head.option.option_id for g in groups(r.options))[:s.select_top]
            if not selected and r.options:      # only the deposit baseline is left
                selected = (r.options[0].option.option_id,)
            if not selected:
                errors.append("select: the result has no option to select")
                return None
        return dataclasses.replace(r, rm_status=RmStatus.APPROVED, rm_note=s.rm_note,
                                   rm_selected=selected, rm_option_notes={})

    def _narrate(self, s: Scenario, rec: RunRecord) -> None:
        for lang in s.langs:
            if self.max_cost_usd is not None and self.spent_usd >= self.max_cost_usd:
                rec.errors.append(f"budget: eval limit ${self.max_cost_usd:.2f} reached "
                                  f"(${self.spent_usd:.2f} spent); no {lang} text")
                continue
            before = self._ledger()
            t = time.perf_counter()
            try:
                d = self.narrator.draft(rec.approved, rec.evidence, lang)
            except Exception as e:          # noqa: BLE001 - recorded as a finding of the run
                rec.errors.append(f"narrator {lang}: {type(e).__name__}: {e}")
                continue
            rec.seconds_narrate[lang] = time.perf_counter() - t
            cost = max(0.0, self._ledger() - before)
            rec.narrator_cost_usd += cost
            self.spent_usd += cost
            rec.narratives[lang] = d

    def _ledger(self) -> float:
        spent = getattr(self.narrator, "spent_today", None)
        return float(spent()) if spent else 0.0
