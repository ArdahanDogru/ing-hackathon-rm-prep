import inspect
import shutil
from datetime import date, datetime

import pytest
from openpyxl import Workbook

from tests.ingest.conftest import FIXTURES, T0
from rmprep.ingest.adapters import tefas
from rmprep.contracts import Flag
from rmprep.ingest.parsing import ParseError
from rmprep.ingest.snapshot import SnapshotWriter

CSV = FIXTURES / "tefas" / "tefas_export.csv"


def _xlsx(path, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Fon Verileri"
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


def _fetch(tmp_path, cfg, inbox):
    src = cfg.sources["tefas"]
    w = SnapshotWriter(tmp_path / "snaps", {}, created_at=T0, snapshot_id="20261009-150000-0001")
    rec = tefas.fetch(src, w, inbox=inbox, now=lambda: T0)
    w.set_source("tefas", rec)
    return rec, w.finalize()


@pytest.fixture
def inbox(tmp_path):
    d = tmp_path / "inbox"
    d.mkdir()
    return d


# --- no scraping -----------------------------------------------------------------

def test_module_has_no_http_client():
    src = inspect.getsource(tefas)
    assert "httpx" not in src and "requests" not in src and "urllib" not in src


# --- parse_file: CSV -----------------------------------------------------------------

def test_csv_turkish_formats(cfg):
    rows = tefas.parse_file(CSV.read_bytes(), "tefas_export.csv", cfg.sources["tefas"])
    assert len(rows) == 3
    first = rows[0]
    assert first.locator == "row=2"
    assert first.as_of == date(2026, 10, 8) and first.entity == "AAA"
    assert first.values == {"price": 1.234567, "total_value": 12345670.0,
                            "investor_count": 12345.0}


def test_csv_cp1254_encoding(cfg):
    data = CSV.read_text(encoding="utf-8").encode("cp1254")
    rows = tefas.parse_file(data, "x.csv", cfg.sources["tefas"])
    assert len(rows) == 3


def test_empty_value_cell_left_out(cfg):
    data = "Tarih;Fon Kodu;Fiyat;Kişi Sayısı\n08.10.2026;aaa;1,5;\n".encode()
    [row] = tefas.parse_file(data, "x.csv", cfg.sources["tefas"])
    assert row.values == {"price": 1.5} and row.entity == "AAA"


def test_header_not_found(cfg):
    with pytest.raises(ParseError, match="header row not found"):
        tefas.parse_file(b"Date;Code;Price\n08.10.2026;AAA;1\n", "x.csv", cfg.sources["tefas"])


def test_header_without_value_column(cfg):
    with pytest.raises(ParseError, match="no value column"):
        tefas.parse_file("Tarih;Fon Kodu;Fon Adı\n".encode(), "x.csv", cfg.sources["tefas"])


def test_bad_number_names_file_and_row(cfg):
    data = "Tarih;Fon Kodu;Fiyat\n08.10.2026;AAA;1,5\n08.10.2026;BBB;n/a\n".encode()
    with pytest.raises(ParseError, match=r"x.csv row=3: bad number"):
        tefas.parse_file(data, "x.csv", cfg.sources["tefas"])


def test_unsupported_extension(cfg):
    with pytest.raises(ParseError, match="unsupported file type"):
        tefas.parse_file(b"", "export.xls", cfg.sources["tefas"])


# --- parse_file: XLSX -----------------------------------------------------------------

def test_xlsx_with_title_rows_uppercase_headers_and_typed_cells(tmp_path, cfg):
    path = _xlsx(tmp_path / "e.xlsx", [
        ["TEFAS Fon Karşılaştırma"],
        [],
        ["TARİH", "FON KODU", "FON ADI", "FİYAT", "KİŞİ SAYISI"],
        [datetime(2026, 10, 8), "AAA", "Örnek", 1.234567, 12345],
        ["07.10.2026", "AAA", "Örnek", "1,230001", "12.300"],
        [46302, "AAA", "Örnek", 1.2, 12000],
    ])
    rows = tefas.parse_file(path.read_bytes(), "e.xlsx", cfg.sources["tefas"])
    assert [r.locator for r in rows] == ["Fon Verileri!row=4", "Fon Verileri!row=5",
                                         "Fon Verileri!row=6"]
    assert [r.as_of for r in rows] == [date(2026, 10, 8), date(2026, 10, 7), date(2026, 10, 7)]
    assert rows[0].values == {"price": 1.234567, "investor_count": 12345.0}
    assert rows[1].values == {"price": 1.230001, "investor_count": 12300.0}


def test_corrupt_xlsx(cfg):
    with pytest.raises(ParseError, match="cannot open xlsx"):
        tefas.parse_file(b"not a zip", "e.xlsx", cfg.sources["tefas"])


# --- fetch -------------------------------------------------------------------------------

def test_fetch_copies_files_byte_for_byte(tmp_path, cfg, inbox):
    shutil.copy(CSV, inbox / "Fon Getirileri (Ekim).csv")
    rec, snap = _fetch(tmp_path, cfg, inbox)
    assert rec.status == "ok"
    [p] = rec.payloads
    assert p.meta == {"original_name": "Fon Getirileri (Ekim).csv"}
    assert snap.read_payload(p.path) == CSV.read_bytes()
    assert (inbox / "Fon Getirileri (Ekim).csv").exists()      # inbox not modified


def test_fetch_skips_lock_and_hidden_files(tmp_path, cfg, inbox):
    shutil.copy(CSV, inbox / "a.csv")
    (inbox / "~$a.xlsx").write_bytes(b"lock")
    (inbox / ".gitkeep").write_bytes(b"")
    rec, _ = _fetch(tmp_path, cfg, inbox)
    assert rec.request["files"] == ["a.csv"]


def test_fetch_empty_inbox_fails(tmp_path, cfg, inbox):
    rec, _ = _fetch(tmp_path, cfg, inbox)
    assert rec.status == "failed" and "no files" in rec.error


def test_fetch_one_bad_file_fails_all(tmp_path, cfg, inbox):
    shutil.copy(CSV, inbox / "a.csv")
    (inbox / "b.csv").write_bytes(b"nothing useful\n")
    rec, snap = _fetch(tmp_path, cfg, inbox)
    assert rec.status == "failed" and "b.csv" in rec.error
    assert rec.payloads == ()


# --- parse (snapshot -> DataPoints) ----------------------------------------------------------

def test_parse_datapoints(tmp_path, cfg, inbox):
    shutil.copy(CSV, inbox / "a.csv")
    _, snap = _fetch(tmp_path, cfg, inbox)
    pts = tefas.parse(cfg, cfg.sources["tefas"], snap)
    assert len(pts) == 9                                     # 3 rows x 3 value columns
    price = [p for p in pts if p.quantity == "fund_price" and p.entity == "AAA"
             and p.as_of == date(2026, 10, 8)][0]
    assert price.value == 1.234567 and price.unit == "TRY"
    assert price.source == "tefas" and price.flags == frozenset()
    assert price.raw_ref == "20261009-150000-0001/payloads/tefas/a.csv#row=2;col=price"
    count = [p for p in pts if p.quantity == "fund_investor_count"][0]
    assert count.unit == "count"
    assert not any(Flag.MISSING in p.flags for p in pts)
