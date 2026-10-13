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
# v1.3 (2026-10-11): warning audience, talking points, to_confirm; narrator
# section talking_points, sentence title, need_tags (docs/web-ui.md section 3).
# v1.4 (2026-10-12): NarrativeBrief + Backend.brief (docs/web-ui.md "LLM brief").
# v1.5 (2026-10-12): per-block edits of the meeting text (rm_edits, edit_checks,
# Backend.edit_narrative; docs/web-ui.md "Section-by-section editing").
# v1.6 (2026-10-12): ProductOption.asset_class, DecisionResult.recommended
# (docs/decision.md section 10, D19).
# v1.7 (2026-10-12): approval times, DecisionResult.rm_decided_at and
# NarrativeDraft.approved_at (deliverable 6, the decision record).
# v1.8 (2026-10-13): model allocation bands, DecisionResult.allocation and
# allocation_notes (docs/decision.md section 11, D20).
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
    asset_class: str = ""   # v1.6: nakit_benzeri | borclanma | dengeli | hisse | altin_doviz ("" = not set)

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


WARNING_AUDIENCES = ("client", "rm")


@dataclass(frozen=True)
class DecisionWarning:
    code: str               # concentration | fx_exposure | risk_estimate | low_stability |
                            # deposit_vs_market | no_fx_deposit_data | stale_tax_input (D22)
    message: str
    evidence_ids: tuple[str, ...] = ()
    option_ids: tuple[str, ...] = ()            # options it is about; () = the whole result
    audience: str = "rm"                        # v1.3: "client" may go into client-facing text

    def __post_init__(self) -> None:
        if self.audience not in WARNING_AUDIENCES:
            raise ValueError(f"audience must be one of {WARNING_AUDIENCES}, got {self.audience!r}")


@dataclass(frozen=True)
class TalkingPoint:
    """v1.3: one card of "Müşteriyle konuşulacaklar" (decision D18, docs/web-ui.md)."""

    code: str               # deposit_real | best_alternative | access | risk_fit
    label: str              # short, e.g. "Mevduatta reel getiri"
    figure: str             # the large number as text, Turkish format, e.g. "−%8,3"
    text: str               # one sentence, from the client's view
    evidence_ids: tuple[str, ...] = ()
    option_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("code", "label", "figure", "text"):
            if not getattr(self, name).strip():
                raise ValueError(f"talking point {name} must be non-empty")


@dataclass(frozen=True)
class AllocationBand:
    """v1.8: one asset class of the strategic model allocation (D20)."""

    asset_class: str            # a D19 class
    low: float | None           # % of the portfolio; None = no band (dengeli funds)
    high: float | None
    source: str                 # short source text ("Ata Yatırım, 28.04.2026" / "çıkarım")
    inferred: bool              # the band is our inference, not a source value
    option_id: str | None       # the best scored option of the class for this client
    note: str                   # "" | "ceiling" | "none" | "negative_real" (texts in config)

    def __post_init__(self) -> None:
        if not self.asset_class.strip():
            raise ValueError("asset_class must be non-empty")
        if (self.low is None) != (self.high is None):
            raise ValueError("low and high are both set or both None")
        if self.low is not None and not 0 <= self.low <= self.high <= 100:
            raise ValueError(f"band must satisfy 0 <= low <= high <= 100, got {self.low}-{self.high}")


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
    talking_points: tuple[TalkingPoint, ...] = ()   # v1.3, D18: 0..3, display order
    to_confirm: tuple[str, ...] = ()                # v1.3, D16: commands for the RM
    recommended: tuple[str, ...] = ()               # v1.6, D19: the engine's top 3 (option ids, in order)
    rm_decided_at: datetime | None = None           # v1.7: when the RM approved / rejected (Europe/Istanbul)
    allocation: tuple[AllocationBand, ...] = ()     # v1.8, D20: model bands per asset class
    allocation_notes: tuple[str, ...] = ()          # v1.8, D20: holding hints from the persona text

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
        if len(self.recommended) > 3:
            raise ValueError("at most 3 recommended options")
        if len(set(self.recommended)) != len(self.recommended):
            raise ValueError("a recommended option appears twice")
        if not set(self.recommended) <= set(ids):
            raise ValueError("recommended names options that are not scored")
        for band in self.allocation:
            if band.option_id is not None and band.option_id not in ids:
                raise ValueError(f"allocation {band.asset_class} names an option that is not scored")
        if len(self.talking_points) > 3:
            raise ValueError("at most 3 talking points")
        for tp in self.talking_points:
            if not set(tp.option_ids) <= set(ids):
                raise ValueError(f"talking point {tp.code} names options that are not scored")

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
        if self.rm_decided_at is not None:
            if self.rm_status == RmStatus.PENDING:
                raise ValueError("a pending result has no decision time")
            if self.rm_decided_at.tzinfo is None:
                raise ValueError("rm_decided_at must be timezone-aware")
            object.__setattr__(self, "rm_decided_at", self.rm_decided_at.astimezone(TR_TZ))

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
# v1.3: the sections of a draft from narrator N9 on (talking_points added at the
# end). NARRATIVE_SECTIONS stays the v1.2 list, so a v1.2 narrator stays valid.
NARRATIVE_SECTIONS_V13 = NARRATIVE_SECTIONS + ("talking_points",)
NARRATIVE_SOURCES = ("llm", "template")


BLOCKING_CHECK_KINDS = ("phrase", "option", "internal", "label")   # v1.5; "number" only warns


class NarrativeStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


@dataclass(frozen=True)
class NarrativeSentence:
    text: str
    option_ids: tuple[str, ...] = ()     # options the sentence talks about
    evidence_ids: tuple[str, ...] = ()   # DataPoint ids it rests on
    title: str = ""                      # v1.3: talking_points only, a 2-4 word heading


@dataclass(frozen=True)
class NarrativeSection:
    key: str                             # one of NARRATIVE_SECTIONS
    sentences: tuple[NarrativeSentence, ...]

    def __post_init__(self) -> None:
        if self.key not in NARRATIVE_SECTIONS_V13:
            raise ValueError(f"unknown section key {self.key!r}; known: {NARRATIVE_SECTIONS_V13}")


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
    need_tags: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # v1.3: option_id -> persona priorities
    rm_edits: Mapping[str, str] = field(default_factory=dict)        # v1.5: block id -> the RM's text
    edit_checks: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # v1.5: block id -> "kind: message"
    approved_at: datetime | None = None  # v1.7: when the RM approved the text (Europe/Istanbul)

    def blocking_findings(self) -> dict[str, tuple[str, ...]]:
        """The findings of the edited blocks that stop the approval (v1.5)."""
        out = {}
        for block, findings in self.edit_checks.items():
            hard = tuple(f for f in findings if f.split(":", 1)[0].strip() in BLOCKING_CHECK_KINDS)
            if hard:
                out[block] = hard
        return out

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
        if self.approved_at is not None:
            if self.status != NarrativeStatus.APPROVED:
                raise ValueError("a draft has no approval time")
            if self.approved_at.tzinfo is None:
                raise ValueError("approved_at must be timezone-aware")

    def to_dict(self) -> dict:
        return _to_json(self)

    @classmethod
    def from_dict(cls, d: Mapping) -> NarrativeDraft:
        return _from_json(cls, d)


BRIEF_MAX_CHARS = 280


@dataclass(frozen=True)
class NarrativeBrief:
    """v1.4: the dashboard brief of a ready run, for the RM only (never in the
    card or the meeting text)."""

    run_id: str
    lang: str                            # "TR" | "EN"
    text: str                            # 1-2 sentences, at most BRIEF_MAX_CHARS
    source: str                          # "llm" | "template"
    model: str                           # "" for the template
    prompt_version: str
    checks: tuple[str, ...]              # validator findings / errors; () = passed
    created_at: datetime                 # timezone-aware
    cost_usd: float = 0.0
    cite: tuple[str, ...] = ()           # evidence ids and option ids it rests on

    def __post_init__(self) -> None:
        if self.lang not in NARRATIVE_LANGS:
            raise ValueError(f"lang must be one of {NARRATIVE_LANGS}, got {self.lang!r}")
        if self.source not in NARRATIVE_SOURCES:
            raise ValueError(f"source must be one of {NARRATIVE_SOURCES}, got {self.source!r}")
        if (self.source == "template") != (self.model == ""):
            raise ValueError("model must be empty exactly for a template brief")
        if not self.text.strip() or len(self.text) > BRIEF_MAX_CHARS:
            raise ValueError(f"text must be 1..{BRIEF_MAX_CHARS} characters")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.cost_usd < 0:
            raise ValueError("cost_usd must be >= 0")

    def to_dict(self) -> dict:
        return _to_json(self)

    @classmethod
    def from_dict(cls, d: Mapping) -> NarrativeBrief:
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

    def edit_narrative(self, run_id: str, lang: str, block_id: str,
                       text: str | None) -> NarrativeDraft:
        """v1.5: set (text) or restore (None) one block of a draft meeting text;
        the block is checked at once (NarrativeDraft.edit_checks)."""
        ...

    def brief(self, run_id: str, lang: str = "TR") -> NarrativeBrief | None:
        """v1.4: the brief of a ready run; None while its background job runs
        (the call starts the job if needed). A needs_rm_input run raises ValueError."""
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
