"""R3: stable finding ids, ResearchService.research_many and ask_product (no network)."""

import dataclasses
import re
import threading

from rmprep.contracts import Persona, ProductOption
from rmprep.research.checks import REASONS
from rmprep.research.config import load_config
from rmprep.research.service import ResearchService
from rmprep.research.shape import cut_words
from rmprep.research.types import Finding, ProductResearch, QuestionAnswer, Source, finding_id
from tests.research.conftest import NOW, FakeProvider, ready_result

CONFIG = load_config()
ID = re.compile(r"^F[0-9a-f]{8}$")
SRC = (Source("https://a.example/x", "x"),)


def fund(code):
    return ProductOption(f"fund:{code}", "fund", f"Fon {code}", fund_kind="money_market")


def service(tmp_path, *providers, workers=2, **kw):
    return ResearchService(CONFIG, providers, tmp_path, now=lambda: NOW, max_workers=workers, **kw)


def product(findings=(), news=()):
    return ProductResearch("fund:AAA", "Fon", "", "", tuple(findings), "TR", "exa", NOW, news=tuple(news))


def f(text, date=""):
    return Finding(text, "urun", SRC, "high", date)


# --- finding ids -------------------------------------------------------------


def test_finding_id_format_and_collision_counter():
    a = finding_id("fund:AAA", "2026-10-01", "Metin.")
    assert ID.match(a)
    assert a == finding_id("fund:AAA", "2026-10-01", "Metin.")
    assert finding_id("fund:AAA", "2026-10-01", "Metin.", 1) != a
    assert finding_id("fund:BBB", "2026-10-01", "Metin.") != a


def test_ids_are_set_unique_and_stable(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    [r] = s.research_many([fund("BBF")], "TR")
    ids = [x.id for x in r.findings + r.news]
    assert ids and all(ID.match(i) for i in ids) and len(set(ids)) == len(ids)
    s2 = service(tmp_path, FakeProvider())          # read back from the cache file
    [r2] = s2.research_many([fund("BBF")], "TR")
    assert r2 == r and [x.id for x in r2.findings] == [x.id for x in r.findings]


def test_ids_always_recomputed_and_v2_dict_gets_ids():
    r = product([f("Bir.")], [f("Haber.", "2026-10-10")])
    d = r.to_dict()
    assert all("id" in x for x in d["findings"] + d["news"])
    for x in d["findings"] + d["news"]:
        del x["id"]                                  # a v2 cache file has no ids
    back = ProductResearch.from_dict(d)
    assert back == r
    assert all(ID.match(x.id) for x in back.findings + back.news)
    forged = dataclasses.replace(r, findings=(dataclasses.replace(r.findings[0], id="FAKE"),))
    assert forged.findings[0].id == r.findings[0].id


def test_same_date_and_text_get_different_ids():
    r = product([f("Aynı."), f("Aynı.")], [f("Aynı.", "2026-10-10"), f("Aynı.", "2026-10-10")])
    ids = [x.id for x in r.news + r.findings]
    assert len(set(ids)) == 4 and all(ID.match(i) for i in ids)
    again = product([f("Aynı."), f("Aynı.")], [f("Aynı.", "2026-10-10"), f("Aynı.", "2026-10-10")])
    assert [x.id for x in again.news + again.findings] == ids


def test_news_and_findings_with_one_id_do_not_collide():
    r = product([f("Aynı.", "2026-10-10")], [f("Aynı.", "2026-10-10")])
    assert r.news[0].id != r.findings[0].id


def test_id_changes_when_the_text_changes():
    long = "bir iki üç dört beş altı yedi sekiz dokuz on"
    r = product([f(long)])
    cut = dataclasses.replace(r, findings=(dataclasses.replace(r.findings[0], text=cut_words(long, 4)),))
    assert cut.findings[0].id != r.findings[0].id
    assert cut.findings[0].id == finding_id("fund:AAA", "", cut_words(long, 4))


def test_question_answer_ids_use_option_id():
    a = QuestionAnswer("q", "", (f("Bir."),), "TR", "exa", NOW)
    b = dataclasses.replace(a, option_id="fund:AAA")
    assert a.option_id == "" and a.findings[0].id == finding_id("", "", "Bir.")
    assert b.findings[0].id == finding_id("fund:AAA", "", "Bir.")
    assert QuestionAnswer.from_dict(b.to_dict()) == b
    d = a.to_dict()
    del d["option_id"]
    assert QuestionAnswer.from_dict(d) == a


# --- research_many -----------------------------------------------------------


def test_research_many_input_order_and_each_product_once(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p, workers=3)
    out = s.research_many([fund("BBF"), fund("AAL"), fund("BBF"), fund("AKE")], "TR")
    assert [r.option_id for r in out] == ["fund:BBF", "fund:AAL", "fund:AKE"]
    assert all(r.error == "" for r in out)
    assert sorted(c[1] for c in p.calls) == ["fund:AAL", "fund:AKE", "fund:BBF"]


def test_research_many_second_call_and_new_service_make_no_call(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    first = s.research_many([fund("BBF"), fund("AAL")], "TR")
    n = len(p.calls)
    assert s.research_many([fund("BBF"), fund("AAL")], "TR") == first and len(p.calls) == n
    other = FakeProvider()
    again = service(tmp_path, other).research_many([fund("BBF"), fund("AAL")], "TR")
    assert again == first and other.calls == []


def test_research_many_reuses_a_job_started_by_start(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p, workers=3)
    r = ready_result()
    s.start(r)
    out = s.research_many([o for o in [fund("BBF"), fund("AAL"), fund("AKE")]], "TR")
    assert [x.error for x in out] == ["", "", ""]
    assert len(p.calls) == 3


def test_research_many_retries_a_failed_job(tmp_path):
    p = FakeProvider(fail="credit")
    s = service(tmp_path, p)
    [bad] = s.research_many([fund("BBF")], "TR")
    assert bad.error == "exa: credit"
    p.fail = None
    [ok] = s.research_many([fund("BBF")], "TR")
    assert ok.error == "" and len(p.calls) == 2


def test_research_many_deposit_is_an_error_item_without_a_call(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    dep = ProductOption("deposit:ing_turuncu", "deposit", "Turuncu")
    td = ProductOption("time_deposit:ing_e_vadeli", "time_deposit", "E-Vadeli")
    out = s.research_many([dep, fund("BBF"), td], "TR")
    assert [r.option_id for r in out] == ["deposit:ing_turuncu", "fund:BBF", "time_deposit:ing_e_vadeli"]
    assert out[0].error == "not researched: deposit" and out[2].error == "not researched: time_deposit"
    assert out[1].error == "" and [c[1] for c in p.calls] == ["fund:BBF"]


def test_research_many_without_providers(tmp_path):
    s = ResearchService(CONFIG, [], tmp_path, now=lambda: NOW, off_reason="no key in .env: EXA_API_KEY")
    out = s.research_many([fund("BBF"), fund("AAL")], "TR")
    assert [r.error for r in out] == ["no key in .env: EXA_API_KEY"] * 2
    assert s.research_many([], "TR") == []


def test_research_many_one_failing_product_does_not_break_the_others(tmp_path):
    class Picky(FakeProvider):
        def research_product(self, option, lang):
            if option.option_id == "fund:AAL":
                raise RuntimeError("boom")
            return super().research_product(option, lang)

    out = service(tmp_path, Picky(), workers=3).research_many([fund("BBF"), fund("AAL"), fund("AKE")], "TR")
    assert [bool(r.error) for r in out] == [False, True, False]
    assert "boom" in out[1].error


def test_research_many_runs_in_parallel(tmp_path):
    barrier = threading.Barrier(4, timeout=5)

    class Waiting(FakeProvider):
        def research_product(self, option, lang):
            barrier.wait()                  # a serial run raises BrokenBarrierError
            return super().research_product(option, lang)

    opts = [fund(c) for c in ("AAA", "BBB", "CCC", "DDD")]
    out = service(tmp_path, Waiting(), workers=4).research_many(opts, "TR")
    assert [r.error for r in out] == [""] * 4


def test_default_pool_size_is_five(tmp_path):
    s = ResearchService(CONFIG, [FakeProvider()], tmp_path, now=lambda: NOW)
    assert s._pool._max_workers == 5


# --- ask_product -------------------------------------------------------------

PERSONA = ready_result().persona


def test_ask_product_refuses_client_words_without_a_call(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    out = s.ask_product(fund("BBF"), "müşterim için uygun mu?", "TR")
    assert out == REASONS["TR"]["client"] and p.calls == []
    assert not (tmp_path / "product_questions").exists()


def test_ask_product_persona_age_is_refused_only_with_a_persona(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    q = f"{PERSONA.yas} yıllık getirisi nedir?"
    assert isinstance(s.ask_product(fund("BBF"), q, "TR"), QuestionAnswer)
    assert s.ask_product(fund("BBF"), q + " ", "TR", persona=PERSONA) == REASONS["TR"]["client"]
    assert len(p.calls) == 1


def test_ask_product_answer_cache_and_folder(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    opt = fund("BBF")
    a = s.ask_product(opt, "Yönetim ücreti ne kadar?", "TR")
    assert isinstance(a, QuestionAnswer) and a.option_id == "fund:BBF"
    assert a.findings and all(ID.match(x.id) for x in a.findings)
    assert a.findings[0].id == finding_id("fund:BBF", "", a.findings[0].text)
    assert p.calls == [("question", "Yönetim ücreti ne kadar?", "TR", ("fund:BBF",))]
    files = list((tmp_path / "product_questions").glob("fund_BBF-TR-20261014-v2-*.json"))
    assert len(files) == 1
    assert s.questions("any-run", "TR") == [] and s.questions("fund_BBF", "TR") == []
    assert s.ask_product(opt, "  Yönetim ücreti ne kadar?  ", "TR") == a and len(p.calls) == 1
    again = service(tmp_path, FakeProvider())
    assert again.ask_product(opt, "Yönetim ücreti ne kadar?", "TR") == a


def test_ask_product_error_is_a_string_and_not_cached(tmp_path):
    p = FakeProvider(fail="credit")
    s = service(tmp_path, p)
    out = s.ask_product(fund("BBF"), "Yönetim ücreti ne kadar?", "TR")
    assert out == "exa: credit"
    assert not (tmp_path / "product_questions").exists()
    p.fail = RuntimeError("boom")
    assert s.ask_product(fund("BBF"), "Yönetim ücreti ne kadar?", "TR") == "RuntimeError: boom"


def test_ask_product_off_and_not_researchable(tmp_path):
    off = ResearchService(CONFIG, [], tmp_path, now=lambda: NOW, off_reason="no key in .env: EXA_API_KEY")
    assert off.ask_product(fund("BBF"), "Soru?", "TR") == "no key in .env: EXA_API_KEY"
    p = FakeProvider()
    dep = ProductOption("deposit:ing_turuncu", "deposit", "Turuncu")
    assert service(tmp_path, p).ask_product(dep, "Soru?", "TR") == "not researched: deposit"
    assert p.calls == []
