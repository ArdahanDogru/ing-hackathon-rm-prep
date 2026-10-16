"""I14: source ing_web, ING's own public rate page (ASP.NET form postback)."""

import copy
from datetime import date, datetime

import httpx
import pytest

from tests.ingest.conftest import (
    FIXTURES,
    ING_PRODUCTS,
    ING_URL,
    TEST_ING_WEB,
    FakeEvds,
    FakeIng,
    add_ing_web,
    ing_hidden,
    ing_page,
)
from rmprep.contracts import TR_TZ, Flag
from rmprep.ingest.adapters import ing_web
from rmprep.ingest.config import ConfigError, IngWebSource, parse_config
from rmprep.ingest.snapshot import SnapshotWriter

T16 = datetime(2026, 10, 16, 15, 0, tzinfo=TR_TZ)       # the day of the saved pages
SID = "20261016-150000-0001"
EV, TU, KID, ACC = ING_PRODUCTS      # e-Vadeli, Turuncu, Turuncu Çocuk, e-Turuncu Biriktiren
EV_PAGE, TU_PAGE = ing_page(f"step3_{EV}"), ing_page(f"step3_{TU}")
MANUAL_NAMES = [line for line in (FIXTURES / "ing_web" / "manual_entities_20261016.txt")
                .read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]


@pytest.fixture
def icfg(config_raw):
    return parse_config(add_ing_web(config_raw))


def _fetch(tmp_path, cfg, fake=None):
    fake = fake or FakeIng()
    sleeps: list[float] = []
    src = cfg.sources["ing_web"]
    w = SnapshotWriter(tmp_path / "snaps", {}, created_at=T16, snapshot_id=SID)
    rec = ing_web.fetch(src, w, client=fake.client(), now=lambda: T16, sleep=sleeps.append)
    w.set_source("ing_web", rec)
    return rec, w.finalize(), fake, sleeps


def _points(tmp_path, cfg, fake=None):
    rec, snap, _, _ = _fetch(tmp_path, cfg, fake)
    assert rec.status == "ok", rec.error
    return ing_web.parse(cfg, cfg.sources["ing_web"], snap)


def _by_entity(points):
    return {p.entity: p for p in points}


# --- config ---------------------------------------------------------------------------------

def test_config_parses_source(icfg):
    src = icfg.sources["ing_web"]
    assert isinstance(src, IngWebSource)
    assert src.url == ING_URL and src.delay_seconds == 2 and src.quantity == "deposit_rate"
    assert src.form.currency_field == "5575$DdlCurrencyType" and src.form.currency == "0"
    assert [p.value for p in src.products] == list(ING_PRODUCTS)
    tu = src.products[1]
    assert tu.layout == "balance" and tu.rates == {"Standart Faiz": "standart",
                                                    "Hoş Geldin Faizi": "hoş geldin"}
    assert tu.balance_labels["9.999,99 'e kadar"] == "0-9.999,99 TL"


@pytest.mark.parametrize("url,match", [
    ("http://www.ing.com.tr/tr/bilgi-destek/mevduat/mevduat-faiz-oranlari", "https URL on"),
    ("https://www.example.com/tr/x", "https URL on"),
    ("https://www.ing.com.tr/documents/rates.pdf", "disallowed by ing.com.tr/robots.txt"),
    ("https://www.ing.com.tr/tr/arama/faiz", "disallowed by ing.com.tr/robots.txt"),
    ("https://www.ing.com.tr/tr/basvuru-tamam", "disallowed by ing.com.tr/robots.txt"),
])
def test_config_rejects_bad_url(config_raw, url, match):
    add_ing_web(config_raw)["sources"]["ing_web"]["url"] = url
    with pytest.raises(ConfigError, match=match):
        parse_config(config_raw)


def _bad(config_raw, change):
    raw = add_ing_web(config_raw)
    change(raw["sources"]["ing_web"])
    with pytest.raises(ConfigError) as e:
        parse_config(raw)
    return str(e.value)


def test_config_rejects_unknown_keys(config_raw):
    assert "sources.ing_web: unknown key(s) ['retries']" in _bad(
        config_raw, lambda s: s.update(retries=3))
    assert "sources.ing_web.form: unknown key(s) ['x']" in _bad(
        config_raw, lambda s: s["form"].update(x=1))
    assert "sources.ing_web.products[0]: unknown key(s) ['rates']" in _bad(
        config_raw, lambda s: s["products"][0].update(rates={"a": "b"}))


@pytest.mark.parametrize("change,match", [
    (lambda s: s["form"].pop("send_target"), r"form: missing key\(s\) \['send_target'\]"),
    (lambda s: s.update(products=[]), "products: must be a non-empty list"),
    (lambda s: s["products"][0].update(layout="list"), r"products\[0\]\.layout: must be one of"),
    (lambda s: s["products"][0].update(entity="ING {row}"),
     r"products\[0\]\.entity: must use exactly the fields \['column', 'row'\]"),
    (lambda s: s["products"][1].update(entity="ING {rate}, {row}"),
     r"products\[1\]\.entity: must use exactly the fields \['balance', 'rate'\]"),
    (lambda s: s["products"][1].update(rates={}), r"products\[1\]\.rates: must not be empty"),
    (lambda s: s["products"][0].update(min_rows=0), r"products\[0\]\.min_rows: must be a positive"),
    (lambda s: s["products"].append(copy.deepcopy(s["products"][0])),
     r"products\[4\]\.value: 'E_TIME_DEPOSIT_ACCOUNT' is listed twice"),
    (lambda s: s.update(quantity="gold_price"), "unknown quantity 'gold_price'"),
    (lambda s: s.update(delay_seconds=-1), "delay_seconds: must be >= 0"),
    (lambda s: s["products"][1].pop("rates"), r"products\[1\]: missing key\(s\) \['rates'\]"),
])
def test_config_rejects_bad_values(config_raw, change, match):
    import re
    assert re.search(match, _bad(config_raw, change))


@pytest.mark.parametrize("url,ok", [
    (ING_URL, True),
    ("https://www.ing.com.tr/assets/x.css", True),            # Allow: /assets/*.css
    ("https://www.ing.com.tr/assets/x.pdf", False),
    ("https://www.ing.com.tr/objects/a", False),
    ("https://www.ing.com.tr/tr/x-hata", False),
    ("https://www.ing.com.tr/tr/x-mim?a=1", False),
    ("https://www.ing.com.tr/tr/x?IsPreview=1", False),
    ("https://www.ing.com.tr/tr/sayfa1000", False),
    ("https://www.ing.com.tr/error-page", False),
    ("https://www.ing.com.tr/tr/search/x", False),
])
def test_check_url_allowed_follows_robots(url, ok):
    if ok:
        ing_web.check_url_allowed(url)
    else:
        with pytest.raises(ValueError, match="robots.txt"):
            ing_web.check_url_allowed(url)


# --- parse (the saved pages of 2026-10-16) ----------------------------------------------------

def test_parse_e_vadeli(tmp_path, icfg):
    pts = [p for p in _points(tmp_path, icfg) if p.entity.startswith("ING e-Vadeli")]
    assert len(pts) == 11 * 8
    rows = _by_entity(pts)
    p = rows["ING e-Vadeli Mevduat, 32-45 gün, 99.999,99-250.000 TL"]
    assert p.value == 34.5 and p.quantity == "deposit_rate" and p.unit == "pct"
    assert p.as_of == date(2026, 10, 16)
    assert p.source == "ing_web" and p.source_url == ING_URL and p.fetched_at == T16
    assert p.flags == frozenset()
    assert p.raw_ref == (f"{SID}/payloads/ing_web/{EV}.html#{EV};row=32-45 gün;"
                         f"column=99.999,99-250.000")
    assert p.note == ("16 Ekim 2026 itibariyle geçerli; ing.com.tr rate form, product "
                      "E_TIME_DEPOSIT_ACCOUNT; gross/net not stated")
    assert rows["ING e-Vadeli Mevduat, 7-15 gün, 4.999,99-99.999 TL"].value == 32.0
    assert rows["ING e-Vadeli Mevduat, 1-6 gün, 30.000.000 üzeri TL"].value == 5.0
    assert rows["ING e-Vadeli Mevduat, 366-370 gün, 999.999,99-1.999.999 TL"].value == 34.0


def test_parse_turuncu(tmp_path, icfg):
    pts = [p for p in _points(tmp_path, icfg) if p.entity.startswith("ING Turuncu Hesap ")]
    assert len(pts) == 14 * 2
    rows = _by_entity(pts)
    std = rows["ING Turuncu Hesap standart, 0-9.999,99 TL"]
    assert std.value == 23.0
    assert std.note == ("Standart Faiz; Faiz işletilmeyecek tutar 3.000 TL; 16 Ekim 2026 "
                        "itibariyle geçerli; ing.com.tr rate form, product "
                        "E_ORANGE_ACCOUNT_GROUP; gross/net not stated")
    welcome = rows["ING Turuncu Hesap hoş geldin, 100.000-249.999 TL"]
    assert welcome.value == 39.0
    assert welcome.note.startswith("Hoş Geldin Faizi; Faiz işletilmeyecek tutar 15.000 TL; ")
    assert welcome.raw_ref.endswith(f"#{TU};row=100.000-249.999;column=Hoş Geldin Faizi")
    assert rows["ING Turuncu Hesap hoş geldin, 35.000.000 TL üzeri"].value == 23.0
    assert {p.as_of for p in pts} == {date(2026, 10, 16)}


def test_parse_turuncu_cocuk(tmp_path, icfg):
    pts = [p for p in _points(tmp_path, icfg) if p.entity.startswith("ING Turuncu Çocuk")]
    assert len(pts) == 14 * 2
    rows = _by_entity(pts)
    p = rows["ING Turuncu Çocuk Hesabı standart, 0-9.999,99 TL"]
    assert p.value == 23.0 and p.as_of == date(2026, 10, 16)
    assert p.note == ("Standart Faiz; Faiz işletilmeyecek tutar 3.000 TL; 16 Ekim 2026 "
                      "itibariyle geçerli; ing.com.tr rate form, product "
                      "ORANGE_ACCOUNT_KID_GROUP; gross/net not stated")
    assert rows["ING Turuncu Çocuk Hesabı hoş geldin, 10.000-49.999 TL"].value == 39.0
    assert rows["ING Turuncu Çocuk Hesabı hoş geldin, 35.000.000 TL üzeri"].value == 23.0


def test_parse_e_turuncu_biriktiren_without_no_interest_column(tmp_path, icfg):
    pts = [p for p in _points(tmp_path, icfg) if p.entity.startswith("ING e-Turuncu")]
    rows = _by_entity(pts)
    assert sorted(rows) == ["ING e-Turuncu Biriktiren standart, 0-10.000 TL",
                            "ING e-Turuncu Biriktiren standart, 10.000 TL üzeri"]
    assert {p.value for p in pts} == {23.0}
    p = rows["ING e-Turuncu Biriktiren standart, 0-10.000 TL"]
    assert p.note == ("Standart Faiz; 16 Ekim 2026 itibariyle geçerli; ing.com.tr rate form, "
                      "product E_ORANGE_ACCOUNT_ACCUMULATING_GROUP; gross/net not stated")
    assert p.raw_ref.endswith(f"#{ACC};row=10.000 'e kadar;column=Standart Faiz")


def test_config_no_interest_column_is_optional(icfg):
    acc = icfg.sources["ing_web"].products[3]
    assert acc.value == ACC and acc.no_interest_column == "" and acc.rates == {
        "Standart Faiz": "standart"}


def test_unexpected_no_interest_column_fails(tmp_path, config_raw):
    # Without no_interest_column in the config, a page that has the column
    # does not match the header: the source fails.
    del add_ing_web(config_raw)["sources"]["ing_web"]["products"][1]["no_interest_column"]
    rec, _, _, _ = _fetch(tmp_path, parse_config(config_raw))
    assert rec.status == "failed" and f"{TU}: header [" in rec.error
    assert "does not match ['Standart Faiz', 'Hoş Geldin Faizi']" in rec.error


def test_entity_names_are_the_manual_names(tmp_path, icfg):
    names = [p.entity for p in _points(tmp_path, icfg)]
    assert len(names) == len(set(names)) == 116 + 28 + 2
    # e-Vadeli and Turuncu Hesap replace the manual files: the same names.
    replaced = {n for n in names if n.startswith(("ING e-Vadeli ", "ING Turuncu Hesap "))}
    assert replaced == set(MANUAL_NAMES)


def test_parse_is_deterministic_and_fallback_keeps_origin(tmp_path, icfg):
    _, snap, _, _ = _fetch(tmp_path, icfg)
    src = icfg.sources["ing_web"]
    assert ing_web.parse(icfg, src, snap) == ing_web.parse(icfg, src, snap)
    pts = ing_web.parse(icfg, src, snap, out_snapshot_id="20261017-090000-0002",
                        out_date=date(2026, 10, 17))
    assert {p.snapshot_id for p in pts} == {"20261017-090000-0002"}
    assert {p.as_of for p in pts} == {date(2026, 10, 16)}
    assert all(p.raw_ref.startswith(f"{SID}/") for p in pts)


# --- the form flow ----------------------------------------------------------------------------

def test_three_requests_per_product_with_the_delay(tmp_path, icfg):
    rec, snap, fake, sleeps = _fetch(tmp_path, icfg)
    assert rec.status == "ok"
    assert [r.method for r in fake.requests] == ["GET", "POST", "POST"] * 4
    assert {str(r.url) for r in fake.requests} == {ING_URL}
    assert all(r.headers["User-Agent"] == TEST_ING_WEB["user_agent"] for r in fake.requests)
    assert sleeps == [2] * 11                           # before every request but the first
    assert [p.path for p in rec.payloads] == [f"payloads/ing_web/{p}.html" for p in ING_PRODUCTS]
    assert snap.read_payload(f"payloads/ing_web/{EV}.html") == EV_PAGE.encode("utf-8")
    assert [p.meta for p in rec.payloads] == [{"product": p, "url": ING_URL} for p in ING_PRODUCTS]


def test_form_fields_of_the_postbacks(tmp_path, icfg):
    _, _, fake, _ = _fetch(tmp_path, icfg)
    step1, step2 = ing_hidden(ing_page("step1_get")), ing_hidden(ing_page("step2_currency"))
    currency, send = fake.forms[0], fake.forms[1]
    assert currency == {**step1, "__EVENTTARGET": "5575$DdlCurrencyType", "__EVENTARGUMENT": "",
                        "5575$DdlCurrencyType": "0", "5575$DdlProductList": "-1"}
    assert send == {**step2, "__EVENTTARGET": "5575$BtnSend", "__EVENTARGUMENT": "",
                    "5575$DdlCurrencyType": "0", "5575$DdlProductList": EV}
    assert fake.forms[3]["5575$DdlProductList"] == TU
    assert all(FakeIng.COOKIE in r.headers.get("cookie", "") for r in fake.requests
               if r.method == "POST")


def test_request_record_has_no_form_state(tmp_path, icfg):
    rec, _, _, _ = _fetch(tmp_path, icfg)
    assert rec.request["products"] == list(ING_PRODUCTS)
    assert rec.request["delay_seconds"] == 2
    assert "__VIEWSTATE" not in str(rec.request)


@pytest.mark.parametrize("status", [302, 500, 403])
def test_http_status_other_than_200_fails(tmp_path, icfg, status):
    rec, _, fake, _ = _fetch(tmp_path, icfg, FakeIng(status=status))
    assert rec.status == "failed" and f"HTTP {status}" in rec.error and rec.payloads == ()
    assert len(fake.requests) == 1                      # no redirect is followed


def test_connection_error_fails(tmp_path, icfg):
    class Refuse(FakeIng):
        def __call__(self, request):
            raise httpx.ConnectError("refused")

    rec, _, _, _ = _fetch(tmp_path, icfg, Refuse())
    assert rec.status == "failed" and "ConnectError" in rec.error


def test_product_not_offered_fails(tmp_path, config_raw):
    add_ing_web(config_raw)["sources"]["ing_web"]["products"][0]["value"] = "E_NEW_PRODUCT"
    rec, _, _, _ = _fetch(tmp_path, parse_config(config_raw))
    assert rec.status == "failed"
    assert "product 'E_NEW_PRODUCT' is not in the list of the page" in rec.error


def test_send_answer_without_table_fails(tmp_path, icfg):
    # The real site answers a send without the right form state with the
    # form page itself (no table), as checked on 2026-10-16.
    rec, _, _, _ = _fetch(tmp_path, icfg, FakeIng(pages={EV: ing_page("step2_currency")}))
    assert rec.status == "failed" and f"{EV}: no rate table on the page" in rec.error
    assert rec.payloads == ()


def test_currency_postback_ignored_fails(tmp_path, icfg):
    # The step-2 answer is the step-1 page (no product list): the form changed.
    class NoProducts(FakeIng):
        def __call__(self, request):
            response = super().__call__(request)
            if request.method == "POST" and len(self.forms) == 1:
                return httpx.Response(200, text=ing_page("step1_get"))
            return response

    rec, _, _, _ = _fetch(tmp_path, icfg, NoProducts())
    assert rec.status == "failed"
    assert f"product '{EV}' is not in the list of the page" in rec.error


# --- page changes: the source fails, never partial rows -----------------------------------------

@pytest.mark.parametrize("product,page,reason", [
    (EV, EV_PAGE.replace("<table", "<div", 1), "no rate table on the page"),
    (EV, EV_PAGE.replace("</table>", "</table><table></table>", 1),
     "2 tables on the page, expected 1"),
    (EV, EV_PAGE.replace("itibariyle geçerli", "geçerlidir"),
     "no '<d> <month> <yyyy> itibariyle geçerli' text"),
    (TU, TU_PAGE.replace(">Standart Faiz</div></td></tr>", ">Faiz</div></td></tr>", 1),
     "header ['Faiz İşletilmeyecek Tutar (TL)', 'Hoş Geldin Faizi', 'Faiz'] does not match"),
    (TU, TU_PAGE.replace("Turuncu Hesap Bakiyesi (TL)", "Bakiye", 1),
     "first header cell 'Bakiye', expected 'Turuncu Hesap Bakiyesi (TL)'"),
    (EV, EV_PAGE.replace("%34,50", "yok", 1), "'yok' is not a percent"),
    (EV, EV_PAGE.replace("<div class='label'>99.999,99-250.000</div>",
                         "<div class='label'>100.000-250.000</div>", 1),
     "cell label '100.000-250.000' does not match the column '99.999,99-250.000'"),
], ids=["no_table", "two_tables", "no_as_of", "header", "first_header", "not_percent",
        "cell_label"])                    # short ids: the pages are too long for an id
def test_page_change_fails_the_source(tmp_path, icfg, product, page, reason):
    rec, _, _, _ = _fetch(tmp_path, icfg, FakeIng(pages={product: page}))
    assert rec.status == "failed" and f"{product}: {reason}" in rec.error
    assert rec.payloads == ()


def test_too_few_rows_fails(tmp_path, config_raw):
    add_ing_web(config_raw)["sources"]["ing_web"]["products"][0]["min_rows"] = 12
    rec, _, _, _ = _fetch(tmp_path, parse_config(config_raw))
    assert rec.status == "failed" and f"{EV}: 11 rows, minimum 12" in rec.error


def test_too_few_columns_fails(tmp_path, config_raw):
    add_ing_web(config_raw)["sources"]["ing_web"]["products"][0]["min_columns"] = 9
    rec, _, _, _ = _fetch(tmp_path, parse_config(config_raw))
    assert rec.status == "failed" and f"{EV}: 8 columns, minimum 9" in rec.error


def test_row_with_a_missing_cell_fails(tmp_path, icfg):
    cell = ("<td><div class='label'>30.000.000 üzeri</div>"
            "<div class='value text-center'>%5,00</div></td></tr>")
    rec, _, _, _ = _fetch(tmp_path, icfg, FakeIng(pages={EV: EV_PAGE.replace(cell, "</tr>", 1)}))
    assert rec.status == "failed" and f"{EV}: row '1-6 gün' has 7 cells, expected 8" in rec.error


def test_as_of_with_an_unknown_month_fails(tmp_path, icfg):
    page = EV_PAGE.replace("16 Ekim 2026 itibariyle", "16 Ekimm 2026 itibariyle")
    rec, _, _, _ = _fetch(tmp_path, icfg, FakeIng(pages={EV: page}))
    assert rec.status == "failed" and "itibariyle geçerli" in rec.error
