import copy
import functools
import gzip
import json
import re
from datetime import datetime
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


def default_detail_pages() -> dict[str, bytes]:
    """Detail pages for the three funds of the fixture tefas_web page."""
    return {"AAL": detail_page("ZBJ", "AAL"), "IGL": detail_page("IPB", "IGL"),
            "ZZZ": detail_page("MAC", "ZZZ")}


class FakeEvds:
    """httpx transport that serves fixture files and records requests. Also
    serves the TEFAS web page (tefas_page=None -> HTTP 503 for it)."""

    def __init__(self, status=200, body=None, error=None, tefas_page=b"default",
                 detail_pages=None):
        self.status, self.body, self.error = status, body, error
        self.tefas_page = tefas_web_page() if tefas_page == b"default" else tefas_page
        # fund code -> detail page bytes; a code without a page gives HTTP 404
        self.detail_pages = default_detail_pages() if detail_pages is None else detail_pages
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "www.tefas.gov.tr":
            if request.url.path.startswith(DETAIL_PATH):
                page = self.detail_pages.get(request.url.path[len(DETAIL_PATH):])
                return httpx.Response(404) if page is None else httpx.Response(200, content=page)
            if self.tefas_page is None:
                return httpx.Response(503)
            return httpx.Response(200, content=self.tefas_page)
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
                "Fon Alımına Kapalı, Fon Bozumuna Kapalı": 0},
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
    for name, q in TEST_DETAIL_QUANTITIES.items():
        raw["quantities"].setdefault(name, copy.deepcopy(q))
    raw["sources"]["tefas_detail"] = copy.deepcopy(TEST_TEFAS_DETAIL)
    return raw


@pytest.fixture
def cfg(config_raw):
    return parse_config(config_raw)
