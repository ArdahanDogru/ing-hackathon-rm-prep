"""Tolerant parsing of Turkish number and date formats (TEFAS and manual files)."""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

_EXCEL_EPOCH = date(1899, 12, 30)
_DATE_FORMATS = ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d")


class ParseError(ValueError):
    """A value or file cannot be parsed."""


def decode_text(data: bytes) -> str:
    """UTF-8 (with or without BOM), else Windows Turkish (cp1254)."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1254")


def sniff_delimiter(text: str) -> str:
    """`;` (Turkish Excel default), `,` or tab, chosen from the first line."""
    first = text.split("\n", 1)[0]
    counts = {d: first.count(d) for d in (";", ",", "\t")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] else ";"


def read_csv_rows(data: bytes) -> list[list[str]]:
    text = decode_text(data)
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=sniff_delimiter(text)))


def detect_decimal(texts: Iterable[str]) -> str:
    """Decimal separator of a file, from its value strings.

    "," if any value uses a decimal comma ("1.234,56", "12,5") or several dots
    ("1.234.567"); "." for English style ("1,234.56") or plain "12.5".
    A file with only values like "1.234" is read as decimal point.
    """
    for t in texts:
        t = t.strip()
        if "," in t:
            return "." if "." in t and t.rfind(".") > t.rfind(",") else ","
        if t.count(".") > 1:
            return ","
    return "."


def parse_number(v: Any, decimal: str = ",") -> float | None:
    """Number from a cell. Empty, "-" -> None. Strings use `decimal` as the
    decimal separator; the other of "." / "," is a thousands separator."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ParseError(f"bad number {v!r}")
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        s = str(v).strip().replace(" ", "").replace(" ", "").removesuffix("%")
        if s in ("", "-"):
            return None
        if decimal == ",":
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
        try:
            x = float(s)
        except ValueError:
            raise ParseError(f"bad number {v!r}") from None
    if not math.isfinite(x):
        raise ParseError(f"bad number {v!r}")
    return x


def parse_date(v: Any) -> date:
    """Date from a cell: date/datetime objects, Excel serial numbers, or text in
    dd.mm.yyyy, dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd (a time part is ignored)."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 1 <= v < 100000:
            return _EXCEL_EPOCH + timedelta(days=int(v))
        raise ParseError(f"bad date {v!r}")
    s = str(v or "").strip()
    if not s:
        raise ParseError("empty date")
    s = s.replace("T", " ").split(" ", 1)[0]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ParseError(f"bad date {v!r}")
