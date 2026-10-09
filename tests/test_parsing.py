from datetime import date, datetime

import pytest

from rmprep.parsing import (
    ParseError,
    decode_text,
    detect_decimal,
    parse_date,
    parse_number,
    read_csv_rows,
    sniff_delimiter,
)


@pytest.mark.parametrize("text,decimal,expected", [
    ("1.234,56", ",", 1234.56),
    ("12.345.670,00", ",", 12345670.0),
    ("0,987654", ",", 0.987654),
    ("12.345", ",", 12345.0),
    ("1,234.56", ".", 1234.56),
    ("12.5", ".", 12.5),
    ("45,5%", ",", 45.5),
    (" 1 234,5 ", ",", 1234.5),
    ("1 234,5", ",", 1234.5),
    ("-3,5", ",", -3.5),
    (7, ",", 7.0),
    (2.5, ",", 2.5),
])
def test_parse_number(text, decimal, expected):
    assert parse_number(text, decimal) == pytest.approx(expected)


@pytest.mark.parametrize("text", [None, "", "  ", "-"])
def test_empty_number_is_none(text):
    assert parse_number(text) is None


@pytest.mark.parametrize("text", ["abc", "1,2,3x", True, float("nan")])
def test_bad_number_rejected(text):
    with pytest.raises(ParseError):
        parse_number(text)


@pytest.mark.parametrize("texts,expected", [
    (["1,5", "2"], ","),
    (["1.234.567"], ","),
    (["1,234.56"], "."),
    (["12.5", "3"], "."),
    ([], "."),
])
def test_detect_decimal(texts, expected):
    assert detect_decimal(texts) == expected


@pytest.mark.parametrize("value,expected", [
    ("09.10.2026", date(2026, 10, 9)),
    ("09/10/2026", date(2026, 10, 9)),
    ("09-10-2026", date(2026, 10, 9)),
    ("2026-10-09", date(2026, 10, 9)),
    ("09.10.2026 00:00:00", date(2026, 10, 9)),
    ("2026-10-09T00:00:00", date(2026, 10, 9)),
    (datetime(2026, 10, 9, 0, 0), date(2026, 10, 9)),
    (date(2026, 10, 9), date(2026, 10, 9)),
    (46304, date(2026, 10, 9)),            # Excel serial number
])
def test_parse_date(value, expected):
    assert parse_date(value) == expected


@pytest.mark.parametrize("value", ["", None, "31.02.2026", "10/2026", "yesterday", -5])
def test_bad_date_rejected(value):
    with pytest.raises(ParseError):
        parse_date(value)


def test_decode_utf8_bom_and_cp1254():
    assert decode_text("﻿Fon Adı".encode("utf-8")) == "Fon Adı"
    assert decode_text("Fon Adı;Kişi".encode("cp1254")) == "Fon Adı;Kişi"


@pytest.mark.parametrize("text,expected", [
    ("a;b;c\n1;2;3", ";"), ("a,b,c", ","), ("a\tb", "\t"), ("single", ";")])
def test_sniff_delimiter(text, expected):
    assert sniff_delimiter(text) == expected


def test_read_csv_rows_keeps_quoted_separators():
    rows = read_csv_rows('a;b\n"x;y";"1,5"\n'.encode())
    assert rows == [["a", "b"], ["x;y", "1,5"]]
