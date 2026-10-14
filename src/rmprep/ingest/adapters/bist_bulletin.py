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
columns, TARIH = the day of the URL, at least `min_shares` shares); a bad file
fails the source and is not cached.

Parse (pure, from the files in the manifest): adjusted closes (`adjust`),
returns over 1/3/6/12 months (`period_return`), the SPK weekly volatility
(`spk_volatility`), the mean daily traded value of the last 63 bulletins, the
BIST 100 membership. as_of = the date of the newest bulletin.
"""

from __future__ import annotations

import calendar
import io
import math
import os
import stat
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx

from rmprep.contracts import TR_TZ, DataPoint, EntityInfo
from rmprep.ingest.config import BIST_HOST, BistBulletinSource, Config
from rmprep.ingest.snapshot import PayloadRef, Snapshot, SnapshotWriter, SourceRecord, raw_ref

REQUIRED_COLUMNS = ("TARIH", "ISLEM KODU", "BULTEN ADI", "PAZAR", "ENSTRUMAN GRUBU",
                    "BIST 100 ENDEKS", "ONCEKI KAPANIS FIYATI", "KAPANIS FIYATI",
                    "TOPLAM ISLEM HACMI")
ADJUST_TOLERANCE = 0.001          # previous close differs by more -> corporate action
TURNOVER_DAYS = 63                # about 3 months of bulletins
MIN_WEEKS = 26                    # fewer weekly returns -> no volatility row
RETURN_MONTHS = {"stock_return_1m": 1, "stock_return_3m": 3, "stock_return_6m": 6,
                 "stock_return_1y": 12}
MISSING_SUFFIX = ".missing"


class BulletinError(ValueError):
    """A bulletin file does not have the expected content."""


@dataclass(frozen=True)
class Share:
    code: str                     # without ".E", e.g. "THYAO"
    name: str                     # BULTEN ADI
    market: str                   # PAZAR, e.g. "Z"
    bist100: bool
    close: float
    prev_close: float | None      # ONCEKI KAPANIS FIYATI as published (None if empty or 0)
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
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        raise BulletinError("the CSV is not UTF-8") from None
    if len(lines) < 2:
        raise BulletinError("the CSV has no header lines")
    header = [_column(c) for c in lines[0].split(";")]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise BulletinError(f"missing column(s) {missing}")
    col = {c: header.index(c) for c in REQUIRED_COLUMNS}

    shares: list[Share] = []
    seen: set[str] = set()
    # Fast path (about 11,000 rows a day, 630 of them shares): when TARIH is the
    # first column, check it without splitting, and split only the share rows.
    day_prefix = f"{day.isoformat()};" if day is not None and col["TARIH"] == 0 else None
    for n, line in enumerate(lines[2:], start=3):
        if not line.strip():
            continue
        if day_prefix is not None:
            if not line.startswith(day_prefix):
                raise BulletinError(f"bulletin date {line.split(';', 1)[0].strip()}, "
                                    f"expected {day}")
            if ";EQT;" not in line:
                continue
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
        prev = _number(f[col["ONCEKI KAPANIS FIYATI"]], n, "ONCEKI KAPANIS FIYATI")
        shares.append(Share(
            code=code[:-2], name=f[col["BULTEN ADI"]].strip(), market=f[col["PAZAR"]].strip(),
            bist100=f[col["BIST 100 ENDEKS"]].strip() == "1", close=close,
            prev_close=prev if prev else None,
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
    cache. All-or-nothing for the record: one failed or bad file fails the
    source (the good files fetched before stay in the cache)."""
    cache = writer.cache_dir(src.name)
    cache.mkdir(parents=True, exist_ok=True)
    start = today - timedelta(days=src.history_days)
    recheck_from = today - timedelta(days=src.recheck_days)
    counts = {"fetched": 0, "from_cache": 0, "not_published": 0}
    request: dict[str, Any] = {
        "method": "GET", "url": src.url, "user_agent": src.user_agent,
        "from": start.isoformat(), "to": today.isoformat(),
        "min_interval_s": src.min_interval_s, "files": counts,
        "robots": "robots.txt (2026-10-14) allows /; only the bulletin files are requested"}

    def failed(error: str) -> SourceRecord:
        return SourceRecord(status="failed", on_failure=src.on_failure, request=request,
                            error=error)

    used: list[tuple[date, str]] = []
    last_start: float | None = None
    day = start
    while day <= today:
        current, day = day, day + timedelta(days=1)
        if current.weekday() >= 5:
            continue
        url = src.day_url(current)
        name = url.rsplit("/", 1)[-1]
        file, marker = cache / name, cache / (name.rsplit(".", 1)[0] + MISSING_SUFFIX)
        if file.is_file():
            used.append((current, name))
            counts["from_cache"] += 1
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
        try:
            shares = read_bulletin(resp.content, current)
        except BulletinError as e:
            return failed(f"{name}: {e}")
        if len(shares) < src.min_shares:
            return failed(f"{name}: only {len(shares)} shares with a closing price "
                          f"(minimum {src.min_shares})")
        _write_read_only(file, resp.content)
        marker.unlink(missing_ok=True)
        used.append((current, name))
        counts["fetched"] += 1

    if not used:
        return failed(f"no bulletin from {start} to {today}")
    refs = tuple(writer.add_cache_payload(src.name, name, meta={"date": d.isoformat()})
                 for d, name in used)
    return SourceRecord(status="ok", on_failure=src.on_failure, fetched_at=now(),
                        request=request, payloads=refs)


# --- calculations (pure) ---------------------------------------------------------------------

def adjust(observations: list[tuple[date, float, float | None]]) -> tuple[list[tuple[date, float]], int]:
    """Adjusted closes of one share from (day, close, published previous close),
    oldest first. When a day's published previous close differs from the
    close of the share's previous row by more than 0.1 % (split, bonus
    shares, dividend), all earlier closes are multiplied by their ratio.
    Returns (day, adjusted close) and the number of adjustments."""
    ratios = [None] * len(observations)
    for i in range(1, len(observations)):
        prev_pub, last_close = observations[i][2], observations[i - 1][1]
        if prev_pub and last_close and abs(prev_pub / last_close - 1) > ADJUST_TOLERANCE + 1e-12:
            ratios[i] = prev_pub / last_close
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


def period_return(series: list[tuple[date, float]], months: int) -> float | None:
    """% change from the last close on or before the date `months` months
    before the newest day to the newest close; None if the history is shorter."""
    newest_day, newest = series[-1]
    target = months_before(newest_day, months)
    base = [c for d, c in series if d <= target]
    if not base or base[-1] <= 0:
        return None
    return (newest / base[-1] - 1) * 100


def spk_volatility(series: list[tuple[date, float]]) -> float | None:
    """Annual volatility in % by the SPK method: weekly return = close of the
    week's last trading day / close of its first trading day - 1 (SPK guide
    9.3.2.1, footnote 22), sigma = sqrt(52 / (T - 1) * sum((r - mean)^2)) over the
    T weeks of the last year. A week with one trading day has no return.
    None with fewer than 26 weekly returns."""
    start = months_before(series[-1][0], 12)
    weeks: dict[tuple[int, int], list[tuple[date, float]]] = {}
    for d, c in series:
        if d > start:
            weeks.setdefault(d.isocalendar()[:2], []).append((d, c))
    returns = [w[-1][1] / w[0][1] - 1 for w in (sorted(v) for v in weeks.values())
               if len(w) >= 2 and w[0][1] > 0]
    if len(returns) < MIN_WEEKS:
        return None
    mean = sum(returns) / len(returns)
    var = 52 / (len(returns) - 1) * sum((r - mean) ** 2 for r in returns)
    return 100 * math.sqrt(var)


# --- parse -----------------------------------------------------------------------------------

_MEMO: dict[tuple[str, date], list[Share]] = {}     # (SHA-256, day) -> shares
_MEMO_MAX = 2000


def _shares(snap: Snapshot, ref: PayloadRef, day: date) -> list[Share]:
    """read_bulletin of one payload; the result is kept per file hash (the
    files are immutable), so a build_evidence does not decode 280 ZIPs again."""
    data = snap.read_payload(ref.path)           # verifies the hash
    key = (ref.sha256, day)
    if key not in _MEMO:
        if len(_MEMO) >= _MEMO_MAX:
            del _MEMO[next(iter(_MEMO))]
        _MEMO[key] = read_bulletin(data, day)
    return _MEMO[key]


def _files(src: BistBulletinSource,
           snap: Snapshot) -> tuple[SourceRecord, list[tuple[date, PayloadRef]]]:
    rec = snap.sources.get(src.name)
    if rec is None or rec.status != "ok":
        raise ValueError(f"{snap.snapshot_id}: source {src.name!r} has no ok record")
    return rec, sorted((date.fromisoformat(p.meta["date"]), p) for p in rec.payloads)


def _read_all(src: BistBulletinSource,
              snap: Snapshot) -> tuple[SourceRecord, list[tuple[date, PayloadRef, list[Share]]]]:
    rec, files = _files(src, snap)
    return rec, [(d, p, _shares(snap, p, d)) for d, p in files]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def parse(cfg: Config, src: BistBulletinSource, snap: Snapshot, *,
          out_snapshot_id: str | None = None, out_date: date | None = None) -> list[DataPoint]:
    """`out_date` is ignored: as_of is the date of the newest bulletin."""
    rec, files = _read_all(src, snap)
    sid = out_snapshot_id or snap.snapshot_id
    newest_day, newest_ref, newest_shares = files[-1]
    history: dict[str, list[tuple[date, float, float | None]]] = {}
    turnover: dict[str, list[float]] = {}
    recent = {d for d, _, _ in files[-TURNOVER_DAYS:]}
    for d, _, shares in files:
        for s in shares:
            history.setdefault(s.code, []).append((d, s.close, s.prev_close))
            if d in recent:
                turnover.setdefault(s.code, []).append(s.turnover)
    all_files = f"files={files[0][0]}..{newest_day}"
    recent_files = f"files={files[-TURNOVER_DAYS:][0][0]}..{newest_day}"

    points = []
    for s in sorted(newest_shares, key=lambda s: s.code):
        def point(quantity: str, value: float, locator: str, note: str) -> DataPoint:
            return DataPoint.create(
                quantity=quantity, entity=s.code, value=value,
                unit=cfg.quantities[quantity].unit, as_of=newest_day, source=src.name,
                source_url=src.source_url, fetched_at=rec.fetched_at, snapshot_id=sid,
                raw_ref=raw_ref(snap.snapshot_id, newest_ref.path, locator), note=note)

        adjusted, n_adj = adjust(history[s.code])
        adj_note = f"{s.name}; adjusted closes, {_plural(n_adj, 'price adjustment')}"
        points.append(point("stock_close", s.close, s.code, s.name))
        for quantity, months in RETURN_MONTHS.items():
            r = period_return(adjusted, months)
            if r is not None:
                points.append(point(quantity, r, f"{s.code};{all_files}", adj_note))
        vol = spk_volatility(adjusted)
        if vol is not None:
            points.append(point("stock_volatility_1y", vol, f"{s.code};{all_files}",
                                f"{adj_note}; SPK weekly method"))
        values = turnover[s.code]
        points.append(point("stock_turnover_3m", sum(values) / len(values),
                            f"{s.code};{recent_files}",
                            f"{s.name}; mean daily traded value over "
                            f"{_plural(len(values), 'trading day')}"))
        points.append(point("stock_bist100", 1.0 if s.bist100 else 0.0, s.code, s.name))
    return points


def entities(src: BistBulletinSource, snap: Snapshot) -> dict[str, EntityInfo]:
    """Share code -> name (BULTEN ADI) and "BIST pay · <PAZAR>", from the newest
    bulletin."""
    _, files = _files(src, snap)
    day, newest = files[-1]
    return {s.code: EntityInfo(s.name, f"BIST pay · {s.market}", src.name)
            for s in sorted(_shares(snap, newest, day), key=lambda s: s.code)}
