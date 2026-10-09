"""TEFAS web adapter: fund returns and risk values from one allowed HTML page.

Rules (organizers' rule 8 + tefas.gov.tr/robots.txt, 2026-10-09):
- one GET per ingest of `src.url` (default /tr/fon-getirileri), no redirects;
- never any request to /api/ or other robots-disallowed paths (config.py
  rejects such URLs; `check_url_allowed` checks again before the request);
- the raw HTML is stored in the snapshot and parsed from there.

The page is a Next.js page: the data sits in `self.__next_f.push([1, "..."])`
script chunks. The chunks are JSON string literals; joined, they contain one
JSON object per fund: {"fonKodu": "AAL", "fonUnvan": ..., "getiri1a": 3.0, ...,
"riskDegeri": "1"}. The page shows no as-of date; the site says the data is
from the previous day, so as_of = previous business day before the snapshot
date (weekends skipped; Turkish public holidays are not known to the tool).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx

from rmprep.config import TEFAS_DISALLOWED_PREFIXES, Config, TefasWebSource
from rmprep.contracts import TR_TZ, DataPoint, Flag
from rmprep.snapshot import Snapshot, SnapshotWriter, SourceRecord, raw_ref

PAYLOAD_NAME = "fon-getirileri.html"
_PUSH_RE = re.compile(r"self\.__next_f\.push\((\[.*?\])\)</script>", re.S)
_FUND_START_RE = re.compile(r'\{"fonKodu":')
_FUND_CODE_RE = re.compile(r"^[A-Z0-9]{2,6}$")


class TefasWebParseError(ValueError):
    """The page does not have the expected structure."""


def check_url_allowed(url: str) -> None:
    path = urlsplit(url).path
    if path.startswith(TEFAS_DISALLOWED_PREFIXES):
        raise ValueError(f"{path!r} is disallowed by tefas.gov.tr/robots.txt")


def previous_business_day(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:          # Saturday, Sunday
        d -= timedelta(days=1)
    return d


def extract_funds(html: str) -> list[dict[str, Any]]:
    """Fund objects from the page, one per fund code, sorted by code. The row of
    column titles (string values in the return fields) is left out."""
    chunks = []
    for raw in _PUSH_RE.findall(html):
        try:
            arr = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if len(arr) > 1 and isinstance(arr[1], str):
            chunks.append(arr[1])
    text = "".join(chunks)

    decoder = json.JSONDecoder()
    funds: dict[str, dict[str, Any]] = {}
    for m in _FUND_START_RE.finditer(text):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        code = obj.get("fonKodu")
        if (isinstance(code, str) and _FUND_CODE_RE.match(code)
                and "getiri1a" in obj and not isinstance(obj["getiri1a"], str)):
            funds.setdefault(code, obj)
    return [funds[c] for c in sorted(funds)]


def _value(v: Any) -> float | None:
    """Number from a page field; None for null, "-", or other text."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    elif isinstance(v, str):
        try:
            x = float(v.strip().replace(",", "."))
        except ValueError:
            return None
    else:
        return None
    return x if math.isfinite(x) else None


def fetch(
    src: TefasWebSource,
    writer: SnapshotWriter,
    *,
    client: httpx.Client,
    now: Callable[[], datetime] = lambda: datetime.now(TR_TZ),
) -> SourceRecord:
    request = {"method": "GET", "url": src.url, "user_agent": src.user_agent,
               "robots": "robots.txt disallows /api/; only this HTML page is requested"}

    def failed(error: str) -> SourceRecord:
        return SourceRecord(status="failed", on_failure=src.on_failure,
                            request=request, error=error)

    check_url_allowed(src.url)
    try:
        resp = client.get(src.url, headers={"User-Agent": src.user_agent},
                          timeout=src.timeout_seconds, follow_redirects=False)
    except httpx.HTTPError as e:
        return failed(f"{type(e).__name__}: {e}")
    if resp.status_code != 200:
        return failed(f"HTTP {resp.status_code}")
    try:
        funds = extract_funds(resp.content.decode("utf-8"))
    except UnicodeDecodeError:
        return failed("page is not UTF-8")
    if len(funds) < src.min_funds:
        return failed(f"only {len(funds)} funds found (minimum {src.min_funds}); "
                      "the page structure may have changed")
    ref = writer.add_payload(src.name, PAYLOAD_NAME, resp.content,
                             meta={"url": src.url, "funds": len(funds)})
    return SourceRecord(status="ok", on_failure=src.on_failure, fetched_at=now(),
                        request=request, payloads=(ref,))


def parse(cfg: Config, src: TefasWebSource, snap: Snapshot, *,
          out_snapshot_id: str | None = None, out_date: date | None = None) -> list[DataPoint]:
    """`out_date` is ignored: as_of always comes from the snapshot that holds the
    page, also for fallback rows."""
    rec = snap.sources.get(src.name)
    if rec is None or rec.status != "ok":
        raise ValueError(f"{snap.snapshot_id}: source {src.name!r} has no ok record")
    sid = out_snapshot_id or snap.snapshot_id
    as_of = previous_business_day(snap.created_at.date())
    flags = [Flag.NEEDS_CHECK] if src.flag_needs_check else []
    [payload] = rec.payloads

    points = []
    for fund in extract_funds(snap.read_payload(payload.path).decode("utf-8")):
        code = fund["fonKodu"]
        note = (f"{fund.get('fonUnvan') or ''}; {fund.get('fonTurAciklama') or ''}; "
                "as_of assumed = previous business day")
        for field, quantity in src.value_fields.items():
            value = _value(fund.get(field))
            if value is None:
                continue
            points.append(DataPoint.create(
                quantity=quantity, entity=code, value=value,
                unit=cfg.quantities[quantity].unit, as_of=as_of, source=src.name,
                source_url=src.url, fetched_at=rec.fetched_at, snapshot_id=sid,
                raw_ref=raw_ref(snap.snapshot_id, payload.path, f"fonKodu={code};field={field}"),
                flags=flags, note=note))
    return points
