"""Borsa İstanbul end-of-day bulletin adapter (I11): shares from the official
daily bulletin files.

Rules (checked 2026-10-14): robots.txt allows "/"; real-time data needs a
licence, the end-of-day bulletins are published for download. One ZIP per
trading day (`src.url`, e.g. /data/thb/YYYY/MM/thbYYYYMMDD1.zip), at least
`min_interval_s` between requests, no redirects, honest User-Agent; only URLs
on www.borsaistanbul.com under /data/ are requested.

Cache: the bulletin of a past day never changes, so each file is fetched once
into `<data>/cache/<source>/` and made read-only. A weekday without a bulletin
(HTTP 404, or the site's HTML "page not found" with status 200) gets a small
`.missing` marker and is not asked again, except in the last `recheck_days`
days (not yet published). The snapshot does not copy the files: its manifest
references them with their SHA-256 (snapshot.py, cache payloads), and replay
verifies them.

File: one CSV, `;`, UTF-8 with BOM, two header lines (TR, EN), decimal point,
LF line ends. Header names are matched with single spaces ("ISLEM  KODU" has
two). Shares only: ENSTRUMAN GRUBU "EQT", code ending ".E", closing price > 0
(the 13.10.2026 file: 628 of them; ETFs, warrants and certificates are left
out). A new file is checked before it is cached (a ZIP with one CSV, the
columns, TARIH = the day of the URL, at least `min_shares` shares). A bad file
of the last `recheck_days` days fails the source and is not cached. A bad
older file (I11d: e.g. another format in old years) gets a `.bad` marker and
the history starts after it; the manifest request records `history_from` and
`unreadable_newest`. Probe 2026-10-14 (one file per year, 2021-2025): the same
columns every year; 2023 added "BIST KATILIM TUM ENDEKS" at the end; no BOM
before 2026.

Parse (pure, from the files in the manifest): adjusted closes (`adjust`: jumps
beyond ±`adjust_jump_pct` are corporate actions, I11b, from a base price within
the daily limit `price_limit_pct`, I11c; dividends not adjusted),
returns over 1/3/6/12 months and 3/5 years (`period_return`), the SPK weekly
volatility over 1 and 5 years (`spk_volatility_weeks`), the mean daily traded
value of the last 63 bulletins, the BIST 100 membership. as_of = the date of
the newest bulletin. Rows only for quantities in the config (I11d: the 3y/5y
quantities are optional).
"""

from __future__ import annotations

import bisect
import calendar
import functools
import io
import math
import os
import stat
import sys
import time
import zipfile
from array import array
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx

from rmprep.contracts import TR_TZ, DataPoint, EntityInfo
from rmprep.ingest.config import BIST_HOST, BistBulletinSource, Config
from rmprep.ingest.snapshot import PayloadRef, Snapshot, SnapshotWriter, SourceRecord, raw_ref

REQUIRED_COLUMNS = ("TARIH", "ISLEM KODU", "BULTEN ADI", "PAZAR", "ENSTRUMAN GRUBU",
                    "BIST 100 ENDEKS", "ACILIS FIYATI", "EN DUSUK FIYAT", "EN YUKSEK FIYAT",
                    "KAPANIS FIYATI", "TOPLAM ISLEM HACMI")
TURNOVER_DAYS = 63                # about 3 months of bulletins
MIN_WEEKS = 26                    # fewer weekly returns -> no volatility row
RETURN_MONTHS = {"stock_return_1m": 1, "stock_return_3m": 3, "stock_return_6m": 6,
                 "stock_return_1y": 12, "stock_return_3y": 36, "stock_return_5y": 60}
VOLATILITY_MONTHS = {"stock_volatility_1y": 12, "stock_volatility_5y": 60}
MISSING_SUFFIX = ".missing"       # a weekday without a bulletin
BAD_SUFFIX = ".bad"               # an old bulletin that cannot be read (I11d)


class BulletinError(ValueError):
    """A bulletin file does not have the expected content."""


@dataclass(frozen=True)
class Share:
    code: str                     # without ".E", e.g. "THYAO"
    name: str                     # BULTEN ADI
    market: str                   # PAZAR, e.g. "Z"
    bist100: bool
    close: float
    open_price: float             # ACILIS FIYATI (0 when the share did not open)
    low: float                    # EN DUSUK FIYAT (0 when not given)
    high: float                   # EN YUKSEK FIYAT (0 when not given)
    turnover: float               # TOPLAM ISLEM HACMI, TRY


# --- reading a bulletin --------------------------------------------------------------------

def _column(name: str) -> str:
    return " ".join(name.split()).upper()


def _number(text: str, line: int, column: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    try:
        x = float(text)
    except ValueError:
        raise BulletinError(f"line {line}: bad {column} {text!r}") from None
    if not math.isfinite(x):
        raise BulletinError(f"line {line}: bad {column} {text!r}")
    return x


def _check_dates(body: str, day: date) -> None:
    """Every non-empty row starts with "<day>;" (TARIH is the first column).
    Counted with C-level string methods; the rows are walked only on error."""
    prefix = f"{day.isoformat()};"
    lines = body.split("\n")
    rows = len(lines) - lines.count("")
    if body.count("\n" + prefix) + body.startswith(prefix) != rows:
        bad = next(line for line in lines if line and not line.startswith(prefix))
        raise BulletinError(f"bulletin date {bad.split(';', 1)[0].strip()}, expected {day}")


def _share_rows(body: str) -> Iterable[tuple[int, str]]:
    """(line number in the file, row) of the rows with ";EQT;", in order; found
    with str.find, so Python does not walk the other 10,000 rows."""
    n, pos, i = 3, 0, body.find(";EQT;")
    while i >= 0:
        start = body.rfind("\n", 0, i) + 1
        end = body.find("\n", i)
        end = len(body) if end < 0 else end
        n += body.count("\n", pos, start)
        pos = start
        yield n, body[start:end]
        i = body.find(";EQT;", end)


def read_bulletin(data: bytes, day: date | None = None) -> list[Share]:
    """The shares of one bulletin ZIP, in file order. With `day`, every row
    must have TARIH = day. Raises BulletinError."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise BulletinError(f"expected one CSV in the ZIP, found {len(names)}")
        raw = z.read(names[0])
    except (zipfile.BadZipFile, EOFError):
        raise BulletinError("not a ZIP") from None
    try:
        text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError:
        raise BulletinError("the CSV is not UTF-8") from None
    head = text.split("\n", 2)
    if len(head) < 2:
        raise BulletinError("the CSV has no header lines")
    header = [_column(c) for c in head[0].split(";")]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise BulletinError(f"missing column(s) {missing}")
    col = {c: header.index(c) for c in REQUIRED_COLUMNS}
    body = head[2] if len(head) > 2 else ""

    shares: list[Share] = []
    seen: set[str] = set()
    if day is not None and col["TARIH"] == 0:
        # Fast path (about 11,000 rows a day, 630 of them shares): check the
        # dates and find the share rows with C-level string methods.
        _check_dates(body, day)
        rows: Iterable[tuple[int, str]] = _share_rows(body)
    else:
        rows = ((n, line) for n, line in enumerate(body.split("\n"), start=3) if line.strip())
    for n, line in rows:
        f = line.split(";")
        if len(f) < len(header):
            raise BulletinError(f"line {n}: {len(f)} fields, expected {len(header)}")
        if day is not None and f[col["TARIH"]].strip() != day.isoformat():
            raise BulletinError(f"bulletin date {f[col['TARIH']].strip()}, expected {day}")
        code = f[col["ISLEM KODU"]].strip()
        if f[col["ENSTRUMAN GRUBU"]].strip() != "EQT" or not code.endswith(".E"):
            continue
        close = _number(f[col["KAPANIS FIYATI"]], n, "KAPANIS FIYATI")
        if close is None or close <= 0:
            continue
        if code in seen:
            raise BulletinError(f"line {n}: share {code} twice")
        seen.add(code)
        def price(column: str) -> float:          # empty, 0 or negative -> 0.0
            x = _number(f[col[column]], n, column)
            return x if x and x > 0 else 0.0

        shares.append(Share(
            code=code[:-2], name=f[col["BULTEN ADI"]].strip(), market=f[col["PAZAR"]].strip(),
            bist100=f[col["BIST 100 ENDEKS"]].strip() == "1", close=close,
            open_price=price("ACILIS FIYATI"), low=price("EN DUSUK FIYAT"),
            high=price("EN YUKSEK FIYAT"),
            turnover=_number(f[col["TOPLAM ISLEM HACMI"]], n, "TOPLAM ISLEM HACMI") or 0.0))
    return shares


# --- fetch -----------------------------------------------------------------------------------

def check_url_allowed(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != BIST_HOST or not parts.path.startswith("/data/"):
        raise ValueError(f"{url!r} is not a bulletin file URL on {BIST_HOST}/data/")


def _is_html(body: bytes) -> bool:
    return body.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html"))


def _write_read_only(path, data: bytes) -> None:
    part = path.with_name(path.name + ".part")
    part.write_bytes(data)
    os.chmod(part, stat.S_IREAD)
    os.replace(part, path)


def fetch(
    src: BistBulletinSource,
    writer: SnapshotWriter,
    *,
    client: httpx.Client,
    today: date,
    now: Callable[[], datetime] = lambda: datetime.now(TR_TZ),
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> SourceRecord:
    """Fetch the bulletins of the last `history_days` days that are not in the
    cache. A failed request or a bad file of the last `recheck_days` days fails
    the source (the good files fetched before stay in the cache). A bad OLDER
    file (another format, I11d) does not: it gets a `.bad` marker, and the
    history starts after the newest such file, so it has no gap."""
    cache = writer.cache_dir(src.name)
    cache.mkdir(parents=True, exist_ok=True)
    start = today - timedelta(days=src.history_days)
    recheck_from = today - timedelta(days=src.recheck_days)
    counts = {"fetched": 0, "from_cache": 0, "not_published": 0, "unreadable": 0}
    request: dict[str, Any] = {
        "method": "GET", "url": src.url, "user_agent": src.user_agent,
        "from": start.isoformat(), "to": today.isoformat(),
        "min_interval_s": src.min_interval_s, "files": counts,
        "robots": "robots.txt (2026-10-14) allows /; only the bulletin files are requested"}

    def failed(error: str) -> SourceRecord:
        return SourceRecord(status="failed", on_failure=src.on_failure, request=request,
                            error=error)

    used: list[tuple[date, str]] = []
    unreadable: tuple[date, str, str] | None = None      # the newest: (day, file, reason)
    last_start: float | None = None
    day = start
    while day <= today:
        current, day = day, day + timedelta(days=1)
        if current.weekday() >= 5:
            continue
        url = src.day_url(current)
        name = url.rsplit("/", 1)[-1]
        stem = name.rsplit(".", 1)[0]
        file, marker, bad = cache / name, cache / (stem + MISSING_SUFFIX), cache / (stem + BAD_SUFFIX)
        if file.is_file():
            used.append((current, name))
            counts["from_cache"] += 1
            continue
        if bad.is_file():
            counts["unreadable"] += 1
            unreadable = (current, name, bad.read_text(encoding="utf-8").strip())
            continue
        if marker.is_file() and current < recheck_from:
            counts["not_published"] += 1
            continue

        check_url_allowed(url)
        if last_start is not None:
            wait = last_start + src.min_interval_s - monotonic()
            if wait > 0:
                sleep(wait)
        last_start = monotonic()
        try:
            resp = client.get(url, headers={"User-Agent": src.user_agent},
                              timeout=src.timeout_seconds, follow_redirects=False)
        except httpx.HTTPError as e:
            return failed(f"{name}: {type(e).__name__}: {e}")
        if resp.status_code == 404 or (resp.status_code == 200 and _is_html(resp.content)):
            marker.write_text(f"{now().isoformat()}: HTTP {resp.status_code}, no bulletin\n",
                              encoding="utf-8")
            counts["not_published"] += 1
            continue
        if resp.status_code != 200:
            return failed(f"{name}: HTTP {resp.status_code}")
        problem = None
        try:
            shares = read_bulletin(resp.content, current)
        except BulletinError as e:
            problem = str(e)
        else:
            if len(shares) < src.min_shares:
                problem = (f"only {len(shares)} shares with a closing price "
                           f"(minimum {src.min_shares})")
        if problem is not None:
            if current >= recheck_from:
                return failed(f"{name}: {problem}")
            bad.write_text(problem + "\n", encoding="utf-8")
            counts["unreadable"] += 1
            unreadable = (current, name, problem)
            continue
        _write_read_only(file, resp.content)
        marker.unlink(missing_ok=True)
        used.append((current, name))
        counts["fetched"] += 1

    if unreadable is not None:
        request["unreadable_newest"] = {"file": unreadable[1], "reason": unreadable[2]}
        used = [(d, name) for d, name in used if d > unreadable[0]]
    if not used:
        return failed(f"no bulletin from {start} to {today}")
    request["history_from"] = used[0][0].isoformat()
    refs = tuple(writer.add_cache_payload(src.name, name, meta={"date": d.isoformat()})
                 for d, name in used)
    return SourceRecord(status="ok", on_failure=src.on_failure, fetched_at=now(),
                        request=request, payloads=refs)


# --- calculations (pure) ---------------------------------------------------------------------

def base_price(open_price: float, low: float, high: float, close: float,
               limit_pct: float) -> float:
    """The base price of a corporate-action day (I11c). The day's prices must
    stay within ± the daily price limit P of the base b: high <= b(1 + P) and
    low >= b(1 - P), so b is in [high / (1 + P), low / (1 - P)]. The base is
    the open clamped to that interval. With an empty interval, or no low or
    high, the open (the close when the open is 0). [VARSAYIM] The open stands
    for the base when it is allowed."""
    fallback = open_price if open_price > 0 else close
    if low <= 0 or high <= 0:
        return fallback
    p = limit_pct / 100
    lo, hi = high / (1 + p), low / (1 - p)
    if lo > hi:
        return fallback
    return min(max(fallback, lo), hi)


def adjust(observations: list[tuple[date, float, float, float, float]],
           jump_pct: float, limit_pct: float) -> tuple[list[tuple[date, float]], int]:
    """Adjusted closes of one share from (day, close, open, low, high), oldest
    first (I11b, I11c).

    The bulletins publish the previous close NOT adjusted and no reference
    price, so a corporate action (split, bonus shares, reverse split) is found
    by its jump: close / close of the share's previous row outside
    [1 - jump_pct %, 1 + jump_pct %] (the daily price limit is ±10 %). Then all
    earlier closes are multiplied by base / previous close (`base_price`).
    Cash dividends stay below the limit and are not adjusted.
    Returns (day, adjusted close) and the number of jumps."""
    limit = jump_pct / 100
    ratios: list[float | None] = [None] * len(observations)
    for i in range(1, len(observations)):
        _, close, open_price, low, high = observations[i]
        last_close = observations[i - 1][1]
        if abs(close / last_close - 1) > limit + 1e-12:
            ratios[i] = base_price(open_price, low, high, close, limit_pct) / last_close
    factor, out = 1.0, []
    for i in range(len(observations) - 1, -1, -1):
        out.append((observations[i][0], observations[i][1] * factor))
        if ratios[i] is not None:
            factor *= ratios[i]
    return out[::-1], sum(r is not None for r in ratios)


def months_before(d: date, months: int) -> date:
    """The same day `months` months earlier; the day is clamped to the month."""
    y, m = divmod(d.month - 1 - months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _day_key(item: tuple[date, float]) -> date:
    return item[0]


def period_return(series: list[tuple[date, float]], months: int) -> float | None:
    """% change from the last close on or before the date `months` months
    before the newest day to the newest close; None if the history is shorter."""
    newest_day, newest = series[-1]
    i = bisect.bisect_right(series, months_before(newest_day, months), key=_day_key)
    if i == 0 or series[i - 1][1] <= 0:
        return None
    return (newest / series[i - 1][1] - 1) * 100


@functools.lru_cache(maxsize=4096)
def _iso_week(d: date) -> tuple[int, int]:
    return d.isocalendar()[:2]


def spk_volatility_weeks(series: list[tuple[date, float]],
                         months: int) -> tuple[float | None, int]:
    """Annual volatility in % by the SPK method over the days after the date
    `months` months before the newest day (SPK guide: 5 years), and the number
    of weekly returns T. Weekly return = close of the week's last trading day
    / close of its first trading day - 1 (SPK guide 9.3.2.1, footnote 22),
    sigma = sqrt(52 / (T - 1) * sum((r - mean)^2)). A week with one trading day
    has no return. The value is None with fewer than 26 weekly returns."""
    i = bisect.bisect_right(series, months_before(series[-1][0], months), key=_day_key)
    weeks: dict[tuple[int, int], list[float]] = {}
    for d, c in series[i:]:
        w = weeks.setdefault(_iso_week(d), [c, c, 0])
        w[1], w[2] = c, w[2] + 1              # first close, last close, trading days
    returns = [last / first - 1 for first, last, n in weeks.values() if n >= 2 and first > 0]
    if len(returns) < MIN_WEEKS:
        return None, len(returns)
    mean = sum(returns) / len(returns)
    var = 52 / (len(returns) - 1) * sum((r - mean) ** 2 for r in returns)
    return 100 * math.sqrt(var), len(returns)


def spk_volatility(series: list[tuple[date, float]], months: int = 12) -> float | None:
    return spk_volatility_weeks(series, months)[0]


# --- parse -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Day:
    """The shares of one bulletin in a compact form for the memo (I11d: about
    1,250 files and 700,000 share rows): interned texts and float arrays."""
    codes: tuple[str, ...]
    names: tuple[str, ...]
    markets: tuple[str, ...]
    bist100: bytes
    close: array
    open: array
    low: array
    high: array
    turnover: array

    @classmethod
    def of(cls, shares: list[Share]) -> _Day:
        return cls(
            codes=tuple(sys.intern(s.code) for s in shares),
            names=tuple(sys.intern(s.name) for s in shares),
            markets=tuple(sys.intern(s.market) for s in shares),
            bist100=bytes(s.bist100 for s in shares),
            close=array("d", (s.close for s in shares)),
            open=array("d", (s.open_price for s in shares)),
            low=array("d", (s.low for s in shares)),
            high=array("d", (s.high for s in shares)),
            turnover=array("d", (s.turnover for s in shares)))


_MEMO: dict[tuple[str, date], _Day] = {}     # (SHA-256, day) -> shares of that file
_MEMO_MAX = 4000


def _day(snap: Snapshot, ref: PayloadRef, day: date) -> _Day:
    """The shares of one payload; kept per file hash (the files are immutable),
    so a later build_evidence does not decode the ZIPs again."""
    data = snap.read_payload(ref.path)           # verifies the hash
    key = (ref.sha256, day)
    if key not in _MEMO:
        if len(_MEMO) >= _MEMO_MAX:
            del _MEMO[next(iter(_MEMO))]
        _MEMO[key] = _Day.of(read_bulletin(data, day))
    return _MEMO[key]


def _files(src: BistBulletinSource,
           snap: Snapshot) -> tuple[SourceRecord, list[tuple[date, PayloadRef]]]:
    rec = snap.sources.get(src.name)
    if rec is None or rec.status != "ok":
        raise ValueError(f"{snap.snapshot_id}: source {src.name!r} has no ok record")
    return rec, sorted((date.fromisoformat(p.meta["date"]), p) for p in rec.payloads)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


_PARSED: dict[tuple, list[DataPoint]] = {}   # parse results (parse is pure)
_PARSED_MAX = 8


def parse(cfg: Config, src: BistBulletinSource, snap: Snapshot, *,
          out_snapshot_id: str | None = None, out_date: date | None = None) -> list[DataPoint]:
    """`out_date` is ignored: as_of is the date of the newest bulletin. The
    quantities of I11d (3y/5y returns, 5y volatility) give rows only when they
    are in `quantities`. The result is kept per snapshot, files and config, so
    a repeated build_evidence only verifies the file hashes."""
    rec, refs = _files(src, snap)
    key = (str(snap.path), snap.snapshot_id, out_snapshot_id, rec.fetched_at, src,
           tuple(ref.sha256 for _, ref in refs),
           tuple((q, cfg.quantities[q].unit) for q in _ALL_QUANTITIES if q in cfg.quantities))
    if key in _PARSED:
        for _, ref in refs:
            snap.read_payload(ref.path)              # verifies the hashes, as without the memo
        return list(_PARSED[key])
    points = _parse(cfg, src, snap, rec, refs, out_snapshot_id)
    if len(_PARSED) >= _PARSED_MAX:
        del _PARSED[next(iter(_PARSED))]
    _PARSED[key] = points
    return list(points)


_ALL_QUANTITIES = ("stock_close", *RETURN_MONTHS, *VOLATILITY_MONTHS, "stock_turnover_3m",
                   "stock_bist100")


def _parse(cfg: Config, src: BistBulletinSource, snap: Snapshot, rec: SourceRecord,
           refs: list[tuple[date, PayloadRef]], out_snapshot_id: str | None) -> list[DataPoint]:
    days = [(d, _day(snap, ref, d)) for d, ref in refs]
    sid = out_snapshot_id or snap.snapshot_id
    newest_day, newest = days[-1]
    newest_ref = refs[-1][1]

    # Per share: days and close/open/low/high columns; turnover of the last 63 files.
    columns: dict[str, tuple[list[date], array, array, array, array]] = {}
    turnover: dict[str, list[float]] = {}
    recent_from = days[-TURNOVER_DAYS:][0][0]
    for d, day in days:
        for i, code in enumerate(day.codes):
            col = columns.get(code)
            if col is None:
                col = columns[code] = ([], array("d"), array("d"), array("d"), array("d"))
            col[0].append(d)
            col[1].append(day.close[i])
            col[2].append(day.open[i])
            col[3].append(day.low[i])
            col[4].append(day.high[i])
            if d >= recent_from:
                t = turnover.setdefault(code, [0.0, 0])
                t[0] += day.turnover[i]
                t[1] += 1
    all_files = f"files={days[0][0]}..{newest_day}"
    recent_files = f"files={recent_from}..{newest_day}"
    history_note = ""
    if rec.request and rec.request.get("unreadable_newest"):
        cut = rec.request["unreadable_newest"]
        history_note = f"; history from {days[0][0]} ({cut['file']} unreadable: {cut['reason']})"

    points = []
    for i in sorted(range(len(newest.codes)), key=lambda i: newest.codes[i]):
        code, name = newest.codes[i], newest.names[i]

        def point(quantity: str, value: float, locator: str, note: str) -> None:
            if quantity in cfg.quantities:
                points.append(DataPoint.create(
                    quantity=quantity, entity=code, value=value,
                    unit=cfg.quantities[quantity].unit, as_of=newest_day, source=src.name,
                    source_url=src.source_url, fetched_at=rec.fetched_at, snapshot_id=sid,
                    raw_ref=raw_ref(snap.snapshot_id, newest_ref.path, locator), note=note))

        adjusted, jumps = adjust(list(zip(*columns[code])), src.adjust_jump_pct,
                                 src.price_limit_pct)
        adj_note = (f"{name}; adjusted closes ({_plural(jumps, 'jump')} beyond "
                    f"±{src.adjust_jump_pct:g} %); dividends not adjusted{history_note}")
        point("stock_close", newest.close[i], code, name)
        for quantity, months in RETURN_MONTHS.items():
            r = period_return(adjusted, months)
            if r is not None:
                point(quantity, r, f"{code};{all_files}", adj_note)
        for quantity, months in VOLATILITY_MONTHS.items():
            vol, weeks = spk_volatility_weeks(adjusted, months)
            if vol is not None:
                point(quantity, vol, f"{code};{all_files}",
                      f"{adj_note}; SPK weekly method, {weeks} weeks")
        total, n = turnover[code]
        point("stock_turnover_3m", total / n, f"{code};{recent_files}",
              f"{name}; mean daily traded value over {_plural(n, 'trading day')}")
        point("stock_bist100", float(newest.bist100[i]), code, name)
    return points


def entities(src: BistBulletinSource, snap: Snapshot) -> dict[str, EntityInfo]:
    """Share code -> name (BULTEN ADI) and "BIST pay · <PAZAR>", from the newest
    bulletin."""
    _, refs = _files(src, snap)
    day, ref = refs[-1]
    newest = _day(snap, ref, day)
    return {code: EntityInfo(name, f"BIST pay · {market}", src.name)
            for code, name, market in sorted(zip(newest.codes, newest.names, newest.markets))}
