import json
import os
import shutil
import stat
from datetime import timedelta

import duckdb
import pytest
import yaml

from tests.ingest.conftest import FIXTURES, KEY, T0, FakeEvds
from rmprep.cli import main
from rmprep.contracts import Flag
from rmprep.ingest.pipeline import ExclusionError, Paths, build_evidence, ingest, replay
from rmprep.ingest.snapshot import MANIFEST, SnapshotIntegrityError, open_snapshot
from rmprep.ingest.store import EvidenceStore

TEFAS_CSV = FIXTURES / "tefas" / "tefas_export.csv"
RATES_CSV = FIXTURES / "manual" / "rates.csv"
USD = "USD/TRY CBRT buying rate"


def make_project(root, config_raw, *, tefas=True, manual_text=None):
    (root / "config").mkdir(parents=True)
    (root / "config" / "sources.yaml").write_text(
        yaml.safe_dump(config_raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    t, m = root / "data/inbox/tefas", root / "data/inbox/manual"
    t.mkdir(parents=True)
    m.mkdir(parents=True)
    if tefas:
        shutil.copy(TEFAS_CSV, t / "tefas_export.csv")
    text = RATES_CSV.read_text(encoding="utf-8") if manual_text is None else manual_text
    if text:
        (m / "rates.csv").write_text(text, encoding="utf-8")
    return Paths(root)


def run(paths, *, fake=None, key=KEY, at=T0):
    fake = fake or FakeEvds()
    return ingest(paths, env={"EVDS_API_KEY": key} if key else {},
                  client=fake.client(), now=lambda: at)


@pytest.fixture
def paths(tmp_path, config_raw):
    return make_project(tmp_path / "proj", config_raw)


def by(ev, **kw):
    return [p for p in ev.datapoints if all(getattr(p, k) == v for k, v in kw.items())]


def parquet_rows(path):
    # TIMESTAMPTZ -> Python datetime needs pytz; read it as epoch microseconds.
    return duckdb.connect().execute(
        f"SELECT * REPLACE (epoch_us(fetched_at) AS fetched_at) FROM '{path}' ORDER BY id"
    ).fetchall()


# --- ingest --------------------------------------------------------------------------

def test_ingest_end_to_end(paths):
    ev = run(paths)
    assert {k: r.status for k, r in ev.source_status.items()} == \
        {"evds": "ok", "manual": "ok", "tefas": "ok", "tefas_web": "ok"}
    assert len(by(ev, source="evds", entity=USD)) == 3
    assert len(by(ev, source="tefas")) == 9
    assert len(by(ev, source="tefas_web")) == 8 + 2 + 8      # AAL, IGL (nulls skipped), ZZZ
    assert len(by(ev, source="manual")) == 2
    assert all(Flag.MANUAL_ENTRY in p.flags for p in by(ev, source="manual"))
    placeholders = [p for p in ev.datapoints if "placeholder" in p.note]
    assert len(placeholders) == 2 and all(p.value is None for p in placeholders)
    assert len(ev.source_status["manual"].rejected_rows) == 5

    with EvidenceStore(paths.db) as store:
        assert store.points(ev.snapshot_id) == list(ev.datapoints)
    assert (paths.export / f"{ev.snapshot_id}.parquet").exists()


def test_key_not_stored_anywhere(paths):
    ev = run(paths)
    snap_dir = paths.snapshots / ev.snapshot_id
    for f in snap_dir.rglob("*"):
        if f.is_file():
            assert KEY.encode() not in f.read_bytes(), f
    assert all(KEY not in p.note for p in ev.datapoints)


# --- replay ------------------------------------------------------------------------------

def test_replay_gives_identical_output(paths):
    ev = run(paths)
    parquet = paths.export / f"{ev.snapshot_id}.parquet"
    before_bytes = parquet.read_bytes()
    before_rows = parquet_rows(parquet)
    with EvidenceStore(paths.db) as store:
        before_points = store.points(ev.snapshot_id)

    # Remove every derived output and break the online inputs.
    os.remove(paths.db)
    shutil.rmtree(paths.export)
    shutil.rmtree(paths.root / "data/inbox")
    os.remove(paths.config)

    ev2 = replay(paths, ev.snapshot_id)
    assert ev2 == ev
    with EvidenceStore(paths.db) as store:
        assert store.points(ev.snapshot_id) == before_points
    assert parquet_rows(parquet) == before_rows
    assert parquet.read_bytes() == before_bytes


def test_replay_twice_is_idempotent(paths):
    ev = run(paths)
    replay(paths, ev.snapshot_id)
    replay(paths, ev.snapshot_id)
    with EvidenceStore(paths.db) as store:
        assert len(store.points(ev.snapshot_id)) == len(ev.datapoints)


def test_replay_ignores_current_config(paths):
    ev = run(paths)
    raw = yaml.safe_load(paths.config.read_text(encoding="utf-8"))
    raw["quantities"]["usd_try"]["max"] = 10                     # would flag out_of_range
    paths.config.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    assert replay(paths, ev.snapshot_id) == ev


def test_replay_of_tampered_snapshot_fails(paths):
    ev = run(paths)
    f = paths.snapshots / ev.snapshot_id / "payloads/tefas/tefas_export.csv"
    os.chmod(f, stat.S_IREAD | stat.S_IWRITE)
    f.write_bytes(f.read_bytes().replace(b"1,234567", b"9,999999"))
    with pytest.raises(SnapshotIntegrityError):
        replay(paths, ev.snapshot_id)


# --- failures and fallback ------------------------------------------------------------------

def test_no_api_key_uses_previous_snapshot(paths):
    first = run(paths)
    later = T0 + timedelta(days=30)
    ev = run(paths, key=None, at=later)

    rec = ev.source_status["evds"]
    assert rec.status == "failed" and "EVDS_API_KEY" in rec.error
    assert rec.fallback_from == first.snapshot_id
    usd = by(ev, source="evds", entity=USD)
    assert len(usd) == 3
    assert all(Flag.FALLBACK_SNAPSHOT in p.flags for p in usd)
    assert all(p.snapshot_id == ev.snapshot_id for p in usd)
    assert all(p.raw_ref.startswith(first.snapshot_id + "/") for p in usd)
    assert all(p.fetched_at == T0 for p in usd)                 # original fetch time
    latest = max(usd, key=lambda p: p.as_of)
    assert Flag.STALE in latest.flags                           # 32 days old at the new snapshot
    assert all(f"fallback from {first.snapshot_id}" in p.note for p in usd)


def test_fallback_skips_failed_snapshots(paths):
    first = run(paths)
    run(paths, key=None, at=T0 + timedelta(days=1))
    ev = run(paths, fake=FakeEvds(status=503), at=T0 + timedelta(days=2))
    assert ev.source_status["evds"].fallback_from == first.snapshot_id


def test_http_error_without_previous_gives_missing_rows(paths):
    ev = run(paths, fake=FakeEvds(status=500))
    evds_pts = by(ev, source="evds")
    assert len(evds_pts) == 4                                   # one per configured series
    assert all(p.value is None and Flag.MISSING in p.flags for p in evds_pts)
    assert all("HTTP 500" in p.note for p in evds_pts)
    assert ev.source_status["evds"].fallback_from is None


def test_on_failure_exclude(tmp_path, config_raw):
    config_raw["sources"]["evds"]["on_failure"] = "exclude"
    paths = make_project(tmp_path / "proj", config_raw)
    run(paths)
    ev = run(paths, fake=FakeEvds(status=500), at=T0 + timedelta(days=1))
    assert by(ev, source="evds") == []
    rec = ev.source_status["evds"]
    assert rec.excluded is True and rec.fallback_from is None
    manifest = json.loads((paths.snapshots / ev.snapshot_id / MANIFEST).read_text("utf-8"))
    assert manifest["sources"]["evds"]["excluded"] is True


def test_empty_tefas_inbox_falls_back(tmp_path, config_raw):
    paths = make_project(tmp_path / "proj", config_raw)
    first = run(paths)
    os.remove(paths.root / "data/inbox/tefas/tefas_export.csv")
    ev = run(paths, at=T0 + timedelta(days=1))
    tefas_pts = by(ev, source="tefas")
    assert len(tefas_pts) == 9
    assert all(Flag.FALLBACK_SNAPSHOT in p.flags for p in tefas_pts)
    assert ev.source_status["tefas"].fallback_from == first.snapshot_id


def test_tefas_web_failure_falls_back(paths):
    first = run(paths)
    ev = run(paths, fake=FakeEvds(tefas_page=None), at=T0 + timedelta(days=3))
    rec = ev.source_status["tefas_web"]
    assert rec.status == "failed" and rec.fallback_from == first.snapshot_id
    rows = by(ev, source="tefas_web")
    assert rows and all(Flag.FALLBACK_SNAPSHOT in p.flags for p in rows)
    assert {p.as_of for p in rows} == {T0.date() - timedelta(days=1)}   # from the old page


def test_disabled_source_skipped(tmp_path, config_raw):
    config_raw["sources"]["tefas"]["enabled"] = False
    paths = make_project(tmp_path / "proj", config_raw)
    ev = run(paths)
    assert ev.source_status["tefas"].status == "skipped"
    assert by(ev, source="tefas") == []


# --- conflict and read-time exclusion ---------------------------------------------------------

@pytest.fixture
def conflict_paths(tmp_path, config_raw):
    config_raw["sources"]["manual"]["allowed_quantities"].append("usd_try")
    text = RATES_CSV.read_text(encoding="utf-8") + \
        f"usd_try;{USD};43,00;TRY;08.10.2026;https://fx.example/;branch board rate\n"
    return make_project(tmp_path / "proj", config_raw, manual_text=text)


def test_cross_source_conflict(conflict_paths):
    ev = run(conflict_paths)
    rows = by(ev, quantity="usd_try", entity=USD, as_of=T0.date() - timedelta(days=1))
    assert {p.source for p in rows} == {"evds", "manual"}
    assert all(Flag.CONFLICT in p.flags for p in rows)


def test_read_time_exclusion_removes_source_and_its_conflict(conflict_paths):
    ev = run(conflict_paths)
    view = build_evidence(conflict_paths.snapshots, ev.snapshot_id, {"manual"})
    assert view.excluded_sources == {"manual"}
    assert by(view, source="manual") == []
    [evds_row] = by(view, entity=USD, as_of=T0.date() - timedelta(days=1))
    assert Flag.CONFLICT not in evds_row.flags
    # The stored full result is unchanged.
    with EvidenceStore(conflict_paths.db) as store:
        assert store.points(ev.snapshot_id) == list(ev.datapoints)
    # Same exclusion -> same result.
    assert build_evidence(conflict_paths.snapshots, ev.snapshot_id, {"manual"}) == view


def test_unknown_exclusion_rejected(paths):
    ev = run(paths)
    with pytest.raises(ExclusionError, match="kap"):
        build_evidence(paths.snapshots, ev.snapshot_id, {"kap"})


# --- is_latest -----------------------------------------------------------------------------

def test_replaying_old_snapshot_keeps_newest_latest(paths):
    old = run(paths)
    new = run(paths, at=T0 + timedelta(days=1))
    replay(paths, old.snapshot_id)
    with EvidenceStore(paths.db) as store:
        assert store.latest_snapshot_id() == new.snapshot_id
        assert set(store.is_latest(new.snapshot_id).values()) == {True}
        assert set(store.is_latest(old.snapshot_id).values()) == {False}


# --- CLI -------------------------------------------------------------------------------------

def test_cli_show_replay_list(paths, capsys):
    ev = run(paths)
    root = ["--root", str(paths.root)]

    assert main(root + ["show", ev.snapshot_id]) == 0
    out = capsys.readouterr().out
    assert ev.snapshot_id in out and "rejected rates.csv row 4: missing source_url" in out
    assert "manual_entry=2" in out

    assert main(root + ["show", ev.snapshot_id, "--exclude", "manual"]) == 0
    out = capsys.readouterr().out
    assert "excluded at read time: manual" in out and "manual_entry" not in out

    assert main(root + ["replay", ev.snapshot_id]) == 0
    assert f"replayed {ev.snapshot_id}" in capsys.readouterr().out

    assert main(root + ["list"]) == 0
    assert ev.snapshot_id in capsys.readouterr().out


def test_cli_evds_find_without_key(paths, capsys, monkeypatch):
    monkeypatch.delenv("EVDS_API_KEY", raising=False)
    assert main(["--root", str(paths.root), "evds-find", "mevduat"]) == 2
    assert "EVDS_API_KEY is empty" in capsys.readouterr().err


def test_cli_evds_find_output(paths, capsys, monkeypatch):
    from argparse import Namespace

    from tests.ingest.test_evds import FakeMeta
    from rmprep.cli import _evds_meta
    monkeypatch.setenv("EVDS_API_KEY", KEY)
    assert _evds_meta(paths, Namespace(command="evds-find", text="mevduat"),
                      client=FakeMeta().client()) == 0
    out = capsys.readouterr().out
    assert "bie_mevfaiz" in out and "TP.MEV.X1" in out and KEY not in out


def test_cli_errors_exit_2(paths, capsys):
    ev = run(paths)
    root = ["--root", str(paths.root)]
    assert main(root + ["replay", "20200101-000000-0000"]) == 2
    assert main(root + ["show", ev.snapshot_id, "--exclude", "nope"]) == 2
    assert "error:" in capsys.readouterr().err
