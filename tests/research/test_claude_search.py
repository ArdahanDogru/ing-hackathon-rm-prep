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
    return NS(content=blocks, stop_reason=stop, model="claude-sonnet-5-5", usage=usage)


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
    assert r.cost_usd == pytest.approx(10000 * 2 / 1e6 + 500 * 10 / 1e6 + 0.01)
    kw = sdk.calls[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["max_tokens"] == 8000
    assert kw["tools"] == [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3,
                            "blocked_domains": ["kap.org.tr"]}]
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
    assert a.cost_usd == pytest.approx(2 * (0.02 + 0.005) + 0.01)


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


def test_a_non_web_search_result_url_is_not_a_source():
    bad = "javascript:alert(1)"
    sdk = FakeSdk(message([
        results(bad),
        text("Bu cümle javascript bağlantısına dayanıyor.", bad),
    ]))
    r = provider(sdk).research_product(PPN, "TR")
    assert r.findings == ()
    assert r.checks == ("1 findings without a valid source dropped",)
