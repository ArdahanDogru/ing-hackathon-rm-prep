"""The facts pack: everything the narrator may say about one approved run
(docs/narrator.md, "Input: the facts pack"). Deterministic; no LLM.

Named options are the baseline, the RM's selection and the other members of
the groups (rmprep.grouping) that hold a selected option. Rejected options are
in the pack only as a count per rule; no other option is in it."""

from __future__ import annotations

import dataclasses
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from rmprep import grouping
from rmprep.contracts import (
    DecisionResult,
    EvidenceSet,
    RmStatus,
    ScoredOption,
)

# persona fields the text may use (not scored; the narrator is where they matter)
CLIENT_FIELDS = ("profil", "yas", "risk_profili", "durum", "yatirim_amaci", "yatirim_ufku",
                 "oncelikler", "acik_kisitlar", "rm_notu")


@dataclass(frozen=True)
class KeyNumber:
    evidence_id: str
    quantity: str           # DataPoint.quantity, e.g. fund_return_1y
    value: float
    unit: str
    as_of: date
    source: str


@dataclass(frozen=True)
class OptionFacts:
    option_id: str
    label: str
    kind: str                                   # grouping.group_key
    fx: bool
    score: float
    confidence: float
    stability: float
    reasons: tuple[tuple[str, float, str], ...]  # (score part, value, reason), largest first
    numbers: tuple[KeyNumber, ...]
    evidence_ids: tuple[str, ...]
    warnings: tuple[str, ...] = ()              # messages of the warnings that name it
    rm_note: str = ""


@dataclass(frozen=True)
class GroupFacts:
    key: str                                    # grouping.group_key of the members
    selected: tuple[str, ...]                   # option ids the RM selected
    alternatives: tuple[str, ...]               # the other members (visible ones only)


@dataclass(frozen=True)
class WarningFacts:
    code: str
    message: str
    option_ids: tuple[str, ...] = ()            # named options only; () = the whole result
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class NoteFacts:
    message: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Facts:
    run_id: str
    persona_id: str
    snapshot_id: str
    client: Mapping[str, object]                # CLIENT_FIELDS of the persona
    baseline: OptionFacts | None                # the deposit, if the result has one
    selected: tuple[OptionFacts, ...]           # display order
    alternatives: tuple[OptionFacts, ...]       # group alternatives, display order
    groups: tuple[GroupFacts, ...]
    warnings: tuple[WarningFacts, ...]
    data_quality: tuple[NoteFacts, ...]
    assumptions: tuple[str, ...]
    open_questions: tuple[str, ...]
    rm_note: str
    rejected_count: int
    rejected_rules: Mapping[str, int]           # rule_id -> options it rejected

    def named_options(self) -> dict[str, OptionFacts]:
        out = {} if self.baseline is None else {self.baseline.option_id: self.baseline}
        out.update((o.option_id, o) for o in (*self.selected, *self.alternatives))
        return out

    def evidence_ids(self) -> frozenset[str]:
        ids = {i for o in self.named_options().values() for i in o.evidence_ids}
        ids.update(i for w in self.warnings for i in w.evidence_ids)
        ids.update(i for n in self.data_quality for i in n.evidence_ids)
        return frozenset(ids)

    def to_dict(self) -> dict:
        return _plain(self)


def _plain(x):
    """JSON-ready copy: dataclasses and mappings -> dict, tuples -> list, dates -> ISO."""
    if dataclasses.is_dataclass(x):
        return {f.name: _plain(getattr(x, f.name)) for f in dataclasses.fields(x)}
    if isinstance(x, Mapping):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (tuple, list)):
        return [_plain(v) for v in x]
    if isinstance(x, date):
        return x.isoformat()
    return x


def _option_facts(o: ScoredOption, ev: EvidenceSet, warnings: list[str], note: str) -> OptionFacts:
    by_id = {dp.id: dp for dp in ev.datapoints}
    ids = list(dict.fromkeys([*o.evidence_ids, *(i for c in o.constraints
                                                   for i in c.evidence_ids)]))
    numbers = tuple(KeyNumber(dp.id, dp.quantity, dp.value, dp.unit, dp.as_of, dp.source)
                    for dp in (by_id.get(i) for i in ids) if dp is not None and dp.value is not None)
    reasons = sorted(((k, v, o.reasons[k]) for k, v in o.score_parts.items()),
                     key=lambda r: -abs(r[1]))
    return OptionFacts(
        option_id=o.option.option_id, label=o.option.label, kind=grouping.group_key(o),
        fx=o.option.fx, score=o.score, confidence=o.confidence, stability=o.stability,
        reasons=tuple(reasons), numbers=numbers, evidence_ids=tuple(ids),
        warnings=tuple(warnings), rm_note=note)


def build_facts(r: DecisionResult, ev: EvidenceSet) -> Facts:
    if r.rm_status != RmStatus.APPROVED:
        raise ValueError("the narrator writes only for an approved result")
    selected = set(r.rm_selected)

    groups = []
    for g in grouping.groups(r.options):
        members = (g.head, *g.alternatives)
        mine = tuple(o.option.option_id for o in members if o.option.option_id in selected)
        if mine:
            others = tuple(o.option.option_id for o in members if o.option.option_id not in selected)
            groups.append(GroupFacts(g.key, mine,
                                     others[:grouping.DEFAULT_RULE.visible_alternatives]))
    alternative_ids = {i for g in groups for i in g.alternatives}
    baseline = next((o for o in r.options if o.option.kind == "deposit"), None)
    named = selected | alternative_ids | ({baseline.option.option_id} if baseline else set())

    rejected_labels = [x.option.label for x in r.rejected]
    warnings = []
    for w in r.warnings:
        ids = tuple(i for i in w.option_ids if i in named)
        if (w.option_ids and not ids) or any(lbl in w.message for lbl in rejected_labels):
            continue
        warnings.append(WarningFacts(w.code, w.message, ids, w.evidence_ids))

    def facts(o: ScoredOption) -> OptionFacts:
        oid = o.option.option_id
        return _option_facts(o, ev, [w.message for w in warnings if oid in w.option_ids],
                             r.rm_option_notes.get(oid, ""))

    p = r.persona
    return Facts(
        run_id=r.run_id, persona_id=p.persona_id, snapshot_id=r.snapshot_id,
        client={k: getattr(p, k) for k in CLIENT_FIELDS},
        baseline=facts(baseline) if baseline else None,
        selected=tuple(facts(o) for o in r.options if o.option.option_id in selected),
        alternatives=tuple(facts(o) for o in r.options if o.option.option_id in alternative_ids),
        groups=tuple(groups),
        warnings=tuple(warnings),
        data_quality=tuple(NoteFacts(n.message, n.evidence_ids) for n in r.data_quality),
        assumptions=r.assumptions,
        open_questions=tuple(q.text for q in r.questions if q.answer is None),
        rm_note=r.rm_note,
        rejected_count=len(r.rejected),
        rejected_rules=dict(sorted(Counter(c.rule_id for x in r.rejected
                                           for c in x.failed).items())),
    )
