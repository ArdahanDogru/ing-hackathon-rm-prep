"""TCMB EVDS adapter.

Request:  GET {base_url}series={code}&startDate=dd-mm-yyyy&endDate=dd-mm-yyyy&type=json
          with the API key in the `key` HTTP header (never in the URL).
          Confirmed by the "EVDS Web Servis Kılavuzu" (EVDS3): base URL
          https://evds3.tcmb.gov.tr/igmevdsms-dis/, wrong/missing key -> 403,
          max 1000 observations per request, startDate should be the first day
          of a period of the series frequency.
Response: {"totalCount": n, "items": [{"Tarih": "08-10-2026", "TP_FG_J0": "123.4", ...}]}
          The value column is the series code with "." replaced by "_".
          NOT yet confirmed for EVDS3 (the guide shows no JSON example); a
          different shape makes fetch fail with a clear error, nothing is stored.

Metadata helpers (`list_datagroups`, `list_series`, `find_series`) use the
guide's metadata services; they are for finding series codes, not for ingest.
"""

from __future__ import annotations

import calendar
import json
import math
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from rmprep.ingest.config import Config, EvdsSeries, EvdsSource, normalize_header
from rmprep.contracts import TR_TZ, DataPoint, Flag
from rmprep.ingest.snapshot import MANIFEST, Snapshot, SnapshotWriter, SourceRecord, raw_ref

_DAILY_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")
_MONTHLY_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


class EvdsParseError(ValueError):
    """EVDS response has an unexpected shape."""


Observation = tuple[int, date, float | None]   # (item index, as_of, value)


# --- request --------------------------------------------------------------------

def get_api_key(src: EvdsSource, env: Mapping[str, str] = os.environ) -> str | None:
    key = env.get(src.api_key_env, "").strip()
    return key or None


def _evds_date(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def request_start(today: date, lookback_days: int) -> date:
    """First day of the month that contains today - lookback_days. The guide
    says startDate must be the first day of a period, or the first monthly
    value is left out."""
    return (today - timedelta(days=lookback_days)).replace(day=1)


def series_url(src: EvdsSource, code: str, start: date, end: date) -> str:
    return (f"{src.base_url}series={code}&startDate={_evds_date(start)}"
            f"&endDate={_evds_date(end)}&type=json")


def fetch(
    src: EvdsSource,
    writer: SnapshotWriter,
    *,
    api_key: str | None,
    client: httpx.Client,
    today: date,
    now: Callable[[], datetime] = lambda: datetime.now(TR_TZ),
) -> SourceRecord:
    """Fetch all non-placeholder series. All-or-nothing: if one series fails, the
    source fails and no payload is stored."""
    start = request_start(today, src.lookback_days)
    real = [s for s in src.series if not s.is_placeholder]
    request: dict[str, Any] = {
        "base_url": src.base_url,
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "series": [s.code for s in real],
        "auth": "HTTP header 'key' (value not stored)",
    }

    def failed(error: str) -> SourceRecord:
        return SourceRecord(status="failed", on_failure=src.on_failure,
                            request=request, error=error)

    if not api_key:
        return failed(f"API key not set (environment variable {src.api_key_env})")

    received: list[tuple[EvdsSeries, str, bytes]] = []
    for s in real:
        url = series_url(src, s.code, start, today)
        try:
            resp = client.get(url, headers={"key": api_key}, timeout=src.timeout_seconds)
        except httpx.HTTPError as e:
            return failed(f"{s.code}: {type(e).__name__}: {e}")
        if resp.status_code != 200:
            return failed(f"{s.code}: HTTP {resp.status_code}")
        try:
            parse_payload(resp.content, s.code)
        except EvdsParseError as e:
            return failed(f"{s.code}: {e}")
        received.append((s, url, resp.content))

    fetched_at = now()
    refs = tuple(
        writer.add_payload(src.name, f"{s.code}.json", body, meta={"series": s.code, "url": url})
        for s, url, body in received
    )
    return SourceRecord(status="ok", on_failure=src.on_failure, fetched_at=fetched_at,
                        request=request, payloads=refs)


# --- parsing ------------------------------------------------------------------------

def parse_evds_date(text: str) -> date:
    """Daily/weekly "dd-mm-yyyy" -> that date; monthly "yyyy-m" -> last day of
    the month (the value is known only at the end of the period)."""
    text = str(text).strip()
    if m := _DAILY_RE.match(text):
        return date(int(m[3]), int(m[2]), int(m[1]))
    if m := _MONTHLY_RE.match(text):
        y, mo = int(m[1]), int(m[2])
        if not 1 <= mo <= 12:
            raise EvdsParseError(f"bad month in date {text!r}")
        return date(y, mo, calendar.monthrange(y, mo)[1])
    raise EvdsParseError(f"unsupported EVDS date {text!r}")


def _parse_value(v: Any) -> float | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool):
        raise EvdsParseError(f"bad value {v!r}")
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        s = v.strip()
        if "," in s and "." not in s:
            s = s.replace(",", ".")
        try:
            x = float(s)
        except ValueError:
            raise EvdsParseError(f"bad value {v!r}") from None
    if not math.isfinite(x):
        raise EvdsParseError(f"bad value {v!r}")
    return x


def parse_payload(data: bytes, code: str) -> list[Observation]:
    """Observations of one series. A null or absent value gives value None
    (holiday, no publication); it is not an error."""
    try:
        doc = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise EvdsParseError(f"response is not JSON ({e.__class__.__name__})") from None
    items = doc.get("items") if isinstance(doc, dict) else None
    if not isinstance(items, list):
        raise EvdsParseError("response has no 'items' list")
    column = code.replace(".", "_")
    out: list[Observation] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or "Tarih" not in item:
            raise EvdsParseError(f"items[{i}] has no 'Tarih'")
        try:
            out.append((i, parse_evds_date(item["Tarih"]), _parse_value(item.get(column))))
        except EvdsParseError as e:
            raise EvdsParseError(f"items[{i}]: {e}") from None
    return out


def _point(cfg: Config, src: EvdsSource, s: EvdsSeries, *, value: float | None,
           as_of: date, fetched_at: datetime, snapshot_id: str, ref: str,
           extra_flags: tuple[Flag, ...] = (), note: str = "") -> DataPoint:
    flags = set(extra_flags)
    if not s.verified:
        flags.add(Flag.UNVERIFIED_SERIES)
    if value is None:
        flags.add(Flag.MISSING)
    return DataPoint.create(
        quantity=s.quantity, entity=s.entity, value=value,
        unit=cfg.quantities[s.quantity].unit, as_of=as_of, source=src.name,
        source_url=src.source_url, fetched_at=fetched_at, snapshot_id=snapshot_id,
        raw_ref=ref, flags=flags, note=note,
    )


def parse(
    cfg: Config,
    src: EvdsSource,
    snap: Snapshot,
    *,
    out_snapshot_id: str | None = None,
    out_date: date | None = None,
) -> list[DataPoint]:
    """DataPoints from a snapshot where this source has status ok.

    `out_snapshot_id` / `out_date` are for fallback: rows are emitted for a newer
    snapshot, but `raw_ref` and `fetched_at` still point to `snap`.
    """
    rec = snap.sources.get(src.name)
    if rec is None or rec.status != "ok":
        raise ValueError(f"{snap.snapshot_id}: source {src.name!r} has no ok record")
    sid = out_snapshot_id or snap.snapshot_id
    day = out_date or snap.created_at.date()
    by_code = {p.meta["series"]: p for p in rec.payloads}

    points: list[DataPoint] = []
    for i, s in enumerate(src.series):
        if s.is_placeholder:
            points.append(_point(
                cfg, src, s, value=None, as_of=day, fetched_at=snap.created_at,
                snapshot_id=sid,
                ref=raw_ref(snap.snapshot_id, MANIFEST, f"config.sources.{src.name}.series[{i}]"),
                note="placeholder series code; set the real EVDS code in sources.yaml"))
            continue

        payload = by_code[s.code]
        observations = [
            (idx, as_of, v)
            for idx, as_of, v in parse_payload(snap.read_payload(payload.path), s.code)
            if v is not None
        ]
        if not observations:
            points.append(_point(
                cfg, src, s, value=None, as_of=day, fetched_at=rec.fetched_at,
                snapshot_id=sid, ref=raw_ref(snap.snapshot_id, payload.path, "items"),
                note="no observations in the requested date range"))
            continue
        for idx, as_of, v in observations:
            points.append(_point(
                cfg, src, s, value=v, as_of=as_of, fetched_at=rec.fetched_at,
                snapshot_id=sid, ref=raw_ref(snap.snapshot_id, payload.path, f"items[{idx}]")))
    return points


def missing_points(cfg: Config, src: EvdsSource, snapshot_id: str,
                   created_at: datetime, note: str) -> list[DataPoint]:
    """One missing row per configured series. Used when the source failed and no
    earlier ok snapshot exists."""
    return [
        _point(cfg, src, s, value=None, as_of=created_at.date(), fetched_at=created_at,
               snapshot_id=snapshot_id,
               ref=raw_ref(snapshot_id, MANIFEST, f"sources.{src.name}"), note=note)
        for s in src.series
    ]


# --- metadata (finding series codes; not used by ingest) ------------------------------

@dataclass(frozen=True)
class SeriesInfo:
    code: str
    name: str
    name_eng: str
    datagroup: str
    frequency: str
    start: str
    end: str


def _meta_get(src: EvdsSource, client: httpx.Client, api_key: str, path: str) -> Any:
    try:
        resp = client.get(src.base_url + path, headers={"key": api_key},
                          timeout=src.timeout_seconds)
    except httpx.HTTPError as e:
        raise EvdsParseError(f"{type(e).__name__}: {e}") from None
    if resp.status_code != 200:
        hint = " (check EVDS_API_KEY)" if resp.status_code == 403 else ""
        raise EvdsParseError(f"HTTP {resp.status_code} for {path}{hint}")
    try:
        return json.loads(resp.content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise EvdsParseError(f"response for {path} is not JSON") from None


def _records(doc: Any) -> list[dict[str, Any]]:
    """The guide does not show the JSON shape: accept a list of objects, or an
    object whose first list value holds them."""
    if isinstance(doc, dict):
        doc = next((v for v in doc.values() if isinstance(v, list)), [])
    return [d for d in doc if isinstance(d, dict)] if isinstance(doc, list) else []


def _field(rec: dict[str, Any], name: str) -> str:
    """Field by name, ignoring case (the guide writes e.g. Serie_Code)."""
    for k, v in rec.items():
        if k.lower() == name.lower() and v is not None:
            return str(v)
    return ""


def list_datagroups(src: EvdsSource, client: httpx.Client, api_key: str) -> list[dict[str, Any]]:
    return _records(_meta_get(src, client, api_key, "datagroups/mode=0&type=json"))


def list_series(src: EvdsSource, client: httpx.Client, api_key: str,
                code: str) -> list[SeriesInfo]:
    """Series of a data group, or one series. `code` = data group or series code."""
    recs = _records(_meta_get(src, client, api_key, f"serieList/type=json&code={code}"))
    return [SeriesInfo(code=_field(r, "serie_code"), name=_field(r, "serie_name"),
                       name_eng=_field(r, "serie_name_eng"),
                       datagroup=_field(r, "datagroup_code"),
                       frequency=_field(r, "frequency_str"),
                       start=_field(r, "start_date"), end=_field(r, "end_date"))
            for r in recs]


def find_series(src: EvdsSource, client: httpx.Client, api_key: str, text: str,
                max_groups: int = 15) -> tuple[list[dict[str, Any]], list[SeriesInfo]]:
    """Data groups whose name contains `text` (case and Turkish letters ignored),
    and the series of the first `max_groups` of them."""
    needle = normalize_header(text)
    groups = [g for g in list_datagroups(src, client, api_key)
              if any(isinstance(v, str) and needle in normalize_header(v) for v in g.values())]
    series: list[SeriesInfo] = []
    for g in groups[:max_groups]:
        series.extend(list_series(src, client, api_key, _field(g, "datagroup_code")))
    return groups, series
