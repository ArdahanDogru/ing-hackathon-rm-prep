import json
from datetime import date, timedelta

import httpx
import pytest

from tests.ingest.conftest import (CPI_ANNUAL_ENTITY, CPI_CODE, FIXTURES, KEY, T0, FakeEvds,
                                   add_cpi_annual)
from rmprep.ingest.adapters import evds
from rmprep.ingest.config import parse_config
from rmprep.contracts import Flag
from rmprep.ingest.snapshot import MANIFEST, SnapshotWriter

TODAY = T0.date()


def _fetch(tmp_path, cfg, fake, api_key=KEY):
    src = cfg.sources["evds"]
    w = SnapshotWriter(tmp_path / "snaps", {"cfg": "copy"}, created_at=T0,
                       snapshot_id="20261009-150000-0001", secrets=[KEY])
    rec = evds.fetch(src, w, api_key=api_key, client=fake.client(), today=TODAY,
                     now=lambda: T0)
    w.set_source("evds", rec)
    return rec, w.finalize()


def _by_entity(points):
    out = {}
    for p in points:
        out.setdefault(p.entity, []).append(p)
    return out


# --- fetch -----------------------------------------------------------------------

def test_fetch_ok_stores_one_payload_per_real_series(tmp_path, cfg):
    fake = FakeEvds()
    rec, snap = _fetch(tmp_path, cfg, fake)
    assert rec.status == "ok" and rec.fetched_at == T0
    assert [p.meta["series"] for p in rec.payloads] == ["TP.DK.USD.A.YTL", "TP.FG.J0"]
    assert snap.read_payload("payloads/evds/TP.FG.J0.json") == \
        (FIXTURES / "evds" / "TP.FG.J0.json").read_bytes()


def test_fetch_sends_key_in_header_not_url(tmp_path, cfg):
    fake = FakeEvds()
    _fetch(tmp_path, cfg, fake)
    assert len(fake.requests) == 2
    for r in fake.requests:
        assert r.headers["key"] == KEY
        assert KEY not in str(r.url)


def test_fetch_url_format(tmp_path, cfg):
    # Format from the EVDS Web Servis Kılavuzu (EVDS3).
    fake = FakeEvds()
    _fetch(tmp_path, cfg, fake)
    assert str(fake.requests[1].url) == (
        "https://evds3.tcmb.gov.tr/igmevdsms-dis/series=TP.FG.J0"
        "&startDate=01-06-2026&endDate=09-10-2026&type=json")   # 120 days back -> 1 June


@pytest.mark.parametrize("today,days,expected", [
    (date(2026, 10, 9), 120, date(2026, 6, 1)),
    (date(2026, 10, 9), 8, date(2026, 10, 1)),
    (date(2026, 1, 15), 30, date(2025, 12, 1)),
])
def test_request_start_is_first_day_of_month(today, days, expected):
    assert evds.request_start(today, days) == expected


def test_placeholder_series_not_requested(tmp_path, cfg):
    fake = FakeEvds()
    _fetch(tmp_path, cfg, fake)
    assert not any("VERIFY_" in str(r.url) for r in fake.requests)


def test_key_never_in_manifest(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    assert KEY not in (snap.path / MANIFEST).read_text(encoding="utf-8")


def test_no_api_key_fails_without_request(tmp_path, cfg):
    fake = FakeEvds()
    rec, snap = _fetch(tmp_path, cfg, fake, api_key=None)
    assert rec.status == "failed"
    assert "EVDS_API_KEY" in rec.error
    assert fake.requests == [] and rec.payloads == ()


def test_get_api_key_from_env(cfg):
    src = cfg.sources["evds"]
    assert evds.get_api_key(src, {"EVDS_API_KEY": " abc "}) == "abc"
    assert evds.get_api_key(src, {"EVDS_API_KEY": ""}) is None
    assert evds.get_api_key(src, {}) is None


def test_http_error_fails_and_stores_nothing(tmp_path, cfg):
    rec, snap = _fetch(tmp_path, cfg, FakeEvds(status=500))
    assert rec.status == "failed" and "HTTP 500" in rec.error
    assert rec.payloads == ()
    assert not (snap.path / "payloads" / "evds").exists()


def test_connection_error_fails(tmp_path, cfg):
    rec, _ = _fetch(tmp_path, cfg, FakeEvds(error=httpx.ConnectError("refused")))
    assert rec.status == "failed" and "ConnectError" in rec.error


def test_html_instead_of_json_fails(tmp_path, cfg):
    rec, _ = _fetch(tmp_path, cfg, FakeEvds(body=b"<html>Login</html>"))
    assert rec.status == "failed" and "not JSON" in rec.error


def test_one_bad_series_fails_whole_source(tmp_path, config_raw):
    config_raw["sources"]["evds"]["series"][1]["code"] = "TP.UNKNOWN"
    rec, _ = _fetch(tmp_path, parse_config(config_raw), FakeEvds())
    assert rec.status == "failed" and "TP.UNKNOWN: HTTP 404" in rec.error
    assert rec.payloads == ()


# --- parse ---------------------------------------------------------------------------

def test_parse_values_dates_units(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    pts = _by_entity(evds.parse(cfg, cfg.sources["evds"], snap))
    usd = pts["USD/TRY CBRT buying rate"]
    assert [(p.as_of, p.value) for p in usd] == [
        (date(2026, 10, 3), 41.521), (date(2026, 10, 7), 41.6034), (date(2026, 10, 8), 41.6512)]
    assert {p.unit for p in usd} == {"TRY"}
    assert usd[0].raw_ref == "20261009-150000-0001/payloads/evds/TP.DK.USD.A.YTL.json#items[0]"
    assert usd[0].fetched_at == T0 and usd[0].snapshot_id == "20261009-150000-0001"


def test_null_values_are_skipped_not_missing(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    usd = _by_entity(evds.parse(cfg, cfg.sources["evds"], snap))["USD/TRY CBRT buying rate"]
    assert date(2026, 10, 4) not in {p.as_of for p in usd}
    assert all(Flag.MISSING not in p.flags for p in usd)


def test_monthly_as_of_is_last_day_of_month(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    cpi = _by_entity(evds.parse(cfg, cfg.sources["evds"], snap))["CPI general index (2003=100)"]
    assert [p.as_of for p in cpi] == [date(2026, 7, 31), date(2026, 8, 31), date(2026, 9, 30)]


def test_unverified_series_flagged(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    pts = evds.parse(cfg, cfg.sources["evds"], snap)
    assert all(Flag.UNVERIFIED_SERIES in p.flags for p in pts)


def test_verified_series_not_flagged(tmp_path, config_raw):
    config_raw["sources"]["evds"]["series"][0]["verified"] = True
    cfg = parse_config(config_raw)
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    usd = _by_entity(evds.parse(cfg, cfg.sources["evds"], snap))["USD/TRY CBRT buying rate"]
    assert all(p.flags == frozenset() for p in usd)


def test_placeholder_gives_missing_row(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    pts = _by_entity(evds.parse(cfg, cfg.sources["evds"], snap))
    [p] = pts["CBRT one-week repo rate"]
    assert p.value is None
    assert p.flags == {Flag.MISSING, Flag.UNVERIFIED_SERIES}
    assert p.as_of == TODAY
    assert p.raw_ref == f"20261009-150000-0001/{MANIFEST}#config.sources.evds.series[2]"
    assert "placeholder" in p.note


def test_series_without_observations_gives_missing_row(tmp_path, cfg):
    empty = b'{"totalCount":0,"items":[]}'
    _, snap = _fetch(tmp_path, cfg, FakeEvds(body=empty))
    pts = _by_entity(evds.parse(cfg, cfg.sources["evds"], snap))
    [p] = pts["USD/TRY CBRT buying rate"]
    assert p.value is None and Flag.MISSING in p.flags
    assert "no observations" in p.note


def test_parse_for_fallback_keeps_origin(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    pts = evds.parse(cfg, cfg.sources["evds"], snap,
                     out_snapshot_id="20261010-090000-0002", out_date=date(2026, 10, 10))
    real = [p for p in pts if p.value is not None]
    assert {p.snapshot_id for p in pts} == {"20261010-090000-0002"}
    assert all(p.raw_ref.startswith("20261009-150000-0001/") for p in pts)
    assert {p.fetched_at for p in real} == {T0}
    placeholder = [p for p in pts if "placeholder" in p.note][0]
    assert placeholder.as_of == date(2026, 10, 10)


def test_parse_is_deterministic(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    src = cfg.sources["evds"]
    assert evds.parse(cfg, src, snap) == evds.parse(cfg, src, snap)


def test_parse_refuses_failed_source(tmp_path, cfg):
    _, snap = _fetch(tmp_path, cfg, FakeEvds(status=500))
    with pytest.raises(ValueError, match="no ok record"):
        evds.parse(cfg, cfg.sources["evds"], snap)


def test_missing_points_one_per_series(cfg):
    pts = evds.missing_points(cfg, cfg.sources["evds"], "20261009-150000-0001", T0,
                              note="EVDS failed; no earlier snapshot")
    assert len(pts) == len(cfg.sources["evds"].series)
    assert all(p.value is None and Flag.MISSING in p.flags for p in pts)
    assert all(p.as_of == TODAY for p in pts)


# --- low-level parsing --------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("08-10-2026", date(2026, 10, 8)),
    ("2026-9", date(2026, 9, 30)),
    ("2026-02", date(2026, 2, 28)),
    ("2028-2", date(2028, 2, 29)),
])
def test_parse_evds_date(text, expected):
    assert evds.parse_evds_date(text) == expected


@pytest.mark.parametrize("text", ["2026-Q3", "2026", "8/10/2026", "2026-13"])
def test_unsupported_date_rejected(text):
    with pytest.raises(evds.EvdsParseError):
        evds.parse_evds_date(text)


@pytest.mark.parametrize("raw,expected", [
    ("41.5210", 41.521), ("41,5210", 41.521), (12, 12.0), (None, None), ("  ", None)])
def test_value_parsing(raw, expected):
    body = ('{"items":[{"Tarih":"08-10-2026","TP_X":%s}]}' %
            ("null" if raw is None else f'"{raw}"' if isinstance(raw, str) else raw)).encode()
    [(_, _, v)] = evds.parse_payload(body, "TP.X")
    assert v == expected


# --- I5: per-series lookback and annual change ---------------------------------------------

CPI_SID = "20261009-150000-0001"
CPI_PAYLOAD = f"payloads/evds/{CPI_CODE}.json"


def _cpi_cfg(config_raw):
    return parse_config(add_cpi_annual(config_raw))


def _annual(points):
    return [p for p in points if p.quantity == "cpi_annual"]


def test_series_lookback_overrides_source_lookback(tmp_path, config_raw):
    fake = FakeEvds()
    rec, _ = _fetch(tmp_path, _cpi_cfg(config_raw), fake)
    urls = [str(r.url) for r in fake.requests]
    assert f"series={CPI_CODE}&startDate=01-09-2025&endDate=09-10-2026&type=json" in urls[2]
    assert "startDate=01-06-2026" in urls[0] and "startDate=01-06-2026" in urls[1]
    assert rec.request["start_date"] == "2026-06-01"
    assert rec.request["series_start_dates"] == {CPI_CODE: "2025-09-01"}


def test_request_has_no_series_start_dates_without_override(tmp_path, cfg):
    rec, _ = _fetch(tmp_path, cfg, FakeEvds())
    assert "series_start_dates" not in rec.request


def test_annual_change_row_from_13_months(tmp_path, config_raw):
    cfg = _cpi_cfg(config_raw)
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    [p] = _annual(evds.parse(cfg, cfg.sources["evds"], snap))
    assert p.value == (137.23 / 105.78 - 1) * 100          # full float, about 29.73
    assert round(p.value, 2) == 29.73
    assert p.entity == CPI_ANNUAL_ENTITY and p.unit == "pct"
    assert p.as_of == date(2026, 9, 30)
    assert p.source == "evds" and p.source_url == cfg.sources["evds"].source_url
    assert p.fetched_at == T0 and p.snapshot_id == CPI_SID
    assert p.raw_ref == f"{CPI_SID}/{CPI_PAYLOAD}#{CPI_CODE}:2026-9/2025-9"
    assert p.flags == frozenset()                         # the series is verified
    assert p.note == f"12-month change of {CPI_CODE}: 137.23 (2026-9) / 105.78 (2025-9) - 1"


def test_annual_change_keeps_index_rows(tmp_path, config_raw):
    cfg = _cpi_cfg(config_raw)
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    pts = _by_entity(evds.parse(cfg, cfg.sources["evds"], snap))
    assert len(pts["CPI general index (2025=100)"]) == 13


def test_annual_change_of_unverified_series_is_flagged(tmp_path, config_raw):
    add_cpi_annual(config_raw)["sources"]["evds"]["series"][-1]["verified"] = False
    cfg = parse_config(config_raw)
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    [p] = _annual(evds.parse(cfg, cfg.sources["evds"], snap))
    assert p.flags == {Flag.UNVERIFIED_SERIES}


def _cpi_body(items):
    return json.dumps({"totalCount": len(items), "items": items}).encode()


def _cpi_items():
    return json.loads((FIXTURES / "evds" / f"{CPI_CODE}.json").read_bytes())["items"]


class CpiOnly(FakeEvds):
    """Serves `body` for the CPI series and the fixtures for the others."""

    def __init__(self, body):
        super().__init__()
        self.cpi = body

    def __call__(self, request):
        if CPI_CODE in str(request.url):
            self.requests.append(request)
            return httpx.Response(200, content=self.cpi)
        return super().__call__(request)


def test_12_months_give_no_annual_row(tmp_path, config_raw):
    cfg = _cpi_cfg(config_raw)
    _, snap = _fetch(tmp_path, cfg, CpiOnly(_cpi_body(_cpi_items()[1:])))   # 2025-10 .. 2026-9
    pts = evds.parse(cfg, cfg.sources["evds"], snap)
    assert _annual(pts) == []                                # no row, not a missing row
    assert len(_by_entity(pts)["CPI general index (2025=100)"]) == 12


def test_annual_change_uses_latest_month_with_value(tmp_path, config_raw):
    items = _cpi_items() + [{"Tarih": "2026-10", "TP_TUKFIY2025_GENEL": None}]
    cfg = _cpi_cfg(config_raw)
    _, snap = _fetch(tmp_path, cfg, CpiOnly(_cpi_body(items)))
    [p] = _annual(evds.parse(cfg, cfg.sources["evds"], snap))
    assert p.as_of == date(2026, 9, 30)


def test_null_value_12_months_back_gives_no_annual_row(tmp_path, config_raw):
    items = _cpi_items()
    items[0]["TP_TUKFIY2025_GENEL"] = None
    cfg = _cpi_cfg(config_raw)
    _, snap = _fetch(tmp_path, cfg, CpiOnly(_cpi_body(items)))
    assert _annual(evds.parse(cfg, cfg.sources["evds"], snap)) == []


def test_zero_value_12_months_back_gives_no_annual_row(tmp_path, config_raw):
    items = _cpi_items()
    items[0]["TP_TUKFIY2025_GENEL"] = "0"
    cfg = _cpi_cfg(config_raw)
    _, snap = _fetch(tmp_path, cfg, CpiOnly(_cpi_body(items)))
    assert _annual(evds.parse(cfg, cfg.sources["evds"], snap)) == []


def test_annual_change_row_for_fallback_keeps_origin(tmp_path, config_raw):
    cfg = _cpi_cfg(config_raw)
    _, snap = _fetch(tmp_path, cfg, FakeEvds())
    [p] = _annual(evds.parse(cfg, cfg.sources["evds"], snap,
                             out_snapshot_id="20261010-090000-0002", out_date=date(2026, 10, 10)))
    assert p.snapshot_id == "20261010-090000-0002"
    assert p.raw_ref.startswith(f"{CPI_SID}/") and p.fetched_at == T0
    assert p.as_of == date(2026, 9, 30)


def test_failed_cpi_series_gives_no_annual_missing_row(cfg, config_raw):
    cfg = _cpi_cfg(config_raw)
    pts = evds.missing_points(cfg, cfg.sources["evds"], CPI_SID, T0, note="EVDS failed")
    assert _annual(pts) == []


def test_forbidden_key_fails(tmp_path, cfg):
    rec, _ = _fetch(tmp_path, cfg, FakeEvds(status=403))
    assert rec.status == "failed" and "HTTP 403" in rec.error


# --- metadata helpers ---------------------------------------------------------------------

GROUPS = [
    {"DATAGROUP_CODE": "bie_mevfaiz", "DATAGROUP_NAME": "Mevduat Faiz Oranları",
     "FREQUENCY_STR": "HAFTALIK"},
    {"DATAGROUP_CODE": "bie_dkdovytl", "DATAGROUP_NAME": "Döviz Kurları",
     "FREQUENCY_STR": "İŞ GÜNÜ"},
]
SERIES = {
    "bie_mevfaiz": [{"SERIE_CODE": "TP.MEV.X1", "SERIE_NAME": "TL 3 aya kadar",
                     "DATAGROUP_CODE": "bie_mevfaiz", "FREQUENCY_STR": "HAFTALIK",
                     "START_DATE": "01-01-2002", "END_DATE": "03-10-2026"}],
    "TP.DK.USD.A.YTL": [{"SERIE_CODE": "TP.DK.USD.A.YTL", "SERIE_NAME": "(USD) ABD Doları (Döviz Alış)",
                         "FREQUENCY_STR": "İŞ GÜNÜ", "START_DATE": "02-01-1950",
                         "END_DATE": "09-10-2026"}],
}


class FakeMeta:
    def __init__(self, status=200):
        self.status = status
        self.requests = []

    def __call__(self, request):
        import json as _json
        self.requests.append(request)
        url = str(request.url)
        if self.status != 200:
            return httpx.Response(self.status)
        if "datagroups/" in url:
            return httpx.Response(200, json=GROUPS)
        code = url.rsplit("code=", 1)[1]
        return httpx.Response(200, content=_json.dumps(SERIES.get(code, [])).encode())

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self))


def test_find_series_matches_turkish_text(cfg):
    fake = FakeMeta()
    groups, series = evds.find_series(cfg.sources["evds"], fake.client(), KEY, "MEVDUAT faiz")
    assert [evds._field(g, "datagroup_code") for g in groups] == ["bie_mevfaiz"]
    assert [(s.code, s.name, s.frequency) for s in series] == [
        ("TP.MEV.X1", "TL 3 aya kadar", "HAFTALIK")]
    assert all(r.headers["key"] == KEY and KEY not in str(r.url) for r in fake.requests)
    assert str(fake.requests[0].url) == \
        "https://evds3.tcmb.gov.tr/igmevdsms-dis/datagroups/mode=0&type=json"


def test_list_series_for_one_code(cfg):
    [s] = evds.list_series(cfg.sources["evds"], FakeMeta().client(), KEY, "TP.DK.USD.A.YTL")
    assert s.name == "(USD) ABD Doları (Döviz Alış)" and s.start == "02-01-1950"


def test_metadata_accepts_wrapped_list():
    assert evds._records({"items": [{"a": 1}], "totalCount": 1}) == [{"a": 1}]
    assert evds._records("x") == []


def test_metadata_403_hint(cfg):
    with pytest.raises(evds.EvdsParseError, match="check EVDS_API_KEY"):
        evds.list_datagroups(cfg.sources["evds"], FakeMeta(status=403).client(), KEY)


@pytest.mark.parametrize("body", [b'{"items":[{"Tarih":"08-10-2026","TP_X":"ND"}]}',
                                  b'{"items":[{"TP_X":"1"}]}',
                                  b'{"error":"bad key"}'])
def test_malformed_payload_rejected(body):
    with pytest.raises(evds.EvdsParseError):
        evds.parse_payload(body, "TP.X")
