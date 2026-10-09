"""Contracts shared across layers. Owned by the lead (see CLAUDE.md,
"Multi-agent workflow"); workers request changes, they never edit this file.

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
class EvidenceSet:
    """Checked evidence of one snapshot (rmprep.ingest.pipeline.build_evidence).
    Downstream must read excluded_sources so it can say what a result was
    computed without. Excluded (read time, by the user) != missing."""

    snapshot_id: str
    created_at: datetime
    excluded_sources: frozenset[str]                 # excluded at read time (UI)
    source_status: Mapping[str, SourceStatusLike]    # from the manifest
    datapoints: tuple[DataPoint, ...]                # checked, sorted by id
