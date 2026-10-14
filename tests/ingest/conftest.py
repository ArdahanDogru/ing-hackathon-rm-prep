import copy
import functools
import gzip
import io
import json
import re
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from rmprep.ingest.config import load_raw, parse_config
from rmprep.contracts import TR_TZ

PROJECT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Fixed "now" for tests: 9 October 2026, 15:00 Turkey time.
T0 = datetime(2026, 10, 9, 15, 0, tzinfo=TR_TZ)
KEY = "test-key-123"


TEFAS_WEB_LABELS = {"fonKodu": "Fon Kodu", "fonUnvan": "Fon Adı", "getiri1a": "1 Ay (%)",
                    "getiri1y": "1 Yıl (%)", "riskDegeri": "Fonun Risk Değeri"}
TEFAS_WEB_FUNDS = [
    {"fonKodu": "AAL", "fonUnvan": "ATA PORTFÖY PARA PİYASASI (TL) FONU",
     "fonTurAciklama": "Para Piyasası Şemsiye Fonu", "getiri1a": 3.005, "getiri3a": 8.352,
     "getiri6a": 17.7082, "getiri1y": 42.2491, "getiriyb": 29.7921, "getiri3y": 247.7674,
     "getiri5y": 406.9754, "getiriOrani": None, "riskDegeri": "1"},
    {"fonKodu": "IGL", "fonUnvan": "TEB PORTFÖY ING BANK PARA PİYASASI (TL) FONU",
     "fonTurAciklama": "Para Piyasası Şemsiye Fonu", "getiri1a": 3, "getiri3a": None,
     "getiri6a": None, "getiri1y": None, "getiriyb": 28.1, "getiri3y": None,
     "getiri5y": None, "getiriOrani": None, "riskDegeri": "-"},
    {"fonKodu": "ZZZ", "fonUnvan": "ÖRNEK HİSSE \"YOĞUN\" FONU",
     "fonTurAciklama": "Hisse Senedi Şemsiye Fonu", "getiri1a": -8.8392, "getiri3a": -3.2854,
     "getiri6a": 5.4855, "getiri1y": 31.0107, "getiriyb": 24.0088, "getiri3y": 57.8985,
     "getiri5y": 1114.1215, "getiriOrani": None, "riskDegeri": "6"},
]


def tefas_web_page(funds=TEFAS_WEB_FUNDS, chunks=3) -> bytes:
    """HTML shaped like tefas.gov.tr/tr/fon-getirileri: the data is a JSON text
    split over several `self.__next_f.push([1, "..."])` script chunks, with a
    row of column titles before the funds."""
    payload = '1a:["$","div",null,' + json.dumps(
        {"columns": TEFAS_WEB_LABELS, "rows": funds}, ensure_ascii=False) + "]\n"
    size = len(payload) // chunks + 1
    parts = [payload[i:i + size] for i in range(0, len(payload), size)]
    scripts = "".join(f"<script>self.__next_f.push({json.dumps([1, p], ensure_ascii=False)})</script>"
                      for p in parts)
    return f"<!DOCTYPE html><html><body>{scripts}</body></html>".encode("utf-8")


DETAIL_PATH = "/tr/fon-detayli-analiz/"


@functools.lru_cache(maxsize=None)
def _real_detail_page(fixture: str) -> str:
    return gzip.decompress((FIXTURES / "tefas_detail" / f"{fixture}.html.gz").read_bytes()).decode()


def detail_page(fixture: str, code: str | None = None, **fields) -> bytes:
    """A real TEFAS fund detail page (fixtures: ZBJ money market, MAC equity, IPB
    variable; fetched 2026-10-10, all with null fees; trade on TEFAS), ABU (not
    on TEFAS, null valör) and AC4 (closed for purchase and redemption), the last
    two from the first live run, snapshot 20261010-161537-9555). `code` renames the fund;
    `fields` set values in the page data (bilgiData/profilData), e.g.
    girisKomisyonu=1.5. The data is JSON inside JS string literals, so quotes
    in the page text are escaped as \\"."""
    html = _real_detail_page(fixture)
    if code:
        html = html.replace(f'\\"fonKodu\\":\\"{fixture}\\"', f'\\"fonKodu\\":\\"{code}\\"')
    for name, value in fields.items():
        new = json.dumps(value, ensure_ascii=False).replace('"', '\\"')
        html, n = re.subn(rf'(\\"{name}\\":)(null|-?[0-9.]+|\\"[^\\"]*\\")',
                          lambda m: m[1] + new, html)
        assert n, name
    return html.encode("utf-8")


_VARLIK_RE = re.compile(r',\\"varlikData\\":\[[^\]]*\]')


def set_varlik(page: bytes, rows: list[dict] | None) -> bytes:
    """A detail page with its varlikData list replaced by `rows` (I8); None
    removes the key. Quotes are escaped as in the page (see detail_page)."""
    html = page.decode("utf-8")
    new = "" if rows is None else ',"varlikData":' + json.dumps(rows, ensure_ascii=False)
    html, n = _VARLIK_RE.subn(lambda m: new.replace('"', '\\"'), html)
    assert n == 1
    return html.encode("utf-8")


def holding(code: str, kind: str, share) -> dict:
    """One varlikData row as on the page."""
    return {"fonKodu": code, "fonUnvan": "ÖRNEK FON", "kiymetTip": kind, "portfoyOrani": share}


TEST_HOLDINGS_QUANTITY = {"unit": "pct", "max_age_days": 5, "min": -100, "max": 200,
                          "conflict_tolerance": 0.01}


def add_holdings(config_raw: dict) -> dict:
    """config_raw with the I8 holdings rows switched on for tefas_detail."""
    config_raw["quantities"].setdefault("fund_holding_share",
                                        copy.deepcopy(TEST_HOLDINGS_QUANTITY))
    config_raw["sources"]["tefas_detail"]["holdings_quantity"] = "fund_holding_share"
    return config_raw


def default_detail_pages() -> dict[str, bytes]:
    """Detail pages for the three funds of the fixture tefas_web page."""
    return {"AAL": detail_page("ZBJ", "AAL"), "IGL": detail_page("IPB", "IGL"),
            "ZZZ": detail_page("MAC", "ZZZ")}


# I10: exchange-traded funds as on /tr/fon-getirileri?fundType=BYF (probe
# 2026-10-14: the same embedded data as the fund page; risk missing for one).
BYF_URL = "https://www.tefas.gov.tr/tr/fon-getirileri?fundType=BYF"
TEFAS_BYF_FUNDS = [
    {"fonKodu": "BOE", "fonUnvan": "ÖRNEK PORTFÖY BIST 30 ENDEKSİ HİSSE SENEDİ YOĞUN BORSA YATIRIM FONU",
     "fonTurAciklama": "Hisse Senedi Yoğun", "getiri1a": 2.5, "getiri3a": 6.1,
     "getiri6a": 12.0, "getiri1y": 35.2, "getiriyb": 20.4, "getiri3y": 180.0,
     "getiri5y": None, "getiriOrani": None, "riskDegeri": "6"},
    {"fonKodu": "GLD", "fonUnvan": "ÖRNEK PORTFÖY ALTIN BORSA YATIRIM FONU",
     "fonTurAciklama": "Endeks Fon", "getiri1a": 4.0, "getiri3a": None, "getiri6a": None,
     "getiri1y": 50.1, "getiriyb": 40.0, "getiri3y": None, "getiri5y": None,
     "getiriOrani": None, "riskDegeri": None},
]


def add_byf(config_raw: dict) -> dict:
    """config_raw with the I10 BYF source (a copy of tefas_web with the BYF URL)
    and tefas_detail reading the fund lists of both sources."""
    byf = copy.deepcopy(config_raw["sources"]["tefas_web"])
    byf.update(url=BYF_URL, source_url=BYF_URL, min_funds=2)
    config_raw["sources"]["tefas_byf"] = byf
    config_raw["sources"]["tefas_detail"]["funds_from"] = ["tefas_web", "tefas_byf"]
    return config_raw


# --- Borsa İstanbul end-of-day bulletins (I11) ------------------------------------------------

BIST_URL = "https://www.borsaistanbul.com/data/thb/{yyyy}/{mm}/thb{yyyymmdd}1.zip"
# The real header lines (TR, EN) and four real rows of the 13.10.2026 bulletin:
# AEFES, THYAO (shares), APBDL (ETF), one warrant. LF line ends, UTF-8 with BOM.
BIST_SAMPLE = FIXTURES / "bist_bulletin" / "thb202610131_sample.csv"
BIST_END = date(2026, 10, 8)              # the newest test bulletin, the day before T0
BIST_HOLIDAY = date(2026, 9, 15)          # a weekday without a bulletin (HTTP 404)
BIST_SPLIT_INDEX = 40                     # BBB: 2-for-1 split on its 41st trading day


def bist_header() -> list[str]:
    return BIST_SAMPLE.read_text(encoding="utf-8-sig").splitlines()[:2]


def bist_name(day: date) -> str:
    return f"thb{day:%Y%m%d}1.zip"


def bist_trading_days(end: date = BIST_END, n: int = 60) -> list[date]:
    """The last n weekdays up to `end`, without BIST_HOLIDAY, oldest first."""
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5 and d != BIST_HOLIDAY:
            days.append(d)
        d -= timedelta(days=1)
    return days[::-1]


def bist_row(day: date, code: str, name: str, close, prev_close, *, group="EQT",
             pazar="Z", bist100=0, volume=1000.0) -> dict[str, str]:
    return {"TARIH": day.isoformat(), "ISLEM  KODU": code, "BULTEN ADI": name,
            "PAZAR": pazar, "ENSTRUMAN GRUBU": group, "BIST 100 ENDEKS": str(bist100),
            "ONCEKI KAPANIS FIYATI": str(prev_close), "KAPANIS FIYATI": str(close),
            "TOPLAM ISLEM HACMI": str(volume)}


def bulletin_zip(day: date, rows: list[dict[str, str]], header: list[str] | None = None) -> bytes:
    """A bulletin ZIP as published: one CSV, `;`, UTF-8 with BOM, two header
    lines, LF line ends. Columns not in a row are "0". Deterministic bytes."""
    header = header or bist_header()
    cols = header[0].split(";")
    lines = header + [";".join(r.get(c, "0") for c in cols) for r in rows]
    csv = ("﻿" + "\n".join(lines) + "\n").encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo(f"thb{day:%Y%m%d}1.csv", date_time=(2026, 1, 1, 0, 0, 0)), csv)
    return buf.getvalue()


def bist_closes(days: list[date] | None = None) -> dict[str, dict[date, tuple[float, float]]]:
    """Code -> day -> (close, previous close as published) of the test shares.
    AAA rises 0.2 % a day (BIST 100); BBB has a 2-for-1 split (the exchange
    publishes the previous close halved on the split day); CCC is flat and has
    no row on its 21st day (suspended)."""
    days = days or bist_trading_days()
    out: dict[str, dict[date, tuple[float, float]]] = {"AAA": {}, "BBB": {}, "CCC": {}}
    for k, d in enumerate(days):
        a = round(100 * 1.002 ** k, 4)
        out["AAA"][d] = (a, round(100 * 1.002 ** max(k - 1, 0), 4))
        b = round(50 + 0.1 * k, 4)
        b_prev = round(50 + 0.1 * max(k - 1, 0), 4)
        if k >= BIST_SPLIT_INDEX:
            b, b_prev = round(b / 2, 4), round(b_prev / 2, 4)
        out["BBB"][d] = (b, b_prev)
        if k != 20:
            out["CCC"][d] = (10.0, 10.0)
    return out


BIST_SHARES = {"AAA": ("AAA HOLDING", "Z", 1, 1_000_000.0), "BBB": ("BBB SANAYI", "N", 0, 500_000.0),
               "CCC": ("CCC GIDA", "T", 0, 10_000.0)}


def bist_history(days: list[date] | None = None) -> dict[str, bytes]:
    """File name -> bulletin ZIP for the test trading days. Each bulletin also
    has rows that are not used: an ETF, a warrant, and a share without a close."""
    days = days or bist_trading_days()
    closes = bist_closes(days)
    files = {}
    for d in days:
        rows = [bist_row(d, f"{code}.E", name, *closes[code][d], pazar=pazar, bist100=b100,
                         volume=vol)
                for code, (name, pazar, b100, vol) in BIST_SHARES.items() if d in closes[code]]
        rows += [bist_row(d, "XETF.F", "ORNEK BYF", 12.5, 12.4, group="ETF"),
                 bist_row(d, "WWW.V", "ORNEK VARANT", 0.02, 0.01, group="ECW"),
                 bist_row(d, "ZERO.E", "ISLEM GORMEYEN", 0, 5.0)]
        files[bist_name(d)] = bulletin_zip(d, rows)
    return files


@functools.lru_cache(maxsize=1)
def _default_bist_files() -> dict[str, bytes]:
    return bist_history()                         # shared; tests must not change it


TEST_BIST_QUANTITIES = {
    "stock_close": {"unit": "TRY", "max_age_days": 5, "min": 0.01, "max": 1e6,
                    "conflict_tolerance": 0.0},
    **{f"stock_return_{p}": {"unit": "pct", "max_age_days": 5, "min": -100, "max": 10000,
                             "conflict_tolerance": 0.0} for p in ("1m", "3m", "6m", "1y")},
    "stock_volatility_1y": {"unit": "pct", "max_age_days": 5, "min": 0, "max": 500,
                            "conflict_tolerance": 0.0},
    "stock_turnover_3m": {"unit": "TRY", "max_age_days": 5, "min": 0, "max": 1e15,
                          "conflict_tolerance": 0.0},
    "stock_bist100": {"unit": "flag", "max_age_days": 5, "min": 0, "max": 1,
                      "conflict_tolerance": 0.0},
}
TEST_BIST_SOURCE = {
    "adapter": "bist_bulletin", "enabled": True, "on_failure": "previous",
    "source_url": "https://www.borsaistanbul.com/tr/sayfa/2412/gunluk-bulten",
    "tos_note": "test copy of the bist_bulletin source",
    "url": BIST_URL,
    "user_agent": "rmprep-hackathon-prototype/0.1 (ING hackathon; test)",
    "timeout_seconds": 30, "history_days": 90, "min_interval_s": 1.0, "recheck_days": 3,
    "min_shares": 2,
}


def add_bist(config_raw: dict) -> dict:
    """config_raw with the I11 bist_bulletin source and its quantities."""
    for name, q in TEST_BIST_QUANTITIES.items():
        config_raw["quantities"].setdefault(name, copy.deepcopy(q))
    config_raw["sources"]["bist_bulletin"] = copy.deepcopy(TEST_BIST_SOURCE)
    return config_raw


class FakeEvds:
    """httpx transport that serves fixture files and records requests. Also
    serves the TEFAS web page (tefas_page=None -> HTTP 503 for it), the BYF
    view of it (byf_page, same rule) and the BIST bulletins (bist_files: file
    name -> ZIP; others -> HTTP 404)."""

    def __init__(self, status=200, body=None, error=None, tefas_page=b"default",
                 detail_pages=None, byf_page=b"default", bist_files=None):
        self.status, self.body, self.error = status, body, error
        self.bist_files = bist_files                # None -> _default_bist_files()
        self.tefas_page = tefas_web_page() if tefas_page == b"default" else tefas_page
        self.byf_page = tefas_web_page(TEFAS_BYF_FUNDS) if byf_page == b"default" else byf_page
        # fund code -> detail page bytes; a code without a page gives HTTP 404
        self.detail_pages = default_detail_pages() if detail_pages is None else detail_pages
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "www.borsaistanbul.com":
            files = _default_bist_files() if self.bist_files is None else self.bist_files
            data = files.get(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(404) if data is None else httpx.Response(200, content=data)
        if request.url.host == "www.tefas.gov.tr":
            if request.url.path.startswith(DETAIL_PATH):
                page = self.detail_pages.get(request.url.path[len(DETAIL_PATH):])
                return httpx.Response(404) if page is None else httpx.Response(200, content=page)
            page = self.byf_page if request.url.params.get("fundType") == "BYF" else self.tefas_page
            if page is None:
                return httpx.Response(503)
            return httpx.Response(200, content=page)
        if self.error:
            raise self.error
        if self.body is not None:
            return httpx.Response(self.status, content=self.body)
        code = re.search(r"series=([^&]+)&", str(request.url))[1]
        path = FIXTURES / "evds" / f"{code}.json"
        if not path.exists():
            return httpx.Response(404)
        return httpx.Response(self.status, content=path.read_bytes())

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


# Fixed EVDS series for tests, so tests do not change when the real codes in
# config/sources.yaml change. Two real codes (fixtures exist) + two placeholders.
TEST_EVDS_SERIES = [
    {"code": "TP.DK.USD.A.YTL", "quantity": "usd_try", "entity": "USD/TRY CBRT buying rate",
     "frequency": "daily", "verified": False},
    {"code": "TP.FG.J0", "quantity": "cpi_index", "entity": "CPI general index (2003=100)",
     "frequency": "monthly", "verified": False},
    {"code": "VERIFY_POLICY_RATE", "quantity": "policy_rate",
     "entity": "CBRT one-week repo rate", "frequency": "daily", "verified": False},
    {"code": "VERIFY_DEPOSIT_RATE_TRY", "quantity": "deposit_rate",
     "entity": "TRY deposit rate, weighted average", "frequency": "weekly", "verified": False},
]

# I5: the 2025=100 CPI series with 13 months (2025-9 .. 2026-9) and its annual
# change. Index 105.78 (2025-9) and 137.23 (2026-9), as checked on 2026-10-14.
CPI_CODE = "TP.TUKFIY2025.GENEL"
CPI_ANNUAL_ENTITY = "TÜFE yıllık değişim (TÜİK)"
TEST_CPI_ANNUAL_QUANTITY = {"unit": "pct", "max_age_days": 45, "min": -50, "max": 500,
                            "conflict_tolerance": 0.01}
TEST_CPI_SERIES = {
    "code": CPI_CODE, "quantity": "cpi_index", "entity": "CPI general index (2025=100)",
    "frequency": "monthly", "verified": True, "lookback_days": 400,
    "annual_change": {"quantity": "cpi_annual", "entity": CPI_ANNUAL_ENTITY},
}


def add_cpi_annual(config_raw: dict) -> dict:
    """config_raw with the I5 CPI series added as the last EVDS series."""
    config_raw["quantities"].setdefault("cpi_annual", copy.deepcopy(TEST_CPI_ANNUAL_QUANTITY))
    config_raw["sources"]["evds"]["series"].append(copy.deepcopy(TEST_CPI_SERIES))
    return config_raw


# tefas_detail source and its quantities for tests, so tests do not depend on
# whether (or how) config/sources.yaml has them.
TEST_DETAIL_QUANTITIES = {
    "fund_buy_valor_days": {"unit": "days", "max_age_days": 5, "min": 0, "max": 30,
                            "conflict_tolerance": 0.0},
    "fund_sell_valor_days": {"unit": "days", "max_age_days": 5, "min": 0, "max": 30,
                             "conflict_tolerance": 0.0},
    "fund_entry_fee": {"unit": "pct", "max_age_days": 5, "min": 0, "max": 20,
                       "conflict_tolerance": 0.0},
    "fund_exit_fee": {"unit": "pct", "max_age_days": 5, "min": 0, "max": 20,
                      "conflict_tolerance": 0.0},
    "fund_buyable": {"unit": "flag", "max_age_days": 5, "min": 0, "max": 1,
                     "conflict_tolerance": 0.0},
}
TEST_TEFAS_DETAIL = {
    "adapter": "tefas_detail", "enabled": True, "on_failure": "previous",
    "source_url": "https://www.tefas.gov.tr/tr/fon-detayli-analiz",
    "tos_note": "test copy of the tefas_detail source",
    "url": "https://www.tefas.gov.tr/tr/fon-detayli-analiz/{code}",
    "user_agent": "rmprep-hackathon-prototype/0.1 (ING hackathon; test)",
    "timeout_seconds": 30, "min_interval_s": 1.0, "max_fail_share": 0.05,
    "funds_from": "tefas_web", "exclude_categories": ["Serbest Şemsiye Fonu"],
    "flag_needs_check": True,
    "value_fields": {
        "bilgiData.sonFiyat": "fund_price",
        "bilgiData.portBuyukluk": "fund_total_value",
        "bilgiData.yatirimciSayi": "fund_investor_count",
    },
    "optional_fields": {
        "profilData.fonGeriAlisValor": "fund_buy_valor_days",
        "profilData.fonSatisValor": "fund_sell_valor_days",
        "profilData.riskDegeri": "fund_risk_level",
        "profilData.girisKomisyonu": "fund_entry_fee",
        "profilData.cikisKomisyonu": "fund_exit_fee",
    },
    "status": {
        "field": "profilData.tefasDurum",
        "quantity": "fund_buyable",
        "map": {"TEFAS'ta işlem görüyor": 1, "TEFAS'ta işlem görmüyor": 0,
                "Fon Alımına Kapalı, Fon Bozumuna Kapalı": 0,
                "Platformda İşlem Görmüyor": 0},          # BYF on the exchange (I10)
    },
}


@pytest.fixture
def config_raw():
    raw = copy.deepcopy(load_raw(PROJECT / "config" / "sources.yaml"))
    raw["sources"]["evds"]["series"] = copy.deepcopy(TEST_EVDS_SERIES)
    raw["sources"]["tefas_web"]["min_funds"] = 2     # the fixture page has 3 funds
    # The hand export source is off in the real config (2026-10-10; tefas_detail
    # gives the same values), but its adapter stays usable: tests keep it on.
    raw["sources"]["tefas"]["enabled"] = True
    # Sources added to the real config later (I10, I11) have their own fixtures;
    # the end-to-end tests keep the source list they were written for.
    for name in ("tefas_byf", "bist_bulletin"):
        raw["sources"].pop(name, None)
    if isinstance(raw["sources"].get("tefas_detail", {}).get("funds_from"), list):
        raw["sources"]["tefas_detail"]["funds_from"] = "tefas_web"
    for name, q in TEST_DETAIL_QUANTITIES.items():
        raw["quantities"].setdefault(name, copy.deepcopy(q))
    raw["sources"]["tefas_detail"] = copy.deepcopy(TEST_TEFAS_DETAIL)
    return raw


@pytest.fixture
def cfg(config_raw):
    return parse_config(config_raw)
