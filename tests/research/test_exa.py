import json
from datetime import datetime

import httpx
import pytest

from rmprep.contracts import TR_TZ, ProductOption
from rmprep.research.config import load_config
from rmprep.research.exa import NEWS_SCHEMA, QUESTION_SCHEMA, ExaProvider, parse_news, product_schema
from rmprep.research.types import ResearchError

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=TR_TZ)
CONFIG = load_config()
PPN = ProductOption("fund:PPN", "fund", "NUROL PORTFÖY PARA PİYASASI (TL) FONU", entity="PPN",
                    fund_kind="money_market", asset_class="nakit_benzeri")
NUROL = "https://www.nurolportfoy.com.tr/fon/ppn"
FONOLOJI = "https://fonoloji.com/ppn/"
HABER1 = "https://www.example-haber.com/nurol-ostim"
HABER2 = "https://www.example-ekonomi.com/nurol-yeni"


def cite(field, *urls, conf="high"):
    return {"field": field, "citations": [{"url": u, "title": "x"} for u in urls], "confidence": conf}


PRODUCT_BODY = {
    "requestId": "r1",
    "costDollars": {"total": 0.012},
    "results": [
        {"url": NUROL, "title": "Nurol Portföy | PPN", "publishedDate": "2026-10-12T00:00:00.000Z"},
        {"url": FONOLOJI, "title": "PPN", "publishedDate": None},
        {"url": "https://pro-av.panasonic.net/x", "title": "AK-HRP1000GJ"},
    ],
    "output": {
        "content": {
            "sirket": "Nurol Portföy Yönetimi A.Ş.",
            "bulgular": [
                {"konu": "strateji", "metin": "Fon, kısa vadeli TL para piyasası araçlarına yatırım yapar."},
                {"konu": "Yönetici şirket", "metin": "Şirket Nurol Yatırım Bankası iştirakidir."},
                {"konu": "genel", "metin": "Konusu tanımsız bulgu."},
                {"konu": "strateji", "metin": "Kaynağı sonuç olmayan bulgu."},
                {"konu": "dikkat", "metin": "Kaynağı hiç olmayan bulgu."},
            ],
        },
        "grounding": [
            cite("sirket", NUROL + "/"),
            cite("bulgular[0].metin", NUROL),
            cite("bulgular[0].konu", FONOLOJI, conf="low"),
            cite("bulgular[1]", NUROL, conf="medium"),
            cite("bulgular[2].metin", NUROL),
            cite("bulgular[3].metin", "https://example.org/not-a-result"),
        ],
    },
}
NEWS_BODY = {
    "requestId": "r2",
    "costDollars": {"total": 0.007},
    "results": [
        {"url": HABER1, "title": "Nurol OSTİM", "publishedDate": "2026-10-08T09:00:00.000Z"},
        {"url": HABER2, "title": "Nurol yeni", "publishedDate": "2026-09-30T00:00:00.000Z"},
        {"url": FONOLOJI, "title": "PPN", "publishedDate": None},
    ],
    "output": {
        "content": {"haberler": [
            {"metin": "Nurol Portföy OSTİM payını artırdı."},
            {"metin": "Nurol Portföy yeni fon kurdu."},
            {"metin": "Tarihsiz kaynaktan haber."},
            {"metin": "Kaynaksız haber."},
        ]},
        "grounding": [
            cite("haberler[0].metin", HABER2, HABER1),
            cite("haberler[1]", HABER2),
            cite("haberler[2].metin", FONOLOJI),
            cite("haberler[3].metin", "https://example.org/not-a-result"),
        ],
    },
}


def provider(handler, key="k-123"):
    return ExaProvider(CONFIG.exa, CONFIG.system_prompt, key, highlights_prompt=CONFIG.highlights_prompt,
                       news_days=90, transport=httpx.MockTransport(handler), now=lambda: NOW)


def answering(body, seen=None, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=body)
    return handler


def two_calls(highlights, news, seen=None, news_status=200):
    """The highlights reply for a request without a category, the news reply for one with it."""
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if "category" in json.loads(request.content):
            return httpx.Response(news_status, json=news)
        return httpx.Response(200, json=highlights)
    return handler


def test_schemas_name_the_topics_of_their_kind():
    for kind, names in (("fund", ("strateji", "yonetici_sirket", "dikkat")),
                        ("etf", ("strateji", "yonetici_sirket", "dikkat")),
                        ("stock", ("is", "finansal", "sermaye"))):
        schema = product_schema(kind)
        assert "ozet" not in schema["properties"] and schema["required"] == ["sirket", "bulgular"]
        desc = schema["properties"]["bulgular"]["items"]["properties"]["konu"]["description"]
        assert all(n in desc for n in names)
    assert "sermaye" not in product_schema("fund")["properties"]["bulgular"]["items"]["properties"]["konu"]["description"]
    assert "ozet" not in QUESTION_SCHEMA["properties"] and "ozet" not in NEWS_SCHEMA["properties"]


def test_product_makes_two_calls_highlights_then_news():
    seen = []
    provider(two_calls(PRODUCT_BODY, NEWS_BODY, seen)).research_product(PPN, "TR")
    assert len(seen) == 2
    for req in seen:
        assert req.method == "POST" and req.url == "https://api.exa.ai/search"
        assert req.headers["x-api-key"] == "k-123"
    assert json.loads(seen[0].content) == {
        "query": "NUROL PORTFÖY PARA PİYASASI (TL) FONU (PPN) fonu ve yöneten portföy yönetim şirketi",
        "type": "deep",
        "excludeDomains": ["kap.org.tr"],
        "systemPrompt": CONFIG.system_prompt["TR"] + " " + CONFIG.highlights_prompt["TR"],
        "outputSchema": product_schema("fund"),
        "contents": {"highlights": True},
    }
    assert json.loads(seen[1].content) == {
        "query": "Nurol Portföy Yönetimi A.Ş. PPN haber",
        "type": "auto",
        "category": "news",
        "startPublishedDate": "2026-07-16T00:00:00.000Z",
        "excludeDomains": ["kap.org.tr"],
        "systemPrompt": CONFIG.system_prompt["TR"],
        "outputSchema": NEWS_SCHEMA,
        "contents": {"highlights": True},
    }


def test_news_query_uses_the_label_when_there_is_no_company():
    body = json.loads(json.dumps(PRODUCT_BODY))
    body["output"]["content"]["sirket"] = ""
    seen = []
    provider(two_calls(body, NEWS_BODY, seen)).research_product(PPN, "TR")
    assert json.loads(seen[1].content)["query"] == "NUROL PORTFÖY PARA PİYASASI (TL) FONU PPN haber"


def test_product_findings_keep_only_sourced_items_of_a_known_topic():
    r = provider(two_calls(PRODUCT_BODY, NEWS_BODY)).research_product(PPN, "TR")
    assert r.provider == "exa" and r.created_at == NOW
    assert r.company == "Nurol Portföy Yönetimi A.Ş." and r.summary == ""
    assert [(f.topic, f.confidence) for f in r.findings] == [("strateji", "high"), ("yonetici_sirket", "medium")]
    assert [s.url for s in r.findings[0].sources] == [NUROL, FONOLOJI]
    assert r.findings[0].sources[0].published == "2026-10-12"
    assert r.findings[0].sources[1].published == ""
    assert "2 findings without a valid source dropped" in r.checks
    assert "1 bullets with an unknown topic dropped" in r.checks


def test_product_cost_adds_the_news_call():
    r = provider(two_calls(PRODUCT_BODY, NEWS_BODY)).research_product(PPN, "TR")
    assert r.cost_usd == pytest.approx(0.019)


def test_news_items_are_dated_by_their_newest_source():
    r = provider(two_calls(PRODUCT_BODY, NEWS_BODY)).research_product(PPN, "TR")
    assert [(n.topic, n.text, n.date) for n in r.news] == [
        ("haber", "Nurol Portföy OSTİM payını artırdı.", "2026-10-08"),
        ("haber", "Nurol Portföy yeni fon kurdu.", "2026-09-30"),
        ("haber", "Tarihsiz kaynaktan haber.", ""),
    ]
    assert [s.url for s in r.news[0].sources] == [HABER2, HABER1]
    assert "1 news items without a valid source dropped" in r.checks


def test_parse_news_keeps_only_sourced_items():
    items, dropped = parse_news(NEWS_BODY, CONFIG.exa.exclude_domains)
    assert len(items) == 3 and dropped == 1
    assert items[2].date == ""
    with pytest.raises(ResearchError) as e:
        parse_news({"costDollars": {"total": 0.007}, "results": []}, ())
    assert e.value.kind == "request" and e.value.cost_usd == pytest.approx(0.007)


def test_a_news_item_from_an_excluded_domain_is_dropped():
    body = json.loads(json.dumps(NEWS_BODY))
    body["results"].append({"url": "https://www.kap.org.tr/tr/x", "title": "KAP", "publishedDate": "2026-10-10"})
    body["output"]["content"]["haberler"] = [{"metin": "KAP bildirimi."}]
    body["output"]["grounding"] = [cite("haberler[0].metin", "https://www.kap.org.tr/tr/x")]
    items, dropped = parse_news(body, CONFIG.exa.exclude_domains)
    assert items == [] and dropped == 1


@pytest.mark.parametrize("konu,topic", [
    ("strateji", "strateji"), ("Strateji", "strateji"), ("Yönetici şirket", "yonetici_sirket"),
    ("yonetici_sirket", "yonetici_sirket"), ("yönetici-şirket", "yonetici_sirket"), ("DİKKAT", "dikkat"),
    ("genel", None), ("urun", None), ("", None)])
def test_fund_topics_are_mapped(konu, topic):
    body = json.loads(json.dumps(PRODUCT_BODY))
    body["output"]["content"]["bulgular"] = [{"konu": konu, "metin": "Bulgu."}]
    body["output"]["grounding"] = [cite("bulgular[0].metin", NUROL)]
    r = provider(two_calls(body, NEWS_BODY)).research_product(PPN, "TR")
    assert [f.topic for f in r.findings] == ([topic] if topic else [])
    assert ("1 bullets with an unknown topic dropped" in r.checks) == (topic is None)


def test_stock_topics_and_stock_schema():
    stock = ProductOption("stock:THYAO", "stock", "TÜRK HAVA YOLLARI")
    body = json.loads(json.dumps(PRODUCT_BODY))
    body["output"]["content"]["bulgular"] = [{"konu": "finansal", "metin": "Net kâr arttı."},
                                             {"konu": "İş", "metin": "Havayolu işletir."},
                                             {"konu": "strateji", "metin": "Hisse için tanımsız."}]
    body["output"]["grounding"] = [cite(f"bulgular[{i}].metin", NUROL) for i in range(3)]
    seen = []
    r = provider(two_calls(body, NEWS_BODY, seen)).research_product(stock, "EN")
    assert [f.topic for f in r.findings] == ["finansal", "is"]
    assert "1 bullets with an unknown topic dropped" in r.checks
    payload = json.loads(seen[0].content)
    assert payload["query"] == "TÜRK HAVA YOLLARI (THYAO) hissesi ve şirket"
    assert payload["systemPrompt"] == CONFIG.system_prompt["EN"] + " " + CONFIG.highlights_prompt["EN"]
    assert payload["outputSchema"] == product_schema("stock")
    assert json.loads(seen[1].content)["systemPrompt"] == CONFIG.system_prompt["EN"]


def test_deposit_has_no_query():
    with pytest.raises(ResearchError) as e:
        provider(answering(PRODUCT_BODY)).research_product(
            ProductOption("deposit:ing_turuncu", "deposit", "Turuncu Hesap"), "TR")
    assert e.value.kind == "request"


def test_unsourced_company_is_left_out():
    body = json.loads(json.dumps(PRODUCT_BODY))
    body["output"]["grounding"] = [g for g in body["output"]["grounding"] if g["field"] != "sirket"]
    seen = []
    r = provider(two_calls(body, NEWS_BODY, seen)).research_product(PPN, "TR")
    assert r.company == "" and r.summary == ""
    assert "sirket: no valid source, left out" in r.checks
    assert json.loads(seen[1].content)["query"] == "NUROL PORTFÖY PARA PİYASASI (TL) FONU PPN haber"


def test_non_web_result_url_cannot_be_a_source():
    body = {"results": [{"url": "javascript:alert(1)", "title": "x"}],
            "output": {"content": {"sirket": "",
                                   "bulgular": [{"konu": "strateji", "metin": "Bulgu."}]},
                       "grounding": [cite("bulgular[0].metin", "javascript:alert(1)")]}}
    r = provider(answering(body)).research_product(PPN, "TR")
    assert r.findings == () and r.news == ()
    assert r.checks == ("1 findings without a valid source dropped",)


def test_a_failed_news_call_keeps_the_highlights():
    r = provider(two_calls(PRODUCT_BODY, {"error": "x"}, news_status=402)).research_product(PPN, "TR")
    assert [f.topic for f in r.findings] == ["strateji", "yonetici_sirket"]
    assert r.news == () and "news: credit" in r.checks
    assert r.cost_usd == pytest.approx(0.012)


def test_a_billed_news_reply_without_output_adds_its_cost():
    news = {"requestId": "r2", "costDollars": {"total": 0.007}, "results": []}
    r = provider(two_calls(PRODUCT_BODY, news)).research_product(PPN, "TR")
    assert len(r.findings) == 2 and r.news == ()
    assert "news: request" in r.checks
    assert r.cost_usd == pytest.approx(0.019)


def test_a_news_server_error_and_a_news_connection_error_keep_the_highlights():
    r = provider(two_calls(PRODUCT_BODY, {"error": "x"}, news_status=500)).research_product(PPN, "TR")
    assert len(r.findings) == 2 and "news: server" in r.checks

    def down_for_news(request):
        if "category" in json.loads(request.content):
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json=PRODUCT_BODY)
    r = provider(down_for_news).research_product(PPN, "TR")
    assert len(r.findings) == 2 and "news: connection" in r.checks


def test_question_request_and_answer():
    body = {"costDollars": {"total": 0.007},
            "results": [{"url": NUROL, "title": "Haber", "publishedDate": "2026-10-08"}],
            "output": {"content": {"bulgular": [{"metin": "Pay oranı %5,58'e çıktı."}]},
                       "grounding": [cite("bulgular[0].metin", NUROL)]}}
    seen = []
    a = provider(answering(body, seen)).answer_question("Nurol Portföy son haberler", [PPN], "TR")
    assert len(seen) == 1
    payload = json.loads(seen[0].content)
    assert payload["query"] == "Nurol Portföy son haberler"
    assert payload["type"] == "auto" and payload["outputSchema"] == QUESTION_SCHEMA
    assert "category" not in payload and "startPublishedDate" not in payload
    assert payload["systemPrompt"] == (CONFIG.system_prompt["TR"]
                                       + " İlgili ürünler: NUROL PORTFÖY PARA PİYASASI (TL) FONU (PPN).")
    assert a.summary == ""
    assert [(f.topic, f.text) for f in a.findings] == [("soru", "Pay oranı %5,58'e çıktı.")]
    assert a.cost_usd == 0.007 and a.question == "Nurol Portföy son haberler"


@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "auth"), (402, "credit"),
                                         (429, "rate_limit"), (500, "server"), (400, "request")])
def test_http_errors_become_kinds(status, kind):
    with pytest.raises(ResearchError) as e:
        provider(answering({"error": "x"}, status=status)).research_product(PPN, "TR")
    assert e.value.kind == kind
    assert "k-123" not in str(e.value)


def test_key_echoed_by_the_server_is_removed_from_the_error():
    with pytest.raises(ResearchError) as e:
        provider(answering({"error": "Invalid API key: k-123"}, status=401)).research_product(PPN, "TR")
    assert e.value.kind == "auth"
    assert "k-123" not in str(e.value) and "k-123" not in e.value.message
    assert "***" in e.value.message


def test_key_echoed_by_the_news_call_does_not_reach_the_checks():
    news_down = two_calls(PRODUCT_BODY, {"error": "Invalid API key: k-123"}, news_status=401)
    r = provider(news_down).research_product(PPN, "TR")
    assert "news: auth" in r.checks
    assert "k-123" not in repr(r)


def test_connection_error_and_missing_output():
    def down(request):
        raise httpx.ConnectError("boom")
    with pytest.raises(ResearchError) as e:
        provider(down).research_product(PPN, "TR")
    assert e.value.kind == "connection"
    with pytest.raises(ResearchError) as e:
        provider(answering({"results": []})).research_product(PPN, "TR")
    assert e.value.kind == "request"


def test_a_paid_reply_without_output_carries_its_cost():
    body = {"requestId": "r1", "costDollars": {"total": 0.012}, "results": []}
    for call in (lambda p: p.research_product(PPN, "TR"), lambda p: p.answer_question("PPN nedir?", [PPN], "TR")):
        with pytest.raises(ResearchError) as e:
            call(provider(answering(body)))
        assert e.value.kind == "request" and e.value.cost_usd == pytest.approx(0.012)


def test_a_failed_highlights_call_costs_nothing_and_makes_no_news_call():
    seen = []
    with pytest.raises(ResearchError) as e:
        provider(answering({"error": "x"}, seen, status=402)).research_product(PPN, "TR")
    assert e.value.kind == "credit" and e.value.cost_usd == 0.0
    assert len(seen) == 1


def test_a_malformed_url_in_the_results_is_ignored():
    body = json.loads(json.dumps(PRODUCT_BODY))
    body["results"].append({"url": "http://[bad", "title": "broken"})
    body["output"]["grounding"].append(cite("bulgular[3].metin", "http://[bad"))
    r = provider(two_calls(body, NEWS_BODY)).research_product(PPN, "TR")
    assert [f.text for f in r.findings] == ["Fon, kısa vadeli TL para piyasası araçlarına yatırım yapar.",
                                            "Şirket Nurol Yatırım Bankası iştirakidir."]


def _news_with_dates(*dates):
    urls = [f"https://www.example-haber.com/n{i}" for i in range(len(dates))]
    return {"costDollars": {"total": 0.007},
            "results": [{"url": u, "title": "x", "publishedDate": d} for u, d in zip(urls, dates)],
            "output": {"content": {"haberler": [{"metin": "Bir haber."}]},
                       "grounding": [cite("haberler[0].metin", *urls)]}}


def test_a_malformed_source_date_never_wins_over_a_valid_one():
    items, _ = parse_news(_news_with_dates("unknown-date", "2026-10-01T08:00:00.000Z"), ())
    assert items[0].date == "2026-10-01"
    items, _ = parse_news(_news_with_dates("unknown-date", "2026-13-45", "20261001"), ())
    assert items[0].date == ""


@pytest.mark.parametrize("content,grounding", [({"haberler": 5}, []), ({"haberler": [{"metin": "x"}]}, 5),
                                               ({"haberler": [{"metin": ["x"]}]}, [5])])
def test_a_malformed_news_reply_keeps_the_highlights(content, grounding):
    news = {"costDollars": {"total": 0.007}, "results": [], "output": {"content": content, "grounding": grounding}}
    r = provider(two_calls(PRODUCT_BODY, news)).research_product(PPN, "TR")
    assert len(r.findings) == 2 and r.news == ()
    assert r.cost_usd == pytest.approx(0.019)
    assert "news: request" in r.checks


def test_an_iso_week_date_is_not_a_news_date():
    items, _ = parse_news(_news_with_dates("2026-W40-1", "2026-10-01"), ())
    assert items[0].date == "2026-10-01"
    items, _ = parse_news(_news_with_dates("2026-W40-1"), ())
    assert items[0].date == ""
