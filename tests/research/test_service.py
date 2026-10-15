import dataclasses
import hashlib
import json
import math
import shutil
import threading
from pathlib import Path

import pytest

from rmprep.contracts import ProductOption
from rmprep.research.config import DEFAULT_PATH, load_config
from rmprep.research.types import Finding, ProductResearch, QuestionAnswer, Source
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
    assert (tmp_path / "products" / "fund_BBF-TR-20261014-v2.json").is_file()   # no ':' in a Windows file name
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
    assert not (tmp_path / "products" / "fund_BBF-TR-20261014-v2.json").exists()
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
    assert a.question == "Nurol Portföy son haberler" and a.summary == "" and a.version == 2
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


def test_a_failed_cache_write_never_blocks_a_product(tmp_path):
    (tmp_path / "products").write_text("not a directory", encoding="utf-8")
    p = FakeProvider()
    s = service(tmp_path, p)
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    st = s.status(r, "TR")
    assert st["state"] == "ready"
    [x] = st["products"]
    assert x["error"] == "" and len(x["findings"]) == 1
    assert len(p.calls) == 1
    assert s.spent_today() == pytest.approx(0.01)


def test_a_failed_cache_write_never_blocks_a_question(tmp_path):
    (tmp_path / "questions").write_text("not a directory", encoding="utf-8")
    p = FakeProvider()
    s = service(tmp_path, p)
    a = s.ask(ready_result(), "PPN nedir?", "TR")
    assert a.error == "" and [f.text for f in a.findings] == ["Bulgu."]
    assert len(p.calls) == 1


# --- final review fixes: the ledger fails closed, failed paid calls are recorded ---

def ledger_rows(tmp_path):
    lines = (tmp_path / "costs.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines]


def test_an_unreadable_ledger_stops_the_calls(tmp_path):
    (tmp_path / "costs.jsonl").mkdir()               # reading it raises an OSError, not FileNotFoundError
    p = FakeProvider()
    s = service(tmp_path, p)
    assert s.spent_today() == math.inf
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    assert p.calls == []
    assert s.status(r, "TR")["products"][0]["error"] == LIMIT_ERROR


def test_a_missing_ledger_is_zero(tmp_path):
    assert service(tmp_path, FakeProvider()).spent_today() == 0.0


def test_a_failed_ledger_write_keeps_the_result_and_still_counts(tmp_path, monkeypatch):
    real_open = Path.open

    def failing(self, mode="r", *args, **kwargs):
        if self.name == "costs.jsonl" and mode.startswith("a"):
            raise OSError("disk full")
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing)
    cfg = dataclasses.replace(CONFIG, max_cost_usd_per_day=0.005)
    p = FakeProvider(cost=0.01)
    s = service(tmp_path, p, config=cfg)
    r = ready_result(("fund:BBF", "fund:AAL"))
    s.start(r)
    s.wait()
    first, second = s.status(r, "TR")["products"]
    assert first["error"] == "" and len(first["findings"]) == 1      # the paid result is not lost
    assert (tmp_path / "products" / "fund_BBF-TR-20261014-v2.json").is_file()   # and it is cached
    assert second["error"] == LIMIT_ERROR                              # the in-memory total counts
    assert len(p.calls) == 1
    assert s.spent_today() == pytest.approx(0.01)
    assert not (tmp_path / "costs.jsonl").exists()


def test_a_failed_paid_call_is_recorded_then_the_next_provider_runs(tmp_path):
    exa = FakeProvider("exa", fail="credit", fail_cost=0.012)
    claude = FakeProvider("claude", cost=0.03)
    s = service(tmp_path, exa, claude)
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    assert s.status(r, "TR")["products"][0]["provider"] == "claude"
    rows = ledger_rows(tmp_path)
    assert [(x["provider"], x["kind"], x["cost_usd"]) for x in rows] == [
        ("exa", "product", 0.012), ("claude", "product", 0.03)]
    assert s.spent_today() == pytest.approx(0.042)


def test_a_failed_paid_call_that_stops_is_recorded(tmp_path):
    exa = FakeProvider("exa", fail="request", fail_cost=0.012)
    claude = FakeProvider("claude")
    s = service(tmp_path, exa, claude)
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    assert s.status(r, "TR")["products"][0]["error"] == "exa: request"
    assert claude.calls == []
    [row] = ledger_rows(tmp_path)
    assert (row["provider"], row["kind"], row["cost_usd"]) == ("exa", "product", 0.012)
    assert s.spent_today() == pytest.approx(0.012)


def test_a_failed_question_that_cost_money_is_recorded(tmp_path):
    s = service(tmp_path, FakeProvider("exa", fail="request", fail_cost=0.02))
    a = s.ask(ready_result(), "PPN nedir?", "TR")
    assert a.error == "exa: request"
    [row] = ledger_rows(tmp_path)
    assert (row["kind"], row["cost_usd"]) == ("question", 0.02)


def test_a_failed_call_without_cost_writes_no_row(tmp_path):
    s = service(tmp_path, FakeProvider("exa", fail="credit"))
    s.start(ready_result(("fund:BBF",)))
    s.wait()
    assert not (tmp_path / "costs.jsonl").exists()


# --- v2: the service shapes every result and caches it under a v2 name ---

SRC = Source("https://exa.example/x", "x")
SIX = ("Fon kısa vadeli devlet tahvillerine yatırım yapar.", "Portföyde ağırlıklı olarak bono bulunur.",
       "Yönetici şirket yeni bir fon ailesi kurmuştur.", "Fon günlük işlem gören bir araçtır.",
       "Varlıkların büyük kısmı mevduatta tutulur.", "Faiz oranı düşerse fon değer kazanabilir.")


class LongProvider(FakeProvider):
    def research_product(self, option, lang):
        self.calls.append(("product", option.option_id, lang))
        self._maybe_fail()
        fs = tuple(Finding(t, "strateji", (SRC,), "high") for t in SIX)
        return ProductResearch(option.option_id, option.label, "Şirket A.Ş.", "Çok uzun bir özet. " * 30,
                               fs, lang, self.name, NOW, self.cost)

    def answer_question(self, question, products, lang):
        self.calls.append(("question", question, lang, ()))
        fs = tuple(Finding(t, "soru", (SRC,)) for t in SIX)
        return QuestionAnswer(question, "Uzun yanıt.", fs, lang, self.name, NOW, self.cost)


def test_a_product_is_shaped_before_it_is_cached(tmp_path):
    s = service(tmp_path, LongProvider())
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    [x] = s.status(r, "TR")["products"]
    assert len(x["findings"]) == 4 and x["summary"] == "" and x["version"] == 2 and x["news_days"] == 90
    cached = json.loads((tmp_path / "products" / "fund_BBF-TR-20261014-v2.json").read_text(encoding="utf-8"))
    assert len(cached["findings"]) == 4 and cached["summary"] == "" and cached["version"] == 2
    assert not (tmp_path / "products" / "fund_BBF-TR-20261014.json").exists()


def test_a_shaped_claude_product_has_no_news_section_an_exa_product_has_90_days(tmp_path):
    s = service(tmp_path, LongProvider("claude"))
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    assert s.status(r, "TR")["products"][0]["news_days"] == 0
    s2 = service(tmp_path / "b", LongProvider("exa"))
    s2.start(r)
    s2.wait()
    assert s2.status(r, "TR")["products"][0]["news_days"] == 90


def test_a_v1_cache_file_is_not_read(tmp_path):
    products = tmp_path / "products"
    products.mkdir()
    v1 = ProductResearch("fund:BBF", "BBF", "Eski A.Ş.", "Eski uzun özet.",
                         (Finding("Eski bulgu.", "urun", (SRC,)),), "TR", "exa", NOW, 0.01)
    (products / "fund_BBF-TR-20261014.json").write_text(json.dumps(v1.to_dict()), encoding="utf-8")
    p = FakeProvider()
    s = service(tmp_path, p)
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    assert len(p.calls) == 1
    [x] = s.status(r, "TR")["products"]
    assert x["company"] == "Şirket A.Ş." and x["version"] == 2


def test_an_error_product_carries_the_news_days(tmp_path):
    s = service(tmp_path, FakeProvider(fail="credit"))
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    [x] = s.status(r, "TR")["products"]
    assert x["error"] == "exa: credit" and x["news_days"] == 90
    s2 = service(tmp_path / "b", FakeProvider(fail=KeyError("bulgular")))
    s2.start(r)
    s2.wait()
    assert s2.status(r, "TR")["products"][0]["news_days"] == 90


def test_a_job_that_raised_is_an_error_product_with_the_news_days(tmp_path):
    s = service(tmp_path, FakeProvider())
    s._product = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
    r = ready_result(("fund:BBF",))
    s.start(r)
    s.wait()
    [x] = s.status(r, "TR")["products"]
    assert x["error"].startswith("RuntimeError") and x["news_days"] == 90


def test_an_answer_is_shaped_and_cached_under_a_v2_name(tmp_path):
    s = service(tmp_path, LongProvider())
    r = ready_result()
    a = s.ask(r, "Nurol Portföy son haberler", "TR")
    assert len(a.findings) == 4 and a.summary == "" and a.version == 2
    digest = hashlib.sha1("Nurol Portföy son haberler".encode("utf-8")).hexdigest()[:12]
    assert (tmp_path / "questions" / f"{r.run_id}-TR-v2-{digest}.json").is_file()
    assert s.ask(r, "Nurol Portföy son haberler", "TR") == a


def test_questions_lists_only_v2_files(tmp_path):
    s = service(tmp_path, FakeProvider())
    r = ready_result()
    s.ask(r, "Nurol Portföy son haberler", "TR")
    old = QuestionAnswer("Eski soru", "Eski uzun yanıt.", (), "TR", "exa", NOW)
    (tmp_path / "questions" / f"{r.run_id}-TR-0123456789ab.json").write_text(
        json.dumps(old.to_dict()), encoding="utf-8")
    assert [q.question for q in s.questions(r.run_id, "TR")] == ["Nurol Portföy son haberler"]
