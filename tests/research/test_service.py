import dataclasses
import shutil
import threading
from pathlib import Path

import pytest

from rmprep.contracts import ProductOption
from rmprep.research.config import DEFAULT_PATH, load_config
from rmprep.research.service import (LIMIT_ERROR, QuestionRefused, ResearchService,
                                     research_from_root, research_products, researchable)
from tests.research.conftest import NOW, RECOMMENDED, FakeProvider, ready_result

CONFIG = load_config()


def service(tmp_path, *providers, config=CONFIG, workers=1):
    return ResearchService(config, providers, tmp_path, now=lambda: NOW, max_workers=workers)


def test_researchable_kinds():
    assert researchable(ProductOption("fund:PPN", "fund", "PPN", fund_kind="money_market"))
    assert researchable(ProductOption("etf:GLDTR", "etf", "Altın BYF"))
    assert researchable(ProductOption("stock:THYAO", "stock", "THY"))
    assert not researchable(ProductOption("deposit:ing_turuncu", "deposit", "Turuncu"))
    assert not researchable(ProductOption("time_deposit:ing_e_vadeli", "time_deposit", "E-Vadeli"))


def test_products_follow_the_recommended_order():
    r = ready_result(("fund:AKE", "fund:BBF"))
    assert [o.option_id for o in research_products(r)] == ["fund:AKE", "fund:BBF"]


def test_start_researches_each_recommended_product(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    s.start(ready_result())
    s.wait()
    st = s.status(ready_result(), "TR")
    assert st["state"] == "ready"
    assert [x["option_id"] for x in st["products"]] == list(RECOMMENDED)
    assert st["questions"] == []
    assert [c[1] for c in p.calls] == list(RECOMMENDED)


def test_cache_file_names_and_cache_hit(tmp_path):
    s = service(tmp_path, FakeProvider())
    s.start(ready_result())
    s.wait()
    assert (tmp_path / "products" / "fund_BBF-TR-20261014.json").is_file()   # no ':' in a Windows file name
    again = FakeProvider()
    s2 = service(tmp_path, again)
    s2.start(ready_result())
    s2.wait()
    assert s2.status(ready_result(), "TR")["state"] == "ready"
    assert again.calls == []


def test_running_while_a_job_waits(tmp_path):
    gate = threading.Event()
    s = service(tmp_path, FakeProvider(gate=gate), workers=3)
    s.start(ready_result())
    assert s.status(ready_result(), "TR") == {"state": "running"}
    gate.set()
    s.wait()
    assert s.status(ready_result(), "TR")["state"] == "ready"


def test_off_without_providers(tmp_path):
    s = ResearchService(CONFIG, [], tmp_path, now=lambda: NOW, off_reason="no key in .env: EXA_API_KEY")
    assert not s.enabled
    s.start(ready_result())
    assert s.status(ready_result(), "TR") == {"state": "off", "reason": "no key in .env: EXA_API_KEY"}
    with pytest.raises(QuestionRefused):
        s.ask(ready_result(), "PPN nedir?", "TR")


def test_daily_limit_stops_calls(tmp_path):
    cfg = dataclasses.replace(CONFIG, max_cost_usd_per_day=0.015)
    p = FakeProvider(cost=0.01)
    s = service(tmp_path, p, config=cfg)
    s.start(ready_result())
    s.wait()
    products = s.status(ready_result(), "TR")["products"]
    assert [x["error"] for x in products] == ["", "", LIMIT_ERROR]
    assert len(p.calls) == 2
    assert s.spent_today() == pytest.approx(0.02)


def test_fallback_on_credit_but_not_on_request(tmp_path):
    exa, claude = FakeProvider("exa", fail="credit"), FakeProvider("claude")
    s = service(tmp_path, exa, claude)
    s.start(ready_result(("fund:BBF",)))
    s.wait()
    [x] = s.status(ready_result(("fund:BBF",)), "TR")["products"]
    assert x["provider"] == "claude" and x["error"] == ""
    exa2, claude2 = FakeProvider("exa", fail="request"), FakeProvider("claude")
    s2 = service(tmp_path / "b", exa2, claude2)
    s2.start(ready_result(("fund:BBF",)))
    s2.wait()
    [y] = s2.status(ready_result(("fund:BBF",)), "TR")["products"]
    assert y["error"] == "exa: request" and claude2.calls == []


def test_failed_product_is_not_retried_by_status_only_by_start(tmp_path):
    p = FakeProvider(fail="credit")
    s = service(tmp_path, p)
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    assert s.status(r, "TR")["products"][0]["error"] == "exa: credit"
    assert s.status(r, "TR")["state"] == "ready"           # polling ends; no new call
    assert len(p.calls) == 1
    assert not (tmp_path / "products" / "fund_BBF-TR-20261014.json").exists()
    p.fail = None
    s.start(r)                                              # a new run view retries
    s.wait()
    assert s.status(r, "TR")["products"][0]["error"] == ""
    assert len(p.calls) == 2


def test_a_provider_bug_becomes_an_error_not_a_crash(tmp_path):
    s = service(tmp_path, FakeProvider(fail=KeyError("bulgular")))
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    assert s.status(r, "TR")["products"][0]["error"].startswith("KeyError")


def test_ask_caches_and_lists_questions(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    r = ready_result()
    a = s.ask(r, "  Nurol Portföy son haberler ", "TR")
    assert a.question == "Nurol Portföy son haberler" and a.summary == "Yanıt."
    assert p.calls == [("question", "Nurol Portföy son haberler", "TR", RECOMMENDED)]
    assert s.ask(r, "Nurol Portföy son haberler", "TR") == a
    assert len(p.calls) == 1
    assert [q.question for q in s.questions(r.run_id, "TR")] == ["Nurol Portföy son haberler"]
    assert s.questions(r.run_id, "EN") == []


def test_refused_question_costs_nothing(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    with pytest.raises(QuestionRefused) as e:
        s.ask(ready_result(), "Müşterim için hangisi?", "TR")
    assert "müşteri bilgisi" in str(e.value)
    assert p.calls == []


def test_failed_question_is_returned_not_cached(tmp_path):
    s = service(tmp_path, FakeProvider(fail="server"))
    a = s.ask(ready_result(), "PPN nedir?", "TR")
    assert a.error == "exa: server" and a.findings == ()
    assert s.questions(ready_result().run_id, "TR") == []


def test_research_from_root_reads_keys(tmp_path):
    (tmp_path / "config").mkdir()
    shutil.copy(DEFAULT_PATH, tmp_path / "config" / "research.yaml")
    off = research_from_root(tmp_path, env={})
    assert not off.enabled
    assert off.status(ready_result(), "TR") == {"state": "off", "reason": "no key in .env: EXA_API_KEY"}
    on = research_from_root(tmp_path, env={"EXA_API_KEY": "k"})
    assert on.enabled and [p.name for p in on._providers] == ["exa"]
