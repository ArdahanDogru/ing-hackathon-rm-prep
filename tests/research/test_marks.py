"""R4: RM marks on research bullets (per finding id and Turkish day) and the other candidates
(entries of `products` after the top 3) in the run's research status (no network)."""

import dataclasses
import json
import threading
from datetime import timedelta

import pytest

from rmprep.contracts import ProductOption
from rmprep.research.config import load_config
from rmprep.research.service import ResearchService
from rmprep.research.types import Finding, ProductResearch, Source
from tests.research.conftest import NOW, FakeProvider, ready_result

CONFIG = load_config()
TODAY = NOW.date()
YESTERDAY = TODAY - timedelta(days=1)
NEWS_SRC = (Source("https://a.example/n", "x"),)


def service(tmp_path, *providers, workers=2, now=NOW):
    return ResearchService(CONFIG, providers, tmp_path, now=lambda: now, max_workers=workers)


def fund(code):
    return ProductOption(f"fund:{code}", "fund", f"Fon {code}", fund_kind="money_market")


def marks_file(tmp_path, day=TODAY):
    return tmp_path / "marks" / f"{day:%Y%m%d}.json"


class WithNews(FakeProvider):
    def research_product(self, option, lang):
        r = super().research_product(option, lang)
        return dataclasses.replace(r, news=(Finding("Haber.", "haber", NEWS_SRC, "high", "2026-10-13"),))


def ready_status(s, result, lang="TR"):
    s.start(result, lang)
    s.wait()
    st = s.status(result, lang)
    assert st["state"] == "ready"
    return st


# --- set_mark / marks --------------------------------------------------------


def test_set_replace_and_remove(tmp_path):
    s = service(tmp_path)
    assert s.marks() == {}
    s.set_mark("Fabcdef01", "ok", "R1", "fund:BBF")
    assert s.marks() == {"Fabcdef01": "ok"}
    s.set_mark("Fabcdef01", "wrong", "R2", "fund:BBF")
    assert s.marks() == {"Fabcdef01": "wrong"}
    row = json.loads(marks_file(tmp_path).read_text(encoding="utf-8"))["Fabcdef01"]
    assert row == {"mark": "wrong", "run_id": "R2", "option_id": "fund:BBF", "at": NOW.isoformat()}
    s.set_mark("Fabcdef01", None, "R2", "fund:BBF")
    assert s.marks() == {}
    s.set_mark("F00000000", None, "R2", "fund:BBF")            # absent: no error


def test_a_bad_mark_or_id_is_a_value_error(tmp_path):
    s = service(tmp_path)
    with pytest.raises(ValueError, match="mark must be 'ok', 'wrong' or null, got 'maybe'"):
        s.set_mark("Fabcdef01", "maybe", "R1", "fund:BBF")
    for bad in ("x123", "Fabcdef0", "Fabcdef012", "FABCDEF01", ""):
        with pytest.raises(ValueError):
            s.set_mark(bad, "ok", "R1", "fund:BBF")
    assert s.marks() == {} and not marks_file(tmp_path).exists()


def test_file_is_lf_utf8_and_leaves_no_temp_file(tmp_path):
    s = service(tmp_path)
    s.set_mark("Fabcdef01", "ok", "R1", "fund:ÇŞ")
    raw = marks_file(tmp_path).read_bytes()
    assert b"\r" not in raw and "fund:ÇŞ" in raw.decode("utf-8")
    assert [p.name for p in (tmp_path / "marks").iterdir()] == [marks_file(tmp_path).name]


def test_another_day(tmp_path):
    service(tmp_path, now=NOW - timedelta(days=1)).set_mark("Fabcdef01", "ok", "R1", "fund:BBF")
    s = service(tmp_path)
    assert marks_file(tmp_path, YESTERDAY).exists()
    assert s.marks() == {} and s.marks(day=YESTERDAY) == {"Fabcdef01": "ok"}


def test_a_broken_file_is_no_marks_and_set_mark_rewrites_it(tmp_path):
    s = service(tmp_path, FakeProvider())
    marks_file(tmp_path).parent.mkdir(parents=True)
    marks_file(tmp_path).write_text("{not json", encoding="utf-8")
    assert s.marks() == {}
    st = ready_status(s, ready_result())
    assert all(f["mark"] is None for p in st["products"] for f in p["findings"])
    s.set_mark("Fabcdef01", "ok", "R1", "fund:BBF")
    assert json.loads(marks_file(tmp_path).read_text(encoding="utf-8")).keys() == {"Fabcdef01"}
    assert s.marks() == {"Fabcdef01": "ok"}


# --- the marks in the status -------------------------------------------------


def test_a_mark_is_shared_by_runs_and_news_carry_it(tmp_path):
    s = service(tmp_path, WithNews(), workers=3)
    run_a, run_b = ready_result(), dataclasses.replace(ready_result(), run_id="R-other")
    st = ready_status(s, run_a)
    first = st["products"][0]
    assert all("mark" in f and f["mark"] is None for p in st["products"] for f in p["findings"] + p["news"])
    s.set_mark(first["findings"][0]["id"], "ok", run_a.run_id, first["option_id"])
    s.set_mark(first["news"][0]["id"], "wrong", run_a.run_id, first["option_id"])
    st_b = s.status(run_b, "TR")
    marked = [(p["option_id"], f["id"], f["mark"]) for p in st_b["products"]
              for f in p["findings"] + p["news"] if f["mark"] is not None]
    assert marked == [(first["option_id"], first["findings"][0]["id"], "ok"),
                      (first["option_id"], first["news"][0]["id"], "wrong")]
    assert st_b["products"][0]["findings"][0]["mark"] == "ok"
    assert st_b["products"][0]["news"][0]["mark"] == "wrong"
    assert all(f["mark"] is None for p in st_b["products"][1:] for f in p["findings"] + p["news"])


def test_an_unknown_finding_id_is_kept_but_never_shown(tmp_path):
    s = service(tmp_path, FakeProvider(), workers=3)
    s.set_mark("Fdeadbeef", "ok", "R1", "fund:ZZZ")
    st = ready_status(s, ready_result())
    assert s.marks() == {"Fdeadbeef": "ok"}
    assert "Fdeadbeef" in json.loads(marks_file(tmp_path).read_text(encoding="utf-8"))
    assert all(f["mark"] is None for p in st["products"] for f in p["findings"] + p["news"])


def test_answers_to_questions_carry_no_mark(tmp_path):
    s = service(tmp_path, FakeProvider(), workers=3)
    result = ready_result()
    s.ask(result, "Nurol Portföy son haberler", "TR")
    st = ready_status(s, result)
    assert st["questions"] and all("mark" not in f for q in st["questions"] for f in q["findings"])


# --- candidates --------------------------------------------------------------

ONE = ("fund:BBF",)        # the run's top 3 holds one product; AAL, AKE, ABU are the others


def others(st, top=1):
    """The candidates: the entries of `products` after the run's top products."""
    return st["products"][top:]


def candidate_ids(st, top=1):
    return [c["option_id"] for c in others(st, top)]


def test_candidates_are_the_other_researched_options_in_display_order(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p, workers=3)
    result = ready_result(ONE)
    s.research_many([fund("BBF"), fund("ABU"), fund("AAL")], "TR")
    st = s.status(result, "TR")
    assert st["state"] == "ready"
    assert "candidates" not in st
    assert [x["option_id"] for x in st["products"][:1]] == ["fund:BBF"]      # the top product first
    assert candidate_ids(st) == ["fund:AAL", "fund:ABU"]            # then the run's option order
    assert all("mark" in f and f["mark"] is None for c in st["products"] for f in c["findings"] + c["news"])
    first = others(st)[0]
    assert set(first) == set(st["products"][0])                      # one shape
    s.set_mark(first["findings"][0]["id"], "ok", result.run_id, first["option_id"])
    assert others(s.status(result, "TR"))[0]["findings"][0]["mark"] == "ok"


def test_the_top_products_are_not_candidates(tmp_path):
    s = service(tmp_path, FakeProvider(), workers=3)
    st = ready_status(s, ready_result())             # BBF, AAL, AKE
    assert [x["option_id"] for x in st["products"]] == ["fund:BBF", "fund:AAL", "fund:AKE"]
    assert candidate_ids(st, 3) == []
    s.research_many([fund("ABU")], "TR")
    st = s.status(ready_result(), "TR")      # the top 3 in recommended order, then the candidate
    assert [x["option_id"] for x in st["products"]] == ["fund:BBF", "fund:AAL", "fund:AKE", "fund:ABU"]


def test_an_option_researched_in_another_run_appears(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p, workers=3)
    other = dataclasses.replace(ready_result(("fund:ABU",)), run_id="R-other")
    s.start(other)
    s.wait()
    st = ready_status(s, ready_result(ONE))
    assert candidate_ids(st) == ["fund:ABU"]


def test_no_research_today_means_no_candidate_and_no_call(tmp_path):
    p = FakeProvider()
    s = service(tmp_path, p)
    s.research_many([fund("BBF")], "TR")
    n = len(p.calls)
    st = s.status(ready_result(ONE), "TR")
    assert candidate_ids(st) == [] and len(p.calls) == n
    ready_status(service(tmp_path, p), ready_result(ONE))
    assert len(p.calls) == n


def test_other_language_and_other_day_are_no_candidates(tmp_path):
    p = FakeProvider()
    service(tmp_path, p).research_many([fund("AAL")], "EN")
    service(tmp_path, p, now=NOW - timedelta(days=1)).research_many([fund("AKE")], "TR")
    assert candidate_ids(ready_status(service(tmp_path, p), ready_result(ONE))) == []


def test_a_running_candidate_is_left_out_and_a_failed_one_shows_its_error(tmp_path):
    gate = threading.Event()

    class Gated(FakeProvider):
        def research_product(self, option, lang):
            if option.option_id == "fund:AAL":
                self.gate = gate
            else:
                self.gate = None
            return super().research_product(option, lang)

    s = service(tmp_path, Gated(), workers=3)
    result = ready_result(ONE)
    s.start(result)
    s.wait()
    runner = threading.Thread(target=s.research_many, args=([fund("AAL")], "TR"))
    runner.start()
    st = s.status(result, "TR")
    assert st["state"] == "ready" and "fund:AAL" not in candidate_ids(st)
    gate.set()
    runner.join(5)
    assert candidate_ids(s.status(result, "TR")) == ["fund:AAL"]
    bad = service(tmp_path / "bad", FakeProvider(fail="credit"))
    bad.start(result)
    bad.wait()
    bad.research_many([fund("AKE")], "TR")
    [c] = others(bad.status(result, "TR"))
    assert c["option_id"] == "fund:AKE" and c["error"] == "exa: credit"


def test_a_new_service_shows_the_candidates_from_the_cache_files(tmp_path):
    p = FakeProvider()
    service(tmp_path, p, workers=3).research_many([fund("AAL"), fund("ABU")], "TR")
    fresh_provider = FakeProvider()
    fresh = service(tmp_path, fresh_provider)
    st = ready_status(fresh, ready_result(ONE))
    assert st["state"] == "ready" and candidate_ids(st) == ["fund:AAL", "fund:ABU"]
    assert isinstance(ProductResearch.from_dict(dict(others(st)[0])),
                      ProductResearch)
    assert [c[1] for c in fresh_provider.calls] == ["fund:BBF"]      # only the top product is started
    assert list(fresh._jobs) == [("fund:BBF", "TR", TODAY)]


def test_a_broken_cache_file_is_no_candidate(tmp_path):
    service(tmp_path, FakeProvider()).research_many([fund("AAL"), fund("ABU")], "TR")
    (tmp_path / "products" / "fund_AAL-TR-20261014-v2.json").write_text("{x", encoding="utf-8")
    st = ready_status(service(tmp_path, FakeProvider()), ready_result(ONE))
    assert candidate_ids(st) == ["fund:ABU"]


def test_status_off_has_no_candidates(tmp_path):
    st = service(tmp_path).status(ready_result(ONE), "TR")
    assert st["state"] == "off" and "candidates" not in st and "products" not in st
