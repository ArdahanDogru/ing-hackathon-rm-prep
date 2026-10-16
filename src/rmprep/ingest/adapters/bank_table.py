"""Bank rate table adapter (I15): TL deposit rates from a bank's own public page,
for sources such as isbank_web and ziraat_web (one adapter, one source per
bank, so a changed page fails only its own bank).

Rules (checked by the lead 2026-10-16): robots.txt allows the pages (the
Disallow lines of each host are in config.BANK_ROBOTS_DISALLOW; config rejects
a disallowed URL and `check_url_allowed` checks again before the request); the
legal notices say "information only" and have no rule on automated access.
One GET per source and ingest, no redirects, honest User-Agent. The page HTML
is the payload; `fetch` parses it before it stores it, and `parse` is pure.

Each configured table is chosen by its exact header row (the row label cell,
then the amount columns; whitespace normalised), which also detects a changed
page. Body rows: the first cell is the row label (a term), then one percent
per column ("%31", "% 3 7,95" = 37,95 after all whitespace is removed; the
decimal mark is config: "," or "."). `skip_rows` are labels that are not
terms. The pages show no date, so as_of = the Turkish date of the fetch.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any

import httpx

from rmprep.contracts import TR_TZ, DataPoint
from rmprep.ingest.config import (
    BANK_ROBOTS_DISALLOW,
    BankTable,
    BankTableSource,
    Config,
    robots_disallows,
)
from rmprep.ingest.snapshot import Snapshot, SnapshotWriter, SourceRecord, raw_ref

PAYLOAD_NAME = "page.html"
NO_DATE_NOTE = "the page shows no date; as_of = the fetch date; gross/net not stated"
_PERCENT = {",": re.compile(r"^%(\d+)(?:,(\d+))?$"), ".": re.compile(r"^%(\d+)(?:\.(\d+))?$")}


class BankPageError(ValueError):
    """The page does not have the expected table or values."""


def check_url_allowed(url: str) -> None:
    host = url.split("/", 3)[2] if "://" in url else ""
    patterns = BANK_ROBOTS_DISALLOW.get(host)
    if patterns is None or robots_disallows(patterns, url):
        raise ValueError(f"{url!r} is disallowed by {host}/robots.txt (or the host has no "
                         "rules in the code)")


# --- reading a page --------------------------------------------------------------------------

class _Tables(HTMLParser):
    """Every <table> of a page as rows of cell texts (<td> and <th>, any nesting
    of other tags inside a cell; whitespace normalised)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._stack: list[list[list[str]]] = []      # open tables
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            table: list[list[str]] = []
            self.tables.append(table)
            self._stack.append(table)
            self._row = self._cell = None
        elif tag == "tr" and self._stack:
            self._row = []
            self._stack[-1].append(self._row)
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._row.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row[-1] = " ".join("".join(self._cell).split())
            self._cell = None
        elif tag == "tr":
            self._row = None
        elif tag == "table" and self._stack:
            self._stack.pop()
            self._row = self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def read_tables(html: str) -> list[list[list[str]]]:
    parser = _Tables()
    parser.feed(html)
    parser.close()
    return [[row for row in table if row] for table in parser.tables]


def percent(text: str, decimal: str) -> float:
    compact = re.sub(r"\s+", "", text)
    m = _PERCENT[decimal].match(compact)
    if not m:
        raise BankPageError(f"{text!r} is not a percent")
    return float(f"{m.group(1)}.{m.group(2) or 0}")


@dataclass(frozen=True)
class Row:
    entity: str
    value: float
    note: str
    locator: str


def parse_page(src: BankTableSource, html: str) -> list[Row]:
    """The rows of every configured table. Raises BankPageError (with the table
    index) if a table is missing, found twice, or does not match."""
    tables = read_tables(html)
    out: list[Row] = []
    for i, table in enumerate(src.tables):
        try:
            out.extend(_table_rows(i, table, tables))
        except BankPageError as e:
            raise BankPageError(f"tables[{i}]: {e}") from None
    return out


def _table_rows(i: int, table: BankTable, tables: list[list[list[str]]]) -> list[Row]:
    found = [t for t in tables if t and tuple(t[0]) == table.header]
    if not found:
        raise BankPageError(f"no table with the header {list(table.header)}")
    if len(found) > 1:
        raise BankPageError(f"{len(found)} tables with the header {list(table.header)}")
    columns = table.header[1:]
    note = f"{table.note}; {NO_DATE_NOTE}" if table.note else NO_DATE_NOTE
    body = [row for row in found[0][1:] if row[0] not in table.skip_rows]
    if len(body) < table.min_rows:
        raise BankPageError(f"{len(body)} rows, minimum {table.min_rows}")
    out = []
    for row in body:
        label, cells = row[0], row[1:]
        if not label:
            raise BankPageError("a row without a label")
        if len(cells) != len(columns):
            raise BankPageError(f"row {label!r} has {len(cells)} cells, expected {len(columns)}")
        for column, cell in zip(columns, cells):
            out.append(Row(entity=table.entity.format(row=label, column=column),
                           value=percent(cell, table.decimal), note=note,
                           locator=f"tables[{i}];row={label};column={column}"))
    return out


# --- fetch and parse -------------------------------------------------------------------------

def fetch(
    src: BankTableSource,
    writer: SnapshotWriter,
    *,
    client: httpx.Client,
    now: Callable[[], datetime] = lambda: datetime.now(TR_TZ),
) -> SourceRecord:
    """One GET. The page is parsed before it is stored: a bad page fails the
    source and nothing is stored."""
    request: dict[str, Any] = {
        "method": "GET", "url": src.url, "user_agent": src.user_agent,
        "tables": len(src.tables),
        "robots": "robots.txt (2026-10-16) allows the page; only this URL is requested"}

    def failed(error: str) -> SourceRecord:
        return SourceRecord(status="failed", on_failure=src.on_failure, request=request,
                            error=error)

    check_url_allowed(src.url)
    try:
        resp = client.get(src.url, headers={"User-Agent": src.user_agent},
                          timeout=src.timeout_seconds, follow_redirects=False)
    except httpx.HTTPError as e:
        return failed(f"{type(e).__name__}: {e}")
    if resp.status_code != 200:
        return failed(f"HTTP {resp.status_code}")
    try:
        parse_page(src, resp.content.decode("utf-8"))
    except UnicodeDecodeError:
        return failed("the page is not UTF-8")
    except BankPageError as e:
        return failed(str(e))
    ref = writer.add_payload(src.name, PAYLOAD_NAME, resp.content, meta={"url": src.url})
    return SourceRecord(status="ok", on_failure=src.on_failure, fetched_at=now(),
                        request=request, payloads=(ref,))


def parse(cfg: Config, src: BankTableSource, snap: Snapshot, *,
          out_snapshot_id: str | None = None, out_date: date | None = None) -> list[DataPoint]:
    """`out_date` is ignored: as_of is the Turkish date of the fetch (the pages
    show no date), also for fallback rows."""
    rec = snap.sources.get(src.name)
    if rec is None or rec.status != "ok":
        raise ValueError(f"{snap.snapshot_id}: source {src.name!r} has no ok record")
    sid = out_snapshot_id or snap.snapshot_id
    [payload] = rec.payloads
    as_of = rec.fetched_at.astimezone(TR_TZ).date()
    unit = cfg.quantities[src.quantity].unit
    return [DataPoint.create(
        quantity=src.quantity, entity=row.entity, value=row.value, unit=unit, as_of=as_of,
        source=src.name, source_url=src.url, fetched_at=rec.fetched_at, snapshot_id=sid,
        raw_ref=raw_ref(snap.snapshot_id, payload.path, row.locator), note=row.note)
        for row in parse_page(src, snap.read_payload(payload.path).decode("utf-8"))]
