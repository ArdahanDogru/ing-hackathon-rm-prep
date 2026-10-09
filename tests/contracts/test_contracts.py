import dataclasses
from datetime import date, datetime, timedelta, timezone

import pytest

from rmprep.contracts import TR_TZ, DataPoint, Flag, make_id

UTC = timezone.utc


def _dp(**overrides) -> DataPoint:
    kwargs = dict(
        quantity="policy_rate",
        entity="TP.X",
        value=40.5,
        unit="pct",
        as_of=date(2026, 10, 1),
        source="evds",
        source_url="https://evds2.tcmb.gov.tr/",
        fetched_at=datetime(2026, 10, 9, 15, 0, tzinfo=TR_TZ),
        snapshot_id="20261009-150000-ab12",
        raw_ref="20261009-150000-ab12/payloads/evds.json#items[0]",
    )
    kwargs.update(overrides)
    return DataPoint.create(**kwargs)


# --- id ---------------------------------------------------------------------

def test_make_id_matches_reference_vectors():
    assert make_id("evds", "policy_rate", "TP.X", date(2026, 10, 1)) == "E27595228"
    assert make_id("tefas", "fund_price", "AFT", date(2026, 10, 8)) == "E1b3c6f36"


@pytest.mark.parametrize("field,value", [
    ("source", "manual"),
    ("quantity", "deposit_rate"),
    ("entity", "TP.Y"),
    ("as_of", date(2026, 10, 2)),
])
def test_id_changes_with_each_key_field(field, value):
    assert _dp(**{field: value}).id != _dp().id


def test_id_ignores_non_key_fields():
    other = _dp(value=1.0, unit="x", note="n", snapshot_id="S2", raw_ref="S2/p#0",
                fetched_at=datetime(2027, 1, 1, tzinfo=TR_TZ))
    assert other.id == _dp().id


def test_wrong_id_rejected():
    dp = _dp()
    with pytest.raises(ValueError, match="does not match"):
        dataclasses.replace(dp, id="E00000000")


def test_key_field_edit_rejected_by_id_check():
    with pytest.raises(ValueError, match="does not match"):
        dataclasses.replace(_dp(), as_of=date(2020, 1, 1))


@pytest.mark.parametrize("field", ["source", "quantity", "entity"])
def test_separator_in_key_field_rejected(field):
    with pytest.raises(ValueError, match="must not contain"):
        _dp(**{field: "a|b"})


# --- value / missing ----------------------------------------------------------

def test_null_value_without_missing_flag_rejected():
    with pytest.raises(ValueError, match="requires the missing flag"):
        _dp(value=None)


def test_null_value_with_missing_flag_accepted():
    dp = _dp(value=None, flags=[Flag.MISSING])
    assert dp.value is None and Flag.MISSING in dp.flags


def test_missing_flag_with_value_rejected():
    with pytest.raises(ValueError, match="missing flag set"):
        _dp(flags=[Flag.MISSING])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "1.5"])
def test_bad_values_rejected(bad):
    with pytest.raises(ValueError):
        _dp(value=bad)


def test_int_value_stored_as_float():
    assert isinstance(_dp(value=3).value, float)


# --- dates --------------------------------------------------------------------

def test_naive_fetched_at_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        _dp(fetched_at=datetime(2026, 10, 9, 12, 0))


def test_fetched_at_converted_to_turkey_time_same_instant():
    utc_time = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
    dp = _dp(fetched_at=utc_time)
    assert dp.fetched_at.tzinfo == TR_TZ
    assert dp.fetched_at.hour == 15
    assert dp.fetched_at.utcoffset() == timedelta(hours=3)
    assert dp.fetched_at == utc_time


def test_as_of_datetime_rejected():
    with pytest.raises(ValueError, match="as_of must be a date"):
        _dp(as_of=datetime(2026, 10, 1, tzinfo=TR_TZ))


# --- strings and flags ----------------------------------------------------------

@pytest.mark.parametrize("field", ["source_url", "raw_ref", "unit", "snapshot_id"])
def test_empty_required_string_rejected(field):
    with pytest.raises(ValueError, match="non-empty"):
        _dp(**{field: "  "})


def test_string_flags_coerced():
    dp = _dp(flags=["stale", Flag.CONFLICT])
    assert dp.flags == {Flag.STALE, Flag.CONFLICT}
    assert dp.sorted_flags() == ["conflict", "stale"]


def test_unknown_flag_rejected():
    with pytest.raises(ValueError):
        _dp(flags=["suspicious"])


def test_all_contract_flags_exist():
    assert {f.value for f in Flag} == {
        "missing", "stale", "out_of_range", "conflict", "fallback_snapshot",
        "unverified_series", "manual_entry", "needs_check",
    }


# --- immutability / with_flags ---------------------------------------------------

def test_datapoint_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _dp().value = 1.0  # type: ignore[misc]


def test_with_flags_adds_flags_and_keeps_value():
    dp = _dp(note="first")
    flagged = dp.with_flags(Flag.STALE, Flag.NEEDS_CHECK, note="second")
    assert flagged.flags == {Flag.STALE, Flag.NEEDS_CHECK}
    assert flagged.note == "first; second"
    assert flagged.value == dp.value and flagged.id == dp.id
    assert dp.flags == frozenset() and dp.note == "first"


def test_with_flags_without_note_keeps_note():
    assert _dp().with_flags(Flag.STALE).note == ""
