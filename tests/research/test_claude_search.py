import shutil
from datetime import datetime
from types import SimpleNamespace as NS

import pytest

from rmprep.contracts import TR_TZ, ProductOption
from rmprep.research.claude_search import ClaudeSearchProvider
from rmprep.research.config import DEFAULT_PATH, load_config
from rmprep.research.service import research_from_root
from rmprep.research.types import ResearchError

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=TR_TZ)
CONFIG = load_config()
PPN = ProductOption("fund:PPN", "fund", "NUROL PORTFÖY PARA PİYASASI (TL) FONU", fund_kind="money_market")
NUROL, FONOLOJI, KAP = "https://www.nurolportfoy.com.tr/fon/ppn", "https://fonoloji.com/ppn", "https://www.kap.org.tr/tr/Bildirim/1"


def results(*urls):
    return NS(type="web_search_tool_result", content=[NS(type="web_search_result", url=u, title=f"T {u}", page_age=None) for u in urls])


def text(t, *urls):
    cits = [NS(type="web_search_result_location", url=u, title="t", cited_text="c") for u in urls]
    return NS(type="text", text=t, citations=cits or None)


def message(blocks, stop="end_turn", searches=1):
    usage = NS(input_tokens=10000, output_tokens=500, cache_creation_input_tokens=0,
               cache_read_input_tokens=0, server_tool_use=NS(web_search_requests=searches))
    return NS(content=blocks, stop_reason=stop, model="claude-haiku-5-5", usage=usage)


class FakeSdk:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return self.replies.pop(0)


def provider(sdk):
    return ClaudeSearchProvider(CONFIG.claude, CONFIG.system_prompt, CONFIG.exa.exclude_domains, sdk=sdk, now=lambda: NOW)


def test_product_findings_company_and_cost():
    sdk = FakeSdk(message([
        results(NUROL, FONOLOJI, KAP),
        text("Fon kısa vadeli para piyasası araçlarına yatırım yapar.", NUROL),
        text("Bu cümlenin kaynağı arama sonucu değil.", "https://other.example/x"),
        text("ŞİRKET: Nurol Portföy Yönetimi A.Ş.\n"),
        text("Şirket Nurol Yatırım Bankası iştirakidir.", FONOLOJI + "/"),
        text("KAP bildirimine göre yeni bir fon kuruldu.", KAP),
        text("Kısa."),
    ]))
    r = provider(sdk).research_product(PPN, "TR")
    assert [(f.topic, f.text) for f in r.findings] == [
        ("urun", "Fon kısa vadeli para piyasası araçlarına yatırım yapar."),
        ("sirket", "Şirket Nurol Yatırım Bankası iştirakidir.")]
    assert r.company == "Nurol Portföy Yönetimi A.Ş." and r.summary == "" and r.provider == "claude"
    assert r.checks == ("2 findings without a valid source dropped",)
    assert r.cost_usd == pytest.approx(10000 * 0.10 / 1e6 + 500 * 0.50 / 1e6 + 0.01)
    kw = sdk.calls[0]
    assert kw["model"] == "claude-haiku-5-5" and kw["max_tokens"] == 8000
    assert kw["tools"] == [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3,
                            "allowed_callers": ["direct"], "blocked_domains": ["kap.org.tr"]}]
    assert "NUROL PORTFÖY PARA PİYASASI (TL) FONU (PPN)" in kw["messages"][0]["content"]
    assert kw["system"].startswith(CONFIG.system_prompt["TR"])
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["fallbacks"] == "default"


def test_pause_turn_continues_and_sums_the_cost():
    first = message([results(NUROL), text("Fonun büyüklüğü 9 milyar TL'dir.", NUROL)], stop="pause_turn")
    sdk = FakeSdk(first, message([text("Fon T+0 valörlüdür, aynı gün ödenir.", NUROL)], searches=0))
    a = provider(sdk).answer_question("PPN valörü nedir?", [PPN], "TR")
    assert [f.text for f in a.findings] == ["Fonun büyüklüğü 9 milyar TL'dir.", "Fon T+0 valörlüdür, aynı gün ödenir."]
    assert all(f.topic == "soru" for f in a.findings)
    assert len(sdk.calls) == 2 and sdk.calls[1]["messages"][-1]["role"] == "assistant"
    assert a.cost_usd == pytest.approx(2 * (0.001 + 0.00025) + 0.01)


def test_refusal_is_a_request_error():
    with pytest.raises(ResearchError) as e:
        provider(FakeSdk(message([], stop="refusal"))).research_product(PPN, "TR")
    assert e.value.kind == "request"


def test_from_env_needs_the_key():
    assert ClaudeSearchProvider.from_env(CONFIG.claude, CONFIG.system_prompt, (), {}) is None
    p = ClaudeSearchProvider.from_env(CONFIG.claude, CONFIG.system_prompt, (), {"ANTHROPIC_API_KEY": "k"})
    assert p is not None and p.name == "claude"


def test_research_from_root_orders_the_providers(tmp_path):
    (tmp_path / "config").mkdir()
    shutil.copy(DEFAULT_PATH, tmp_path / "config" / "research.yaml")
    only_claude = research_from_root(tmp_path, env={"ANTHROPIC_API_KEY": "k"})
    assert [p.name for p in only_claude._providers] == ["claude"]
    both = research_from_root(tmp_path, env={"ANTHROPIC_API_KEY": "k", "EXA_API_KEY": "e"})
    assert [p.name for p in both._providers] == ["exa", "claude"]


TEFAS, FVT = "https://www.tefas.gov.tr/tr/fon-detayli-analiz/PPN", "https://fvt.com.tr/fonlar/yatirim-fonlari/PPN"
BHT = "https://www.bloomberght.com/yatirim-fonlari/nurol-portfoy-para-piyasasi-tl-fonu-ppn"
HAKKIMIZDA = "https://www.nurolportfoy.com.tr/kurumsal/hakkimizda"
LINKEDIN = "https://tr.linkedin.com/company/nurol-portf%C3%B6y-y%C3%B6netimi-a-%C5%9F"


def test_live_reply_shape_cited_spans_inside_lines():
    """Shape of the real reply (live call 2026-10-15, claude-haiku-5-5, web search with
    allowed_callers ["direct"]): the searches are direct (caller {"type": "direct"}) and the
    answer is split into many text blocks. Only the cited span of a line has citations;
    the words around it are separate blocks with citations None. A finding is the line
    (or the sentence at a block end), with the sources of all its cited spans."""
    def direct(*urls):
        b = results(*urls)
        b.caller = NS(type="direct")
        return b
    sdk = FakeSdk(message([
        NS(type="thinking", thinking="", signature="s"),
        NS(type="server_tool_use", id="srvtoolu_1", name="web_search", caller=None,
           input={"query": "Nurol Portföy Para Piyasası TL Fonu PPN"}),
        NS(type="server_tool_use", id="srvtoolu_2", name="web_search", caller=None,
           input={"query": "Nurol Portföy Yönetimi A.Ş. hakkında"}),
        direct(BHT, TEFAS, FVT),
        direct(HAKKIMIZDA, LINKEDIN),
        NS(type="thinking", thinking="", signature="s"),
        text("**NUROL PORTFÖY PARA PİYASASI (TL) FONU (PPN) hakkında**\n\n"
             "- Fon, TEFAS'ta işlem gören bir para piyasası fonu. "),
        text("Fon kodu PPN, ISIN kodu TRYNRPO00029", TEFAS),
        text(" olarak kayıtlı.\n- Fonun kurucusu ve yöneticisi Nurol Portföy Yönetimi A.Ş.; "),
        text("fon, Para Piyasası Şemsiye Fonu yapısı içinde bir para piyasası fonu olarak sınıflandırılıyor.", FVT),
        text("\n- Fonun kuruluş tarihi "),
        text("8 Temmuz 2021", FVT),
        text(" ve halka arzı "),
        text("9 Ağustos 2021", BHT),
        text(" olarak görünüyor.\n- Fonun risk değeri "),
        text("1 / 7", TEFAS),
        text(" olarak görünüyor ve bu, "),
        text("düşük risk aralığına karşılık gelir.", FVT),
        text("\n\n**ŞİRKET: Nurol Portföy Yönetimi A.Ş.**\n\n- Şirket, "),
        text("Nurol Yatırım Bankası A.Ş.'nin %100 bağlı ortaklığı", HAKKIMIZDA),
        text(" olarak tanımlanıyor.\n- Şirket, "),
        text("Sermaye Piyasası Kurulu'ndan 25.11.2020 tarih ve 11934 sayılı yazı ile kuruluş izni", LINKEDIN),
        text(" almış; faaliyet izni ve portföy yöneticiliği yetki belgesi ise "),
        text("06.04.2021 ve 4576 sayılı yazı", LINKEDIN),
        text(" ile verilmiş."),
    ], searches=2))
    r = provider(sdk).research_product(PPN, "TR")
    assert [(f.topic, f.text, [s.url for s in f.sources]) for f in r.findings] == [
        ("urun", "Fon kodu PPN, ISIN kodu TRYNRPO00029 olarak kayıtlı.", [TEFAS]),
        ("urun", "Fonun kurucusu ve yöneticisi Nurol Portföy Yönetimi A.Ş.; fon, Para Piyasası Şemsiye "
                 "Fonu yapısı içinde bir para piyasası fonu olarak sınıflandırılıyor.", [FVT]),
        ("urun", "Fonun kuruluş tarihi 8 Temmuz 2021 ve halka arzı 9 Ağustos 2021 olarak görünüyor.", [FVT, BHT]),
        ("urun", "Fonun risk değeri 1 / 7 olarak görünüyor ve bu, düşük risk aralığına karşılık gelir.",
         [TEFAS, FVT]),
        ("sirket", "Şirket, Nurol Yatırım Bankası A.Ş.'nin %100 bağlı ortaklığı olarak tanımlanıyor.",
         [HAKKIMIZDA]),
        ("sirket", "Şirket, Sermaye Piyasası Kurulu'ndan 25.11.2020 tarih ve 11934 sayılı yazı ile kuruluş "
                   "izni almış; faaliyet izni ve portföy yöneticiliği yetki belgesi ise 06.04.2021 ve 4576 "
                   "sayılı yazı ile verilmiş.", [LINKEDIN]),
    ]
    assert r.company == "Nurol Portföy Yönetimi A.Ş." and r.checks == ()


def test_live_reply_markdown_and_period_after_a_quote_are_removed():
    """Second live call (2026-10-15): bold labels, and the period after a cited quote
    starts the next text block."""
    fvt = "https://fvt.com.tr/yatirim-fonlari/ppn-nurol-portfoy-para-piyasasi-tl-fonu/"
    sdk = FakeSdk(message([
        results(fvt),
        text(".\n- **Ücret ve vergi:** Yıllık yönetim ücreti %0,70 olarak yer alıyor "),
        text("Yıllık **%0.70** yönetim ücreti bulunmaktadır.", fvt),
        text(". Stopaj oranı ise %17,5 olarak belirtiliyor ve bu oran fon satıldığında kâr üzerinden kesiliyor "),
        text("Satıldığında kârdan **%17.5** stopaj kesilir.", fvt),
        text(".\n"),
    ]))
    r = provider(sdk).research_product(PPN, "TR")
    assert [f.text for f in r.findings] == [
        "Ücret ve vergi: Yıllık yönetim ücreti %0,70 olarak yer alıyor Yıllık %0.70 yönetim ücreti bulunmaktadır.",
        "Stopaj oranı ise %17,5 olarak belirtiliyor ve bu oran fon satıldığında kâr üzerinden kesiliyor "
        "Satıldığında kârdan %17.5 stopaj kesilir.",
    ]


@pytest.mark.parametrize("blocks, cited", [
    # an uncited sentence after the cited span, on the same line
    ([text("- Fon kodu "), text("PPN", FVT),
      text(" olarak kayıtlı. Fon devlet garantilidir ve her yıl yüzde 80 getiri verir.\n")],
     "Fon kodu PPN olarak kayıtlı."),
    # an uncited sentence before the cited span, on the same line
    ([text("- Fon devlet garantilidir ve yüzde 80 getiri verir. Ayrıca "),
      text("fon kodu PPN olarak kayıtlıdır", FVT), text(".\n")],
     "Ayrıca fon kodu PPN olarak kayıtlıdır."),
])
def test_an_uncited_sentence_never_takes_the_source_of_its_line(blocks, cited):
    r = provider(FakeSdk(message([results(FVT), *blocks]))).research_product(PPN, "TR")
    assert [(f.text, [s.url for s in f.sources]) for f in r.findings] == [(cited, [FVT])]
    assert not any("garanti" in f.text for f in r.findings)


OPENER = {'"': '"', ")": "(", "**": "**", "”": "“"}


@pytest.mark.parametrize("close", list(OPENER))
@pytest.mark.parametrize("where", ["cited block end", "inside the uncited block"])
def test_a_closer_after_a_sentence_end_also_ends_the_finding(close, where):
    op = OPENER[close]
    if where == "cited block end":      # the cited span ends with the sentence end and the closer
        blocks = [text("- Fon "), text(f"{op}PPN kodlu fon kayıtlıdır.{close}", FVT),
                  text(" Fon devlet garantilidir.\n")]
        cited = f"Fon {op}PPN kodlu fon kayıtlıdır.{close}"
    else:                               # the sentence end and the closer are in the next, uncited block
        blocks = [text("- Fon kodu "), text("PPN", FVT),
                  text(f" olarak {op}kayıtlıdır.{close} Fon devlet garantilidir.\n")]
        cited = f"Fon kodu PPN olarak {op}kayıtlıdır.{close}"
    r = provider(FakeSdk(message([results(FVT), *blocks]))).research_product(PPN, "TR")
    assert [(f.text, [s.url for s in f.sources]) for f in r.findings] == [(cited.replace("**", ""), [FVT])]
    assert not any("garanti" in f.text for f in r.findings)


def test_a_non_web_search_result_url_is_not_a_source():
    bad = "javascript:alert(1)"
    sdk = FakeSdk(message([
        results(bad),
        text("Bu cümle javascript bağlantısına dayanıyor.", bad),
    ]))
    r = provider(sdk).research_product(PPN, "TR")
    assert r.findings == ()
    assert r.checks == ("1 findings without a valid source dropped",)
