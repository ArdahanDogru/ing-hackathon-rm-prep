from datetime import date, timedelta

import pytest

from tests.ingest.conftest import T0
from rmprep.contracts import DataPoint, Flag
from rmprep.ingest.quality import (
    check_cross_source_conflict,
    check_duplicates,
    check_plausibility,
    check_staleness,
    relative_difference,
    run_checks,
)

REF = T0.date()   # 2026-10-09


def dp(value=41.0, *, quantity="usd_try", entity="USD", as_of=date(2026, 10, 8),
       source="evds", raw="S/p#0", flags=()):
    flags = set(flags)
    if value is None:
        flags.add(Flag.MISSING)
    return DataPoint.create(quantity=quantity, entity=entity, value=value, unit="TRY",
                            as_of=as_of, source=source, source_url="https://x.test/",
                            fetched_at=T0, snapshot_id="S", raw_ref=raw, flags=flags)


# --- plausibility -----------------------------------------------------------------

@pytest.mark.parametrize("value,flagged", [(0.5, True), (1.0, False), (41.0, False),
                                           (500.0, False), (501.0, True), (None, False)])
def test_out_of_range(cfg, value, flagged):
    [p] = check_plausibility([dp(value)], cfg)
    assert (Flag.OUT_OF_RANGE in p.flags) is flagged
    assert p.value == value


def test_out_of_range_note(cfg):
    [p] = check_plausibility([dp(4100.0)], cfg)
    assert p.note == "value 4100.0 outside [1.0, 500.0]"


# --- staleness ---------------------------------------------------------------------

def test_stale_latest_observation(cfg):
    old = dp(as_of=REF - timedelta(days=6))           # usd_try max_age_days = 5
    [p] = check_staleness([old], cfg, REF)
    assert Flag.STALE in p.flags and p.note == "age 6 days > max 5"


def test_age_at_limit_not_stale(cfg):
    [p] = check_staleness([dp(as_of=REF - timedelta(days=5))], cfg, REF)
    assert Flag.STALE not in p.flags


def test_only_latest_observation_checked(cfg):
    history = [dp(as_of=REF - timedelta(days=d), raw=f"S/p#{d}") for d in (1, 30, 60)]
    out = check_staleness(history, cfg, REF)
    assert not any(Flag.STALE in p.flags for p in out)


def test_staleness_per_entity(cfg):
    fresh = dp(entity="A", as_of=REF)
    stale = dp(entity="B", as_of=REF - timedelta(days=10))
    a, b = check_staleness([fresh, stale], cfg, REF)
    assert Flag.STALE not in a.flags and Flag.STALE in b.flags


def test_missing_rows_ignored_by_staleness(cfg):
    missing = dp(None, as_of=REF)
    old = dp(as_of=REF - timedelta(days=10), raw="S/p#1")
    m, o = check_staleness([missing, old], cfg, REF)
    assert Flag.STALE not in m.flags and Flag.STALE in o.flags


def test_future_as_of_needs_check(cfg):
    [p] = check_staleness([dp(as_of=REF + timedelta(days=2))], cfg, REF)
    assert Flag.NEEDS_CHECK in p.flags and "after snapshot date" in p.note


# --- duplicates ----------------------------------------------------------------------

def test_identical_duplicates_collapse(cfg):
    out = check_duplicates([dp(41.0, raw="S/p#2"), dp(41.0, raw="S/p#1")])
    [p] = out
    assert p.raw_ref == "S/p#1" and p.flags == frozenset()
    assert p.note == "1 identical duplicate row(s): S/p#2"


def test_conflicting_duplicates_flagged(cfg):
    out = check_duplicates([dp(42.0, raw="S/p#2"), dp(41.0, raw="S/p#1")])
    [p] = out
    assert p.value == 41.0 and p.raw_ref == "S/p#1"
    assert p.flags == {Flag.CONFLICT, Flag.NEEDS_CHECK}
    assert p.note == "duplicate rows with other values: 42.0 @ S/p#2"


# --- cross-source conflict -------------------------------------------------------------

def test_cross_source_conflict_both_flagged(cfg):
    a, b = check_cross_source_conflict([dp(41.0), dp(42.0, source="manual")], cfg)
    assert Flag.CONFLICT in a.flags and Flag.CONFLICT in b.flags
    assert a.note.startswith("differs from manual 42.0")
    assert a.value == 41.0 and b.value == 42.0


def test_within_tolerance_no_conflict(cfg):
    a, b = check_cross_source_conflict([dp(41.0), dp(41.1, source="manual")], cfg)  # 0.24% < 0.5%
    assert Flag.CONFLICT not in a.flags | b.flags


def test_different_date_or_entity_not_compared(cfg):
    pts = [dp(41.0), dp(50.0, source="manual", as_of=date(2026, 10, 7)),
           dp(50.0, source="tefas", entity="EUR")]
    assert not any(Flag.CONFLICT in p.flags for p in check_cross_source_conflict(pts, cfg))


def test_missing_values_not_compared(cfg):
    pts = [dp(41.0), dp(None, source="manual")]
    assert not any(Flag.CONFLICT in p.flags for p in check_cross_source_conflict(pts, cfg))


def test_relative_difference():
    assert relative_difference(0.0, 0.0) == 0.0
    assert relative_difference(100.0, 90.0) == pytest.approx(0.1)


# --- run_checks -----------------------------------------------------------------------------

def test_checks_never_change_values_or_keys(cfg):
    pts = [dp(4100.0, entity="A"), dp(41.0, entity="B", as_of=REF - timedelta(days=40)),
           dp(None, entity="C"), dp(41.0, entity="D"), dp(45.0, entity="D", source="manual")]
    out = run_checks(pts, cfg, REF)
    key = lambda p: (p.id, p.value, p.as_of, p.unit, p.source, p.raw_ref, p.fetched_at)
    assert sorted(map(key, out)) == sorted(map(key, pts))


def test_run_checks_sorted_and_deterministic(cfg):
    pts = [dp(41.0, entity=e) for e in "DCBA"]
    out = run_checks(pts, cfg, REF)
    assert [p.id for p in out] == sorted(p.id for p in out)
    assert run_checks(pts, cfg, REF) == out


def test_unknown_quantity_needs_check(cfg):
    [p] = run_checks([dp(quantity="old_quantity")], cfg, REF)
    assert Flag.NEEDS_CHECK in p.flags and "not in config" in p.note
