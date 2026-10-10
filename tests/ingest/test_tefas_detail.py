import dataclasses
import gzip
from datetime import date

import httpx
import pytest

from tests.ingest.conftest import (
    T0,
    TEFAS_WEB_FUNDS,
    FakeEvds,
    detail_page,
    tefas_web_page,
)
from rmprep.contracts import Flag
from rmprep.ingest.adapters import tefas_detail
from rmprep.ingest.config import ConfigError, TefasDetailSource, parse_config
from rmprep.ingest.quality import run_checks
from rmprep.ingest.snapshot import SnapshotWriter

SID = "20261009-150000-0001"


class FakeClock:
    """monotonic() and sleep() without real waiting; a request may take time."""

    def __init__(self, request_seconds=0.0):
        self.t = 100.0
        self.request_seconds = request_seconds
        self.sleeps: list[float] = []
        self.request_times: list[float] = []

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

    def on_request(self):
        self.request_times.append(self.t)
        self.t += self.request_seconds


def _src(cfg, **changes) -> TefasDetailSource:
    return dataclasses.replace(cfg.sources["tefas_detail"], **changes)


def _fetch(tmp_path, src, *, fake=None, listing=b"default", clock=None):
    fake = fake or FakeEvds()
    clock = clock or FakeClock()
    listing = tefas_web_page() if listing == b"default" else listing

    def handler(request):
        clock.on_request()
        return fake(request)

    w = SnapshotWriter(tmp_path / "snaps", {}, created_at=T0, snapshot_id=SID)
    rec = tefas_detail.fetch(src, w, listing=listing,
                             client=httpx.Client(transport=httpx.MockTransport(handler)),
                             now=lambda: T0, monotonic=clock.monotonic, sleep=clock.sleep)
    w.set_source(src.name, rec)
    return rec, w.finalize(), fake


def _points(tmp_path, cfg, **kw):
    src = _src(cfg)
    rec, snap, _ = _fetch(tmp_path, src, **kw)
    assert rec.status == "ok", rec.error
    return tefas_detail.parse(cfg, src, snap)


def _value(points, entity, quantity):
    [p] = [p for p in points if p.entity == entity and p.quantity == quantity]
    return p.value


def _many_funds(n):
    funds = [dict(TEFAS_WEB_FUNDS[0], fonKodu=f"F{i:02d}") for i in range(n)]
    pages = {f["fonKodu"]: detail_page("ZBJ", f["fonKodu"]) for f in funds}
    return tefas_web_page(funds), pages


# --- config ---------------------------------------------------------------------------------

def test_config_parses_detail_source(cfg):
    src = cfg.sources["tefas_detail"]
    assert isinstance(src, TefasDetailSource)
    assert src.optional_fields["profilData.fonSatisValor"] == "fund_sell_valor_days"
    assert src.optional_fields["profilData.riskDegeri"] == "fund_risk_level"
    assert src.exclude_categories == ("Serbest Şemsiye Fonu",)
    assert src.min_interval_s == 1.0 and src.max_funds is None


@pytest.mark.parametrize("url,match", [
    ("https://www.tefas.gov.tr/tr/fon-detayli-analiz/ZBJ", "must contain {code}"),
    ("https://www.tefas.gov.tr/api/fund/{code}", "disallowed by tefas.gov.tr/robots.txt"),
    ("https://tefas.example.com/tr/fon-detayli-analiz/{code}", "https URL on www.tefas.gov.tr"),
])
def test_config_rejects_bad_url(config_raw, url, match):
    config_raw["sources"]["tefas_detail"]["url"] = url
    with pytest.raises(ConfigError, match=match):
        parse_config(config_raw)


@pytest.mark.parametrize("key,value,match", [
    ("value_fields", {"periyodikData.getiri1a": "fund_price"}, "must be bilgiData.<field>"),
    ("value_fields", {"bilgiData.sonFiyat": "gold_price"}, "unknown quantity"),
    ("optional_fields", {"profilData.riskDegeri": "fund_risk_level",
                         "bilgiData.sonFiyat": "fund_price"}, "also in value_fields"),
    ("funds_from", "manual", "must name a tefas_web source"),
    ("max_fail_share", 1.5, "between 0 and 1"),
    ("min_interval_s", -1, "must be >= 0"),
    ("max_funds", 0, "positive integer"),
])
def test_config_rejects_bad_values(config_raw, key, value, match):
    config_raw["sources"]["tefas_detail"][key] = value
    with pytest.raises(ConfigError, match=match):
        parse_config(config_raw)


@pytest.mark.parametrize("status,match", [
    ({"field": "profilData.tefasDurum", "quantity": "fund_buyable", "map": {"x": 2}},
     "must be 0 or 1"),
    ({"field": "profilData.tefasDurum", "quantity": "fund_buyable",
      "map": {"TEFAS'ta işlem görüyor": 1, "TEFAS'TA  İŞLEM GÖRÜYOR": 0}},
     "same text after normalization"),
    ({"field": "tefasDurum", "quantity": "fund_buyable", "map": {"x": 1}},
     "must be bilgiData.<field>"),
    ({"field": "profilData.tefasDurum", "quantity": "gold", "map": {"x": 1}},
     "unknown quantity"),
    ({"field": "profilData.tefasDurum", "quantity": "fund_buyable", "map": {}},
     "must not be empty"),
])
def test_config_rejects_bad_status(config_raw, status, match):
    config_raw["sources"]["tefas_detail"]["status"] = status
    with pytest.raises(ConfigError, match=match):
        parse_config(config_raw)


def test_config_status_map_is_normalized(cfg):
    st = cfg.sources["tefas_detail"].status
    assert st.field == "profilData.tefasDurum" and st.quantity == "fund_buyable"
    assert st.map == {"tefas'ta işlem görüyor": 1.0, "tefas'ta işlem görmüyor": 0.0,
                      "fon alımına kapalı, fon bozumuna kapalı": 0.0}


def test_normalize_status_turkish_lower_case_and_spaces():
    assert tefas_detail.normalize_status("  TEFAS'ta  İşlem	Görmüyor ") == "tefas'ta işlem görmüyor"
    assert tefas_detail.normalize_status("KAPALI") == "kapalı"


# --- fund list ------------------------------------------------------------------------------

def test_fund_codes_leave_out_excluded_categories(cfg):
    funds = TEFAS_WEB_FUNDS + [dict(TEFAS_WEB_FUNDS[0], fonKodu="SRB",
                                    fonTurAciklama="Serbest Şemsiye Fonu")]
    page = tefas_web_page(funds).decode()
    assert tefas_detail.fund_codes(_src(cfg), page) == ["AAL", "IGL", "ZZZ"]
    assert tefas_detail.fund_codes(_src(cfg, max_funds=2), page) == ["AAL", "IGL"]


# --- fetch ----------------------------------------------------------------------------------

def test_fetch_one_get_per_fund_gzip_payloads(tmp_path, cfg):
    rec, snap, fake = _fetch(tmp_path, _src(cfg))
    assert rec.status == "ok" and rec.rejected_rows == ()
    assert [str(r.url) for r in fake.requests] == [
        f"https://www.tefas.gov.tr/tr/fon-detayli-analiz/{c}" for c in ("AAL", "IGL", "ZZZ")]
    assert all(r.headers["User-Agent"].startswith("rmprep-hackathon-prototype")
               for r in fake.requests)
    assert [p.path for p in rec.payloads] == [
        f"payloads/tefas_detail/{c}.html.gz" for c in ("AAL", "IGL", "ZZZ")]
    assert gzip.decompress(snap.read_payload(rec.payloads[2].path)) == detail_page("MAC", "ZZZ")
    assert rec.payloads[0].meta == {"fund": "AAL",
                                    "url": "https://www.tefas.gov.tr/tr/fon-detayli-analiz/AAL"}
    assert rec.request["funds"] == 3


def test_fetch_waits_min_interval_between_requests(tmp_path, cfg):
    clock = FakeClock(request_seconds=0.25)
    _fetch(tmp_path, _src(cfg), clock=clock)
    gaps = [b - a for a, b in zip(clock.request_times, clock.request_times[1:])]
    assert gaps == [1.0, 1.0]
    assert clock.sleeps == [0.75, 0.75]          # no sleep before the first request


def test_fetch_slow_requests_need_no_sleep(tmp_path, cfg):
    clock = FakeClock(request_seconds=2.0)
    _fetch(tmp_path, _src(cfg), clock=clock)
    assert clock.sleeps == []


def test_fetch_without_listing_fails(tmp_path, cfg):
    rec, _, fake = _fetch(tmp_path, _src(cfg), listing=None)
    assert rec.status == "failed" and "no tefas_web funds" in rec.error
    assert fake.requests == []


def test_fetch_listing_with_only_excluded_funds_fails(tmp_path, cfg):
    funds = [dict(TEFAS_WEB_FUNDS[0], fonTurAciklama="Serbest Şemsiye Fonu")]
    rec, _, fake = _fetch(tmp_path, _src(cfg), listing=tefas_web_page(funds))
    assert rec.status == "failed" and "no tefas_web funds" in rec.error
    assert fake.requests == []


def test_fetch_disallowed_path_is_never_requested(tmp_path, cfg):
    src = _src(cfg, url="https://www.tefas.gov.tr/api/fund/{code}")
    fake = FakeEvds()
    with pytest.raises(ValueError, match="disallowed"):
        _fetch(tmp_path, src, fake=fake)
    assert fake.requests == []


def test_fetch_redirect_is_rejected_not_followed(tmp_path, cfg):
    listing, pages = _many_funds(25)
    fake = FakeEvds(detail_pages=pages)

    def redirect_f03(request):
        if request.url.path.endswith("/F03"):
            fake.requests.append(request)
            return httpx.Response(302, headers={"Location": "https://www.tefas.gov.tr/api/x"})
        return fake(request)

    rec, _, _ = _fetch(tmp_path, _src(cfg), fake=redirect_f03, listing=listing)
    assert rec.status == "ok"
    assert rec.rejected_rows == ({"fund": "F03", "reason": "HTTP 302"},)
    assert len(fake.requests) == 25


@pytest.mark.parametrize("page,reason", [
    (b"<html>new design</html>", "no bilgiData on the page"),
    (detail_page("ZBJ", "F01", sonFiyat="abc"), "bilgiData.sonFiyat: not a number: 'abc'"),
    (detail_page("ZBJ", "F01", yatirimciSayi=None), "bilgiData.yatirimciSayi: no value"),
    (detail_page("ZBJ", "F01", riskDegeri="high"), "profilData.riskDegeri: not a number: 'high'"),
    (detail_page("ZBJ", "XYZ"), "page is for fund 'XYZ'"),
], ids=["no_data", "price_text", "investors_null", "risk_text", "other_fund"])
def test_bad_page_is_rejected_row_with_reason(tmp_path, cfg, page, reason):
    listing, pages = _many_funds(25)
    pages["F01"] = page
    rec, snap, _ = _fetch(tmp_path, _src(cfg), fake=FakeEvds(detail_pages=pages),
                          listing=listing)
    assert rec.status == "ok"
    assert rec.rejected_rows == ({"fund": "F01", "reason": reason},)
    # the raw page is kept for audit, but parse gives no rows for it
    assert "payloads/tefas_detail/F01.html.gz" in [p.path for p in rec.payloads]
    pts = tefas_detail.parse(cfg, _src(cfg), snap)
    assert {p.entity for p in pts} == {f"F{i:02d}" for i in range(25)} - {"F01"}


def test_too_many_failed_pages_fail_the_source_early(tmp_path, cfg):
    listing, pages = _many_funds(25)
    del pages["F00"], pages["F01"]                   # 2/25 = 8 % > 5 %
    rec, _, fake = _fetch(tmp_path, _src(cfg), fake=FakeEvds(detail_pages=pages),
                          listing=listing)
    assert rec.status == "failed"
    assert "2 of 25 pages failed" in rec.error and "page format may have changed" in rec.error
    assert len(fake.requests) == 2                   # stopped at the failure that crossed the share
    assert [r["reason"] for r in rec.rejected_rows] == ["HTTP 404", "HTTP 404"]


def test_failed_share_at_the_limit_is_ok(tmp_path, cfg):
    listing, pages = _many_funds(20)
    del pages["F05"]                                 # 1/20 = 5 %, not more
    rec, _, _ = _fetch(tmp_path, _src(cfg), fake=FakeEvds(detail_pages=pages), listing=listing)
    assert rec.status == "ok" and len(rec.rejected_rows) == 1


def test_connection_error_is_a_failed_page(tmp_path, cfg):
    def handler(request):
        raise httpx.ConnectError("down")
    rec, _, _ = _fetch(tmp_path, _src(cfg), fake=handler)
    assert rec.status == "failed"
    assert rec.rejected_rows[0] == {"fund": "AAL", "reason": "ConnectError: down"}


# --- parse ----------------------------------------------------------------------------------

def test_parse_values_from_real_pages(tmp_path, cfg):
    pts = _points(tmp_path, cfg)
    assert _value(pts, "AAL", "fund_price") == 5.439421                 # ZBJ page
    assert _value(pts, "AAL", "fund_total_value") == 43474009587.69
    assert _value(pts, "AAL", "fund_investor_count") == 27038
    assert _value(pts, "AAL", "fund_risk_level") == 1
    assert _value(pts, "ZZZ", "fund_price") == 0.686755                 # MAC page
    assert _value(pts, "ZZZ", "fund_risk_level") == 6
    assert len(pts) == 3 * 7                                            # fees are null


def test_valor_fields_match_the_page_labels(tmp_path, cfg):
    # MAC page shows "Fon Alış Valörü 1" and "Fon Satış Valörü 2";
    # the data has fonGeriAlisValor 1 and fonSatisValor 2.
    pts = _points(tmp_path, cfg)
    assert _value(pts, "ZZZ", "fund_buy_valor_days") == 1
    assert _value(pts, "ZZZ", "fund_sell_valor_days") == 2
    assert _value(pts, "AAL", "fund_sell_valor_days") == 0


def test_fees_give_rows_only_when_present(tmp_path, cfg):
    pages = {"AAL": detail_page("ZBJ", "AAL", girisKomisyonu=1.5, cikisKomisyonu="0,25"),
             "IGL": detail_page("IPB", "IGL"), "ZZZ": detail_page("MAC", "ZZZ")}
    pts = _points(tmp_path, cfg, fake=FakeEvds(detail_pages=pages))
    assert _value(pts, "AAL", "fund_entry_fee") == 1.5
    assert _value(pts, "AAL", "fund_exit_fee") == 0.25
    assert not [p for p in pts if p.entity != "AAL" and p.quantity.endswith("_fee")]


@pytest.mark.parametrize("risk", [None, "", "-"])
def test_missing_risk_gives_no_risk_row_only(tmp_path, cfg, risk):
    pages = {"AAL": detail_page("ZBJ", "AAL", riskDegeri=risk)}
    listing = tefas_web_page(TEFAS_WEB_FUNDS[:1])
    pts = _points(tmp_path, cfg, fake=FakeEvds(detail_pages=pages), listing=listing)
    assert {p.quantity for p in pts} == {"fund_price", "fund_total_value", "fund_investor_count",
                                         "fund_buy_valor_days", "fund_sell_valor_days", "fund_buyable"}


def test_parse_row_fields(tmp_path, cfg):
    pts = _points(tmp_path, cfg)
    p = next(p for p in pts if p.entity == "ZZZ" and p.quantity == "fund_price")
    assert p.as_of == date(2026, 10, 8)              # previous business day; the page has no date
    assert p.flags == {Flag.NEEDS_CHECK}
    assert p.unit == "TRY" and p.source == "tefas_detail" and p.snapshot_id == SID
    assert p.source_url == "https://www.tefas.gov.tr/tr/fon-detayli-analiz/ZZZ"
    assert p.raw_ref == f"{SID}/payloads/tefas_detail/ZZZ.html.gz#fonKodu=ZZZ;field=bilgiData.sonFiyat"
    assert "as_of assumed" in p.note


def test_needs_check_can_be_switched_off(tmp_path, config_raw):
    config_raw["sources"]["tefas_detail"]["flag_needs_check"] = False
    pts = _points(tmp_path, parse_config(config_raw))
    assert all(p.flags == frozenset() for p in pts)


def test_fallback_rows_keep_original_as_of(tmp_path, cfg):
    _, snap, _ = _fetch(tmp_path, _src(cfg))
    pts = tefas_detail.parse(cfg, _src(cfg), snap, out_snapshot_id="20261013-090000-0002",
                             out_date=date(2026, 10, 13))
    assert {p.as_of for p in pts} == {date(2026, 10, 8)}
    assert {p.snapshot_id for p in pts} == {"20261013-090000-0002"}


def test_parse_is_deterministic(tmp_path, cfg):
    _, snap, _ = _fetch(tmp_path, _src(cfg))
    assert tefas_detail.parse(cfg, _src(cfg), snap) == tefas_detail.parse(cfg, _src(cfg), snap)


def test_same_risk_as_tefas_web_gives_no_conflict(tmp_path, cfg):
    from rmprep.ingest.adapters import tefas_web
    w = SnapshotWriter(tmp_path / "s", {}, created_at=T0, snapshot_id=SID)
    fake = FakeEvds()
    client = fake.client()
    web = tefas_web.fetch(cfg.sources["tefas_web"], w, client=client, now=lambda: T0)
    w.set_source("tefas_web", web)
    det = tefas_detail.fetch(_src(cfg), w, listing=tefas_web_page(), client=client,
                             now=lambda: T0, monotonic=lambda: 0.0, sleep=lambda s: None)
    w.set_source("tefas_detail", det)
    snap = w.finalize()
    pts = (tefas_web.parse(cfg, cfg.sources["tefas_web"], snap)
           + tefas_detail.parse(cfg, _src(cfg), snap))
    risk = [p for p in run_checks(pts, cfg, T0.date()) if p.quantity == "fund_risk_level"]
    assert {(p.entity, p.source) for p in risk} >= {("AAL", "tefas_web"), ("AAL", "tefas_detail")}
    assert not [p for p in risk if Flag.CONFLICT in p.flags]


# --- trade status -> fund_buyable (I3b) ------------------------------------------------------

def _status_points(tmp_path, cfg, pages):
    listing = tefas_web_page([dict(TEFAS_WEB_FUNDS[0], fonKodu=c) for c in pages])
    src = _src(cfg)
    rec, snap, _ = _fetch(tmp_path, src, fake=FakeEvds(detail_pages=pages), listing=listing)
    return rec, tefas_detail.parse(cfg, src, snap)


def test_status_gives_fund_buyable_from_real_pages(tmp_path, cfg):
    rec, pts = _status_points(tmp_path, cfg, {"ZBJ": detail_page("ZBJ"),
                                              "ABU": detail_page("ABU"),
                                              "AC4": detail_page("AC4")})
    assert rec.status == "ok" and rec.rejected_rows == ()
    assert _value(pts, "ZBJ", "fund_buyable") == 1            # "TEFAS'ta işlem görüyor"
    assert _value(pts, "ABU", "fund_buyable") == 0            # "TEFAS'ta İşlem Görmüyor"
    assert _value(pts, "AC4", "fund_buyable") == 0            # "Fon Alımına Kapalı, ..."
    assert _value(pts, "ABU", "fund_price") == 0.109978
    assert not [p for p in pts if p.entity == "ABU" and "valor" in p.quantity]
    p = next(p for p in pts if p.entity == "ABU" and p.quantity == "fund_buyable")
    assert p.unit == "flag"
    assert p.raw_ref.endswith("ABU.html.gz#fonKodu=ABU;field=profilData.tefasDurum")


@pytest.mark.parametrize("text,reason", [
    ("Yeni Durum", "unknown profilData.tefasDurum 'Yeni Durum'; no fund_buyable row"),
    (None, "profilData.tefasDurum: no value; no fund_buyable row"),
])
def test_unknown_status_is_noted_but_does_not_fail_the_page(tmp_path, cfg, text, reason):
    # 1 of 2 pages = 50 % > max_fail_share, so a page failure would fail the source
    rec, pts = _status_points(tmp_path, cfg, {"ZBJ": detail_page("ZBJ", tefasDurum=text),
                                              "MAC": detail_page("MAC")})
    assert rec.status == "ok"
    assert rec.rejected_rows == ({"fund": "ZBJ", "reason": reason},)
    assert not [p for p in pts if p.entity == "ZBJ" and p.quantity == "fund_buyable"]
    assert _value(pts, "ZBJ", "fund_price") == 5.439421       # the other rows stay
    assert _value(pts, "MAC", "fund_buyable") == 1


def test_no_status_block_gives_no_fund_buyable(tmp_path, config_raw):
    del config_raw["sources"]["tefas_detail"]["status"]
    pts = _points(tmp_path, parse_config(config_raw))
    assert not [p for p in pts if p.quantity == "fund_buyable"]
