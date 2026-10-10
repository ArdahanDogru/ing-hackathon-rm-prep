"""Contracts shared across layers. Owned by the lead (see docs/workflow.md);
workers request changes, they never edit this file.

DataPoint: adapters, checks and the evidence store (ingest).
EvidenceSet: what ingest hands to the layers downstream (decision, ui, narrator).
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo

# All timestamps in the system are Turkey time (UTC+3, no DST).
TR_TZ = ZoneInfo("Europe/Istanbul")


class Flag(StrEnum):
    MISSING = "missing"
    STALE = "stale"
    OUT_OF_RANGE = "out_of_range"
    CONFLICT = "conflict"
    FALLBACK_SNAPSHOT = "fallback_snapshot"
    UNVERIFIED_SERIES = "unverified_series"
    MANUAL_ENTRY = "manual_entry"
    NEEDS_CHECK = "needs_check"


_ID_PARTS_SEP = "|"
_NOTE_SEP = "; "


def make_id(source: str, quantity: str, entity: str, as_of: date) -> str:
    """Stable evidence id: "E" + sha1(source|quantity|entity|as_of)[:8]."""
    key = _ID_PARTS_SEP.join([source, quantity, entity, as_of.isoformat()])
    digest = hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()
    return "E" + digest[:8]


@dataclass(frozen=True)
class DataPoint:
    id: str
    quantity: str
    entity: str
    value: float | None
    unit: str
    as_of: date
    source: str
    source_url: str
    fetched_at: datetime
    snapshot_id: str
    raw_ref: str
    flags: frozenset[Flag] = field(default_factory=frozenset)
    note: str = ""

    @classmethod
    def create(
        cls,
        *,
        quantity: str,
        entity: str,
        value: float | None,
        unit: str,
        as_of: date,
        source: str,
        source_url: str,
        fetched_at: datetime,
        snapshot_id: str,
        raw_ref: str,
        flags: Iterable[Flag | str] = (),
        note: str = "",
    ) -> DataPoint:
        """Build a DataPoint and derive its id from the key fields."""
        return cls(
            id=make_id(source, quantity, entity, as_of),
            quantity=quantity,
            entity=entity,
            value=value,
            unit=unit,
            as_of=as_of,
            source=source,
            source_url=source_url,
            fetched_at=fetched_at,
            snapshot_id=snapshot_id,
            raw_ref=raw_ref,
            flags=frozenset(flags),
            note=note,
        )

    def __post_init__(self) -> None:
        for name in ("quantity", "entity", "unit", "source", "source_url",
                     "snapshot_id", "raw_ref"):
            v = getattr(self, name)
            if not isinstance(v, str) or not v.strip():
                raise ValueError(f"{name} must be a non-empty string, got {v!r}")
        for name in ("source", "quantity", "entity"):
            if _ID_PARTS_SEP in getattr(self, name):
                raise ValueError(f"{name} must not contain {_ID_PARTS_SEP!r}")
        if not isinstance(self.note, str):
            raise ValueError("note must be a string")

        # datetime is a subclass of date; as_of must be a plain date.
        if not isinstance(self.as_of, date) or isinstance(self.as_of, datetime):
            raise ValueError(f"as_of must be a date, got {self.as_of!r}")

        if not isinstance(self.fetched_at, datetime):
            raise ValueError("fetched_at must be a datetime")
        if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() is None:
            raise ValueError("fetched_at must be timezone-aware")
        object.__setattr__(self, "fetched_at", self.fetched_at.astimezone(TR_TZ))

        # Flags: coerce strings, reject unknown names.
        object.__setattr__(self, "flags", frozenset(Flag(f) for f in self.flags))

        if self.value is not None:
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise ValueError(f"value must be a number or None, got {self.value!r}")
            if not math.isfinite(self.value):
                raise ValueError("value must be finite; use None with the missing flag")
            object.__setattr__(self, "value", float(self.value))

        if self.value is None and Flag.MISSING not in self.flags:
            raise ValueError("value=None requires the missing flag")
        if self.value is not None and Flag.MISSING in self.flags:
            raise ValueError("missing flag set but value is not None")

        expected = make_id(self.source, self.quantity, self.entity, self.as_of)
        if self.id != expected:
            raise ValueError(f"id {self.id!r} does not match key fields ({expected!r})")

    def with_flags(self, *flags: Flag, note: str | None = None) -> DataPoint:
        """Return a copy with flags added and note appended. Value is unchanged."""
        new_note = self.note
        if note:
            new_note = f"{self.note}{_NOTE_SEP}{note}" if self.note else note
        return dataclasses.replace(self, flags=self.flags | set(flags), note=new_note)

    def sorted_flags(self) -> list[str]:
        return sorted(f.value for f in self.flags)


class SourceStatusLike(Protocol):
    """What downstream layers may read about one source of a snapshot (the
    ingest manifest record has more; do not depend on it)."""

    status: str                 # ok | failed | skipped
    error: str | None
    fallback_from: str | None   # snapshot_id the rows came from, if fallback
    excluded: bool              # on_failure: exclude


@dataclass(frozen=True)
class EntityInfo:
    """Descriptive text for one DataPoint entity (now: one TEFAS fund), verbatim
    from the source. Mapping it to kinds is the decision layer's job."""

    name: str           # e.g. fonUnvan "A1 CAPİTAL PORTFÖY ALTIN FONU"
    category: str       # e.g. fonTurAciklama "Kıymetli Madenler Şemsiye Fonu"
    source: str         # source that gave it, e.g. "tefas_web"


@dataclass(frozen=True)
class EvidenceSet:
    """Checked evidence of one snapshot (rmprep.ingest.pipeline.build_evidence).
    Downstream must read excluded_sources so it can say what a result was
    computed without. Excluded (read time, by the user) != missing."""

    snapshot_id: str
    created_at: datetime
    excluded_sources: frozenset[str]                 # excluded at read time (UI)
    source_status: Mapping[str, SourceStatusLike]    # from the manifest
    datapoints: tuple[DataPoint, ...]                # checked, sorted by id
    entities: Mapping[str, EntityInfo] = field(default_factory=dict)  # entity -> info

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at.isoformat(),
            "excluded_sources": sorted(self.excluded_sources),
            "source_status": {k: _to_json(SourceStatus.of(v))
                              for k, v in sorted(self.source_status.items())},
            "datapoints": [_to_json(dp) for dp in self.datapoints],
            "entities": {k: _to_json(v) for k, v in sorted(self.entities.items())},
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> EvidenceSet:
        return cls(
            snapshot_id=d["snapshot_id"],
            created_at=datetime.fromisoformat(d["created_at"]),
            excluded_sources=frozenset(d["excluded_sources"]),
            source_status={k: _from_json(SourceStatus, v) for k, v in d["source_status"].items()},
            datapoints=tuple(_from_json(DataPoint, x) for x in d["datapoints"]),
            entities={k: _from_json(EntityInfo, v) for k, v in d.get("entities", {}).items()},
        )


@dataclass(frozen=True)
class SourceStatus:
    """Plain SourceStatusLike, for fixtures and serialized EvidenceSets."""

    status: str
    error: str | None = None
    fallback_from: str | None = None
    excluded: bool = False

    @classmethod
    def of(cls, rec: SourceStatusLike) -> SourceStatus:
        return cls(status=rec.status, error=rec.error, fallback_from=rec.fallback_from,
                   excluded=rec.excluded)


# =============================================================================
# Decision / UI contracts - FROZEN v1 (2026-10-10, after step D);
# v1.1 (2026-10-10): option kind "time_deposit" (ING e-Vadeli Mevduat).
# v1.2 (2026-10-10): narrator types + Backend.draft_narrative / approve_narrative
# (docs/narrator.md).
# Design: docs/decision.md and docs/ui.md. Changes only through ing-lead.
# =============================================================================

# --- persona (input; ../persona_schema.json, Turkish field names kept) --------

PERSONA_REQUIRED = (
    "persona_id", "profil", "yas", "risk_profili", "durum", "yatirim_amaci",
    "yatirim_ufku", "likidite_ihtiyaci", "doviz_maruz_kalma_tercihi",
    "gelir_nakit_akisi_ihtiyaci", "anapara_koruma_tercihi", "oncelikler",
    "acik_kisitlar",
)


@dataclass(frozen=True)
class Persona:
    """One client persona, exactly as the schema gives it. Values are free text
    (e.g. risk_profili "Muhafazakâr" | "Temkinli" | "Dengeli" | "Agresif";
    doviz_maruz_kalma_tercihi can be a sentence). Mapping text to levels and
    rules is the decision layer's job, not the contract's."""

    persona_id: str
    profil: str
    yas: int
    risk_profili: str
    durum: str
    yatirim_amaci: str
    yatirim_ufku: str
    likidite_ihtiyaci: str
    doviz_maruz_kalma_tercihi: str
    gelir_nakit_akisi_ihtiyaci: str
    anapara_koruma_tercihi: str
    oncelikler: tuple[str, ...]
    acik_kisitlar: tuple[str, ...]
    rm_notu: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.yas, bool) or not isinstance(self.yas, int):
            raise ValueError(f"yas must be an integer, got {self.yas!r}")
        for name in PERSONA_REQUIRED:
            v = getattr(self, name)
            if name in ("oncelikler", "acik_kisitlar"):
                if not all(isinstance(x, str) for x in v):
                    raise ValueError(f"{name} must be a list of strings")
            elif name != "yas" and (not isinstance(v, str) or not v.strip()):
                raise ValueError(f"{name} must be a non-empty string, got {v!r}")

    @classmethod
    def from_dict(cls, d: Mapping) -> Persona:
        missing = [k for k in PERSONA_REQUIRED if k not in d]
        unknown = sorted(set(d) - {f.name for f in dataclasses.fields(cls)})
        if missing or unknown:
            raise ValueError(f"persona: missing {missing}, unknown {unknown}")
        return _from_json(cls, d)

    def to_dict(self) -> dict:
        return _to_json(self)


# --- decision output (docs/decision.md) ---------------------------------------

class DecisionState(StrEnum):
    READY = "ready"                      # ranked; non-blocking questions may be open
    NEEDS_RM_INPUT = "needs_rm_input"    # an open blocking question; nothing ranked


class RmStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


OPTION_KINDS = ("deposit", "time_deposit", "fund")


@dataclass(frozen=True)
class ProductOption:
    option_id: str          # "deposit:ing_turuncu" | "time_deposit:ing_e_vadeli" | "fund:<code>"
    kind: str               # "deposit" (the baseline) | "time_deposit" (ranked) | "fund"
    label: str              # what the RM reads (deposit name, fund name)
    entity: str = ""        # DataPoint.entity it is measured by, e.g. a fund code
    fund_kind: str = ""     # funds only: money_market | debt | ... (config/decision.yaml)
    fx: bool = False        # funds only: the fund carries FX exposure

    def __post_init__(self) -> None:
        if self.kind not in OPTION_KINDS:
            raise ValueError(f"kind must be one of {OPTION_KINDS}, got {self.kind!r}")
        if self.kind == "fund" and not self.fund_kind:
            raise ValueError("a fund option needs a fund_kind")
        if self.kind in ("deposit", "time_deposit") and (self.fund_kind or self.fx):
            raise ValueError(f"a {self.kind} option has no fund_kind and no fx tag")


@dataclass(frozen=True)
class ConstraintResult:
    rule_id: str            # hard rule, now only "risk_ceiling" (docs/decision.md section 2)
    passed: bool
    reason: str             # why, in words the RM can repeat to the client
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScoredOption:
    option: ProductOption
    score: float                                # sum of score_parts
    score_parts: Mapping[str, float]            # criterion | "penalty:<rule>" -> part (penalties < 0)
    constraints: tuple[ConstraintResult, ...]   # hard rules, all passed
    confidence: float                           # 0..1: how far the inputs can be trusted
    stability: float                            # 0..1: share of perturbed runs in positions 1-10
    evidence_ids: tuple[str, ...] = ()
    reasons: Mapping[str, str] = field(default_factory=dict)   # same keys as score_parts

    def __post_init__(self) -> None:
        for name in ("confidence", "stability"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {v!r}")
        if not all(c.passed for c in self.constraints):
            raise ValueError("a scored option must pass all its constraints")
        if not math.isclose(sum(self.score_parts.values()), self.score, abs_tol=1e-9):
            raise ValueError("score_parts must sum to score")
        if set(self.reasons) != set(self.score_parts):
            raise ValueError("reasons must have exactly the keys of score_parts")


@dataclass(frozen=True)
class RejectedOption:
    option: ProductOption
    failed: tuple[ConstraintResult, ...]        # at least one, all failed

    def __post_init__(self) -> None:
        if not self.failed or any(c.passed for c in self.failed):
            raise ValueError("a rejected option needs failed constraints only")


@dataclass(frozen=True)
class ClarificationQuestion:
    question_id: str        # "q:<field>" | "q:acik_kisitlar[<i>]"
    text: str               # the question for the RM (Turkish)
    reason: str             # why the engine cannot decide without it
    about: str = ""         # persona field it resolves, e.g. "acik_kisitlar[0]"
    choices: tuple[str, ...] = ()
    answer: str | None = None
    blocking: bool = True   # open + blocking -> needs_rm_input

    def __post_init__(self) -> None:
        if self.answer is not None and self.choices and self.answer not in self.choices:
            raise ValueError(f"answer {self.answer!r} is not one of {self.choices}")


@dataclass(frozen=True)
class DecisionWarning:
    code: str               # concentration | fx_exposure | risk_estimate | low_stability |
                            # deposit_vs_market | no_fx_deposit_data
    message: str
    evidence_ids: tuple[str, ...] = ()
    option_ids: tuple[str, ...] = ()            # options it is about; () = the whole result


@dataclass(frozen=True)
class DataQualityNote:
    message: str            # e.g. "tefas_web: 1,613 values need check"
    flags: tuple[str, ...] = ()                 # Flag values involved
    sources: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionResult:
    run_id: str             # "R" + 10 hex; same inputs -> same id (docs/decision.md section 7)
    config_hash: str        # hash of config/decision.yaml as parsed
    created_at: datetime
    persona: Persona        # exactly the persona used (an edited test persona included)
    snapshot_id: str
    excluded_sources: frozenset[str]
    state: DecisionState
    options: tuple[ScoredOption, ...] = ()      # display order; a deposit, if any, is first
    rejected: tuple[RejectedOption, ...] = ()
    questions: tuple[ClarificationQuestion, ...] = ()
    assumptions: tuple[str, ...] = ()
    warnings: tuple[DecisionWarning, ...] = ()
    data_quality: tuple[DataQualityNote, ...] = ()
    rm_status: RmStatus = RmStatus.PENDING
    rm_note: str = ""                           # the RM's general note
    rm_selected: tuple[str, ...] = ()           # option_ids to discuss with the client
    rm_option_notes: Mapping[str, str] = field(default_factory=dict)  # option_id -> note

    @property
    def persona_id(self) -> str:
        return self.persona.persona_id

    def __post_init__(self) -> None:
        for name in ("run_id", "config_hash", "snapshot_id"):
            if not getattr(self, name):
                raise ValueError(f"{name} must be non-empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        object.__setattr__(self, "created_at", self.created_at.astimezone(TR_TZ))

        open_blocking = [q for q in self.questions if q.answer is None and q.blocking]
        if self.state == DecisionState.NEEDS_RM_INPUT:
            if not open_blocking:
                raise ValueError("needs_rm_input requires an unanswered blocking question")
            if self.options or self.rejected:
                raise ValueError("needs_rm_input has no options and no rejected options")
        if self.state == DecisionState.READY and open_blocking:
            raise ValueError("ready with an unanswered blocking question")

        ids = [o.option.option_id for o in self.options]
        if len(ids) != len(set(ids)):
            raise ValueError("option ids must be unique")
        if "deposit" in [o.option.kind for o in self.options[1:]]:
            raise ValueError("a deposit option must be first (the baseline)")

        known = set(ids) | {r.option.option_id for r in self.rejected}
        for w in self.warnings:
            if not set(w.option_ids) <= known:
                raise ValueError(f"warning {w.code} names unknown options")

        if not set(self.rm_selected) <= set(ids):
            raise ValueError("rm_selected names options that are not scored")
        if not set(self.rm_option_notes) <= set(self.rm_selected):
            raise ValueError("rm_option_notes only for selected options")
        if self.rm_status == RmStatus.APPROVED:
            if self.state != DecisionState.READY:
                raise ValueError("only a ready result can be approved")
            if not self.rm_selected:
                raise ValueError("an approved result needs at least one selected option")
        elif self.rm_selected:
            raise ValueError("rm_selected is set only on approval")

    def evidence_ids(self) -> frozenset[str]:
        ids: set[str] = set()
        for o in self.options:
            ids.update(o.evidence_ids)
            for c in o.constraints:
                ids.update(c.evidence_ids)
        for r in self.rejected:
            for c in r.failed:
                ids.update(c.evidence_ids)
        for w in self.warnings:
            ids.update(w.evidence_ids)
        for n in self.data_quality:
            ids.update(n.evidence_ids)
        return frozenset(ids)

    def to_dict(self) -> dict:
        return _to_json(self)

    @classmethod
    def from_dict(cls, d: Mapping) -> DecisionResult:
        return _from_json(cls, d)


# --- narrator (v1.2, docs/narrator.md) ------------------------------------------

NARRATIVE_LANGS = ("TR", "EN")
NARRATIVE_SECTIONS = ("ozet", "oneriler", "alternatifler", "dikkat", "sorular",
                      "teklif_metni", "varsayimlar")
NARRATIVE_SOURCES = ("llm", "template")


class NarrativeStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


@dataclass(frozen=True)
class NarrativeSentence:
    text: str
    option_ids: tuple[str, ...] = ()     # options the sentence talks about
    evidence_ids: tuple[str, ...] = ()   # DataPoint ids it rests on


@dataclass(frozen=True)
class NarrativeSection:
    key: str                             # one of NARRATIVE_SECTIONS
    sentences: tuple[NarrativeSentence, ...]

    def __post_init__(self) -> None:
        if self.key not in NARRATIVE_SECTIONS:
            raise ValueError(f"unknown section key {self.key!r}; known: {NARRATIVE_SECTIONS}")


@dataclass(frozen=True)
class NarrativeDraft:
    """The meeting text for one approved run in one language."""

    run_id: str
    lang: str                            # "TR" | "EN"
    sections: tuple[NarrativeSection, ...]
    source: str                          # "llm" | "template"
    model: str                           # "" for the template
    prompt_version: str
    checks: tuple[str, ...]              # validator findings; () = passed
    created_at: datetime                 # timezone-aware
    cost_usd: float = 0.0
    status: NarrativeStatus = NarrativeStatus.DRAFT
    rm_text: str = ""                    # the RM's edited text (Markdown); required when approved

    def __post_init__(self) -> None:
        if self.lang not in NARRATIVE_LANGS:
            raise ValueError(f"lang must be one of {NARRATIVE_LANGS}, got {self.lang!r}")
        if self.source not in NARRATIVE_SOURCES:
            raise ValueError(f"source must be one of {NARRATIVE_SOURCES}, got {self.source!r}")
        if (self.source == "template") != (self.model == ""):
            raise ValueError("model must be empty exactly for a template draft")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.cost_usd < 0:
            raise ValueError("cost_usd must be >= 0")
        object.__setattr__(self, "status", NarrativeStatus(self.status))
        if self.status == NarrativeStatus.APPROVED and not self.rm_text.strip():
            raise ValueError("an approved narrative needs rm_text")

    def to_dict(self) -> dict:
        return _to_json(self)

    @classmethod
    def from_dict(cls, d: Mapping) -> NarrativeDraft:
        return _from_json(cls, d)


class Backend(Protocol):
    """What the UI calls (docs/ui.md). FakeBackend (ui worker) serves fixtures;
    the real backend (lead, on main) wires ingest + decision and keeps the runs
    of the session in memory."""

    def list_personas(self) -> list[Persona]: ...

    def list_snapshots(self) -> list[str]: ...             # newest first

    def evidence(self, snapshot_id: str,
                 exclude_sources: frozenset[str] = frozenset()) -> EvidenceSet: ...

    def decide(self, persona: Persona, snapshot_id: str,
               exclude_sources: frozenset[str] = frozenset()) -> DecisionResult: ...

    def answer_question(self, run_id: str, question_id: str, answer: str) -> DecisionResult:
        """New run: the inputs of run_id plus this answer (earlier answers kept)."""
        ...

    def approve(self, run_id: str, status: RmStatus, note: str = "",
                selected_option_ids: tuple[str, ...] = ()) -> DecisionResult:
        """Same run with rm_status set; saved (real backend: data/runs/<run_id>.json)."""
        ...

    def annotate(self, run_id: str, note: str,
                 option_notes: Mapping[str, str]) -> DecisionResult:
        """Set rm_note and rm_option_notes of an approved run; saved again."""
        ...

    def save_card(self, run_id: str, markdown: str) -> str:
        """Store the summary card of an approved run; returns where (path or key)."""
        ...

    def draft_narrative(self, run_id: str, lang: str = "TR") -> NarrativeDraft:
        """The meeting text of an approved run (v1.2); cached per (run_id, lang,
        prompt_version, model)."""
        ...

    def approve_narrative(self, run_id: str, lang: str, text: str) -> NarrativeDraft:
        """Store the RM's final text (status approved); the card uses it."""
        ...


# --- JSON (fixtures, UI cache) --------------------------------------------------

def _to_json(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_json(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, StrEnum):
        return obj.value
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, frozenset):
        return sorted(_to_json(x) for x in obj)
    if isinstance(obj, (tuple, list)):
        return [_to_json(x) for x in obj]
    if isinstance(obj, Mapping):
        return {k: _to_json(v) for k, v in obj.items()}
    return obj


def _from_json(tp, data):
    import typing

    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if dataclasses.is_dataclass(tp):
        hints = typing.get_type_hints(tp)
        names = {f.name for f in dataclasses.fields(tp)}
        unknown = set(data) - names
        if unknown:
            raise ValueError(f"{tp.__name__}: unknown keys {sorted(unknown)}")
        return tp(**{k: _from_json(hints[k], v) for k, v in data.items()})
    if origin is typing.Union or type(tp).__name__ == "UnionType":
        if data is None:
            return None
        return _from_json(next(a for a in args if a is not type(None)), data)
    if origin is tuple:
        return tuple(_from_json(args[0], x) for x in data)
    if origin is frozenset:
        return frozenset(_from_json(args[0], x) for x in data)
    if origin in (Mapping, dict) or tp is Mapping:
        return {k: _from_json(args[1], v) for k, v in data.items()}
    if tp is datetime:
        return datetime.fromisoformat(data)
    if tp is date:
        return date.fromisoformat(data)
    if isinstance(tp, type) and issubclass(tp, StrEnum):
        return tp(data)
    if tp is float and isinstance(data, int) and not isinstance(data, bool):
        return float(data)
    return data
