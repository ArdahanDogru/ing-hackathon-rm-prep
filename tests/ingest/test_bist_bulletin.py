"""I11: Borsa İstanbul end-of-day bulletins (adapter bist_bulletin)."""

import functools
import math
import os
import stat
from datetime import date, timedelta

import httpx
import pytest

from tests.ingest.conftest import (
    BIST_END,
    BIST_HOLIDAY,
    BIST_SAMPLE,
    BIST_SPLIT_INDEX,
    T0,
    FakeEvds,
    add_bist,
    bist_closes,
    bist_history,
    bist_long_closes,
    bist_long_days,
    bist_long_history,
    bist_name,
    bist_row,
    bist_trading_days,
    bulletin_zip,
)
from rmprep.contracts import EntityInfo
from rmprep.ingest.adapters import bist_bulletin as bb
from rmprep.ingest.config import BistBulletinSource, ConfigError, parse_config
from rmprep.ingest.snapshot import SnapshotIntegrityError, SnapshotWriter

SID = "20261009-150000-0001"
TODAY = T0.date()                                  # 2026-10-09, a Friday
CACHE = "cache/bist_bulletin"


class Clock:
    """monotonic() and sleep() without real waiting; each request takes 0.2 s."""

    def __init__(self):
        self.t, self.sleeps, self.request_times = 100.0, [], []

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


@pytest.fixture
def bcfg(config_raw):
    return parse_config(add_bist(config_raw))


def _fetch(tmp_path, cfg, fake=None, *, today=TODAY, sid=SID, clock=None):
    fake = fake or FakeEvds()
    clock = clock or Clock()

    def handler(request):
        clock.request_times.append(clock.t)
        clock.t += 0.2
        return fake(request)

    src = cfg.sources["bist_bulletin"]
    w = SnapshotWriter(tmp_path / "snaps", {}, created_at=T0, snapshot_id=sid)
    rec = bb.fetch(src, w, client=httpx.Client(transport=httpx.MockTransport(handler)),
                   today=today, now=lambda: T0, monotonic=clock.monotonic, sleep=clock.sleep)
    w.set_source("bist_bulletin", rec)
    return rec, w.finalize(), fake


def _points(tmp_path, cfg, **kw):
    rec, snap, _ = _fetch(tmp_path, cfg, **kw)
    assert rec.status == "ok", rec.error
    return bb.parse(cfg, cfg.sources["bist_bulletin"], snap)


def _get(points, entity, quantity):
    found = [p for p in points if p.entity == entity and p.quantity == quantity]
    assert len(found) <= 1
    return found[0] if found else None


def _weekdays(start, end):
    d, out = start, []
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


WINDOW = _weekdays(TODAY - timedelta(days=90), TODAY)      # history_days 90


# --- config -----------------------------------------------------------------------------

def test_config_parses_source(bcfg):
    src = bcfg.sources["bist_bulletin"]
    assert isinstance(src, BistBulletinSource)
    assert (src.history_days, src.min_interval_s, src.recheck_days, src.min_shares,
            src.adjust_jump_pct, src.price_limit_pct) == (90, 1.0, 3, 2, 10.5, 10.0)
    assert src.day_url(date(2026, 10, 8)) == \
        "https://www.borsaistanbul.com/data/thb/2026/10/thb202610081.zip"


def test_config_defaults(config_raw):
    s = add_bist(config_raw)["sources"]["bist_bulletin"]
    for key in ("timeout_seconds", "history_days", "min_interval_s", "recheck_days",
                "min_shares"):
        del s[key]
    s.pop("adjust_jump_pct", None)
    s.pop("price_limit_pct", None)
    src = parse_config(config_raw).sources["bist_bulletin"]
    assert (src.timeout_seconds, src.history_days, src.min_interval_s, src.recheck_days,
            src.min_shares, src.adjust_jump_pct,
            src.price_limit_pct) == (30, 400, 1.0, 3, 100, 10.5, 10.0)


@pytest.mark.parametrize("url,match", [
    ("http://www.borsaistanbul.com/data/thb/{yyyy}/{mm}/thb{yyyymmdd}1.zip", "https URL on"),
    ("https://example.com/data/thb/{yyyy}/{mm}/thb{yyyymmdd}1.zip", "https URL on"),
    ("https://www.borsaistanbul.com/tr/thb/{yyyy}/{mm}/thb{yyyymmdd}1.zip", "under /data/"),
    ("https://www.borsaistanbul.com/data/thb/{yyyy}/{mm}/thb.zip", r"\{yyyymmdd\}"),
    ("https://www.borsaistanbul.com/data/thb/{yyyy}/{dd}/thb{yyyymmdd}1.zip", "unknown field"),
])
def test_config_rejects_bad_url(config_raw, url, match):
    add_bist(config_raw)["sources"]["bist_bulletin"]["url"] = url
    with pytest.raises(ConfigError, match=match):
        parse_config(config_raw)


@pytest.mark.parametrize("key,value,match", [
    ("history_days", 0, "positive integer"),
    ("recheck_days", -1, "must be >= 0"),
    ("min_interval_s", -1, "must be >= 0"),
    ("min_shares", 0, "positive integer"),
    ("adjust_jump_pct", 0, "between 0 and 100"),
    ("adjust_jump_pct", 100, "between 0 and 100"),
    ("adjust_jump_pct", "10.5", "must be a number"),
    ("price_limit_pct", 0, "between 0 and 100"),
    ("price_limit_pct", 100, "between 0 and 100"),
    ("price_limit_pct", "10", "must be a number"),
])
def test_config_rejects_bad_values(config_raw, key, value, match):
    add_bist(config_raw)["sources"]["bist_bulletin"][key] = value
    with pytest.raises(ConfigError, match=match):
        parse_config(config_raw)


def test_config_needs_the_stock_quantities(config_raw):
    del add_bist(config_raw)["quantities"]["stock_volatility_1y"]
    with pytest.raises(ConfigError, match="sources.bist_bulletin: quantity "
                                          "'stock_volatility_1y' is not in quantities"):
        parse_config(config_raw)


# --- fetch and cache ------------------------------------------------------------------------

def test_first_fetch_asks_every_weekday_once_in_order(tmp_path, bcfg):
    rec, _, fake = _fetch(tmp_path, bcfg)
    assert rec.status == "ok"
    asked = [r.url.path.rsplit("/", 1)[-1] for r in fake.requests]
    assert asked == [bist_name(d) for d in WINDOW]
    assert str(fake.requests[-1].url) == \
        "https://www.borsaistanbul.com/data/thb/2026/10/thb202610091.zip"
    assert all(r.headers["User-Agent"].startswith("rmprep-hackathon-prototype")
               for r in fake.requests)


def test_fetch_references_the_cached_files(tmp_path, bcfg):
    rec, snap, _ = _fetch(tmp_path, bcfg)
    days = bist_trading_days()
    assert [p.path for p in rec.payloads] == [f"{CACHE}/{bist_name(d)}" for d in days]
    assert [p.meta["date"] for p in rec.payloads] == [d.isoformat() for d in days]
    assert not (snap.path / "payloads" / "bist_bulletin").exists()
    assert rec.request["files"] == {"fetched": 60, "from_cache": 0,
                                    "not_published": len(WINDOW) - 60, "unreadable": 0,
                                    "closed": 0}
    assert rec.request["history_from"] == bist_trading_days()[0].isoformat()


def test_cache_files_are_read_only_and_unchanged(tmp_path, bcfg):
    _fetch(tmp_path, bcfg)
    f = tmp_path / CACHE / bist_name(BIST_END)
    assert f.read_bytes() == bist_history()[bist_name(BIST_END)]
    assert not os.stat(f).st_mode & stat.S_IWRITE


def test_second_fetch_reuses_the_cache(tmp_path, bcfg):
    _fetch(tmp_path, bcfg)
    rec, _, fake = _fetch(tmp_path, bcfg, sid="20261009-150000-0002")
    # Only the recent days without a file are asked again (recheck_days 3):
    # 9 October (not yet published). The holiday is not asked again.
    assert [r.url.path.rsplit("/", 1)[-1] for r in fake.requests] == ["thb202610091.zip"]
    assert rec.request["files"] == {"fetched": 0, "from_cache": 60,
                                    "not_published": len(WINDOW) - 60, "unreadable": 0,
                                    "closed": 0}
    assert len(rec.payloads) == 60


def test_recent_day_published_later_is_fetched(tmp_path, bcfg):
    _fetch(tmp_path, bcfg)
    days = bist_trading_days(end=TODAY, n=61)
    rec, _, fake = _fetch(tmp_path, bcfg, FakeEvds(bist_files=bist_history(days)),
                          sid="20261009-150000-0002")
    assert rec.request["files"]["fetched"] == 1
    assert rec.payloads[-1].meta["date"] == "2026-10-09"


def test_holiday_marker_is_written(tmp_path, bcfg):
    _fetch(tmp_path, bcfg)
    assert (tmp_path / CACHE / f"thb{BIST_HOLIDAY:%Y%m%d}1.missing").is_file()
    assert not (tmp_path / CACHE / bist_name(BIST_HOLIDAY)).exists()


def test_waits_min_interval_between_requests(tmp_path, bcfg):
    clock = Clock()
    _fetch(tmp_path, bcfg, clock=clock)
    gaps = [b - a for a, b in zip(clock.request_times, clock.request_times[1:])]
    assert gaps and min(gaps) >= 1.0 - 1e-9
    assert len(clock.sleeps) == len(clock.request_times) - 1


def test_html_page_counts_as_not_published(tmp_path, bcfg):
    files = dict(bist_history())
    files[bist_name(BIST_END)] = b"<!DOCTYPE html>\n<html lang=\"tr\"><title>Sayfa Bulunamad\xc4\xb1"
    rec, _, _ = _fetch(tmp_path, bcfg, FakeEvds(bist_files=files))
    assert rec.status == "ok" and len(rec.payloads) == 59
    assert (tmp_path / CACHE / f"thb{BIST_END:%Y%m%d}1.missing").is_file()


def test_http_error_fails_the_source_but_keeps_good_files(tmp_path, bcfg):
    class Broken(FakeEvds):
        def __call__(self, request):
            if bist_name(BIST_END) in str(request.url):
                self.requests.append(request)
                return httpx.Response(503)
            return super().__call__(request)

    rec, _, _ = _fetch(tmp_path, bcfg, Broken())
    assert rec.status == "failed" and f"{bist_name(BIST_END)}: HTTP 503" in rec.error
    assert rec.payloads == ()
    assert (tmp_path / CACHE / bist_name(bist_trading_days()[0])).is_file()


def test_connection_error_fails_the_source(tmp_path, bcfg):
    class Refuse(FakeEvds):
        def __call__(self, request):
            raise httpx.ConnectError("refused")

    rec, _, _ = _fetch(tmp_path, bcfg, Refuse())
    assert rec.status == "failed" and "ConnectError" in rec.error


@pytest.mark.parametrize("bad,reason", [
    (b"PK\x03\x04 broken", "not a ZIP"),
    ("other_date", "bulletin date 2026-10-07, expected 2026-10-08"),
    ("few_shares", "only 1 shares with a closing price (minimum 2)"),
    ("no_code_column", "missing column(s) ['ISLEM KODU']"),
])
def test_bad_bulletin_fails_and_is_not_cached(tmp_path, bcfg, bad, reason):
    files = dict(bist_history())
    if bad == "other_date":
        files[bist_name(BIST_END)] = files[bist_name(date(2026, 10, 7))]
    elif bad == "few_shares":
        files[bist_name(BIST_END)] = bulletin_zip(
            BIST_END, [bist_row(BIST_END, "AAA.E", "AAA HOLDING", 1.0, 1.0)])
    elif bad == "no_code_column":
        header = [line.replace("ISLEM  KODU", "KOD").replace("INSTRUMENT SERIES CODE", "CODE")
                  for line in BIST_SAMPLE.read_text(encoding="utf-8-sig").splitlines()[:2]]
        files[bist_name(BIST_END)] = bulletin_zip(BIST_END, [], header=header)
    else:
        files[bist_name(BIST_END)] = bad
    rec, _, _ = _fetch(tmp_path, bcfg, FakeEvds(bist_files=files))
    assert rec.status == "failed" and reason in rec.error
    assert not (tmp_path / CACHE / bist_name(BIST_END)).exists()


# --- an old file that cannot be read (I11d) --------------------------------------------------

OLD = bist_trading_days()[10]                      # 2026-07-30, far before the recheck days


def _old_format_header():
    return [line.replace("ISLEM  KODU", "KOD").replace("INSTRUMENT SERIES CODE", "CODE")
            for line in BIST_SAMPLE.read_text(encoding="utf-8-sig").splitlines()[:2]]


@pytest.mark.parametrize("bad,reason", [
    ("old_format", "missing column(s) ['ISLEM KODU']"),
    ("not_zip", "not a ZIP"),
])
def test_unreadable_old_file_does_not_fail_the_source(tmp_path, bcfg, bad, reason):
    files = dict(bist_history())
    files[bist_name(OLD)] = (bulletin_zip(OLD, [], header=_old_format_header())
                             if bad == "old_format" else b"PK\x03\x04 broken")
    rec, _, _ = _fetch(tmp_path, bcfg, FakeEvds(bist_files=files))
    assert rec.status == "ok"
    days = bist_trading_days()
    after = days[days.index(OLD) + 1:]
    # The history starts after the unreadable file, so it has no gap.
    assert [p.meta["date"] for p in rec.payloads] == [d.isoformat() for d in after]
    assert rec.request["history_from"] == after[0].isoformat()
    assert rec.request["files"]["unreadable"] == 1
    assert rec.request["unreadable_newest"] == {"file": bist_name(OLD), "reason": reason}
    assert (tmp_path / CACHE / f"thb{OLD:%Y%m%d}1.bad").is_file()
    assert not (tmp_path / CACHE / bist_name(OLD)).exists()


def test_unreadable_old_file_is_not_asked_again(tmp_path, bcfg):
    files = dict(bist_history())
    files[bist_name(OLD)] = b"PK\x03\x04 broken"
    _fetch(tmp_path, bcfg, FakeEvds(bist_files=files))
    rec, _, fake = _fetch(tmp_path, bcfg, FakeEvds(bist_files=files), sid="20261009-150000-0002")
    assert bist_name(OLD) not in [r.url.path.rsplit("/", 1)[-1] for r in fake.requests]
    assert rec.request["files"]["unreadable"] == 1
    assert rec.payloads[0].meta["date"] > OLD.isoformat()


def test_history_starts_after_the_newest_unreadable_file(tmp_path, bcfg):
    days = bist_trading_days()
    files = dict(bist_history())
    for d in (days[5], days[12]):
        files[bist_name(d)] = b"PK\x03\x04 broken"
    rec, _, _ = _fetch(tmp_path, bcfg, FakeEvds(bist_files=files))
    assert rec.request["history_from"] == days[13].isoformat()
    assert rec.request["files"]["unreadable"] == 2
    assert rec.request["unreadable_newest"]["file"] == bist_name(days[12])


# --- a day without trading (I11e) ------------------------------------------------------------

def _closed_day(day):
    """A valid bulletin of `day` without a share with a closing price, as on
    8-14.02.2023 (Borsa İstanbul closed after the earthquake): other rows only."""
    return bulletin_zip(day, [bist_row(day, "XETF.F", "ORNEK BYF", 12.5, 12.4, group="ETF"),
                              bist_row(day, "ZERO.E", "ISLEM GORMEYEN", 0, 5.0)])


def test_closed_day_in_the_history_does_not_cut_it(tmp_path, bcfg):
    files = dict(bist_history())
    files[bist_name(OLD)] = _closed_day(OLD)
    rec, _, _ = _fetch(tmp_path, bcfg, FakeEvds(bist_files=files))
    days = bist_trading_days()
    assert rec.status == "ok"
    assert rec.request["history_from"] == days[0].isoformat()
    assert [p.meta["date"] for p in rec.payloads] == [d.isoformat() for d in days if d != OLD]
    assert rec.request["files"]["closed"] == 1 and rec.request["files"]["unreadable"] == 0
    assert "unreadable_newest" not in rec.request
    assert (tmp_path / CACHE / f"thb{OLD:%Y%m%d}1.closed").is_file()
    assert not (tmp_path / CACHE / f"thb{OLD:%Y%m%d}1.bad").exists()
    assert not (tmp_path / CACHE / bist_name(OLD)).exists()


def test_closed_old_day_is_not_asked_again(tmp_path, bcfg):
    files = dict(bist_history())
    files[bist_name(OLD)] = _closed_day(OLD)
    _fetch(tmp_path, bcfg, FakeEvds(bist_files=files))
    rec, _, fake = _fetch(tmp_path, bcfg, FakeEvds(bist_files=files), sid="20261009-150000-0002")
    assert bist_name(OLD) not in [r.url.path.rsplit("/", 1)[-1] for r in fake.requests]
    assert rec.request["files"]["closed"] == 1


def test_closed_day_in_the_recheck_window_does_not_fail(tmp_path, bcfg):
    files = dict(bist_history())
    files[bist_name(BIST_END)] = _closed_day(BIST_END)
    rec, _, _ = _fetch(tmp_path, bcfg, FakeEvds(bist_files=files))
    assert rec.status == "ok" and rec.request["files"]["closed"] == 1
    assert rec.payloads[-1].meta["date"] == bist_trading_days()[-2].isoformat()


def test_closed_day_with_another_date_still_fails(tmp_path, bcfg):
    files = dict(bist_history())
    files[bist_name(BIST_END)] = _closed_day(date(2026, 10, 7))
    rec, _, _ = _fetch(tmp_path, bcfg, FakeEvds(bist_files=files))
    assert rec.status == "failed" and "bulletin date 2026-10-07, expected 2026-10-08" in rec.error


def test_old_bad_marker_with_0_shares_is_reclassified(tmp_path, bcfg):
    # Markers written by I11d for the closed days of February 2023.
    cache = tmp_path / CACHE
    cache.mkdir(parents=True)
    bad = cache / f"thb{OLD:%Y%m%d}1.bad"
    bad.write_text("only 0 shares with a closing price (minimum 2)\n", encoding="utf-8")
    files = dict(bist_history())
    del files[bist_name(OLD)]
    rec, _, fake = _fetch(tmp_path, bcfg, FakeEvds(bist_files=files))
    assert rec.status == "ok"
    assert rec.request["history_from"] == bist_trading_days()[0].isoformat()   # not cut
    assert rec.request["files"]["closed"] == 1 and rec.request["files"]["unreadable"] == 0
    assert not bad.exists() and (cache / f"thb{OLD:%Y%m%d}1.closed").is_file()
    assert bist_name(OLD) not in [r.url.path.rsplit("/", 1)[-1] for r in fake.requests]


def test_old_bad_marker_with_another_reason_stays(tmp_path, bcfg):
    cache = tmp_path / CACHE
    cache.mkdir(parents=True)
    (cache / f"thb{OLD:%Y%m%d}1.bad").write_text("only 1 shares with a closing price "
                                                 "(minimum 2)\n", encoding="utf-8")
    rec, _, _ = _fetch(tmp_path, bcfg)
    assert rec.request["files"]["unreadable"] == 1
    assert rec.request["history_from"] > OLD.isoformat()


def test_no_bulletin_in_the_window_fails(tmp_path, bcfg):
    rec, _, _ = _fetch(tmp_path, bcfg, FakeEvds(bist_files={}))
    assert rec.status == "failed" and "no bulletin" in rec.error


def test_only_the_bulletin_url_is_requested(tmp_path, bcfg):
    _, _, fake = _fetch(tmp_path, bcfg)
    assert {(r.url.scheme, r.url.host) for r in fake.requests} == {("https", "www.borsaistanbul.com")}
    assert all(r.url.path.startswith("/data/thb/2026/") for r in fake.requests)


# --- reading a bulletin ----------------------------------------------------------------------

def test_read_real_sample_rows():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("thb202610131.csv", BIST_SAMPLE.read_bytes())
    shares = bb.read_bulletin(buf.getvalue(), date(2026, 10, 13))
    assert [s.code for s in shares] == ["AEFES", "THYAO"]          # no ETF, no warrant
    thy = shares[1]
    assert (thy.name, thy.market, thy.bist100) == ("TURK HAVA YOLLARI", "Z", True)
    assert thy.close == 286.25 and thy.open_price == 286.25 and thy.turnover > 0
    assert (thy.low, thy.high) == (284.75, 287.25)


# --- parse -----------------------------------------------------------------------------------

def test_parse_shares_only(tmp_path, bcfg):
    pts = _points(tmp_path, bcfg)
    assert {p.entity for p in pts} == {"AAA", "BBB", "CCC"}
    assert {p.as_of for p in pts} == {BIST_END}
    assert {p.source for p in pts} == {"bist_bulletin"}
    assert all(p.flags == frozenset() for p in pts)


def test_close_and_bist100(tmp_path, bcfg):
    pts = _points(tmp_path, bcfg)
    closes = bist_closes()
    p = _get(pts, "AAA", "stock_close")
    assert p.value == closes["AAA"][BIST_END][0] and p.unit == "TRY"
    assert p.raw_ref == f"{SID}/{CACHE}/{bist_name(BIST_END)}#AAA"
    assert p.source_url == bcfg.sources["bist_bulletin"].source_url
    assert p.fetched_at == T0
    assert _get(pts, "BBB", "stock_close").value == closes["BBB"][BIST_END][0]   # not adjusted
    assert _get(pts, "AAA", "stock_bist100").value == 1
    assert _get(pts, "CCC", "stock_bist100").value == 0


def _last_on_or_before(series, day):
    return max(d for d in series if d <= day)


def test_return_1m_uses_adjusted_closes(tmp_path, bcfg):
    pts = _points(tmp_path, bcfg)
    closes = bist_closes()
    days = bist_trading_days()
    base = _last_on_or_before(closes["BBB"], date(2026, 9, 8))
    assert days.index(base) < BIST_SPLIT_INDEX                   # the split is in the month
    adjusted_base = closes["BBB"][base][0] / 2
    p = _get(pts, "BBB", "stock_return_1m")
    assert p.value == pytest.approx((closes["BBB"][BIST_END][0] / adjusted_base - 1) * 100)
    assert p.note == "BBB SANAYI; adjusted closes (1 jump beyond ±10.5 %); dividends not adjusted"
    first = days[0].isoformat()
    assert p.raw_ref == f"{SID}/{CACHE}/{bist_name(BIST_END)}#BBB;files={first}..{BIST_END}"
    aaa = _get(pts, "AAA", "stock_return_1m").value
    a_base = _last_on_or_before(closes["AAA"], date(2026, 9, 8))
    assert aaa == pytest.approx((closes["AAA"][BIST_END][0] / closes["AAA"][a_base][0] - 1) * 100)
    assert _get(pts, "CCC", "stock_return_1m").value == 0


def test_no_return_when_the_history_is_shorter(tmp_path, bcfg):
    pts = _points(tmp_path, bcfg)
    for q in ("stock_return_3m", "stock_return_6m", "stock_return_1y", "stock_return_3y",
              "stock_return_5y", "stock_volatility_5y"):
        assert _get(pts, "AAA", q) is None


def test_no_volatility_with_fewer_than_26_weeks(tmp_path, bcfg):
    assert _get(_points(tmp_path, bcfg), "AAA", "stock_volatility_1y") is None


def test_turnover_is_the_mean_daily_value(tmp_path, bcfg):
    pts = _points(tmp_path, bcfg)
    assert _get(pts, "AAA", "stock_turnover_3m").value == 1_000_000.0
    assert _get(pts, "CCC", "stock_turnover_3m").value == 10_000.0


def test_entities(tmp_path, bcfg):
    _, snap, _ = _fetch(tmp_path, bcfg)
    ents = bb.entities(bcfg.sources["bist_bulletin"], snap)
    assert ents == {"AAA": EntityInfo("AAA HOLDING", "BIST pay · Z", "bist_bulletin"),
                    "BBB": EntityInfo("BBB SANAYI", "BIST pay · N", "bist_bulletin"),
                    "CCC": EntityInfo("CCC GIDA", "BIST pay · T", "bist_bulletin")}


def test_parse_is_deterministic_and_fallback_keeps_origin(tmp_path, bcfg):
    _, snap, _ = _fetch(tmp_path, bcfg)
    src = bcfg.sources["bist_bulletin"]
    assert bb.parse(bcfg, src, snap) == bb.parse(bcfg, src, snap)
    pts = bb.parse(bcfg, src, snap, out_snapshot_id="20261010-090000-0002",
                   out_date=date(2026, 10, 10))
    assert {p.snapshot_id for p in pts} == {"20261010-090000-0002"}
    assert {p.as_of for p in pts} == {BIST_END}
    assert all(p.raw_ref.startswith(f"{SID}/") for p in pts)


def test_parse_memo_still_verifies_the_files(tmp_path, bcfg):
    _, snap, _ = _fetch(tmp_path, bcfg)
    src = bcfg.sources["bist_bulletin"]
    first = bb.parse(bcfg, src, snap)
    first.clear()                                   # the caller's list, not the memo
    assert bb.parse(bcfg, src, snap) and len(bb.parse(bcfg, src, snap)) > 0
    f = tmp_path / CACHE / bist_name(BIST_END)
    os.chmod(f, stat.S_IREAD | stat.S_IWRITE)
    f.write_bytes(f.read_bytes() + b"x")
    with pytest.raises(SnapshotIntegrityError, match="hash mismatch"):
        bb.parse(bcfg, src, snap)


# --- the calculations ------------------------------------------------------------------------

D = [date(2026, 9, d) for d in (10, 11, 14, 15)]


def _adjust(obs, jump_pct=10.5, limit_pct=10.0):
    """bb.adjust on (day, close, open) rows without low and high (0: the open is the base)."""
    return bb.adjust([(d, c, o, 0.0, 0.0) for d, c, o in obs], jump_pct, limit_pct)


def test_adjust_bonus_issue_down_jump_uses_the_open():
    # KORDS 2026-09-14 (real): close 77.65 on 11.09, then open 4.03, close 4.02.
    obs = [(D[0], 77.0, 77.0), (D[1], 77.65, 77.4), (D[2], 4.02, 4.03), (D[3], 4.10, 4.02)]
    adjusted, n = _adjust(obs, 10.5)
    ratio = 4.03 / 77.65
    assert n == 1
    assert adjusted == [(D[0], 77.0 * ratio), (D[1], 77.65 * ratio), (D[2], 4.02), (D[3], 4.10)]


def test_adjust_reverse_split_up_jump():
    obs = [(D[0], 9.5, 9.5), (D[1], 10.0, 9.5), (D[2], 101.0, 100.0)]    # 10-to-1
    adjusted, n = _adjust(obs, 10.5)
    assert n == 1 and adjusted == [(D[0], 95.0), (D[1], 100.0), (D[2], 101.0)]


@pytest.mark.parametrize("close", [109.9, 90.1, 110.5, 89.5])
def test_adjust_moves_within_the_limit_are_real(close):
    # BIST daily price limit is ±10 %; a move up to ±10.5 % is not a corporate action.
    obs = [(D[0], 100.0, 100.0), (D[1], close, 100.0)]
    assert _adjust(obs, 10.5) == ([(D[0], 100.0), (D[1], close)], 0)


def test_adjust_zero_open_uses_the_close():
    obs = [(D[0], 50.0, 50.0), (D[1], 25.5, 0.0)]
    assert _adjust(obs, 10.5) == ([(D[0], 25.5), (D[1], 25.5)], 1)


def test_adjust_two_jumps_multiply():
    obs = [(D[0], 100.0, 100.0), (D[1], 50.0, 50.0), (D[2], 500.0, 500.0), (D[3], 510.0, 500.0)]
    adjusted, n = _adjust(obs, 10.5)
    assert n == 2                                         # x 0.5, then x 10
    assert adjusted == [(D[0], 500.0), (D[1], 500.0), (D[2], 500.0), (D[3], 510.0)]


def test_adjust_limit_comes_from_the_argument():
    obs = [(D[0], 100.0, 100.0), (D[1], 85.0, 85.0)]
    assert _adjust(obs, 20)[1] == 0 and _adjust(obs, 10.5)[1] == 1


# --- the base price within the daily limit (I11c) --------------------------------------------

@pytest.mark.parametrize("open_price,low,high,close,expected", [
    (5.72, 5.70, 6.91, 6.91, 6.91 / 1.1),     # HRKET 21.09 (real): open below [6.28, 6.33]
    (4.03, 3.92, 4.14, 4.02, 4.03),           # KORDS 14.09 (real): open inside [3.76, 4.36]
    (7.00, 5.70, 6.00, 6.00, 5.70 / 0.9),     # open above the interval -> its upper end
    (6.00, 5.00, 7.00, 6.50, 6.00),           # empty interval [6.36, 5.56] -> the open
    (6.00, 0.0, 7.00, 6.50, 6.00),            # no low -> the open
    (6.00, 5.00, 0.0, 6.50, 6.00),            # no high -> the open
    (0.0, 0.0, 0.0, 6.50, 6.50),              # no open -> the close
])
def test_base_price(open_price, low, high, close, expected):
    assert bb.base_price(open_price, low, high, close, 10.0) == pytest.approx(expected)


def test_base_price_limit_comes_from_the_argument():
    assert bb.base_price(5.72, 5.70, 6.91, 6.91, 20.0) == pytest.approx(6.91 / 1.2)


def test_adjust_uses_the_base_price():
    # HRKET: close 88, then a bonus issue day with open 5.72, low 5.70, high 6.91.
    obs = [(D[0], 88.0, 88.0, 87.0, 89.0), (D[1], 6.91, 5.72, 5.70, 6.91),
           (D[2], 7.00, 6.95, 6.90, 7.05)]
    adjusted, n = bb.adjust(obs, 10.5, 10.0)
    assert n == 1
    assert adjusted[0] == (D[0], pytest.approx(88.0 * (6.91 / 1.1) / 88.0))
    assert adjusted[1:] == [(D[1], 6.91), (D[2], 7.00)]


def _jump_history():
    """Bulletins with the real header, 30 trading days up to BIST_END: KRD has
    a KORDS-like bonus issue on its 21st day, REV a reverse split on its 26th,
    UPD a real +9.9 % day on its 11th, HRK a HRKET-like bonus issue (open
    below the base) on its 16th. Rows: (close, previous close, open[, low, high])."""
    days = bist_trading_days(n=30)
    files = {}
    for k, d in enumerate(days):
        krd = (77.65, 77.4, 77.4) if k < 20 else (
            (4.02, 77.65, 4.03, 3.92, 4.14) if k == 20 else (4.02, 4.02, 4.02))
        rev = (10.0, 10.0, 10.0) if k < 25 else (
            (101.0, 10.0, 100.0) if k == 25 else (101.0, 101.0, 101.0))
        upd = (100.0, 100.0, 100.0) if k < 10 else (
            (109.9, 100.0, 100.5) if k == 10 else (109.9, 109.9, 109.9))
        hrk = (88.0, 88.0, 88.0) if k < 15 else (
            (6.91, 88.0, 5.72, 5.70, 6.91) if k == 15 else (6.91, 6.91, 6.91))
        rows = [bist_row(d, f"{c}.E", f"{c} AS", *values[:2], open_price=values[2],
                         low=values[3] if len(values) > 3 else None,
                         high=values[4] if len(values) > 3 else None)
                for c, values in (("KRD", krd), ("REV", rev), ("UPD", upd), ("HRK", hrk))]
        files[bist_name(d)] = bulletin_zip(d, rows)
    return files, days


def test_jumps_in_the_bulletins_are_adjusted(tmp_path, bcfg):
    files, days = _jump_history()
    pts = _points(tmp_path, bcfg, fake=FakeEvds(bist_files=files))
    base = max(d for d in days if d <= date(2026, 9, 8))
    assert days.index(base) < 10                          # all three moves are in the month
    krd = _get(pts, "KRD", "stock_return_1m")
    assert krd.value == pytest.approx((4.02 / (77.65 * 4.03 / 77.65) - 1) * 100)
    assert krd.note == "KRD AS; adjusted closes (1 jump beyond ±10.5 %); dividends not adjusted"
    assert _get(pts, "REV", "stock_return_1m").value == pytest.approx(1.0)   # 10 -> 101 / 10
    upd = _get(pts, "UPD", "stock_return_1m")
    assert upd.value == pytest.approx(9.9)                # a real move, kept
    assert upd.note == "UPD AS; adjusted closes (0 jumps beyond ±10.5 %); dividends not adjusted"
    assert _get(pts, "KRD", "stock_close").value == 4.02  # the close itself is not adjusted
    hrk = _get(pts, "HRK", "stock_return_1m")             # base 6.91 / 1.1, not the open 5.72
    assert hrk.value == pytest.approx((6.91 / (6.91 / 1.1) - 1) * 100)      # +10 %, not +21 %


def test_jump_limit_from_config(tmp_path, config_raw):
    add_bist(config_raw)["sources"]["bist_bulletin"]["adjust_jump_pct"] = 99
    cfg = parse_config(config_raw)
    files, _ = _jump_history()
    pts = _points(tmp_path, cfg, fake=FakeEvds(bist_files=files))
    krd = _get(pts, "KRD", "stock_return_1m")
    assert krd.value == pytest.approx((4.02 / 77.65 - 1) * 100)
    assert "(0 jumps beyond ±99 %)" in krd.note


def test_parse_with_jumps_is_deterministic(tmp_path, bcfg):
    files, _ = _jump_history()
    _, snap, _ = _fetch(tmp_path, bcfg, FakeEvds(bist_files=files))
    src = bcfg.sources["bist_bulletin"]
    assert bb.parse(bcfg, src, snap) == bb.parse(bcfg, src, snap)


def test_period_return_uses_last_day_on_or_before_the_date():
    series = [(date(2026, 9, 4), 100.0), (date(2026, 9, 7), 110.0), (date(2026, 10, 8), 121.0)]
    # one month before 8 October is 8 September -> the close of 7 September
    assert bb.period_return(series, 1) == pytest.approx(10.0)
    assert bb.period_return(series, 3) is None


def test_period_return_end_of_month_clamps_the_day():
    series = [(date(2026, 2, 27), 100.0), (date(2026, 3, 31), 105.0)]
    assert bb.period_return(series, 1) == pytest.approx(5.0)    # 31 March -> 28 February


def _weeks_series(returns, start=date(2025, 10, 13)):
    """Mon close 100, Fri close 100 * (1 + r) for each week."""
    out = []
    for i, r in enumerate(returns):
        monday = start + timedelta(weeks=i)
        out += [(monday, 100.0), (monday + timedelta(days=4), 100.0 * (1 + r))]
    return out


def test_spk_volatility_on_a_known_series():
    r = [0.01, -0.01] * 13                                        # 26 weeks, mean 0
    expected = 100 * math.sqrt(52 / 25 * sum(x * x for x in r))
    assert bb.spk_volatility(_weeks_series(r)) == pytest.approx(expected)


def test_spk_volatility_uses_the_mean():
    r = [0.02, 0.0] * 13                                          # mean 0.01
    expected = 100 * math.sqrt(52 / 25 * sum((x - 0.01) ** 2 for x in r))
    assert bb.spk_volatility(_weeks_series(r)) == pytest.approx(expected)


def test_spk_volatility_needs_26_weeks():
    assert bb.spk_volatility(_weeks_series([0.01, -0.01] * 12 + [0.01])) is None


def test_spk_volatility_skips_weeks_with_one_trading_day():
    series = _weeks_series([0.01, -0.01] * 13)
    lonely = series[-1][0] + timedelta(days=3)                     # a Monday alone
    expected = bb.spk_volatility(series)
    assert bb.spk_volatility(series + [(lonely, 500.0)]) == pytest.approx(expected)


def test_spk_volatility_uses_only_the_last_year():
    old = [(date(2024, 1, 1), 1.0), (date(2024, 1, 5), 1000.0)]   # far outside the year
    series = _weeks_series([0.01, -0.01] * 13)
    assert bb.spk_volatility(old + series) == pytest.approx(bb.spk_volatility(series))


def test_spk_volatility_window_in_months_and_weeks():
    r = [0.02, -0.01] * 30                                        # 60 weeks
    series = _weeks_series(r, start=date(2025, 1, 6))
    value, weeks = bb.spk_volatility_weeks(series, 60)
    mean = sum(r) / len(r)
    assert weeks == 60
    assert value == pytest.approx(100 * math.sqrt(52 / 59 * sum((x - mean) ** 2 for x in r)))
    one_year, weeks_1y = bb.spk_volatility_weeks(series, 12)
    assert 50 <= weeks_1y <= 53 and one_year is not None
    assert bb.spk_volatility_weeks(series[:40], 60) == (None, 20)  # fewer than 26 weeks


def test_period_return_in_years():
    series = [(date(2021, 10, 7), 10.0), (date(2023, 10, 6), 40.0), (date(2026, 10, 8), 100.0)]
    # 5 years before 8.10.2026 is 8.10.2021 -> the close of 7.10.2021 (10);
    # 3 years before is 8.10.2023 -> the close of 6.10.2023 (40).
    assert bb.period_return(series, 60) == pytest.approx(900.0)
    assert bb.period_return(series, 36) == pytest.approx(150.0)
    assert bb.period_return(series[1:], 60) is None


# --- 5 years of history (I11d) ---------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _long_files():
    return bist_long_history()


def _long_cfg(config_raw):
    add_bist(config_raw)["sources"]["bist_bulletin"]["history_days"] = 1900
    return parse_config(config_raw)


def _long_points(tmp_path, cfg):
    return _points(tmp_path, cfg, fake=FakeEvds(bist_files=_long_files()))


def test_long_history_returns_3y_and_5y(tmp_path, config_raw):
    pts = _long_points(tmp_path, _long_cfg(config_raw))
    days = bist_long_days()
    closes = bist_long_closes(days)["AAA"]
    for quantity, years in (("stock_return_3y", 3), ("stock_return_5y", 5)):
        target = date(BIST_END.year - years, BIST_END.month, BIST_END.day)
        base = closes[max(d for d in days if d <= target)]
        p = _get(pts, "AAA", quantity)
        assert p.value == pytest.approx((closes[BIST_END] / base - 1) * 100)
        assert p.unit == "pct" and p.note.endswith("dividends not adjusted")
    assert _get(pts, "LLL", "stock_return_5y").value == 0


def test_long_history_volatility_5y_spk(tmp_path, config_raw):
    pts = _long_points(tmp_path, _long_cfg(config_raw))
    closes = bist_long_closes(bist_long_days())["AAA"]
    for quantity, start in (("stock_volatility_5y", date(2021, 10, 8)),
                            ("stock_volatility_1y", date(2025, 10, 8))):
        weeks = {}
        for d, c in closes.items():
            if d > start:
                weeks.setdefault(d.isocalendar()[:2], []).append((d, c))
        r = [w[-1][1] / w[0][1] - 1 for w in (sorted(v) for v in weeks.values()) if len(w) >= 2]
        mean = sum(r) / len(r)
        p = _get(pts, "AAA", quantity)
        assert p.value == pytest.approx(100 * math.sqrt(52 / (len(r) - 1)
                                                        * sum((x - mean) ** 2 for x in r)))
        assert p.note.endswith(f"; SPK weekly method, {len(r)} weeks")
    assert _get(pts, "LLL", "stock_volatility_5y").value == 0


def test_long_quantities_are_optional(tmp_path, config_raw):
    add_bist(config_raw)["sources"]["bist_bulletin"]["history_days"] = 1900
    for q in ("stock_return_3y", "stock_return_5y", "stock_volatility_5y"):
        del config_raw["quantities"][q]
    pts = _long_points(tmp_path, parse_config(config_raw))
    assert {p.quantity for p in pts if p.entity == "AAA"} == {
        "stock_close", "stock_return_1m", "stock_return_3m", "stock_return_6m",
        "stock_return_1y", "stock_volatility_1y", "stock_turnover_3m", "stock_bist100"}


def test_long_history_requests_start_at_history_days(tmp_path, config_raw):
    rec, _, _ = _fetch(tmp_path, _long_cfg(config_raw), FakeEvds(bist_files=_long_files()))
    assert rec.request["from"] == (TODAY - timedelta(days=1900)).isoformat()
    assert rec.request["history_from"] >= rec.request["from"]
    assert len(rec.payloads) == len([d for d in bist_long_days()
                                     if d >= TODAY - timedelta(days=1900)])
