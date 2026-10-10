"""FakeBackend: the Backend protocol on the fixtures of tests/contracts/fixtures/
(docs/ui.md section 6). Results are the illustrative fixture results with the
inputs of the call put in; runs, approvals and cards stay in memory."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from rmprep.contracts import (
    DecisionResult,
    DecisionState,
    EvidenceSet,
    Persona,
    RmStatus,
)


@dataclass(frozen=True)
class _Inputs:
    persona: Persona
    snapshot_id: str
    excluded_sources: frozenset[str]
    answers: tuple[tuple[str, str], ...] = ()   # sorted (question_id, answer)


def _run_id(inputs: _Inputs) -> str:
    key = [inputs.persona.to_dict(), inputs.snapshot_id, sorted(inputs.excluded_sources),
           list(inputs.answers)]
    blob = json.dumps(key, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "R" + hashlib.sha1(blob, usedforsecurity=False).hexdigest()[:10]


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class FakeBackend:
    def __init__(self, fixtures_dir: Path | str,
                 results: Iterable[DecisionResult] = ()) -> None:
        """results: templates that replace the fixture result of their persona."""
        d = Path(fixtures_dir)
        self._personas = [Persona.from_dict(_read(p)) for p in sorted((d / "personas").glob("*.json"))]
        self._evidence: dict[str, EvidenceSet] = {}
        for p in sorted(d.glob("evidence_*.json")):
            ev = EvidenceSet.from_dict(_read(p))
            old = self._evidence.get(ev.snapshot_id)
            # one EvidenceSet per snapshot: the largest (the results cite its ids)
            if old is None or len(ev.datapoints) > len(old.datapoints):
                self._evidence[ev.snapshot_id] = ev
        given = list(results)
        ids = {r.persona_id for r in given}
        self._templates = given + [t for t in (DecisionResult.from_dict(_read(p))
                                               for p in sorted(d.glob("decision_*.json")))
                                   if t.persona_id not in ids]
        self._runs: dict[str, tuple[DecisionResult, _Inputs]] = {}
        self.saved: dict[str, DecisionResult] = {}   # approved / rejected runs
        self.cards: dict[str, str] = {}

    # --- reading --------------------------------------------------------------

    def list_personas(self) -> list[Persona]:
        return list(self._personas)

    def list_snapshots(self) -> list[str]:
        return sorted(self._evidence, reverse=True)

    def evidence(self, snapshot_id: str,
                 exclude_sources: frozenset[str] = frozenset()) -> EvidenceSet:
        ev = self._evidence[snapshot_id]
        rows = tuple(dp for dp in ev.datapoints if dp.source not in exclude_sources)
        return dataclasses.replace(ev, datapoints=rows, excluded_sources=frozenset(exclude_sources))

    # --- runs -----------------------------------------------------------------

    def decide(self, persona: Persona, snapshot_id: str,
               exclude_sources: frozenset[str] = frozenset()) -> DecisionResult:
        if snapshot_id not in self._evidence:
            raise KeyError(snapshot_id)
        template = next((t for t in self._templates if t.persona_id == persona.persona_id),
                        None) or next(t for t in self._templates if t.state == DecisionState.READY)
        inputs = _Inputs(persona, snapshot_id, frozenset(exclude_sources))
        result = dataclasses.replace(
            template, run_id=_run_id(inputs), persona=persona, snapshot_id=snapshot_id,
            excluded_sources=inputs.excluded_sources)
        return self._keep(result, inputs)

    def answer_question(self, run_id: str, question_id: str, answer: str) -> DecisionResult:
        result, inputs = self._runs[run_id]
        if question_id not in {q.question_id for q in result.questions}:
            raise KeyError(question_id)
        answers = dict(inputs.answers) | {question_id: answer}
        inputs = dataclasses.replace(inputs, answers=tuple(sorted(answers.items())))
        questions = tuple(dataclasses.replace(q, answer=answers.get(q.question_id, q.answer))
                          for q in result.questions)
        open_blocking = any(q.answer is None and q.blocking for q in questions)
        state = DecisionState.NEEDS_RM_INPUT if open_blocking else DecisionState.READY
        new = dataclasses.replace(result, run_id=_run_id(inputs), questions=questions, state=state,
                                  rm_status=RmStatus.PENDING, rm_note="", rm_selected=(),
                                  rm_option_notes={})
        return self._keep(new, inputs)

    def approve(self, run_id: str, status: RmStatus, note: str = "",
                selected_option_ids: tuple[str, ...] = ()) -> DecisionResult:
        result, _ = self._runs[run_id]
        status = RmStatus(status)
        if status == RmStatus.PENDING:
            raise ValueError("approve needs approved or rejected")
        if status == RmStatus.REJECTED and not note.strip():
            raise ValueError("a rejection needs a note")
        selected = tuple(selected_option_ids) if status == RmStatus.APPROVED else ()
        new = dataclasses.replace(result, rm_status=status, rm_note=note, rm_selected=selected,
                                  rm_option_notes={})
        self.saved[run_id] = new
        return self._replace(new)

    def annotate(self, run_id: str, note: str,
                 option_notes: Mapping[str, str]) -> DecisionResult:
        result, _ = self._runs[run_id]
        if result.rm_status != RmStatus.APPROVED:
            raise ValueError("only an approved run can be annotated")
        new = dataclasses.replace(result, rm_note=note, rm_option_notes=dict(option_notes))
        self.saved[run_id] = new
        return self._replace(new)

    def save_card(self, run_id: str, markdown: str) -> str:
        result, _ = self._runs[run_id]
        if result.rm_status != RmStatus.APPROVED:
            raise ValueError("only an approved run has a card")
        self.cards[run_id] = markdown
        return f"memory:cards/{run_id}.md"

    def _keep(self, result: DecisionResult, inputs: _Inputs) -> DecisionResult:
        old = self._runs.get(result.run_id)
        if old is not None:          # same inputs: the run exists, keep its RM status
            return old[0]
        self._runs[result.run_id] = (result, inputs)
        return result

    def _replace(self, result: DecisionResult) -> DecisionResult:
        self._runs[result.run_id] = (result, self._runs[result.run_id][1])
        return result
