"""RealBackend: the Backend protocol (contracts.py, docs/ui.md) on ingest + decision.

Reads snapshots from <root>/data/snapshots, the decision config from
<root>/config/decision.yaml and the personas from the folder above <root>
(../p0*.json). Runs of the session stay in memory; approved and rejected runs
are saved to data/runs/<run_id>.json, cards to data/cards/<run_id>.md, approved
meeting texts to data/narratives/<run_id>-<lang>-approved.json (docs/narrator.md)."""

from __future__ import annotations

import dataclasses
import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rmprep import decision
from rmprep.contracts import (
    TR_TZ, DecisionResult, EvidenceSet, NarrativeDraft, NarrativeStatus, Persona, RmStatus,
)
from rmprep.ingest.pipeline import Paths, build_evidence
from rmprep.ingest.snapshot import list_snapshots


@dataclass(frozen=True)
class _Inputs:
    persona: Persona
    snapshot_id: str
    excluded_sources: frozenset[str]
    answers: tuple[tuple[str, str], ...] = ()   # sorted (question_id, answer)


class RealBackend:
    def __init__(self, root: Path | str, *, personas_dir: Path | str | None = None,
                 now: Callable[[], datetime] = lambda: datetime.now(TR_TZ)) -> None:
        self._paths = Paths(Path(root).resolve())
        self._personas_dir = Path(personas_dir) if personas_dir else self._paths.root.parent
        self._now = now
        self._config = decision.load_config(self._paths.root / "config" / "decision.yaml")
        self._evidence: dict[tuple[str, frozenset[str]], EvidenceSet] = {}
        self._runs: dict[str, tuple[DecisionResult, _Inputs]] = {}
        self._narrator_obj = None          # made on first use (imports the LLM SDK)
        self._narratives: dict[tuple[str, str], NarrativeDraft] = {}   # approved texts
        # Lever 1 (2026-10-10): an approval starts the TR meeting text in the background,
        # so the RM usually finds it ready; opening it waits for that job.
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="narrator")
        self._pending: dict[tuple[str, str], Future] = {}
        self._lock = threading.Lock()

    # --- reading --------------------------------------------------------------

    def list_personas(self) -> list[Persona]:
        out = []
        for f in sorted(self._personas_dir.glob("p0*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(d, dict) and "persona_id" in d:
                out.append(Persona.from_dict(d))
        return out

    def list_snapshots(self) -> list[str]:
        return [s.snapshot_id for s in reversed(list_snapshots(self._paths.snapshots))]

    def evidence(self, snapshot_id: str,
                 exclude_sources: frozenset[str] = frozenset()) -> EvidenceSet:
        key = (snapshot_id, frozenset(exclude_sources))
        if key not in self._evidence:
            self._evidence[key] = build_evidence(self._paths.snapshots, snapshot_id, key[1])
        return self._evidence[key]

    # --- runs -----------------------------------------------------------------

    def decide(self, persona: Persona, snapshot_id: str,
               exclude_sources: frozenset[str] = frozenset()) -> DecisionResult:
        return self._run(_Inputs(persona, snapshot_id, frozenset(exclude_sources)))

    def answer_question(self, run_id: str, question_id: str, answer: str) -> DecisionResult:
        _, inputs = self._runs[run_id]
        answers = dict(inputs.answers) | {question_id: answer}
        return self._run(dataclasses.replace(inputs, answers=tuple(sorted(answers.items()))))

    def approve(self, run_id: str, status: RmStatus, note: str = "",
                selected_option_ids: tuple[str, ...] = ()) -> DecisionResult:
        result, inputs = self._runs[run_id]
        status = RmStatus(status)
        if status == RmStatus.PENDING:
            raise ValueError("approve needs approved or rejected")
        if status == RmStatus.REJECTED and not note.strip():
            raise ValueError("a rejection needs a note")
        if self._is_test_run(inputs.persona):
            raise ValueError("a test run (edited persona) cannot be approved or rejected")
        selected = tuple(selected_option_ids) if status == RmStatus.APPROVED else ()
        new = dataclasses.replace(result, rm_status=status, rm_note=note, rm_selected=selected,
                                  rm_option_notes={})
        saved = self._save(new, inputs)
        if status == RmStatus.APPROVED:
            self._prefetch(run_id, "TR")
        return saved

    def annotate(self, run_id: str, note: str,
                 option_notes: Mapping[str, str]) -> DecisionResult:
        result, inputs = self._runs[run_id]
        if result.rm_status != RmStatus.APPROVED:
            raise ValueError("only an approved run can be annotated")
        new = dataclasses.replace(result, rm_note=note, rm_option_notes=dict(option_notes))
        return self._save(new, inputs)

    def save_card(self, run_id: str, markdown: str) -> str:
        result, _ = self._runs[run_id]
        if result.rm_status != RmStatus.APPROVED:
            raise ValueError("only an approved run has a card")
        path = self._paths.root / "data" / "cards" / f"{run_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8", newline="\n")
        return str(path)

    # --- meeting text (contract v1.2) --------------------------------------------

    def draft_narrative(self, run_id: str, lang: str = "TR") -> NarrativeDraft:
        result, inputs = self._runs[run_id]
        if result.rm_status != RmStatus.APPROVED:
            raise ValueError("a meeting text needs an approved run")
        approved = self._narratives.get((run_id, lang)) or self._saved_text(run_id, lang)
        if approved is not None:
            return approved
        with self._lock:
            job = self._pending.pop((run_id, lang), None)
        if job is not None:
            try:
                return job.result()
            except Exception:
                pass                   # the background draft failed: make it again now
        return self._draft_now(run_id, lang)

    def wait_for_background(self) -> None:
        """Wait for the running background drafts (tests, shutdown)."""
        with self._lock:
            jobs = list(self._pending.values())
        for job in jobs:
            try:
                job.result()
            except Exception:
                pass

    def _prefetch(self, run_id: str, lang: str) -> None:
        with self._lock:
            if (run_id, lang) not in self._pending:
                self._pending[(run_id, lang)] = self._pool.submit(self._draft_now, run_id, lang)

    def _draft_now(self, run_id: str, lang: str) -> NarrativeDraft:
        result, inputs = self._runs[run_id]
        ev = self.evidence(inputs.snapshot_id, inputs.excluded_sources)
        return self._narrator().draft(result, ev, lang)

    def approve_narrative(self, run_id: str, lang: str, text: str) -> NarrativeDraft:
        if not text.strip():
            raise ValueError("the approved meeting text is empty")
        d = dataclasses.replace(self.draft_narrative(run_id, lang),
                                status=NarrativeStatus.APPROVED, rm_text=text)
        path = self._paths.root / "data" / "narratives" / f"{run_id}-{lang}-approved.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d.to_dict(), ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")
        self._narratives[(run_id, lang)] = d
        return d

    def _narrator(self):
        if self._narrator_obj is None:
            from rmprep.narrator.service import narrator_from_root
            self._narrator_obj = narrator_from_root(self._paths.root)
        return self._narrator_obj

    # --- internal -------------------------------------------------------------

    def _run(self, inputs: _Inputs) -> DecisionResult:
        result = decision.decide(self.evidence(inputs.snapshot_id, inputs.excluded_sources),
                                 inputs.persona, self._config, dict(inputs.answers),
                                 created_at=self._now())
        old = self._runs.get(result.run_id)
        if old is not None:          # same inputs: the run exists, keep its RM status
            return old[0]
        saved = self._saved_run(result.run_id)   # approved / rejected before a restart
        self._runs[result.run_id] = (saved or result, inputs)
        return saved or result

    def _saved_run(self, run_id: str) -> DecisionResult | None:
        path = self._paths.root / "data" / "runs" / f"{run_id}.json"
        try:
            return DecisionResult.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _saved_text(self, run_id: str, lang: str) -> NarrativeDraft | None:
        path = self._paths.root / "data" / "narratives" / f"{run_id}-{lang}-approved.json"
        try:
            d = NarrativeDraft.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError):
            return None
        self._narratives[(run_id, lang)] = d
        return d

    def _save(self, result: DecisionResult, inputs: _Inputs) -> DecisionResult:
        self._runs[result.run_id] = (result, inputs)
        path = self._paths.root / "data" / "runs" / f"{result.run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")
        return result

    def _is_test_run(self, persona: Persona) -> bool:
        original = next((p for p in self.list_personas() if p.persona_id == persona.persona_id), None)
        return original != persona
