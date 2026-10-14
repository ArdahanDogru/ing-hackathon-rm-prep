"""TEFAS fund detail adapter: price, size, investors, risk, valör and fees per fund.

Rules (organizers' rule 8 + tefas.gov.tr/robots.txt, checked 2026-10-10):
- one GET per fund of `src.url` (/tr/fon-detayli-analiz/<code>), no redirects,
  at least `min_interval_s` between requests;
- never any request to /api/ or other robots-disallowed paths (config.py
  rejects such URLs; `check_url_allowed` checks again before each request);
- the raw pages are stored gzip-compressed in the snapshot and parsed from there.

Fund list: the funds of the `funds_from` (tefas_web) payloads of the same
snapshot (I10: several sources, e.g. tefas_web and tefas_byf; a code in two
lists is fetched once), without `exclude_categories`. The page is a Next.js page like the
tefas_web page; the data objects `bilgiData` and `profilData` sit in its flight
data. Strict: a page without them, for another fund, or with a required value
that is missing or not a number is a rejected row; optional values (risk, fees)
that are null, "" or "-" give no row. More than `max_fail_share` failed pages ->
the source fails (the page format changed, or the site blocks us).

The page has no date for its values (checked 2026-10-10 on 3 pages), so
as_of = previous business day before the snapshot date, as for tefas_web.

Valör: the page labels "Fon Alış Valörü" (buy) show `fonGeriAlisValor` and
"Fon Satış Valörü" (sell) show `fonSatisValor` (MAC, 2026-10-10: 1 and 2).
The field -> quantity mapping is in config.
"""

from __future__ import annotations

import gzip
import json
import math
import re
import time
from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any, NamedTuple

import httpx

from rmprep.contracts import TR_TZ, DataPoint, Flag
from rmprep.ingest.adapters.tefas_web import (
    check_url_allowed,
    extract_funds,
    flight_text,
    previous_business_day,
)
from rmprep.ingest.config import DETAIL_OBJECTS, Config, TefasDetailSource, normalize_status
from rmprep.ingest.snapshot import Snapshot, SnapshotWriter, SourceRecord, raw_ref

_NO_VALUE = ("", "-")
AS_OF_NOTE = "as_of assumed = previous business day (the page shows no date)"


class PageError(ValueError):
    """One fund page does not have the expected data. The message is the reason."""


def _listed_codes(src: TefasDetailSource, listing_html: str) -> list[str]:
    return [f["fonKodu"] for f in extract_funds(listing_html)
            if f.get("fonTurAciklama") not in src.exclude_categories]


def fund_codes(src: TefasDetailSource, *listing_htmls: str) -> list[str]:
    """Fund codes of the tefas_web pages without the excluded categories,
    without repeats, sorted."""
    codes = sorted({c for html in listing_htmls for c in _listed_codes(src, html)})
    return codes[:src.max_funds] if src.max_funds else codes


def _find_object(text: str, name: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for m in re.finditer(rf'"{name}":\{{', text):
        try:
            obj, _ = decoder.raw_decode(text, m.end() - 1)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "fonKodu" in obj:
            return obj
    return None


def _number(field: str, raw: Any, required: bool) -> float | None:
    if raw is None or (isinstance(raw, str) and raw.strip() in _NO_VALUE):
        if required:
            raise PageError(f"{field}: no value")
        return None
    x: float | None = None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        x = float(raw)
    elif isinstance(raw, str):
        try:
            x = float(raw.strip().replace(",", "."))
        except ValueError:
            x = None
    if x is None or not math.isfinite(x):
        raise PageError(f"{field}: not a number: {raw!r}")
    return x


Holding = tuple[int, str, float]     # (index in varlikData, kiymetTip, portfoyOrani)


def _holdings(src: TefasDetailSource, text: str,
              code: str) -> tuple[list[Holding], list[str]]:
    """I8: the varlikData rows of this fund, and notes for rows that give no
    row. No varlikData, null or an empty list -> nothing. The texts are kept
    verbatim."""
    m = re.search(r'"varlikData":', text)
    if not src.holdings_quantity or m is None:
        return [], []
    try:
        rows, _ = json.JSONDecoder().raw_decode(text, m.end())
    except json.JSONDecodeError:
        return [], [f"varlikData is not JSON; no {src.holdings_quantity} rows"]
    if not isinstance(rows, list):
        return [], []
    out: list[Holding] = []
    notes: list[str] = []
    for i, row in enumerate(rows):
        row = row if isinstance(row, dict) else {}
        kind = row.get("kiymetTip")
        try:
            if row.get("fonKodu") != code:
                raise PageError(f"fund {row.get('fonKodu')!r}, not {code!r}")
            if not isinstance(kind, str) or not kind.strip():
                raise PageError("kiymetTip: no value")
            if "|" in kind:
                raise PageError(f"kiymetTip {kind!r} has '|'")     # '|' separates id parts
            out.append((i, kind, _number("portfoyOrani", row.get("portfoyOrani"), True)))
        except PageError as e:
            notes.append(f"varlikData[{i}]: {e}; no {src.holdings_quantity} row")
    return out, notes


class PageData(NamedTuple):
    values: dict[str, float | None]   # configured field ("bilgiData.sonFiyat") -> value
    notes: list[str]                  # problems that do not fail the page
    holdings: list[Holding]           # I8, empty without holdings_quantity
    status_text: str | None           # the status text verbatim (I10: into the note)


def parse_page(src: TefasDetailSource, html: str, code: str) -> PageData:
    """The values of one fund page. A value None = no value, no row. Notes are
    problems that do not fail the page (an unknown status text, a bad holdings
    row). Raises PageError with the reason if the page fails."""
    page = flight_text(html)
    objects = {}
    for name in DETAIL_OBJECTS:
        obj = _find_object(page, name)
        if obj is None:
            raise PageError(f"no {name} on the page")
        if obj.get("fonKodu") != code:
            raise PageError(f"page is for fund {obj.get('fonKodu')!r}")
        objects[name] = obj

    values: dict[str, float | None] = {}
    for fields, required in ((src.value_fields, True), (src.optional_fields, False)):
        for field in fields:
            obj, _, key = field.partition(".")
            values[field] = _number(field, objects[obj].get(key), required)

    notes: list[str] = []
    status_text = None
    if src.status:
        field = src.status.field
        obj, _, key = field.partition(".")
        text = objects[obj].get(key)
        status_text = text if isinstance(text, str) else None
        flag = src.status.map.get(normalize_status(text)) if status_text is not None else None
        if flag is None:
            what = (f"unknown {field} {text!r}" if status_text and status_text.strip()
                    else f"{field}: no value")
            notes.append(f"{what}; no {src.status.quantity} row")
        values[field] = flag
    holdings, holding_notes = _holdings(src, page, code)
    return PageData(values, notes + holding_notes, holdings, status_text)


def _read_page(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise PageError("page is not UTF-8") from None


def fetch(
    src: TefasDetailSource,
    writer: SnapshotWriter,
    *,
    listings: Mapping[str, bytes],
    client: httpx.Client,
    now: Callable[[], datetime] = lambda: datetime.now(TR_TZ),
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> SourceRecord:
    """`listings` = source name -> the bytes of its tefas_web page in this
    snapshot, for the `funds_from` sources that have an ok page."""
    request: dict[str, Any] = {
        "method": "GET", "url": src.url, "user_agent": src.user_agent,
        "min_interval_s": src.min_interval_s,
        "robots": "robots.txt disallows /api/; only the fund detail HTML pages are requested"}

    pages = {name: listings[name].decode("utf-8") for name in src.funds_from if name in listings}
    codes = fund_codes(src, *pages.values())
    names = ", ".join(src.funds_from)
    if not codes:
        return SourceRecord(status="failed", on_failure=src.on_failure, request=request,
                            error=f"no {names} funds in this snapshot "
                                  f"(the fund list comes from {names})")
    request["funds"] = len(codes)
    request["funds_from"] = {name: len(_listed_codes(src, pages[name])) if name in pages
                             else "no ok page" for name in src.funds_from}
    for code in codes:
        check_url_allowed(src.page_url(code))

    payloads, rejected = [], []      # rejected: failed pages and notes (not failures)
    failed = 0
    last_start: float | None = None
    for code in codes:
        url = src.page_url(code)
        if last_start is not None:
            wait = last_start + src.min_interval_s - monotonic()
            if wait > 0:
                sleep(wait)
        last_start = monotonic()
        try:
            resp = client.get(url, headers={"User-Agent": src.user_agent},
                              timeout=src.timeout_seconds, follow_redirects=False)
            if resp.status_code != 200:
                raise PageError(f"HTTP {resp.status_code}")
            payloads.append(writer.add_payload(src.name, f"{code}.html.gz",
                                               gzip.compress(resp.content, mtime=0),
                                               meta={"fund": code, "url": url}))
            notes = parse_page(src, _read_page(resp.content), code).notes
            rejected.extend({"fund": code, "reason": n} for n in notes)
        except httpx.HTTPError as e:
            failed += 1
            rejected.append({"fund": code, "reason": f"{type(e).__name__}: {e}"})
        except PageError as e:
            failed += 1
            rejected.append({"fund": code, "reason": str(e)})
        if failed > src.max_fail_share * len(codes):
            return SourceRecord(
                status="failed", on_failure=src.on_failure, request=request,
                payloads=tuple(payloads), rejected_rows=tuple(rejected),
                error=(f"{failed} of {len(codes)} pages failed (more than "
                       f"{src.max_fail_share:.0%}; stopped); the page format may have changed"))
    return SourceRecord(status="ok", on_failure=src.on_failure, fetched_at=now(),
                        request=request, payloads=tuple(payloads),
                        rejected_rows=tuple(rejected))


def parse(cfg: Config, src: TefasDetailSource, snap: Snapshot, *,
          out_snapshot_id: str | None = None, out_date: date | None = None) -> list[DataPoint]:
    """`out_date` is ignored: as_of always comes from the snapshot that holds the
    pages, also for fallback rows. Pages rejected at fetch give no rows."""
    rec = snap.sources.get(src.name)
    if rec is None or rec.status != "ok":
        raise ValueError(f"{snap.snapshot_id}: source {src.name!r} has no ok record")
    sid = out_snapshot_id or snap.snapshot_id
    as_of = previous_business_day(snap.created_at.date())
    flags = [Flag.NEEDS_CHECK] if src.flag_needs_check else []
    quantities = {**src.value_fields, **src.optional_fields}
    if src.status:
        quantities[src.status.field] = src.status.quantity

    points = []
    for payload in rec.payloads:
        code = payload.meta["fund"]
        try:
            page = parse_page(
                src, _read_page(gzip.decompress(snap.read_payload(payload.path))), code)
        except PageError:
            continue
        rows = [(quantities[field], code, value, f"fonKodu={code};field={field}",
                 # I10: the status row keeps the status text verbatim
                 f"{page.status_text}; {AS_OF_NOTE}"
                 if src.status and field == src.status.field else AS_OF_NOTE)
                for field, value in page.values.items() if value is not None]
        rows += [(src.holdings_quantity, f"{code}/{kind}", share, f"varlikData[{i}]", kind)
                 for i, kind, share in page.holdings]
        for quantity, entity, value, locator, note in rows:
            points.append(DataPoint.create(
                quantity=quantity, entity=entity, value=value,
                unit=cfg.quantities[quantity].unit, as_of=as_of, source=src.name,
                source_url=payload.meta["url"], fetched_at=rec.fetched_at, snapshot_id=sid,
                raw_ref=raw_ref(snap.snapshot_id, payload.path, locator),
                flags=flags, note=note))
    return points
