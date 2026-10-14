import hashlib
import json
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest

from rmprep.contracts import TR_TZ
from rmprep.ingest.snapshot import (
    MANIFEST,
    SnapshotError,
    SnapshotIntegrityError,
    SnapshotWriter,
    SourceRecord,
    find_previous_ok,
    list_snapshots,
    new_snapshot_id,
    open_snapshot,
    raw_ref,
)

T0 = datetime(2026, 10, 9, 15, 0, tzinfo=TR_TZ)
CONFIG = {"version": 1, "quantities": {}, "sources": {}}
BODY = b'{"items": [{"Tarih": "08-10-2026", "TP_FG_J0": "123,4"}]}'


def _ok(ref=None, at=T0) -> SourceRecord:
    return SourceRecord(status="ok", on_failure="previous", fetched_at=at,
                        request={"url": "https://example.test/series=X"},
                        payloads=(ref,) if ref else ())


def _write(root, created_at=T0, suffix="ab12", status="ok"):
    with SnapshotWriter(root, CONFIG, created_at=created_at,
                        snapshot_id=new_snapshot_id(created_at, suffix)) as w:
        if status == "ok":
            ref = w.add_payload("evds", "TP.FG.J0.json", BODY, meta={"series": "TP.FG.J0"})
            w.set_source("evds", _ok(ref, created_at))
        else:
            w.set_source("evds", SourceRecord(status="failed", on_failure="exclude",
                                              error="HTTP 500", excluded=True))
        return w.finalize()


def _writable(path):
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


# --- ids -------------------------------------------------------------------------

def test_snapshot_id_uses_turkey_time():
    utc_noon = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
    assert new_snapshot_id(utc_noon, "ab12") == "20261009-150000-ab12"


def test_snapshot_id_requires_aware_time():
    with pytest.raises(ValueError):
        new_snapshot_id(datetime(2026, 10, 9, 12, 0))


def test_random_suffix_is_four_hex():
    suffix = new_snapshot_id(T0).split("-")[2]
    assert len(suffix) == 4 and int(suffix, 16) >= 0


def test_raw_ref_format():
    assert raw_ref("20261009-150000-ab12", "payloads/evds/x.json", "items[0]") == \
        "20261009-150000-ab12/payloads/evds/x.json#items[0]"


# --- write / read ------------------------------------------------------------------

def test_roundtrip(tmp_path):
    snap = _write(tmp_path)
    assert snap.snapshot_id == "20261009-150000-ab12"
    assert snap.created_at == T0 and snap.created_at.tzinfo == TR_TZ
    assert snap.config_raw == CONFIG
    rec = snap.sources["evds"]
    assert rec.status == "ok" and rec.fetched_at == T0
    assert rec.payloads[0].meta == {"series": "TP.FG.J0"}
    assert snap.read_payload("payloads/evds/TP.FG.J0.json") == BODY


def test_manifest_is_utf8_with_turkey_offset(tmp_path):
    snap = _write(tmp_path)
    m = json.loads((snap.path / MANIFEST).read_text(encoding="utf-8"))
    assert m["created_at"] == "2026-10-09T15:00:00+03:00"


def test_no_tmp_folder_left(tmp_path):
    _write(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["20261009-150000-ab12"]


def test_finished_files_are_read_only(tmp_path):
    snap = _write(tmp_path)
    for f in snap.path.rglob("*"):
        if f.is_file():
            assert not os.access(f, os.W_OK), f
    with pytest.raises(PermissionError):
        (snap.path / "payloads/evds/TP.FG.J0.json").write_bytes(b"x")


def test_exception_discards_snapshot(tmp_path):
    with pytest.raises(RuntimeError):
        with SnapshotWriter(tmp_path, CONFIG, created_at=T0) as w:
            w.add_payload("evds", "a.json", b"{}")
            raise RuntimeError("fetch crashed")
    assert list(tmp_path.iterdir()) == []


def test_existing_snapshot_id_rejected(tmp_path):
    _write(tmp_path)
    with pytest.raises(SnapshotError, match="already exists"):
        SnapshotWriter(tmp_path, CONFIG, snapshot_id="20261009-150000-ab12")


def test_writer_closed_after_finalize(tmp_path):
    w = SnapshotWriter(tmp_path, CONFIG, created_at=T0)
    w.set_source("evds", SourceRecord(status="skipped", on_failure="previous"))
    w.finalize()
    with pytest.raises(SnapshotError, match="closed"):
        w.add_payload("evds", "late.json", b"{}")


def test_manifest_content_is_deterministic(tmp_path):
    a = _write(tmp_path / "a")
    b = _write(tmp_path / "b")
    assert (a.path / MANIFEST).read_bytes() == (b.path / MANIFEST).read_bytes()


# --- writer guards -------------------------------------------------------------------

def test_secret_in_manifest_refused(tmp_path):
    with pytest.raises(SnapshotError, match="secret"):
        with SnapshotWriter(tmp_path, CONFIG, created_at=T0, secrets=["s3cr3t-key"]) as w:
            w.set_source("evds", SourceRecord(
                status="failed", on_failure="previous",
                error="401 for https://x.test/?key=s3cr3t-key"))
            w.finalize()
    assert list(tmp_path.iterdir()) == []


def test_unreferenced_payload_refused(tmp_path):
    with SnapshotWriter(tmp_path, CONFIG, created_at=T0) as w:
        w.add_payload("evds", "a.json", b"{}")
        with pytest.raises(SnapshotError, match="not referenced"):
            w.finalize()


def test_foreign_payload_ref_refused(tmp_path):
    other = _write(tmp_path / "other")
    with SnapshotWriter(tmp_path / "new", CONFIG, created_at=T0) as w:
        with pytest.raises(SnapshotError, match="not added"):
            w.set_source("evds", other.sources["evds"])


@pytest.mark.parametrize("name", ["../escape.json", "a/b.json", "a\\b.json", ".hidden", ""])
def test_bad_payload_name_rejected(tmp_path, name):
    with SnapshotWriter(tmp_path, CONFIG, created_at=T0) as w:
        with pytest.raises(SnapshotError, match="invalid payload name"):
            w.add_payload("evds", name, b"{}")


def test_turkish_file_name_accepted(tmp_path):
    with SnapshotWriter(tmp_path, CONFIG, created_at=T0) as w:
        ref = w.add_payload("tefas", "Fon Getirileri (Ekim).xlsx", b"PK")
        assert ref.path == "payloads/tefas/Fon Getirileri (Ekim).xlsx"


# --- SourceRecord rules ---------------------------------------------------------------

@pytest.mark.parametrize("kwargs,msg", [
    (dict(status="ok"), "requires fetched_at"),
    (dict(status="failed"), "requires error"),
    (dict(status="ok", fetched_at=T0, excluded=True), "only valid for status failed"),
    (dict(status="failed", error="x", excluded=True, fallback_from="20261001-090000-0000"),
     "not both"),
    (dict(status="done"), "status must be"),
    (dict(status="ok", fetched_at=datetime(2026, 10, 9)), "timezone-aware"),
])
def test_source_record_rules(kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        SourceRecord(on_failure="previous", **kwargs)


# --- integrity --------------------------------------------------------------------------

def test_tampered_payload_detected(tmp_path):
    snap = _write(tmp_path)
    f = snap.path / "payloads/evds/TP.FG.J0.json"
    _writable(f)
    f.write_bytes(BODY.replace(b"123,4", b"999,9"))
    with pytest.raises(SnapshotIntegrityError, match="hash mismatch"):
        open_snapshot(tmp_path, snap.snapshot_id)
    unverified = open_snapshot(tmp_path, snap.snapshot_id, verify=False)
    with pytest.raises(SnapshotIntegrityError):
        unverified.read_payload("payloads/evds/TP.FG.J0.json")


def test_tampered_manifest_detected(tmp_path):
    snap = _write(tmp_path)
    m = snap.path / MANIFEST
    _writable(m)
    m.write_bytes(m.read_bytes().replace(b'"ok"', b'"skipped"'))
    with pytest.raises(SnapshotIntegrityError, match="manifest hash"):
        open_snapshot(tmp_path, snap.snapshot_id)


def test_missing_payload_detected(tmp_path):
    snap = _write(tmp_path)
    f = snap.path / "payloads/evds/TP.FG.J0.json"
    _writable(f)
    f.unlink()
    with pytest.raises(SnapshotIntegrityError, match="missing payload"):
        open_snapshot(tmp_path, snap.snapshot_id)


def test_extra_file_detected(tmp_path):
    snap = _write(tmp_path)
    (snap.path / "payloads/evds/injected.json").write_bytes(b"{}")
    with pytest.raises(SnapshotIntegrityError, match="not in manifest"):
        open_snapshot(tmp_path, snap.snapshot_id)


def test_unknown_payload_path_rejected(tmp_path):
    snap = _write(tmp_path)
    with pytest.raises(SnapshotError, match="no payload"):
        snap.read_payload("payloads/evds/other.json")


def test_unknown_snapshot_rejected(tmp_path):
    with pytest.raises(SnapshotError, match="not found"):
        open_snapshot(tmp_path, "20200101-000000-0000")


# --- listing / previous ok ------------------------------------------------------------------

def test_list_snapshots_sorted_and_ignores_tmp(tmp_path):
    _write(tmp_path, T0 + timedelta(days=1), "bbbb")
    _write(tmp_path, T0, "aaaa")
    (tmp_path / ".tmp-20261011-000000-cccc").mkdir()
    assert [s.snapshot_id for s in list_snapshots(tmp_path)] == [
        "20261009-150000-aaaa", "20261010-150000-bbbb"]


def test_find_previous_ok_skips_failed_and_later(tmp_path):
    _write(tmp_path, T0, "0001")                                          # ok
    _write(tmp_path, T0 + timedelta(days=1), "0002", status="failed")     # failed
    _write(tmp_path, T0 + timedelta(days=3), "0003")                      # ok, but later
    before = T0 + timedelta(days=2)
    assert find_previous_ok(tmp_path, "evds", before) == "20261009-150000-0001"
    assert find_previous_ok(tmp_path, "tefas", before) is None
    assert find_previous_ok(tmp_path, "evds", T0) is None


# --- payloads that live in the cache (I11) ---------------------------------------------------

ZIP = b"PK\x03\x04 bulletin bytes"


def _cached(tmp_path, name="thb202610131.zip", data=ZIP):
    """A cache file next to the snapshots folder, as the bist_bulletin adapter
    writes it: <data>/cache/<source>/<name>."""
    f = tmp_path / "cache" / "bist_bulletin" / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f


def _write_cached(tmp_path, names=("thb202610131.zip",)):
    with SnapshotWriter(tmp_path / "snaps", CONFIG, created_at=T0,
                        snapshot_id="20261009-150000-0001") as w:
        refs = tuple(w.add_cache_payload("bist_bulletin", n, meta={"date": n[3:11]})
                     for n in names)
        w.set_source("bist_bulletin", _ok() if not refs else SourceRecord(
            status="ok", on_failure="previous", fetched_at=T0, payloads=refs))
        return w.finalize()


def test_cache_dir_is_next_to_the_snapshots_folder(tmp_path):
    w = SnapshotWriter(tmp_path / "snaps", CONFIG, created_at=T0)
    assert w.cache_dir("bist_bulletin") == tmp_path / "cache" / "bist_bulletin"
    w.abort()


def test_cache_payload_is_referenced_not_copied(tmp_path):
    _cached(tmp_path)
    snap = _write_cached(tmp_path)
    [ref] = snap.sources["bist_bulletin"].payloads
    assert ref.path == "cache/bist_bulletin/thb202610131.zip"
    assert ref.sha256 == hashlib.sha256(ZIP).hexdigest() and ref.bytes == len(ZIP)
    assert ref.meta == {"date": "20261013"}
    assert not (snap.path / "payloads" / "bist_bulletin").exists()
    assert snap.read_payload(ref.path) == ZIP


def test_cache_payload_must_exist(tmp_path):
    with pytest.raises(SnapshotError, match="no cache file"):
        _write_cached(tmp_path)
    assert list_snapshots(tmp_path / "snaps") == []


@pytest.mark.parametrize("name", ["../x.zip", "a/b.zip", ""])
def test_cache_payload_bad_name_rejected(tmp_path, name):
    with pytest.raises(SnapshotError, match="invalid payload name"):
        _write_cached(tmp_path, names=(name,))


def test_changed_cache_file_fails_open_and_read(tmp_path):
    f = _cached(tmp_path)
    snap = _write_cached(tmp_path)
    _writable(f)
    f.write_bytes(ZIP + b"x")
    with pytest.raises(SnapshotIntegrityError, match="hash mismatch for cache/bist_bulletin/"):
        open_snapshot(tmp_path / "snaps", snap.snapshot_id)
    unverified = open_snapshot(tmp_path / "snaps", snap.snapshot_id, verify=False)
    with pytest.raises(SnapshotIntegrityError):
        unverified.read_payload("cache/bist_bulletin/thb202610131.zip")


def test_missing_cache_file_fails_open(tmp_path):
    f = _cached(tmp_path)
    snap = _write_cached(tmp_path)
    _writable(f)
    f.unlink()
    with pytest.raises(SnapshotIntegrityError, match="missing payload cache/bist_bulletin/"):
        open_snapshot(tmp_path / "snaps", snap.snapshot_id)


def test_writer_reads_cache_payload_before_finalize(tmp_path):
    _cached(tmp_path)
    with SnapshotWriter(tmp_path / "snaps", CONFIG, created_at=T0) as w:
        ref = w.add_cache_payload("bist_bulletin", "thb202610131.zip")
        assert w.read_payload(ref.path) == ZIP
        w.abort()
