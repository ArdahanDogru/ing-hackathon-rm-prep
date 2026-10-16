"""I15: TL deposit rates of other banks (sources isbank_web, ziraat_web; adapter bank_table)."""

import re
from datetime import date, datetime

import httpx
import pytest

from tests.ingest.conftest import (
    ISBANK_URL,
    TEST_BANK_SOURCES,
    ZIRAAT_SKIP,
    ZIRAAT_URL,
    FakeEvds,
    add_banks,
    bank_page,
)
from rmprep.contracts import TR_TZ
from rmprep.ingest.adapters import bank_table
from rmprep.ingest.config import BankTableSource, ConfigError, parse_config
from rmprep.ingest.snapshot import SnapshotWriter

T16 = datetime(2026, 10, 16, 15, 0, tzinfo=TR_TZ)
SID = "20261016-150000-0001"
IS_PAGE, ZI_PAGE = bank_page("isbank"), bank_page("ziraat")


@pytest.fixture
def bcfg(config_raw):
    return parse_config(add_banks(config_raw))


def _fetch(tmp_path, cfg, name, fake=None, at=T16):
    fake = fake or FakeEvds()
    src = cfg.sources[name]
    w = SnapshotWriter(tmp_path / "snaps", {}, created_at=at, snapshot_id=SID)
    rec = bank_table.fetch(src, w, client=fake.client(), now=lambda: at)
    w.set_source(name, rec)
    return rec, w.finalize(), fake


def _points(tmp_path, cfg, name, fake=None):
    rec, snap, _ = _fetch(tmp_path, cfg, name, fake)
    assert rec.status == "ok", rec.error
    return {p.entity: p for p in bank_table.parse(cfg, cfg.sources[name], snap)}


# --- config ---------------------------------------------------------------------------------

def test_config_parses_sources(bcfg):
    src = bcfg.sources["ziraat_web"]
    assert isinstance(src, BankTableSource) and src.adapter == "bank_table"
    assert src.url == ZIRAAT_URL and src.quantity == "deposit_rate"
    branch, internet = src.tables
    assert branch.header == ("Vade Grupları", "0,00 - 999,99 TL", "1.000 TL ve Üzeri")
    assert branch.decimal == "." and branch.min_rows == 9
    assert branch.skip_rows == tuple(ZIRAAT_SKIP) and branch.note == ""
    assert bcfg.sources["isbank_web"].tables[0].skip_rows == ()


def _bad(config_raw, name, change):
    raw = add_banks(config_raw)
    change(raw["sources"][name])
    with pytest.raises(ConfigError) as e:
        parse_config(raw)
    return str(e.value)


@pytest.mark.parametrize("change,match", [
    (lambda s: s.update(url="http://www.isbank.com.tr/kampanyali-mevduat-oranlari"),
     "url: must be an https URL"),
    (lambda s: s.update(url="https://www.examplebank.com.tr/oranlar"),
     "url: no robots.txt rules in the code for 'www.examplebank.com.tr'"),
    (lambda s: s.update(url="https://www.isbank.com.tr/fiyatoran/FiyatTabloGoster.asp?x=1"),
     "is disallowed by www.isbank.com.tr/robots.txt"),
    (lambda s: s.update(tables=[]), "tables: must be a non-empty list"),
    (lambda s: s["tables"][0].update(decimal=";"), r"tables\[0\]\.decimal: must be one of"),
    (lambda s: s["tables"][0].update(entity="İş {row}"),
     r"tables\[0\]\.entity: must use exactly the fields \['column', 'row'\]"),
    (lambda s: s["tables"][0].update(header=["VADE"]),
     r"tables\[0\]\.header: needs the row label cell and at least one column"),
    (lambda s: s["tables"][0].update(min_rows=0), r"tables\[0\]\.min_rows: must be a positive"),
    (lambda s: s["tables"][0].update(skip_rows="Vadesiz"), r"tables\[0\]\.skip_rows: must be"),
    (lambda s: s["tables"][0].update(colour="red"), r"tables\[0\]: unknown key\(s\) \['colour'\]"),
    (lambda s: s.update(quantity="gold_price"), "unknown quantity 'gold_price'"),
    (lambda s: s.update(retries=2), r"unknown key\(s\) \['retries'\]"),
])
def test_config_rejects_bad_values(config_raw, change, match):
    assert re.search(match, _bad(config_raw, "isbank_web", change))


def test_config_rejects_the_same_header_twice(config_raw):
    msg = _bad(config_raw, "ziraat_web",
               lambda s: s["tables"].append(dict(s["tables"][0], entity="Z {row}, {column}")))
    assert "tables[2].header: the same header as tables[0]" in msg


@pytest.mark.parametrize("url,ok", [
    (ISBANK_URL, True),
    (ZIRAAT_URL, True),
    ("https://www.isbank.com.tr/arama/x", False),
    ("https://www.isbank.com.tr/hidden-page", False),
    ("https://www.isbank.com.tr/?tknfv=1", False),
    ("https://www.isbank.com.tr/x/search.asmx/y", False),
    ("https://www.ziraatbank.com.tr/_layouts/x", False),
    ("https://www.ziraatbank.com.tr/tr/bankamiz/basin-odasi/basin-bultenleri/x", False),
])
def test_robots_rules(url, ok):
    if ok:
        bank_table.check_url_allowed(url)
    else:
        with pytest.raises(ValueError, match="robots.txt"):
            bank_table.check_url_allowed(url)


# --- parse (the saved pages of 2026-10-16) ----------------------------------------------------

def test_isbank_table(tmp_path, bcfg):
    rows = _points(tmp_path, bcfg, "isbank_web")
    assert len(rows) == 9 * 6
    p = rows["İş Bankası kampanyalı vadeli TL, 32 - 35 Gün, 10.000.001 TL Üzeri"]
    assert p.value == 37.95                          # "%<span>3<span>7,95</span></span>"
    assert p.quantity == "deposit_rate" and p.unit == "pct" and p.as_of == date(2026, 10, 16)
    assert p.source == "isbank_web" and p.source_url == ISBANK_URL and p.fetched_at == T16
    assert p.flags == frozenset()
    assert p.note == ("campaign rates (İşCep, İnternet Şube, Bankamatik); conditions apply; "
                      "the page shows no date; as_of = the fetch date; gross/net not stated")
    assert p.raw_ref == (f"{SID}/payloads/isbank_web/page.html#tables[0];row=32 - 35 Gün;"
                         f"column=10.000.001 TL Üzeri")
    assert rows["İş Bankası kampanyalı vadeli TL, 28 - 31 Gün, 5.000 - 100.000 TL"].value == 31
    assert rows["İş Bankası kampanyalı vadeli TL, 46 - 91 Gün, 1.000.001 - 10.000.000 TL"
                ].value == 35.5
    assert rows["İş Bankası kampanyalı vadeli TL, 367 Üzeri Gün, 10.000.001 TL Üzeri"].value == 28


def test_ziraat_tables_and_skipped_rows(tmp_path, bcfg):
    rows = _points(tmp_path, bcfg, "ziraat_web")
    branch = [e for e in rows if "(şube)" in e]
    internet = [e for e in rows if "(internet)" in e]
    assert len(branch) == 9 * 2 and len(internet) == 14 * 4
    assert not [e for e in rows if any(s in e for s in ZIRAAT_SKIP)]
    assert rows["Ziraat Bankası vadeli TL (internet), 32 - 45 gün, 500.000,00 TL ve üzeri"
                ].value == 32.0                       # "%32.00", trailing space in the label
    assert rows["Ziraat Bankası vadeli TL (şube), 1 - 29 gün, 1.000 TL ve Üzeri"].value == 4.5
    assert rows["Ziraat Bankası vadeli TL (şube), 1 - 29 gün, 0,00 - 999,99 TL"].value == 0.0
    p = rows["Ziraat Bankası vadeli TL (internet), 1 Yıl Vadeli 3 Ayda Bir Faiz Ödemeli, "
             "5.000 - 99.999,99 TL"]
    assert p.value == 28.0
    assert p.note == "the page shows no date; as_of = the fetch date; gross/net not stated"
    assert p.raw_ref.startswith(f"{SID}/payloads/ziraat_web/page.html#tables[1];row=1 Yıl")


def test_fetch_one_get_and_payload(tmp_path, bcfg):
    rec, snap, fake = _fetch(tmp_path, bcfg, "isbank_web")
    assert [(r.method, str(r.url)) for r in fake.requests] == [("GET", ISBANK_URL)]
    assert fake.requests[0].headers["User-Agent"] == TEST_BANK_SOURCES["isbank_web"]["user_agent"]
    [ref] = rec.payloads
    assert ref.path == "payloads/isbank_web/page.html" and ref.meta == {"url": ISBANK_URL}
    assert snap.read_payload(ref.path) == IS_PAGE.encode("utf-8")
    assert rec.request["tables"] == 1


def test_as_of_is_the_fetch_date_also_for_fallback_rows(tmp_path, bcfg):
    at = datetime(2026, 10, 16, 23, 30, tzinfo=TR_TZ)
    _, snap, _ = _fetch(tmp_path, bcfg, "ziraat_web", at=at)
    src = bcfg.sources["ziraat_web"]
    pts = bank_table.parse(bcfg, src, snap, out_snapshot_id="20261017-090000-0002",
                           out_date=date(2026, 10, 17))
    assert {p.as_of for p in pts} == {date(2026, 10, 16)}
    assert {p.snapshot_id for p in pts} == {"20261017-090000-0002"}
    assert bank_table.parse(bcfg, src, snap) == bank_table.parse(bcfg, src, snap)


# --- cell values ------------------------------------------------------------------------------

@pytest.mark.parametrize("text,decimal,value", [
    ("%31", ",", 31.0),
    ("% 3 7,95", ",", 37.95),
    ("%\n37,5 ", ",", 37.5),
    ("%28.00", ".", 28.0),
    ("%4.50", ".", 4.5),
    ("%0.00", ".", 0.0),
])
def test_percent(text, decimal, value):
    assert bank_table.percent(text, decimal) == value


@pytest.mark.parametrize("text,decimal", [
    ("%28.00", ","), ("%37,95", "."), ("31", ","), ("%", ","), ("%-", "."), ("yok", ","),
    ("%1.234,5", ","),
])
def test_not_a_percent(text, decimal):
    with pytest.raises(bank_table.BankPageError, match="is not a percent"):
        bank_table.percent(text, decimal)


# --- page changes: the source fails, never partial rows -----------------------------------------

@pytest.mark.parametrize("name,page,reason", [
    ("isbank_web", IS_PAGE.replace("VADE<br/>", "Vade<br/>", 1),
     "tables[0]: no table with the header ['VADE', '5.000 - 100.000 TL'"),
    ("isbank_web", IS_PAGE.replace("</table>", "</table>" + IS_PAGE[IS_PAGE.find("<table"):
                                                                  IS_PAGE.find("</table>") + 8], 1),
     "tables[0]: 2 tables with the header"),
    ("isbank_web", IS_PAGE.replace("%28,50", "yok", 1), "tables[0]: 'yok' is not a percent"),
    ("isbank_web", IS_PAGE.replace("<td data-label=\"Time Interval\">%31<br/></td>", "", 1),
     "tables[0]: row '28 - 31 Gün' has 5 cells, expected 6"),
    ("ziraat_web", ZI_PAGE.replace("%4.50", "%4,50", 1), "tables[0]: '%4,50' is not a percent"),
], ids=["header", "two_tables", "not_percent", "missing_cell", "wrong_decimal"])
def test_page_change_fails_the_source(tmp_path, bcfg, name, page, reason):
    host = "www.isbank.com.tr" if name == "isbank_web" else "www.ziraatbank.com.tr"
    rec, _, _ = _fetch(tmp_path, bcfg, name, FakeEvds(bank_pages={host: page}))
    assert rec.status == "failed" and reason in rec.error and rec.payloads == ()


def test_too_few_rows_fails(tmp_path, config_raw):
    add_banks(config_raw)["sources"]["ziraat_web"]["tables"][1]["min_rows"] = 15
    rec, _, _ = _fetch(tmp_path, parse_config(config_raw), "ziraat_web")
    assert rec.status == "failed" and "tables[1]: 14 rows, minimum 15" in rec.error


@pytest.mark.parametrize("status", [301, 404, 503])
def test_http_status_other_than_200_fails(tmp_path, bcfg, status):
    class Status(FakeEvds):
        def __call__(self, request):
            self.requests.append(request)
            return httpx.Response(status, headers={"Location": ISBANK_URL + "?x"})

    rec, _, fake = _fetch(tmp_path, bcfg, "isbank_web", Status())
    assert rec.status == "failed" and f"HTTP {status}" in rec.error and len(fake.requests) == 1


def test_connection_error_fails(tmp_path, bcfg):
    class Refuse(FakeEvds):
        def __call__(self, request):
            raise httpx.ConnectError("refused")

    rec, _, _ = _fetch(tmp_path, bcfg, "isbank_web", Refuse())
    assert rec.status == "failed" and "ConnectError" in rec.error
