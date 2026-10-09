from datetime import date, timedelta

import duckdb
import pytest

from tests.ingest.conftest import T0
from rmprep.contracts import TR_TZ, DataPoint, Flag
from rmprep.ingest.store import EvidenceStore


def dp(snapshot_id="S1", entity="USD", value=41.0, flags=()):
    flags = set(flags) | ({Flag.MISSING} if value is None else set())
    return DataPoint.create(quantity="usd_try", entity=entity, value=value, unit="TRY",
                            as_of=date(2026, 10, 8), source="evds",
                            source_url="https://x.test/", fetched_at=T0,
                            snapshot_id=snapshot_id, raw_ref=f"{snapshot_id}/p#0",
                            flags=flags, note="n")


@pytest.fixture
def store(tmp_path):
    with EvidenceStore(tmp_path / "e.duckdb") as s:
        yield s


def test_roundtrip_equal_datapoints(store):
    pts = [dp(entity="B", flags=[Flag.STALE, Flag.CONFLICT]), dp(entity="A", value=None)]
    store.load("S1", T0, pts)
    back = store.points("S1")
    assert back == sorted(pts, key=lambda p: p.id)
    assert back[0].fetched_at.tzinfo == TR_TZ


@pytest.mark.parametrize("note", ["", 'a, "quoted"; b', "line1\nline2", "Faiz işletilmeyecek tutar | ğüşıöç",
                                  "\\N", "NULL"])
def test_roundtrip_difficult_text(store, note):
    p = DataPoint.create(quantity="usd_try", entity='Bank "A", 3M', value=0.1 + 0.2, unit="TRY",
                         as_of=date(2026, 10, 8), source="manual", source_url="https://x.test/?a=1,2",
                         fetched_at=T0, snapshot_id="S1", raw_ref="S1/p#row=2;col=price",
                         flags=[Flag.MANUAL_ENTRY], note=note)
    store.load("S1", T0, [p])
    assert store.points("S1") == [p]                 # exact float, text and flags


def test_load_is_idempotent(store):
    store.load("S1", T0, [dp()])
    store.load("S1", T0, [dp()])
    assert len(store.points("S1")) == 1


def test_load_replaces_rows(store):
    store.load("S1", T0, [dp(entity="A"), dp(entity="B")])
    store.load("S1", T0, [dp(entity="A")])
    assert [p.entity for p in store.points("S1")] == ["A"]


def test_foreign_snapshot_rows_rejected(store):
    with pytest.raises(ValueError):
        store.load("S1", T0, [dp(snapshot_id="S2")])


def test_is_latest_follows_newest_created_at(store):
    store.load("S2", T0 + timedelta(days=1), [dp("S2")])
    store.load("S1", T0, [dp("S1")])                  # older snapshot loaded later
    assert store.latest_snapshot_id() == "S2"
    assert set(store.is_latest("S2").values()) == {True}
    assert set(store.is_latest("S1").values()) == {False}


def test_snapshot_with_no_rows_can_be_latest(store):
    store.load("S1", T0, [dp("S1")])
    store.load("S2", T0 + timedelta(days=1), [])
    assert store.latest_snapshot_id() == "S2"
    assert set(store.is_latest("S1").values()) == {False}


def test_parquet_export(store, tmp_path):
    store.load("S1", T0, [dp(entity="B"), dp(entity="A", value=None)])
    path = store.export_parquet("S1", tmp_path / "export")
    assert path.name == "S1.parquet"
    con = duckdb.connect()
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM '{path}'").fetchall()]
    assert "is_latest" not in cols and cols[0] == "id"
    rows = con.execute(f"SELECT id, value, flags FROM '{path}'").fetchall()
    assert [r[0] for r in rows] == sorted(r[0] for r in rows)
    assert {tuple(r[2]) for r in rows} == {(), ("missing",)}
