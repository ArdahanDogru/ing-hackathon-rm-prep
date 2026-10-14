import json
from datetime import datetime

import httpx
import pytest

from rmprep.contracts import TR_TZ, ProductOption
from rmprep.research.config import load_config
from rmprep.research.exa import PRODUCT_SCHEMA, QUESTION_SCHEMA, ExaProvider
from rmprep.research.types import ResearchError

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=TR_TZ)
CONFIG = load_config()
PPN = ProductOption("fund:PPN", "fund", "NUROL PORTFÖY PARA PİYASASI (TL) FONU", entity="PPN",
                    fund_kind="money_market", asset_class="nakit_benzeri")
NUROL = "https://www.nurolportfoy.com.tr/fon/ppn"
FONOLOJI = "https://fonoloji.com/ppn/"


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
            "ozet": "PPN bir para piyasası fonudur.",
            "bulgular": [
                {"konu": "urun", "metin": "Fonun yönetim ücreti %0,7'dir."},
                {"konu": "şirket", "metin": "Şirket Nurol Yatırım Bankası iştirakidir."},
                {"konu": "urun", "metin": "Kaynağı sonuç olmayan bulgu."},
                {"konu": "urun", "metin": "Kaynağı hiç olmayan bulgu."},
            ],
        },
        "grounding": [
            cite("sirket", NUROL + "/"),
            cite("ozet", "https://fonoloji.com/ppn", conf="medium"),
            cite("bulgular[0].metin", NUROL),
            cite("bulgular[0].konu", FONOLOJI, conf="low"),
            cite("bulgular[1]", NUROL, conf="medium"),
            cite("bulgular[2].metin", "https://example.org/not-a-result"),
        ],
    },
}


def provider(handler, key="k-123"):
    return ExaProvider(CONFIG.exa, CONFIG.system_prompt, key,
                       transport=httpx.MockTransport(handler), now=lambda: NOW)


def answering(body, seen=None, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=body)
    return handler


def test_product_request_shape():
    seen = []
    provider(answering(PRODUCT_BODY, seen)).research_product(PPN, "TR")
    req = seen[0]
    assert req.method == "POST" and req.url == "https://api.exa.ai/search"
    assert req.headers["x-api-key"] == "k-123"
    payload = json.loads(req.content)
    assert payload == {
        "query": "NUROL PORTFÖY PARA PİYASASI (TL) FONU (PPN) fonu ve yöneten portföy yönetim şirketi",
        "type": "deep",
        "excludeDomains": ["kap.org.tr"],
        "systemPrompt": CONFIG.system_prompt["TR"],
        "outputSchema": PRODUCT_SCHEMA,
        "contents": {"highlights": True},
    }


def test_product_findings_keep_only_sourced_items():
    r = provider(answering(PRODUCT_BODY)).research_product(PPN, "TR")
    assert r.provider == "exa" and r.cost_usd == 0.012 and r.created_at == NOW
    assert r.company == "Nurol Portföy Yönetimi A.Ş."
    assert r.summary == "PPN bir para piyasası fonudur."
    assert [(f.topic, f.confidence) for f in r.findings] == [("urun", "high"), ("sirket", "medium")]
    assert [s.url for s in r.findings[0].sources] == [NUROL, FONOLOJI]
    assert r.findings[0].sources[0].published == "2026-10-12"
    assert r.findings[0].sources[1].published == ""
    assert r.checks == ("2 findings without a valid source dropped",)


def test_unsourced_summary_and_company_are_left_out():
    body = json.loads(json.dumps(PRODUCT_BODY))
    body["output"]["grounding"] = [g for g in body["output"]["grounding"] if g["field"] not in ("sirket", "ozet")]
    r = provider(answering(body)).research_product(PPN, "TR")
    assert r.company == "" and r.summary == ""
    assert "sirket: no valid source, left out" in r.checks and "ozet: no valid source, left out" in r.checks


def test_non_web_result_url_cannot_be_a_source():
    body = {"results": [{"url": "javascript:alert(1)", "title": "x"}],
            "output": {"content": {"sirket": "", "ozet": "",
                                   "bulgular": [{"konu": "urun", "metin": "Bulgu."}]},
                       "grounding": [cite("bulgular[0].metin", "javascript:alert(1)")]}}
    r = provider(answering(body)).research_product(PPN, "TR")
    assert r.findings == ()
    assert r.checks == ("1 findings without a valid source dropped",)


def test_kinds_use_their_query_and_deposit_has_none():
    seen = []
    stock = ProductOption("stock:THYAO", "stock", "TÜRK HAVA YOLLARI")
    provider(answering(PRODUCT_BODY, seen)).research_product(stock, "EN")
    payload = json.loads(seen[0].content)
    assert payload["query"] == "TÜRK HAVA YOLLARI (THYAO) hissesi ve şirket"
    assert payload["systemPrompt"] == CONFIG.system_prompt["EN"]
    with pytest.raises(ResearchError) as e:
        provider(answering(PRODUCT_BODY)).research_product(
            ProductOption("deposit:ing_turuncu", "deposit", "Turuncu Hesap"), "TR")
    assert e.value.kind == "request"


def test_question_request_and_answer():
    body = {"costDollars": {"total": 0.007},
            "results": [{"url": NUROL, "title": "Haber", "publishedDate": "2026-10-08"}],
            "output": {"content": {"ozet": "Nurol Portföy OSTİM payını artırdı.",
                                   "bulgular": [{"metin": "Pay oranı %5,58'e çıktı."}]},
                       "grounding": [cite("ozet", NUROL), cite("bulgular[0].metin", NUROL)]}}
    seen = []
    a = provider(answering(body, seen)).answer_question("Nurol Portföy son haberler", [PPN], "TR")
    payload = json.loads(seen[0].content)
    assert payload["query"] == "Nurol Portföy son haberler"
    assert payload["type"] == "auto" and payload["outputSchema"] == QUESTION_SCHEMA
    assert payload["systemPrompt"] == (CONFIG.system_prompt["TR"]
                                       + " İlgili ürünler: NUROL PORTFÖY PARA PİYASASI (TL) FONU (PPN).")
    assert a.summary == "Nurol Portföy OSTİM payını artırdı."
    assert [(f.topic, f.text) for f in a.findings] == [("soru", "Pay oranı %5,58'e çıktı.")]
    assert a.cost_usd == 0.007 and a.question == "Nurol Portföy son haberler"


@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "auth"), (402, "credit"),
                                         (429, "rate_limit"), (500, "server"), (400, "request")])
def test_http_errors_become_kinds(status, kind):
    with pytest.raises(ResearchError) as e:
        provider(answering({"error": "x"}, status=status)).research_product(PPN, "TR")
    assert e.value.kind == kind
    assert "k-123" not in str(e.value)


def test_connection_error_and_missing_output():
    def down(request):
        raise httpx.ConnectError("boom")
    with pytest.raises(ResearchError) as e:
        provider(down).research_product(PPN, "TR")
    assert e.value.kind == "connection"
    with pytest.raises(ResearchError) as e:
        provider(answering({"results": []})).research_product(PPN, "TR")
    assert e.value.kind == "request"
