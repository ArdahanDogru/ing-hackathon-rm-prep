import json
import os
import shutil
import stat
from datetime import timedelta

import duckdb
import pytest
import yaml

from tests.ingest.conftest import (BIST_END, FIXTURES, ING_URL, KEY, T0, FakeEvds, FakeIng,
                                   add_bist, add_byf, add_cpi_annual, add_holdings,
                                   add_ing_web, bist_name, default_detail_pages, detail_page)
from rmprep.cli import main
from rmprep.decision.universe import EvidenceIndex
from rmprep.contracts import EntityInfo, Flag
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


def run(paths, *, fake=None, key=KEY, at=T0, sleeps=None):
    fake = fake or FakeEvds()
    sleeps = [] if sleeps is None else sleeps
    return ingest(paths, env={"EVDS_API_KEY": key} if key else {},
                  client=fake.client(), now=lambda: at, sleep=sleeps.append)


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
        {"evds": "ok", "manual": "ok", "tefas": "ok", "tefas_detail": "ok", "tefas_web": "ok"}
    assert len(by(ev, source="evds", entity=USD)) == 3
    assert len(by(ev, source="tefas")) == 9
    assert len(by(ev, source="tefas_web")) == 8 + 2 + 8      # AAL, IGL (nulls skipped), ZZZ
    assert len(by(ev, source="tefas_detail")) == 3 * 7        # 3 funds, fees null
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


def test_replay_keeps_cpi_annual_change_row(tmp_path, config_raw):
    paths = make_project(tmp_path / "proj", add_cpi_annual(config_raw))
    ev = run(paths)
    [annual] = by(ev, source="evds", quantity="cpi_annual")
    assert round(annual.value, 2) == 29.73
    os.remove(paths.db)
    os.remove(paths.config)
    assert replay(paths, ev.snapshot_id) == ev


def test_replay_keeps_valid_until_stale_flag(tmp_path, config_raw):
    text = ("quantity;entity;value;unit;as_of;source_url;note;valid_until\n"
            "withholding_tax_rate;TRY deposit up to 6M;17,5;pct;01.07.2026;"
            "https://www.gib.gov.tr/;CK 11444;08.10.2026\n")
    paths = make_project(tmp_path / "proj", config_raw, manual_text=text)
    ev = run(paths)
    [p] = by(ev, source="manual")
    assert Flag.STALE in p.flags and "valid until 08.10.2026" in p.note
    os.remove(paths.db)
    shutil.rmtree(paths.root / "data/inbox")
    assert replay(paths, ev.snapshot_id) == ev


def test_replay_keeps_holdings_rows(tmp_path, config_raw):
    paths = make_project(tmp_path / "proj", add_holdings(config_raw))
    ev = run(paths)
    held = by(ev, source="tefas_detail", quantity="fund_holding_share")
    assert {p.entity.split("/")[0] for p in held} == {"AAL", "IGL", "ZZZ"}
    os.remove(paths.db)
    os.remove(paths.config)
    assert replay(paths, ev.snapshot_id) == ev


def test_ingest_with_byf_source(tmp_path, config_raw):
    paths = make_project(tmp_path / "proj", add_byf(config_raw))
    byf_pages = {c: detail_page("MAC", c, tefasDurum="Platformda İşlem Görmüyor")
                 for c in ("BOE", "GLD")}
    ev = run(paths, fake=FakeEvds(detail_pages={**default_detail_pages(), **byf_pages}))
    assert ev.source_status["tefas_byf"].status == "ok"
    assert ev.source_status["tefas_detail"].status == "ok"
    assert ev.entities["BOE"].source == "tefas_byf" and ev.entities["AAL"].source == "tefas_web"
    assert {p.entity for p in by(ev, source="tefas_byf")} == {"BOE", "GLD"}
    assert {p.entity for p in by(ev, source="tefas_detail", quantity="fund_buyable")} == \
        {"AAL", "IGL", "ZZZ", "BOE", "GLD"}
    os.remove(paths.db)
    os.remove(paths.config)
    assert replay(paths, ev.snapshot_id) == ev


def test_ingest_with_bist_bulletin(tmp_path, config_raw):
    paths = make_project(tmp_path / "proj", add_bist(config_raw))
    sleeps = []
    ev = run(paths, sleeps=sleeps)
    assert ev.source_status["bist_bulletin"].status == "ok"
    assert {p.entity for p in by(ev, source="bist_bulletin")} == {"AAA", "BBB", "CCC"}
    assert ev.entities["AAA"] == EntityInfo("AAA HOLDING", "BIST pay · Z", "bist_bulletin")
    assert (paths.root / "data/cache/bist_bulletin" / bist_name(BIST_END)).is_file()
    assert sleeps                                   # waited between the bulletin requests

    # Replay from the snapshot and the cache only.
    os.remove(paths.db)
    os.remove(paths.config)
    assert replay(paths, ev.snapshot_id) == ev


def test_changed_bist_cache_file_fails_replay(tmp_path, config_raw):
    paths = make_project(tmp_path / "proj", add_bist(config_raw))
    ev = run(paths)
    f = paths.root / "data/cache/bist_bulletin" / bist_name(BIST_END)
    os.chmod(f, stat.S_IREAD | stat.S_IWRITE)
    f.write_bytes(f.read_bytes() + b"x")
    with pytest.raises(SnapshotIntegrityError, match="hash mismatch for cache/bist_bulletin/"):
        replay(paths, ev.snapshot_id)


def test_second_ingest_uses_the_bist_cache(tmp_path, config_raw):
    paths = make_project(tmp_path / "proj", add_bist(config_raw))
    run(paths)
    fake = FakeEvds()
    ev = run(paths, fake=fake, at=T0 + timedelta(hours=1))
    assert ev.source_status["bist_bulletin"].status == "ok"
    assert [r.url.path.rsplit("/", 1)[-1] for r in fake.requests
            if r.url.host == "www.borsaistanbul.com"] == ["thb202610091.zip"]


# --- ing_web (I14) -------------------------------------------------------------------------

T16 = T0 + timedelta(days=7)                       # 2026-10-16 15:00, the day of the ING pages
CELL = "ING e-Vadeli Mevduat, 32-45 gün, 99.999,99-250.000 TL"


def _manual_ing_row(as_of: str, value: str) -> str:
    return ("quantity;entity;value;unit;as_of;source_url;note\n"
            f"deposit_rate;{CELL};{value};pct;{as_of};{ING_URL};hand copy\n")


def test_ingest_with_ing_web_and_replay(tmp_path, config_raw):
    paths = make_project(tmp_path / "proj", add_ing_web(config_raw))
    ev = run(paths, at=T16)
    assert ev.source_status["ing_web"].status == "ok"
    rows = by(ev, source="ing_web")
    assert len(rows) == 116 and {p.as_of.isoformat() for p in rows} == {"2026-10-16"}
    os.remove(paths.db)
    os.remove(paths.config)
    assert replay(paths, ev.snapshot_id) == ev


def test_web_row_wins_over_the_older_manual_row(tmp_path, config_raw):
    paths = make_project(tmp_path / "proj", add_ing_web(config_raw),
                         manual_text=_manual_ing_row("10.10.2026", "35,00"))
    ev = run(paths, at=T16)
    [manual] = by(ev, source="manual", entity=CELL)
    [web] = by(ev, source="ing_web", entity=CELL)
    assert (manual.value, web.value) == (35.0, 34.5)
    assert Flag.CONFLICT not in web.flags                        # another as_of: no conflict
    assert EvidenceIndex(ev).get("deposit_rate", CELL) == web     # the latest as_of wins


def test_same_as_of_different_value_is_a_conflict(tmp_path, config_raw):
    paths = make_project(tmp_path / "proj", add_ing_web(config_raw),
                         manual_text=_manual_ing_row("16.10.2026", "35,00"))
    ev = run(paths, at=T16)
    [manual] = by(ev, source="manual", entity=CELL)
    [web] = by(ev, source="ing_web", entity=CELL)
    assert Flag.CONFLICT in manual.flags and Flag.CONFLICT in web.flags


def test_failed_ing_web_falls_back_to_the_previous_snapshot(tmp_path, config_raw):
    paths = make_project(tmp_path / "proj", add_ing_web(config_raw))
    first = run(paths, at=T16)
    ev = run(paths, fake=FakeEvds(ing=FakeIng(status=503)), at=T16 + timedelta(days=1))
    rec = ev.source_status["ing_web"]
    assert rec.status == "failed" and rec.fallback_from == first.snapshot_id
    rows = by(ev, source="ing_web")
    assert len(rows) == 116 and all(Flag.FALLBACK_SNAPSHOT in p.flags for p in rows)


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


def test_entities_from_tefas_web(paths):
    ev = run(paths)
    assert list(ev.entities) == ["AAL", "IGL", "ZZZ"]
    assert ev.entities["AAL"] == EntityInfo("ATA PORTFÖY PARA PİYASASI (TL) FONU",
                                            "Para Piyasası Şemsiye Fonu", "tefas_web")


def test_replay_gives_identical_entities(paths):
    ev = run(paths)
    assert replay(paths, ev.snapshot_id).entities == ev.entities
    assert build_evidence(paths.snapshots, ev.snapshot_id).to_dict()["entities"] ==         ev.to_dict()["entities"]


def test_tefas_web_failure_falls_back_for_entities(paths):
    first = run(paths)
    ev = run(paths, fake=FakeEvds(tefas_page=None), at=T0 + timedelta(days=3))
    assert ev.entities == first.entities and ev.entities


def test_tefas_web_failure_without_previous_gives_no_entities(paths):
    ev = run(paths, fake=FakeEvds(tefas_page=None))
    assert ev.source_status["tefas_web"].fallback_from is None
    assert ev.entities == {}


def test_tefas_web_on_failure_exclude_gives_no_entities(tmp_path, config_raw):
    config_raw["sources"]["tefas_web"]["on_failure"] = "exclude"
    paths = make_project(tmp_path / "proj", config_raw)
    run(paths)
    ev = run(paths, fake=FakeEvds(tefas_page=None), at=T0 + timedelta(days=1))
    assert ev.source_status["tefas_web"].excluded is True
    assert ev.entities == {}


def test_read_time_exclusion_of_tefas_web_empties_entities(paths):
    ev = run(paths)
    view = build_evidence(paths.snapshots, ev.snapshot_id, {"tefas_web"})
    assert view.entities == {}
    assert build_evidence(paths.snapshots, ev.snapshot_id, {"manual"}).entities == ev.entities


def test_skipped_tefas_web_gives_no_entities(tmp_path, config_raw):
    config_raw["sources"]["tefas_web"]["enabled"] = False
    ev = run(make_project(tmp_path / "proj", config_raw))
    assert ev.source_status["tefas_web"].status == "skipped"
    assert ev.entities == {}


def test_tefas_detail_fetched_after_tefas_web_with_interval(paths):
    fake, sleeps = FakeEvds(), []
    run(paths, fake=fake, sleeps=sleeps)
    tefas = [r.url.path for r in fake.requests if r.url.host == "www.tefas.gov.tr"]
    assert tefas == ["/tr/fon-getirileri", "/tr/fon-detayli-analiz/AAL",
                     "/tr/fon-detayli-analiz/IGL", "/tr/fon-detayli-analiz/ZZZ"]
    assert len(sleeps) == 2 and all(0 < s <= 1.0 for s in sleeps)


def test_tefas_web_failure_fails_tefas_detail_and_both_fall_back(paths):
    first = run(paths)
    ev = run(paths, fake=FakeEvds(tefas_page=None), at=T0 + timedelta(days=3))
    rec = ev.source_status["tefas_detail"]
    assert rec.status == "failed" and "no tefas_web funds" in rec.error
    assert rec.fallback_from == first.snapshot_id
    rows = by(ev, source="tefas_detail")
    assert len(rows) == 21 and all(Flag.FALLBACK_SNAPSHOT in p.flags for p in rows)


def test_tefas_detail_rows_survive_replay_from_gzip(paths):
    ev = run(paths)
    again = build_evidence(paths.snapshots, ev.snapshot_id)
    assert by(again, source="tefas_detail") == by(ev, source="tefas_detail")


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
