"""FakeBackend: the Backend protocol on the fixtures of tests/contracts/fixtures/
(docs/ui.md section 6). Results are the illustrative fixture results with the
inputs of the call put in; runs, approvals, cards and narratives stay in memory.
draft_narrative returns a template draft built from the run (contract v1.2,
docs/narrator.md); the real narrator is not called."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rmprep.contracts import (
    NARRATIVE_SECTIONS,
    TR_TZ,
    DecisionResult,
    DecisionState,
    EvidenceSet,
    NarrativeDraft,
    NarrativeSection,
    NarrativeSentence,
    NarrativeStatus,
    Persona,
    RmStatus,
)

_PROMPT_VERSION = "fake"
_ALTERNATIVES = 3      # non-selected options named in "alternatifler"
_TEXTS = {             # one sentence template per narrative section
    "TR": {
        "ozet": "{pid} · {profil}: {amac}.",
        "oneriler": "Görüşmede konuşulacak: {labels}.",
        "alternatifler": "Diğer seçenekler: {labels}.",
        "no_alternatives": "Başka seçenek yok.",
        "no_warnings": "Uyarı yok.",
        "sorular": "Müşteriye öncelikleri sorun: {priorities}.",
        "teklif_metni": "Sizin için {labels} seçeneklerini konuşmak istiyoruz.",
        "no_assumptions": "Varsayım yok.",
    },
    "EN": {
        "ozet": "{pid} · {profil}: {amac}.",
        "oneriler": "To discuss in the meeting: {labels}.",
        "alternatifler": "Other options: {labels}.",
        "no_alternatives": "No other options.",
        "no_warnings": "No warnings.",
        "sorular": "Ask the client about the priorities: {priorities}.",
        "teklif_metni": "We would like to discuss {labels} with you.",
        "no_assumptions": "No assumptions.",
    },
}


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
        self._narratives: dict[tuple[str, str], NarrativeDraft] = {}   # (run_id, lang)

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
                                  rm_option_notes={}, rm_decided_at=datetime.now(TR_TZ))
        for lang in ("TR", "EN"):                # texts of an earlier decision no longer apply
            self._narratives.pop((run_id, lang), None)
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

    # --- narrator (v1.2) -------------------------------------------------------

    def draft_narrative(self, run_id: str, lang: str = "TR") -> NarrativeDraft:
        result, _ = self._runs[run_id]
        if result.rm_status != RmStatus.APPROVED:
            raise ValueError("only an approved run has a narrative")
        key = (run_id, lang)
        if key not in self._narratives:
            if lang not in _TEXTS:
                raise ValueError(f"unknown narrative language {lang!r}")
            self._narratives[key] = NarrativeDraft(
                run_id=run_id, lang=lang, sections=_template_sections(result, _TEXTS[lang]),
                source="template", model="", prompt_version=_PROMPT_VERSION, checks=(),
                created_at=result.created_at)
        return self._narratives[key]

    def edit_narrative(self, run_id: str, lang: str, block_id: str,
                       text: str | None) -> NarrativeDraft:
        """v1.5: one block of the draft; the stand-in check of rmprep.edits."""
        from rmprep import edits
        d = self.draft_narrative(run_id, lang)
        if d.status == NarrativeStatus.APPROVED:
            raise ValueError("the meeting text is approved; edits are closed")
        result, _ = self._runs[run_id]
        findings = edits.check_block(d, result, None, block_id, text) if text and text.strip() else ()
        new = edits.with_edit(d, block_id, text, findings)
        self._narratives[(run_id, lang)] = new
        return new

    def approve_narrative(self, run_id: str, lang: str, text: str) -> NarrativeDraft:
        if not text.strip():
            raise ValueError("an approved narrative needs a text")
        draft = self.draft_narrative(run_id, lang)
        if draft.blocking_findings():
            raise ValueError(f"blocking findings: {draft.blocking_findings()}")
        approved = dataclasses.replace(draft, status=NarrativeStatus.APPROVED, rm_text=text,
                                       approved_at=datetime.now(TR_TZ))
        self._narratives[(run_id, lang)] = approved
        return approved

    def brief(self, run_id: str, lang: str = "TR"):
        """v1.4: the template brief (no LLM in the fake)."""
        from rmprep.brief import template_brief
        from rmprep.contracts import DecisionState
        result, _ = self._runs[run_id]
        if result.state != DecisionState.READY:
            raise ValueError("a brief needs a ready run")
        if lang not in ("TR", "EN"):
            raise ValueError(f"unknown language {lang!r}")
        return template_brief(result, lang, result.created_at)

    def _keep(self, result: DecisionResult, inputs: _Inputs) -> DecisionResult:
        old = self._runs.get(result.run_id)
        if old is not None:          # same inputs: the run exists, keep its RM status
            return old[0]
        self._runs[result.run_id] = (result, inputs)
        return result

    def _replace(self, result: DecisionResult) -> DecisionResult:
        self._runs[result.run_id] = (result, self._runs[result.run_id][1])
        return result


def _template_sections(r: DecisionResult, texts: Mapping[str, str]) -> tuple[NarrativeSection, ...]:
    """One sentence per section; option and evidence ids are the citations."""
    def sentence(text, options=(), evidence=()):
        return (NarrativeSentence(text, tuple(o.option.option_id for o in options),
                                  tuple(dict.fromkeys(evidence))),)

    def labels(options):
        return ", ".join(o.option.label for o in options)

    def ev(options):
        return [i for o in options for i in o.evidence_ids]

    p = r.persona
    selected = [o for o in r.options if o.option.option_id in r.rm_selected]
    others = [o for o in r.options if o.option.option_id not in r.rm_selected][:_ALTERNATIVES]
    by_id = {o.option.option_id: o for o in r.options}
    if r.warnings:
        named = [by_id[i] for w in r.warnings for i in w.option_ids if i in by_id]
        dikkat = (NarrativeSentence(" ".join(w.message for w in r.warnings),
                                    tuple(dict.fromkeys(o.option.option_id for o in named)),
                                    tuple(dict.fromkeys(i for w in r.warnings
                                                        for i in w.evidence_ids))),)
    else:
        dikkat = sentence(texts["no_warnings"])
    sections = {
        "ozet": sentence(texts["ozet"].format(pid=p.persona_id, profil=p.profil,
                                              amac=p.yatirim_amaci)),
        "oneriler": sentence(texts["oneriler"].format(labels=labels(selected)), selected,
                             ev(selected)),
        "alternatifler": (sentence(texts["alternatifler"].format(labels=labels(others)), others,
                                   ev(others))
                          if others else sentence(texts["no_alternatives"])),
        "dikkat": dikkat,
        "sorular": sentence(texts["sorular"].format(priorities=", ".join(p.oncelikler) or "—")),
        "teklif_metni": sentence(texts["teklif_metni"].format(labels=labels(selected)), selected),
        "varsayimlar": sentence(" ".join(r.assumptions) or texts["no_assumptions"]),
    }
    return tuple(NarrativeSection(k, sections[k]) for k in NARRATIVE_SECTIONS)
