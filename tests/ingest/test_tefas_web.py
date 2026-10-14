from datetime import date, datetime, timedelta

import httpx
import pytest

from tests.ingest.conftest import (BYF_URL, T0, TEFAS_BYF_FUNDS, TEFAS_WEB_FUNDS, FakeEvds,
                                   add_byf, tefas_web_page)
from rmprep.ingest.adapters import tefas_web
from rmprep.ingest.config import ConfigError, parse_config
from rmprep.contracts import TR_TZ, EntityInfo, Flag
from rmprep.ingest.quality import run_checks
from rmprep.ingest.snapshot import SnapshotWriter


def _fetch(tmp_path, cfg, fake, at=T0, sid="20261009-150000-0001", name="tefas_web"):
    src = cfg.sources[name]
    w = SnapshotWriter(tmp_path / "snaps", {}, created_at=at, snapshot_id=sid)
    rec = tefas_web.fetch(src, w, client=fake.client(), now=lambda: at)
    w.set_source(name, rec)
    return rec, w.finalize()


def _points(tmp_path, cfg, **kw):
    _, snap = _fetch(tmp_path, cfg, FakeEvds(), **kw)
    return tefas_web.parse(cfg, cfg.sources["tefas_web"], snap)


def _get(points, entity, quantity):
    return [p for p in points if p.entity == entity and p.quantity == quantity]


# --- robots.txt rules -------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://www.tefas.gov.tr/api/DB/BindHistoryInfo",
    "https://www.tefas.gov.tr/_next/data/x.json",
    "https://www.tefas.gov.tr/static/a.js",
])
def test_config_rejects_robots_disallowed_paths(config_raw, url):
    config_raw["sources"]["tefas_web"]["url"] = url
    with pytest.raises(ConfigError, match="disallowed by tefas.gov.tr/robots.txt"):
        parse_config(config_raw)


@pytest.mark.parametrize("url", ["http://www.tefas.gov.tr/tr/fon-getirileri",
                                 "https://tefas.example.com/tr/fon-getirileri"])
def test_config_rejects_other_hosts_and_http(config_raw, url):
    config_raw["sources"]["tefas_web"]["url"] = url
    with pytest.raises(ConfigError, match="https URL on www.tefas.gov.tr"):
        parse_config(config_raw)


def test_check_url_allowed():
    tefas_web.check_url_allowed("https://www.tefas.gov.tr/tr/fon-getirileri")
    with pytest.raises(ValueError):
        tefas_web.check_url_allowed("https://www.tefas.gov.tr/api/x")


# --- fetch ------------------------------------------------------------------------

def test_fetch_makes_one_request_to_the_page_only(tmp_path, cfg):
    fake = FakeEvds()
    rec, snap = _fetch(tmp_path, cfg, fake)
    assert rec.status == "ok"
    [req] = fake.requests
    assert str(req.url) == "https://www.tefas.gov.tr/tr/fon-getirileri"
    assert req.headers["User-Agent"].startswith("rmprep-hackathon-prototype")
    assert "/api/" not in str(req.url)
    [p] = rec.payloads
    assert p.meta["funds"] == 3
    assert snap.read_payload(p.path) == tefas_web_page()


def test_fetch_http_error_fails(tmp_path, cfg):
    rec, _ = _fetch(tmp_path, cfg, FakeEvds(tefas_page=None))
    assert rec.status == "failed" and "HTTP 503" in rec.error and rec.payloads == ()


def test_fetch_redirect_is_not_followed(tmp_path, cfg):
    def handler(request):
        return httpx.Response(302, headers={"Location": "https://www.tefas.gov.tr/api/x"})
    src = cfg.sources["tefas_web"]
    w = SnapshotWriter(tmp_path / "s", {}, created_at=T0, snapshot_id="20261009-150000-0001")
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r) or handler(r)))
    rec = tefas_web.fetch(src, w, client=client, now=lambda: T0)
    assert rec.status == "failed" and "HTTP 302" in rec.error
    assert len(calls) == 1


def test_fetch_changed_page_fails(tmp_path, cfg):
    rec, _ = _fetch(tmp_path, cfg, FakeEvds(tefas_page=b"<html>new design</html>"))
    assert rec.status == "failed" and "only 0 funds found" in rec.error


# --- extract_funds ------------------------------------------------------------------

@pytest.mark.parametrize("chunks", [1, 3, 7])
def test_extract_funds_joins_chunks_and_skips_title_row(chunks):
    funds = tefas_web.extract_funds(tefas_web_page(chunks=chunks).decode())
    assert [f["fonKodu"] for f in funds] == ["AAL", "IGL", "ZZZ"]
    assert funds[2]["fonUnvan"] == 'ÖRNEK HİSSE "YOĞUN" FONU'


def test_extract_funds_keeps_first_duplicate():
    dup = dict(TEFAS_WEB_FUNDS[0], getiri1a=99.0)
    funds = tefas_web.extract_funds(tefas_web_page(TEFAS_WEB_FUNDS + [dup]).decode())
    assert len(funds) == 3 and funds[0]["getiri1a"] == 3.005


# --- parse -----------------------------------------------------------------------------

@pytest.mark.parametrize("snapshot_day,expected", [
    (date(2026, 10, 9), date(2026, 10, 8)),     # Friday -> Thursday
    (date(2026, 10, 12), date(2026, 10, 9)),    # Monday -> Friday
    (date(2026, 10, 11), date(2026, 10, 9)),    # Sunday -> Friday
])
def test_previous_business_day(snapshot_day, expected):
    assert tefas_web.previous_business_day(snapshot_day) == expected


def test_parse_values_units_and_as_of(tmp_path, cfg):
    pts = _points(tmp_path, cfg)
    [r1m] = _get(pts, "AAL", "fund_return_1m")
    assert r1m.value == 3.005 and r1m.unit == "pct"
    assert r1m.as_of == date(2026, 10, 8)                     # option A
    assert r1m.raw_ref == ("20261009-150000-0001/payloads/tefas_web/fon-getirileri.html"
                           "#fonKodu=AAL;field=getiri1a")
    assert r1m.note.startswith("ATA PORTFÖY PARA PİYASASI (TL) FONU; Para Piyasası")
    [risk] = _get(pts, "AAL", "fund_risk_level")
    assert risk.value == 1.0 and risk.unit == "level"


def test_parse_skips_null_and_dash(tmp_path, cfg):
    pts = _points(tmp_path, cfg)
    igl = {p.quantity for p in pts if p.entity == "IGL"}
    assert igl == {"fund_return_1m", "fund_return_ytd"}       # nulls and risk "-" skipped


def test_parse_flags_needs_check_when_switched_on(tmp_path, config_raw):
    # Set explicitly: the real config switches the flag off (2026-10-14).
    config_raw["sources"]["tefas_web"]["flag_needs_check"] = True
    pts = _points(tmp_path, parse_config(config_raw))
    assert pts and all(p.flags == {Flag.NEEDS_CHECK} for p in pts)


def test_needs_check_can_be_switched_off(tmp_path, config_raw):
    config_raw["sources"]["tefas_web"]["flag_needs_check"] = False
    pts = _points(tmp_path, parse_config(config_raw))
    assert all(p.flags == frozenset() for p in pts)


def test_risk_zero_is_flagged_out_of_range(tmp_path, cfg):
    funds = [dict(TEFAS_WEB_FUNDS[0], riskDegeri="0"), TEFAS_WEB_FUNDS[2]]
    fake = FakeEvds(tefas_page=tefas_web_page(funds))
    _, snap = _fetch(tmp_path, cfg, fake)
    pts = run_checks(tefas_web.parse(cfg, cfg.sources["tefas_web"], snap), cfg, T0.date())
    [risk] = _get(pts, "AAL", "fund_risk_level")
    assert risk.value == 0.0 and Flag.OUT_OF_RANGE in risk.flags


def test_fallback_rows_keep_original_as_of(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    pts = tefas_web.parse(cfg, cfg.sources["tefas_web"], snap,
                          out_snapshot_id="20261013-090000-0002", out_date=date(2026, 10, 13))
    assert {p.as_of for p in pts} == {date(2026, 10, 8)}
    assert {p.snapshot_id for p in pts} == {"20261013-090000-0002"}


def test_parse_is_deterministic(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    src = cfg.sources["tefas_web"]
    assert tefas_web.parse(cfg, src, snap) == tefas_web.parse(cfg, src, snap)


# --- entities (milestone I1) --------------------------------------------------------------

def test_entities_from_page_verbatim(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    ents = tefas_web.entities(cfg.sources["tefas_web"], snap)
    assert list(ents) == ["AAL", "IGL", "ZZZ"]
    assert ents["ZZZ"] == EntityInfo('ÖRNEK HİSSE "YOĞUN" FONU', "Hisse Senedi Şemsiye Fonu",
                                     "tefas_web")
    assert ents["IGL"].name == "TEB PORTFÖY ING BANK PARA PİYASASI (TL) FONU"


def test_entities_skip_fund_without_name_or_type(tmp_path, cfg):
    funds = [dict(TEFAS_WEB_FUNDS[0], fonUnvan=None),
             {k: v for k, v in TEFAS_WEB_FUNDS[1].items() if k != "fonTurAciklama"},
             TEFAS_WEB_FUNDS[2]]
    _, snap = _fetch(tmp_path, cfg, FakeEvds(tefas_page=tefas_web_page(funds)))
    assert list(tefas_web.entities(cfg.sources["tefas_web"], snap)) == ["ZZZ"]


# --- BYF view of the page (I10) ---------------------------------------------------------

def test_config_accepts_byf_url_with_query(config_raw):
    src = parse_config(add_byf(config_raw)).sources["tefas_byf"]
    assert src.adapter == "tefas_web" and src.url == BYF_URL and src.min_funds == 2


def test_byf_page_fetched_and_parsed_with_tefas_web_adapter(tmp_path, config_raw):
    cfg = parse_config(add_byf(config_raw))
    fake = FakeEvds()
    rec, snap = _fetch(tmp_path, cfg, fake, name="tefas_byf")
    assert rec.status == "ok" and [str(r.url) for r in fake.requests] == [BYF_URL]
    pts = tefas_web.parse(cfg, cfg.sources["tefas_byf"], snap)
    assert {p.entity for p in pts} == {"BOE", "GLD"}
    assert {p.source for p in pts} == {"tefas_byf"} and {p.source_url for p in pts} == {BYF_URL}
    assert _get(pts, "BOE", "fund_risk_level")[0].value == 6
    assert _get(pts, "GLD", "fund_risk_level") == []           # risk missing on the page
    assert pts[0].raw_ref.startswith("20261009-150000-0001/payloads/tefas_byf/")


def test_byf_entities_carry_byf_source(tmp_path, config_raw):
    cfg = parse_config(add_byf(config_raw))
    _, snap = _fetch(tmp_path, cfg, FakeEvds(), name="tefas_byf")
    ents = tefas_web.entities(cfg.sources["tefas_byf"], snap)
    assert ents["GLD"] == EntityInfo("ÖRNEK PORTFÖY ALTIN BORSA YATIRIM FONU", "Endeks Fon",
                                     "tefas_byf")


def test_byf_page_with_too_few_funds_fails(tmp_path, config_raw):
    cfg = parse_config(add_byf(config_raw))
    rec, _ = _fetch(tmp_path, cfg, FakeEvds(byf_page=tefas_web_page(TEFAS_BYF_FUNDS[:1])),
                    name="tefas_byf")
    assert rec.status == "failed" and "only 1 funds found (minimum 2)" in rec.error


def test_entities_need_ok_record(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds(tefas_page=None))
    with pytest.raises(ValueError, match="no ok record"):
        tefas_web.entities(cfg.sources["tefas_web"], snap)
