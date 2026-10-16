"""I16: links to the official fund documents on the fund managers' own sites."""

import copy
import gzip
import json
from datetime import date, datetime, timedelta

import httpx
import pytest
import yaml

from tests.ingest.conftest import FIXTURES
from rmprep.contracts import TR_TZ
from rmprep.ingest import fund_docs as fd
from rmprep.ingest.config import ConfigError

FD = FIXTURES / "fund_docs"
YAML = FD / "fund_docs.yaml"
NOW = datetime(2026, 10, 16, 15, 0, tzinfo=TR_TZ)


def _page(path: str) -> bytes:
    return gzip.decompress((FD / path).read_bytes())


NUROL = "https://www.nurolportfoy.com.tr"
KUVEYT = "https://www.kuveytturkportfoy.com.tr"
SITE_PAGES = {
    f"{NUROL}/": "nurol/home.html.gz",
    f"{NUROL}/yatirim-fonlari": "nurol/list.html.gz",
    f"{NUROL}/yatirim-fonlari/para-piyasasi-fonu": "nurol/ppn.html.gz",
    "https://www.osmanliportfoy.com.tr/surekli-bilgilendirme-formu": "osmanli/sbf.html.gz",
    "https://astraportfoy.com.tr/astra-portfoy-fon-eib": "astra/eib.html.gz",
    "https://www.oyakportfoy.com.tr/fon-bilgilendirme-dokumanlari-fon-izahnameleri":
        "oyak/izah.html.gz",
    "https://www.oyakportfoy.com.tr/fon-bilgilendirme-dokumanlari-yatirimci-bilgi-formu":
        "oyak/ybf.html.gz",
    "https://www.akportfoy.com.tr/tr/fon/AIS-ak-portfoy-para-piyasasi-katilim-fonu": "ak/ais.html.gz",
    f"{KUVEYT}/yatirim-evreni/yatirim-fonlari/": "kuveyt/fonlar.html.gz",
    f"{KUVEYT}/yatirim-evreni/yatirim-fonlari/kiymetli-madenler/kut/": "kuveyt/kut.html.gz",
    "https://www.tebportfoy.com.tr/yatirim-fonlari": "teb/fonlar.html.gz",
    "https://www.tebportfoy.com.tr/yatirim-fonlari/teb-portfoy-altin-fonu": "teb/tua.html.gz",
    "https://www.rotaportfoy.com.tr/fon-dunyasi/": "rota/list.html.gz",
    "https://www.rotaportfoy.com.tr/fon-dunyasi/para-piyasasi-fonlari/rpp/": "rota/rpp.html.gz",
    "https://www.garantibbvaportfoy.com.tr/": "garanti/home.html.gz",
    "https://www.garantibbvaportfoy.com.tr/gumus-fon-sepeti-fonu": "garanti/gtz.html.gz",
}
REDIRECTS = {"https://www.akportfoy.com.tr/tr/fon/AIS":
             "/tr/fon/AIS-ak-portfoy-para-piyasasi-katilim-fonu"}


class FakeSites:
    """The saved pages of 2026-10-16 by URL; others give HTTP 404. `override`:
    URL -> httpx.Response (or an exception to raise)."""

    def __init__(self, override=None):
        self.override = override or {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url in self.override:
            r = self.override[url]
            if isinstance(r, Exception):
                raise r
            return r
        if url in REDIRECTS:
            return httpx.Response(302, headers={"Location": REDIRECTS[url]})
        if url in SITE_PAGES:
            return httpx.Response(200, content=_page(SITE_PAGES[url]),
                                  headers={"Content-Type": "text/html; charset=utf-8"})
        return httpx.Response(404, text="not found", headers={"Content-Type": "text/html"})

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self))

    @property
    def urls(self):
        return [str(r.url) for r in self.requests]


class Clock:
    def __init__(self):
        self.t, self.sleeps = 1000.0, []

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


@pytest.fixture(autouse=True)
def _fresh_hosts():
    fd.reset_hosts()          # the per-host state is module-wide (several RMs)
    yield
    fd.reset_hosts()


@pytest.fixture
def cfg():
    return fd.load_config(YAML)


def _raw():
    return yaml.safe_load(YAML.read_text(encoding="utf-8"))


def find(code, issuer, cfg, tmp_path, fake=None, now=NOW, clock=None):
    fake = fake or FakeSites()
    clock = clock or Clock()
    res = fd.find_documents(code, issuer, cfg, client=fake.client(), now=lambda: now,
                            sleep=clock.sleep, cache_dir=tmp_path / "cache",
                            monotonic=clock.monotonic)
    return res, fake, clock


def _docs(res):
    return {d.kind: (d.url, d.date) for d in res.docs}


# --- config ---------------------------------------------------------------------------------

def test_config_loads(cfg):
    assert [m.key for m in cfg.managers] == ["nurol", "osmanli", "astra", "oyak", "ak", "kuveyt",
                                            "teb", "rota", "garanti"]
    assert {m.key: m.verdict for m in cfg.managers}["teb"] == "link_only"
    assert cfg.max_requests == 3 and cfg.delay_seconds == 2
    assert cfg.user_agent.endswith("(ING hackathon; on demand, one fund page per fund per day)")
    assert len(cfg.not_covered) == 3


@pytest.mark.parametrize("change,match", [
    (lambda r: r.update(extra=1), r"unknown key\(s\) \['extra'\]"),
    (lambda r: r["managers"][0].update(verdict="maybe"), r"managers\[0\]\.verdict: must be one of"),
    (lambda r: r["managers"][0]["fund_page"].update(template="https://x/{code}"),
     r"managers\[0\]\.fund_page: exactly one of"),
    (lambda r: r["managers"][0]["docs"][0].pop("path"),
     r"managers\[0\]\.docs\[0\]: needs at least one of label, before, path"),
    (lambda r: r["managers"][0]["docs"][0].update(path="(unclosed"),
     r"managers\[0\]\.docs\[0\]\.path: bad regex"),
    (lambda r: r["managers"][3]["docs"][0].update(page=5), r"managers\[3\]\.docs\[0\]\.page"),
    (lambda r: r["managers"][0].update(dates=["(?P<y>\\d{4})"]),
     r"managers\[0\]\.dates\[0\]: needs the groups d, m, y"),
    (lambda r: r["managers"][0].update(site="http://www.nurolportfoy.com.tr"),
     r"managers\[0\]\.site: must be an https URL"),
    (lambda r: r["managers"][0]["docs"][0].update(kind="kid"), r"docs\[0\]\.kind: must be one of"),
    (lambda r: r["managers"][1].update(issuers=["Nurol Portföy"]),
     r"issuer 'Nurol Portföy' is listed twice"),
    (lambda r: r["not_covered"][0]["reason"].pop("en"), r"not_covered\[0\]\.reason: missing"),
])
def test_config_rejects_bad_values(change, match):
    import re
    raw = _raw()
    change(raw)
    with pytest.raises(ConfigError) as e:
        fd.parse_config(raw)
    assert re.search(match, str(e.value))


# --- one example fund per manager (the URLs of the check table) -------------------------------

EXAMPLES = [
    ("PPN", "Nurol Portföy", "ok",
     ("https://cdn.nurolportfoy.com.tr/Documents/310-ppn-tl--izahnamesi-04-02-2025.pdf",
      date(2025, 2, 4)),
     ("https://cdn.nurolportfoy.com.tr/Documents/307-ppn-izahname-yatirimci-bilgi-formu.pdf",
      None),
     f"{NUROL}/yatirim-fonlari/para-piyasasi-fonu", 2),
    ("OSD", "Osmanlı Portföy", "ok",
     ("https://www.osmanliportfoy.com.tr/upload/CmsPage/OSD_izahname_22226_c1c6c4.pdf", None),
     ("https://www.osmanliportfoy.com.tr/upload/CmsPage/OSD_Yatirimci_Bilgi_Formu_22226_bb7d72.pdf",
      None),
     "https://www.osmanliportfoy.com.tr/surekli-bilgilendirme-formu", 1),
    ("EIB", "Astra Portföy", "ok",
     ("https://astraportfoy.com.tr/uploads/fund-reports/eib/Izahname-EIB_05.12.2025.pdf",
      date(2025, 12, 5)),
     ("https://astraportfoy.com.tr/uploads/fund-reports/eib/Yatirimci-bilgi-formu-EIB_05.12.2025.pdf",
      date(2025, 12, 5)),
     "https://astraportfoy.com.tr/astra-portfoy-fon-eib", 1),
    ("OKT", "Oyak Portföy", "ok",
     ("https://www.oyakportfoy.com.tr/files/pdf/"
      "6788c057-f111-41f5-b7a6-d7a482eac9c4-11-10-2025-12-34-18-.pdf", date(2025, 11, 10)),
     ("https://www.oyakportfoy.com.tr/files/pdf/"
      "4dd214aa-15f2-4c92-9f43-280a451b4407-02-20-2026-12-59-3-.pdf", date(2026, 2, 20)),
     "https://www.oyakportfoy.com.tr/fon-bilgilendirme-dokumanlari-fon-izahnameleri", 2),
    ("AIS", "Ak Portföy", "ok",
     ("https://www.akportfoy.com.tr/doc/6237", None),
     ("https://www.akportfoy.com.tr/doc/5787", None),
     "https://www.akportfoy.com.tr/tr/fon/AIS-ak-portfoy-para-piyasasi-katilim-fonu", 2),
    ("KUT", "Kuveyt Türk Portföy", "ok",
     (f"{KUVEYT}/media/jheljryh/kut-kuveyt-tuerk-portfoey-k%C4%B1ymetli-madenler-kat%C4%B1l%C4%B1m-"
      "fonu-13072026.pdf", date(2026, 7, 13)),
     (f"{KUVEYT}/media/5k3coafn/yat%C4%B1r%C4%B1mc%C4%B1-bilgi-formu.pdf", None),
     f"{KUVEYT}/yatirim-evreni/yatirim-fonlari/kiymetli-madenler/kut/", 2),
    ("TUA", "TEB Portföy", "link_only",
     ("https://www.tebportfoy.com.tr/medium/FundDocument-File-1865.vsf", None),
     ("https://www.tebportfoy.com.tr/medium/FundDocument-File-1870.vsf", None),
     "https://www.tebportfoy.com.tr/yatirim-fonlari/teb-portfoy-altin-fonu", 2),
    ("RPP", "Rota Portföy", "link_only",
     ("https://www.rotaportfoy.com.tr/media/ipqn5hkg/rota-portfoy-para-piyasasi-tl-fonu-"
      "izahnamesi.pdf", None),
     ("https://www.rotaportfoy.com.tr/media/1vzh3l1f/para-piyasasi-tl-fonu_ybf-21112025.pdf",
      date(2025, 11, 21)),
     "https://www.rotaportfoy.com.tr/fon-dunyasi/para-piyasasi-fonlari/rpp/", 2),
    ("GTZ", "Garanti Portföy", "link_only",
     ("https://www.garantibbvaportfoy.com.tr/assets/gtz_izahname__20260306.pdf", date(2026, 3, 6)),
     ("https://www.garantibbvaportfoy.com.tr/assets/gtz_yat_bilgi_20260313.pdf", date(2026, 3, 13)),
     "https://www.garantibbvaportfoy.com.tr/gumus-fon-sepeti-fonu", 2),
]


@pytest.mark.parametrize("code,issuer,verdict,izahname,ybf,page_url,requests", EXAMPLES,
                         ids=[e[0] for e in EXAMPLES])
def test_example_fund(tmp_path, cfg, code, issuer, verdict, izahname, ybf, page_url, requests):
    res, fake, _ = find(code, issuer, cfg, tmp_path)
    assert res.status == "ok", res.reason
    assert res.verdict == verdict and res.code == code
    assert _docs(res) == {"izahname": izahname, "ybf": ybf}
    assert res.page_url == page_url
    assert len(fake.requests) == requests
    assert all(not u.lower().endswith(".pdf") for u in fake.urls)      # never a PDF
    assert res.checked_at == NOW and len(res.page_sha256) == 64 and res.reason is None


def test_labels_are_kept_as_on_the_page(tmp_path, cfg):
    res, _, _ = find("TUA", "TEB Portföy", cfg, tmp_path)
    assert {d.kind: d.label for d in res.docs} == {"izahname": "PDF Görüntüle",
                                                   "ybf": "PDF Görüntüle"}
    res, _, _ = find("OSD", "Osmanlı Portföy", cfg, tmp_path)
    assert {d.kind: d.label for d in res.docs}["ybf"] == "OSD Yatırımcı Bilgi Formu"


def test_nurol_second_lookup_page(tmp_path, cfg):
    # NJG is not on the home cards; the list page has it in its page data.
    fake = FakeSites({f"{NUROL}/yatirim-fonlari/birinci-serbest-fon":
                      httpx.Response(200, content=_page("nurol/ppn.html.gz").replace(b"-ppn-", b"-njg-"),
                                     headers={"Content-Type": "text/html"})})
    res, fake, _ = find("NJG", "Nurol Portföy", cfg, tmp_path, fake)
    assert fake.urls == [f"{NUROL}/", f"{NUROL}/yatirim-fonlari",
                         f"{NUROL}/yatirim-fonlari/birinci-serbest-fon"]
    assert res.status == "ok" and res.page_url == f"{NUROL}/yatirim-fonlari/birinci-serbest-fon"


# --- the date rules -------------------------------------------------------------------------

def test_newest_dated_link_wins_else_the_first(tmp_path, cfg):
    page = ("<html><body>"
            "<a href='/Documents/1-ppn-izahname-01-07-2024.pdf'>a</a>"
            "<a href='/Documents/2-ppn-izahname-guncel.pdf'>b</a>"
            "<a href='/Documents/3-ppn-izahname-04-02-2025.pdf'>c</a>"
            "<a href='/Documents/4-ppn-yatirimci-bilgi-formu.pdf'>d</a>"
            "<a href='/Documents/5-ppn-yatirimci-bilgi-formu-spk.pdf'>e</a></body></html>")
    nurol = cfg.manager("nurol")
    docs = fd.select_docs(nurol, "PPN", [fd.read_links(page, f"{NUROL}/x")])
    assert {d.kind: (d.url.rsplit("/", 1)[1], d.date) for d in docs} == {
        "izahname": ("3-ppn-izahname-04-02-2025.pdf", date(2025, 2, 4)),
        "ybf": ("4-ppn-yatirimci-bilgi-formu.pdf", None)}


def test_pick_first_keeps_the_page_order(cfg):
    # Osmanlı lists the current document first; older versions have a date in
    # the label and the current one has none, so "newest by date" would be wrong.
    page = ("<a href='/upload/CmsPage/OSD_Yatirimci_Bilgi_Formu_22226_bb7d72.pdf'>"
            "OSD Yatırımcı Bilgi Formu</a>"
            "<a href='/upload/CmsPage/OSD_Yatirimci_Bilgi_Formu_36225_a955b.pdf'>"
            "OSD Yatırımcı Bilgi Formu 30.06.2025</a>")
    osmanli = cfg.manager("osmanli")
    assert osmanli.pick == "first" and cfg.manager("nurol").pick == "newest"
    [doc] = fd.select_docs(osmanli, "OSD",
                           [fd.read_links(page, "https://www.osmanliportfoy.com.tr/x")])
    assert doc.url.endswith("_22226_bb7d72.pdf") and doc.date is None
    [doc] = fd.select_docs(osmanli, "OSD",
                           [fd.read_links(page[page.index("<a", 1):],
                                          "https://www.osmanliportfoy.com.tr/x")])
    assert doc.date == date(2025, 6, 30)                 # the date is still read for the label


@pytest.mark.parametrize("key,text,expected", [
    ("osmanli", "PLR Yatırımcı Bilgi Formu 31.12.2025", date(2025, 12, 31)),
    ("oyak", "/files/pdf/abc-02-20-2026-12-59-3-.pdf", date(2026, 2, 20)),
    ("kuveyt", "/media/x/kut-fonu-13072026.pdf", date(2026, 7, 13)),
    ("garanti", "/assets/gtz_yat_bilgi_20260313.pdf", date(2026, 3, 13)),
    ("garanti", "/assets/gtz_yat_bilgi_20261313.pdf", None),           # not a date
    ("ak", "İzahname", None),
])
def test_date_rules(cfg, key, text, expected):
    assert fd.date_of(cfg.manager(key), text) == expected


# --- not_covered, not_found -----------------------------------------------------------------------

@pytest.mark.parametrize("issuer,word", [
    ("İş Portföy", "robots.txt"), ("Azimut PYŞ", "KAP"), ("Yapı Kredi Portföy", "betik"),
    ("Bilinmeyen Portföy", "kural yok"), ("", "kural yok")])
def test_not_covered_makes_no_request(tmp_path, cfg, issuer, word):
    res, fake, _ = find("XYZ", issuer, cfg, tmp_path)
    assert res.status == "not_covered" and fake.requests == []
    assert word in res.reason["tr"] and res.reason["en"]
    assert res.docs == () and res.page_url == ""


def test_not_found_on_a_shared_page(tmp_path, cfg):
    res, _, _ = find("ZZZ", "Osmanlı Portföy", cfg, tmp_path)
    assert res.status == "not_found" and res.docs == ()
    assert res.page_url == "https://www.osmanliportfoy.com.tr/surekli-bilgilendirme-formu"


def test_fund_not_in_the_list_is_not_found_with_the_list_page(tmp_path, cfg):
    res, fake, _ = find("ZZZ", "Kuveyt Türk Portföy", cfg, tmp_path)
    assert res.status == "not_found" and len(fake.requests) == 1
    assert res.page_url == f"{KUVEYT}/yatirim-evreni/yatirim-fonlari/"
    assert "listesinde" in res.reason["tr"]


def test_issuer_match_ignores_case_and_spaces(tmp_path, cfg):
    res, _, _ = find("EIB", "  astra   PORTFÖY ", cfg, tmp_path)
    assert res.status == "ok" and res.manager == "astra" and res.manager_label == "Astra Portföy"


# --- failed ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("status", [404, 403, 500])
def test_http_error_fails(tmp_path, cfg, status):
    fake = FakeSites({"https://astraportfoy.com.tr/astra-portfoy-fon-eib":
                      httpx.Response(status, headers={"Content-Type": "text/html"})})
    res, _, _ = find("EIB", "Astra Portföy", cfg, tmp_path, fake)
    assert res.status == "failed" and f"HTTP {status}" in res.reason["en"]


def test_connection_error_fails_and_never_raises(tmp_path, cfg):
    fake = FakeSites({"https://astraportfoy.com.tr/astra-portfoy-fon-eib":
                      httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED]")})
    res, _, _ = find("EIB", "Astra Portföy", cfg, tmp_path, fake)
    assert res.status == "failed" and "ConnectError" in res.reason["en"]


def test_unexpected_error_fails_and_never_raises(tmp_path, cfg):
    fake = FakeSites({"https://astraportfoy.com.tr/astra-portfoy-fon-eib": RuntimeError("boom")})
    res, _, _ = find("EIB", "Astra Portföy", cfg, tmp_path, fake)
    assert res.status == "failed" and "RuntimeError" in res.reason["en"]


def test_robots_disallowed_page_is_not_requested(tmp_path):
    raw = _raw()
    raw["managers"][2]["robots_disallow"] = ["/astra-portfoy-fon-"]
    res, fake, _ = find("EIB", "Astra Portföy", fd.parse_config(raw), tmp_path)
    assert res.status == "failed" and "robots.txt" in res.reason["en"] and fake.requests == []


def test_redirect_to_another_host_fails(tmp_path, cfg):
    fake = FakeSites({"https://astraportfoy.com.tr/astra-portfoy-fon-eib":
                      httpx.Response(301, headers={"Location": "https://www.kap.org.tr/x"})})
    res, fake, _ = find("EIB", "Astra Portföy", cfg, tmp_path, fake)
    assert res.status == "failed" and "another host" in res.reason["en"]
    assert len(fake.requests) == 1


def test_not_an_html_page_fails(tmp_path, cfg):
    fake = FakeSites({"https://astraportfoy.com.tr/astra-portfoy-fon-eib":
                      httpx.Response(200, content=b"%PDF-1.4", headers={"Content-Type":
                                                                        "application/pdf"})})
    res, _, _ = find("EIB", "Astra Portföy", cfg, tmp_path, fake)
    assert res.status == "failed" and "not an HTML page" in res.reason["en"]


def test_a_pdf_url_is_never_requested(tmp_path):
    raw = _raw()
    raw["managers"][2]["fund_page"]["template"] = "https://astraportfoy.com.tr/fon-{code}.pdf"
    res, fake, _ = find("EIB", "Astra Portföy", fd.parse_config(raw), tmp_path)
    assert res.status == "failed" and "PDF" in res.reason["en"] and fake.requests == []


def test_at_most_max_requests(tmp_path):
    raw = _raw()
    raw["max_requests"] = 1
    res, fake, _ = find("PPN", "Nurol Portföy", fd.parse_config(raw), tmp_path)
    assert res.status == "failed" and "more than 1 request" in res.reason["en"]
    assert len(fake.requests) == 1


# --- the host rule ---------------------------------------------------------------------------------

def test_links_to_other_hosts_are_ignored(cfg):
    page = ("<a href='https://www.kap.org.tr/Izahname-EIB_01.01.2026.pdf'>İzahname</a>"
            "<a href='https://mirror.example/uploads/fund-reports/eib/Izahname-EIB_02.02.2026.pdf'>x</a>"
            "<a href='/uploads/fund-reports/eib/Izahname-EIB_05.12.2025.pdf'>y</a>"
            "<a href='ftp://astraportfoy.com.tr/uploads/fund-reports/eib/Izahname-EIB_06.12.2025.pdf'>z</a>")
    docs = fd.select_docs(cfg.manager("astra"), "EIB",
                          [fd.read_links(page, "https://astraportfoy.com.tr/astra-portfoy-fon-eib")])
    assert [d.url for d in docs] == [
        "https://astraportfoy.com.tr/uploads/fund-reports/eib/Izahname-EIB_05.12.2025.pdf"]


def test_links_to_robots_disallowed_paths_are_ignored(cfg):
    # Nurol's "İndir" proxy is under /api/ (disallowed); the cdn link is used.
    page = ("<a href='/api/proxy/download?url=x-ppn-izahname-01-01-2026.pdf'>İndir</a>"
            "<a href='https://cdn.nurolportfoy.com.tr/Documents/9-ppn-izahname-01-01-2024.pdf'>v</a>")
    docs = fd.select_docs(cfg.manager("nurol"), "PPN", [fd.read_links(page, f"{NUROL}/x")])
    assert [d.url for d in docs] == ["https://cdn.nurolportfoy.com.tr/Documents/9-ppn-izahname-"
                                     "01-01-2024.pdf"]


# --- the cache -------------------------------------------------------------------------------------

def test_result_of_today_comes_from_the_cache(tmp_path, cfg):
    first, _, _ = find("EIB", "Astra Portföy", cfg, tmp_path)
    again, fake, _ = find("EIB", "Astra Portföy", cfg, tmp_path, now=NOW + timedelta(hours=3))
    assert fake.requests == [] and again == first
    assert (tmp_path / "cache" / "EIB-2026-10-16.json").is_file()


def test_another_day_asks_again(tmp_path, cfg):
    find("EIB", "Astra Portföy", cfg, tmp_path)
    res, fake, _ = find("EIB", "Astra Portföy", cfg, tmp_path, now=NOW + timedelta(days=1))
    assert len(fake.requests) == 1 and res.checked_at == NOW + timedelta(days=1)


def test_not_found_is_cached_and_failed_is_not(tmp_path, cfg):
    find("ZZZ", "Osmanlı Portföy", cfg, tmp_path)
    _, fake, _ = find("ZZZ", "Osmanlı Portföy", cfg, tmp_path)
    assert fake.requests == []
    bad = FakeSites({"https://astraportfoy.com.tr/astra-portfoy-fon-eib": httpx.Response(503)})
    find("EIB", "Astra Portföy", cfg, tmp_path, bad)
    res, fake, _ = find("EIB", "Astra Portföy", cfg, tmp_path)
    assert res.status == "ok" and len(fake.requests) == 1


def test_shared_list_page_is_cached_per_day(tmp_path, cfg):
    find("OKT", "Oyak Portföy", cfg, tmp_path)
    res, fake, _ = find("OBI", "Oyak Portföy", cfg, tmp_path)
    assert res.status == "ok" and fake.requests == []     # the second fund costs no request


def test_link_only_pages_are_not_stored(tmp_path, cfg):
    find("TUA", "TEB Portföy", cfg, tmp_path)
    stored = [p for p in (tmp_path / "cache").rglob("*") if p.is_file()]
    assert [p.name for p in stored] == ["TUA-2026-10-16.json"]   # the result: URLs and labels
    data = json.loads(stored[0].read_text(encoding="utf-8"))
    assert set(data) == {"code", "manager", "manager_label", "verdict", "status", "docs",
                         "page_url", "page_sha256", "checked_at", "reason"}


def test_cached_result_roundtrip(tmp_path, cfg):
    res, _, _ = find("GTZ", "Garanti Portföy", cfg, tmp_path)
    assert fd.FundDocs.from_json(json.loads(json.dumps(res.to_json()))) == res


# --- requests: the delay per host, the user agent ------------------------------------------------

def test_delay_between_two_requests_to_one_host(tmp_path, cfg):
    res, fake, clock = find("KUT", "Kuveyt Türk Portföy", cfg, tmp_path)
    assert res.status == "ok" and len(fake.requests) == 2
    assert clock.sleeps and clock.sleeps[0] == pytest.approx(2.0)
    assert all(r.headers["User-Agent"] == cfg.user_agent for r in fake.requests)


def test_delay_counts_across_calls_on_one_host(tmp_path, cfg):
    clock = Clock()
    find("OSD", "Osmanlı Portföy", cfg, tmp_path / "a", clock=clock)
    find("OSD", "Osmanlı Portföy", cfg, tmp_path / "b", clock=clock)   # another cache: a request
    assert clock.sleeps == [pytest.approx(2.0)]


def test_no_delay_for_another_host(tmp_path, cfg):
    clock = Clock()
    find("OSD", "Osmanlı Portföy", cfg, tmp_path, clock=clock)
    find("EIB", "Astra Portföy", cfg, tmp_path, clock=clock)
    assert clock.sleeps == []
