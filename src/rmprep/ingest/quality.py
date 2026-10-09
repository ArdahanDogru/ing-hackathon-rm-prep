"""Quality checks. Pure functions: they add flags and append notes, and never
change a value, date or any other field.

Order: plausibility -> staleness -> duplicates -> cross-source conflict.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from itertools import combinations

from rmprep.ingest.config import Config
from rmprep.contracts import DataPoint, Flag


def run_checks(points: list[DataPoint], cfg: Config, reference_date: date) -> list[DataPoint]:
    """All checks. `reference_date` is the snapshot date (never today's date),
    so the result depends only on the snapshot. Output is sorted by id."""
    pts = check_known_quantity(points, cfg)
    pts = check_plausibility(pts, cfg)
    pts = check_staleness(pts, cfg, reference_date)
    pts = check_duplicates(pts)
    pts = check_cross_source_conflict(pts, cfg)
    return sorted(pts, key=lambda p: p.id)


def check_known_quantity(points: list[DataPoint], cfg: Config) -> list[DataPoint]:
    """Rows from an older config (fallback) can carry a quantity that the
    current config no longer declares. Such rows skip the bound checks."""
    return [p if p.quantity in cfg.quantities else
            p.with_flags(Flag.NEEDS_CHECK, note=f"quantity {p.quantity!r} not in config")
            for p in points]


def check_plausibility(points: list[DataPoint], cfg: Config) -> list[DataPoint]:
    out = []
    for p in points:
        q = cfg.quantities.get(p.quantity)
        if q and p.value is not None and not q.min <= p.value <= q.max:
            p = p.with_flags(Flag.OUT_OF_RANGE,
                             note=f"value {p.value!r} outside [{q.min!r}, {q.max!r}]")
        out.append(p)
    return out


def check_staleness(points: list[DataPoint], cfg: Config, reference_date: date) -> list[DataPoint]:
    """Only the latest observation per (source, quantity, entity) is checked.
    Missing rows are not observations and are ignored here."""
    latest: dict[tuple[str, str, str], date] = {}
    for p in points:
        if p.value is None:
            continue
        key = (p.source, p.quantity, p.entity)
        if key not in latest or p.as_of > latest[key]:
            latest[key] = p.as_of

    out = []
    for p in points:
        q = cfg.quantities.get(p.quantity)
        key = (p.source, p.quantity, p.entity)
        if p.value is not None and q and latest.get(key) == p.as_of:
            age = (reference_date - p.as_of).days
            if age > q.max_age_days:
                p = p.with_flags(Flag.STALE, note=f"age {age} days > max {q.max_age_days}")
            elif age < 0:
                p = p.with_flags(Flag.NEEDS_CHECK, note=f"as_of is {-age} days after snapshot date")
        out.append(p)
    return out


def check_duplicates(points: list[DataPoint]) -> list[DataPoint]:
    """Rows with the same id in one snapshot. Keep the row with the lowest
    raw_ref. Equal values: note only. Different values: conflict + needs_check,
    and the other values with their raw_ref go into the note."""
    groups: dict[str, list[DataPoint]] = defaultdict(list)
    for p in points:
        groups[p.id].append(p)

    out = []
    for group in groups.values():
        group.sort(key=lambda p: p.raw_ref)
        keep, others = group[0], group[1:]
        if others:
            if all(o.value == keep.value for o in others):
                keep = keep.with_flags(note=f"{len(others)} identical duplicate row(s): "
                                            + ", ".join(o.raw_ref for o in others))
            else:
                listed = ", ".join(f"{o.value!r} @ {o.raw_ref}" for o in others)
                keep = keep.with_flags(Flag.CONFLICT, Flag.NEEDS_CHECK,
                                       note=f"duplicate rows with other values: {listed}")
        out.append(keep)
    return out


def relative_difference(a: float, b: float) -> float:
    scale = max(abs(a), abs(b))
    return 0.0 if scale == 0 else abs(a - b) / scale


def check_cross_source_conflict(points: list[DataPoint], cfg: Config) -> list[DataPoint]:
    """Same (quantity, entity, as_of) from different sources. If the relative
    difference of any pair is above the quantity's conflict_tolerance, both rows
    get `conflict`. Entities must use the same name in both sources."""
    groups: dict[tuple[str, str, date], list[int]] = defaultdict(list)
    for i, p in enumerate(points):
        if p.value is not None and p.quantity in cfg.quantities:
            groups[(p.quantity, p.entity, p.as_of)].append(i)

    notes: dict[int, list[str]] = defaultdict(list)
    for (quantity, _, _), idxs in groups.items():
        tol = cfg.quantities[quantity].conflict_tolerance
        for i, j in combinations(idxs, 2):
            a, b = points[i], points[j]
            if a.source == b.source:
                continue
            diff = relative_difference(a.value, b.value)
            if diff > tol:
                notes[i].append(f"differs from {b.source} {b.value!r} ({diff:.4%} > {tol:.4%})")
                notes[j].append(f"differs from {a.source} {a.value!r} ({diff:.4%} > {tol:.4%})")

    return [p.with_flags(Flag.CONFLICT, note="; ".join(notes[i])) if i in notes else p
            for i, p in enumerate(points)]
