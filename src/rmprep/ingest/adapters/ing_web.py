"""ING rate page adapter (I14): ING's own public deposit rates from
https://www.ing.com.tr/tr/bilgi-destek/mevduat/mevduat-faiz-oranlari.

Rules (checked by the lead 2026-10-16): robots.txt allows the page (config.py
rejects disallowed URLs; `check_url_allowed` checks again before each request);
the terms say "for information only, not binding" and have no rule on
automated access. Honest User-Agent, no redirects, at least `delay_seconds`
between two requests.

The rates are not in the page HTML. The page is one ASP.NET WebForms form, so
each product takes three requests with one cookie client:
  1. GET the page; read the hidden `__*` inputs (`__VIEWSTATE` ...).
  2. POST them with `__EVENTTARGET` = the currency field, the currency, and
     "no product": the answer lists the products and has new hidden inputs.
  3. POST the new hidden inputs with `__EVENTTARGET` = the send button and the
     product: the answer has one `<table>` with the rates.
The step-3 HTML of each product is the payload (`<product>.html`); steps 1-2
are not stored. `fetch` parses each page in memory before it stores anything:
one bad page fails the source (never partial rows). `parse` is pure.

Layouts (config `layout`):
- grid (e-Vadeli Mevduat): header = amount columns; each body row = a term; a
  cell repeats its column label, then "%15,00".
- balance (Turuncu Hesap, Turuncu Çocuk Hesabı, e-Turuncu Biriktiren): first
  column = balance, then the amount without interest (optional, I14b: not in
  e-Turuncu Biriktiren) and one column per rate; one row per balance and rate.
`as_of` comes from the text "<d> <month> <yyyy> itibariyle geçerli".
"""

from __future__ import annotations

import html as html_lib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any

import httpx

from rmprep.contracts import TR_TZ, DataPoint
from rmprep.ingest.config import Config, IngProduct, IngWebSource, ing_robots_disallows
from rmprep.ingest.snapshot import Snapshot, SnapshotWriter, SourceRecord, raw_ref

_MONTHS = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
           "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}
_AS_OF_RE = re.compile(r"(\d{1,2})\s+(\w+)\s+(\d{4})\s+itibariyle\s+geçerli")
_PERCENT_RE = re.compile(r"^%\s*(\d{1,3}(?:\.\d{3})*(?:,\d+)?)$")


class IngPageError(ValueError):
    """A page of the form does not have the expected content."""


def check_url_allowed(url: str) -> None:
    if ing_robots_disallows(url):
        raise ValueError(f"{url!r} is disallowed by ing.com.tr/robots.txt")


# --- reading a page --------------------------------------------------------------------------

@dataclass
class _Cell:
    label: str = ""                  # <div class='label'>
    value: str = ""                  # <div class='value ...'>
    text: str = ""                   # text directly in the <td>


class _Page(HTMLParser):
    """Hidden `__*` inputs, the options of each <select>, and the tables
    (rows of cells) of one page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden: dict[str, str] = {}
        self.options: dict[str, list[str]] = {}
        self.tables: list[list[list[_Cell]]] = []
        self._depth = 0                         # open <table> elements
        self._row: list[_Cell] | None = None
        self._cell: _Cell | None = None
        self._div: str | None = None
        self._select: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "input" and a.get("type") == "hidden" and a.get("name", "").startswith("__"):
            self.hidden[a["name"]] = a.get("value", "")
        elif tag == "select":
            self._select = a.get("name", "")
            self.options[self._select] = []
        elif tag == "option" and self._select is not None:
            self.options[self._select].append(a.get("value", ""))
        elif tag == "table":
            self._depth += 1
            self.tables.append([])
        elif tag == "tr" and self._depth:
            self._row = []
            self.tables[-1].append(self._row)
        elif tag == "td" and self._row is not None:
            self._cell = _Cell()
            self._row.append(self._cell)
        elif tag == "div" and self._cell is not None:
            classes = a.get("class", "").split()
            self._div = "label" if "label" in classes else "value" if "value" in classes else None

    def handle_endtag(self, tag: str) -> None:
        if tag == "select":
            self._select = None
        elif tag == "table":
            self._depth = max(self._depth - 1, 0)
        elif tag == "tr":
            self._row = None
        elif tag == "td":
            self._cell = None
        elif tag == "div":
            self._div = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            key = self._div or "text"
            setattr(self._cell, key, getattr(self._cell, key) + data)


def read_page(text: str) -> _Page:
    page = _Page()
    page.feed(text)
    page.close()
    for table in page.tables:
        for row in table:
            for cell in row:
                cell.label, cell.value, cell.text = (" ".join(x.split()) for x in
                                                     (cell.label, cell.value, cell.text))
    return page


def _percent(text: str) -> float:
    m = _PERCENT_RE.match(text)
    if not m:
        raise IngPageError(f"{text!r} is not a percent")
    return float(m.group(1).replace(".", "").replace(",", "."))


def _as_of(text: str) -> tuple[date, str]:
    for m in _AS_OF_RE.finditer(" ".join(html_lib.unescape(text).split())):
        month = _MONTHS.get(m.group(2).lower())
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(1))), m.group(0)
            except ValueError:
                pass
    raise IngPageError("no '<d> <month> <yyyy> itibariyle geçerli' text")


@dataclass(frozen=True)
class Row:
    entity: str
    value: float
    note: str
    locator: str


def parse_page(product: IngProduct, text: str) -> tuple[date, list[Row]]:
    """(as_of, rows) of one step-3 page. Raises IngPageError if the page or the
    table does not match the config."""
    page = read_page(text)
    if not page.tables:
        raise IngPageError("no rate table on the page")
    if len(page.tables) != 1:
        raise IngPageError(f"{len(page.tables)} tables on the page, expected 1")
    as_of, as_of_text = _as_of(text)
    rows = page.tables[0]
    if not rows:
        raise IngPageError("no rate table on the page")
    header, body = rows[0], rows[1:]
    columns = [c.value or c.text for c in header[1:]]
    if any(not c for c in columns):
        raise IngPageError(f"empty column label in the header {columns}")
    if len(body) < product.min_rows:
        raise IngPageError(f"{len(body)} rows, minimum {product.min_rows}")
    if len(columns) < product.min_columns:
        raise IngPageError(f"{len(columns)} columns, minimum {product.min_columns}")
    common = f"{as_of_text}; ing.com.tr rate form, product {product.value}; gross/net not stated"

    if product.layout == "balance":
        first = header[0].value or header[0].text
        if first != product.balance_header:
            raise IngPageError(f"first header cell {first!r}, expected {product.balance_header!r}")
        expected = ([product.no_interest_column] if product.no_interest_column else []) + [
            *(product.rates or {})]
        if sorted(columns) != sorted(expected):
            raise IngPageError(f"header {columns} does not match {expected}")

    out: list[Row] = []
    for tr in body:
        label = tr[0].value or tr[0].text
        if not label:
            raise IngPageError("a row without a label")
        cells = tr[1:]
        if len(cells) != len(columns):
            raise IngPageError(f"row {label!r} has {len(cells)} cells, expected {len(columns)}")
        for column, cell in zip(columns, cells):
            if cell.label != column:
                raise IngPageError(f"cell label {cell.label!r} does not match the column "
                                   f"{column!r}")
        by_column = dict(zip(columns, cells))
        if product.layout == "grid":
            for column, cell in by_column.items():
                out.append(Row(entity=product.entity.format(row=label, column=column),
                               value=_percent(cell.value), note=common,
                               locator=f"{product.value};row={label};column={column}"))
            continue
        amount = ""
        if product.no_interest_column:
            no_interest = by_column[product.no_interest_column].value
            if not no_interest:
                raise IngPageError(f"row {label!r}: no {product.no_interest_column!r}")
            amount = f"Faiz işletilmeyecek tutar {no_interest} TL; "
        balance = (product.balance_labels or {}).get(label, f"{label} TL")
        for column, word in (product.rates or {}).items():
            out.append(Row(
                entity=product.entity.format(rate=word, balance=balance),
                value=_percent(by_column[column].value),
                note=f"{column}; {amount}{common}",
                locator=f"{product.value};row={label};column={column}"))
    return as_of, out


# --- fetch -----------------------------------------------------------------------------------

def fetch(
    src: IngWebSource,
    writer: SnapshotWriter,
    *,
    client: httpx.Client,
    now: Callable[[], datetime] = lambda: datetime.now(TR_TZ),
    sleep: Callable[[float], None] = time.sleep,
) -> SourceRecord:
    """Three requests per product (see the module text). All-or-nothing: one
    failed request or bad page fails the source and nothing is stored."""
    request: dict[str, Any] = {
        "method": "GET, then 2 POSTs per product (ASP.NET form postback)",
        "url": src.url, "user_agent": src.user_agent, "delay_seconds": src.delay_seconds,
        "products": [p.value for p in src.products],
        "robots": "robots.txt (2026-10-16) allows the page; only this URL is requested"}

    def failed(error: str) -> SourceRecord:
        return SourceRecord(status="failed", on_failure=src.on_failure, request=request,
                            error=error)

    check_url_allowed(src.url)
    calls = 0

    def call(data: dict[str, str] | None = None) -> str:
        nonlocal calls
        if calls:
            sleep(src.delay_seconds)
        calls += 1
        resp = client.request("GET" if data is None else "POST", src.url, data=data,
                              headers={"User-Agent": src.user_agent},
                              timeout=src.timeout_seconds, follow_redirects=False)
        if resp.status_code != 200:
            raise IngPageError(f"HTTP {resp.status_code}")
        try:
            return resp.content.decode("utf-8")
        except UnicodeDecodeError:
            raise IngPageError("the page is not UTF-8") from None

    f = src.form
    pages: list[tuple[IngProduct, str]] = []
    for product in src.products:
        try:
            first = read_page(call())
            if "__VIEWSTATE" not in first.hidden:
                raise IngPageError("no __VIEWSTATE on the page")
            listing = read_page(call({**first.hidden, "__EVENTTARGET": f.currency_field,
                                      "__EVENTARGUMENT": "", f.currency_field: f.currency,
                                      f.product_field: f.no_product}))
            if product.value not in listing.options.get(f.product_field, []):
                raise IngPageError(f"product {product.value!r} is not in the list of the page")
            text = call({**listing.hidden, "__EVENTTARGET": f.send_target, "__EVENTARGUMENT": "",
                         f.currency_field: f.currency, f.product_field: product.value})
            parse_page(product, text)
        except httpx.HTTPError as e:
            return failed(f"{product.value}: {type(e).__name__}: {e}")
        except IngPageError as e:
            return failed(f"{product.value}: {e}")
        pages.append((product, text))

    refs = tuple(writer.add_payload(src.name, f"{p.value}.html", text.encode("utf-8"),
                                    meta={"product": p.value, "url": src.url})
                 for p, text in pages)
    return SourceRecord(status="ok", on_failure=src.on_failure, fetched_at=now(),
                        request=request, payloads=refs)


# --- parse -----------------------------------------------------------------------------------

def parse(cfg: Config, src: IngWebSource, snap: Snapshot, *,
          out_snapshot_id: str | None = None, out_date: date | None = None) -> list[DataPoint]:
    """`out_date` is ignored: as_of is the date on the stored page."""
    rec = snap.sources.get(src.name)
    if rec is None or rec.status != "ok":
        raise ValueError(f"{snap.snapshot_id}: source {src.name!r} has no ok record")
    sid = out_snapshot_id or snap.snapshot_id
    products = {p.value: p for p in src.products}
    unit = cfg.quantities[src.quantity].unit
    points = []
    for payload in rec.payloads:
        product = products.get(payload.meta["product"])
        if product is None:
            raise ValueError(f"{snap.snapshot_id}: product {payload.meta['product']!r} "
                             f"is not in the config of {src.name}")
        as_of, rows = parse_page(product, snap.read_payload(payload.path).decode("utf-8"))
        for row in rows:
            points.append(DataPoint.create(
                quantity=src.quantity, entity=row.entity, value=row.value, unit=unit,
                as_of=as_of, source=src.name, source_url=src.url, fetched_at=rec.fetched_at,
                snapshot_id=sid, raw_ref=raw_ref(snap.snapshot_id, payload.path, row.locator),
                note=row.note))
    return points
