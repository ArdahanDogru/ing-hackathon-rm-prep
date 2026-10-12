"""N13c (prompt n9): no ING deposit vs market rate comparison outside oneriler
(it is an RM-only note); the engine's deposit_real point (market only) stays."""

import pytest

from rmprep.contracts import NarrativeSection, NarrativeSentence
from rmprep.narrator.facts import build_facts
from rmprep.narrator.prompt import system_prompt
from rmprep.narrator.template import template_sections
from rmprep.narrator.validator import compares_ing_with_market, validate
from tests.narrator.conftest import engine_result_on, evidence, evidence_n13, p02

ING = ["ıng turuncu hesap (standart)", "ıng turuncu hesap", "turuncu hesap"]


@pytest.mark.parametrize("text, hit", [
    ("ING Turuncu Hesap (standart) %23 faiz veriyor; piyasa ortalaması %43,82.", True),
    ("ING Turuncu Hesap oranı piyasa ortalamasının altında.", True),
    ("Turuncu Hesap faizi piyasa mevduat faizinin gerisinde.", True),
    ("ING Turuncu Hesap pays less than the market average.", True),
    ("ING Turuncu Hesap %23 veriyor, %43,82 ise daha yüksek.", True),     # the market number
    ("ING Turuncu Hesap (standart) %23 faiz veriyor.", False),
    ("Piyasa ortalamasındaki mevduat faizi yıllık +%4,9 reel getiri veriyor.", False),
    ("Piyasa mevduat faizi %43,82.", False),
])
def test_compares_ing_with_market(text, hit):
    assert compares_ing_with_market(text, ING, {43.82}) is hit


@pytest.mark.parametrize("key", ["alternatifler", "dikkat"])
def test_validator_finds_the_comparison(key, config):
    r = p02()
    f = build_facts(r, evidence())
    sections = [NarrativeSection(s.key, (*s.sentences, NarrativeSentence(
        "ING Turuncu Hesap oranı piyasa ortalamasının altında.", ("deposit:ing_turuncu",))))
        if s.key == key else s for s in template_sections(f, "TR", config.disclaimer["TR"])]
    findings = validate(sections, f, r, config, "TR")
    assert {x.split(":", 1)[0] for x in findings} == {"compare"}, findings


@pytest.mark.parametrize("lang", ["TR", "EN"])
@pytest.mark.parametrize("pid", ["p01", "p02"])
def test_template_has_no_ing_comparison(pid, lang, config):
    ev = evidence_n13()
    r = engine_result_on(ev, pid)
    f = build_facts(r, ev)
    sections = template_sections(f, lang, config.disclaimer[lang])
    for sec in sections:
        if sec.key in ("ozet", "teklif_metni", "alternatifler", "dikkat", "talking_points"):
            for s in sec.sentences:
                assert "Turuncu" not in s.text, (sec.key, s.text)
    assert validate(sections, f, r, config, lang) == ()


def test_deposit_real_point_is_allowed(config):
    ev = evidence_n13()
    r = engine_result_on(ev, "p01")
    assert any(t.code == "deposit_real" for t in r.talking_points)
    f = build_facts(r, ev)
    tp = next(s for s in template_sections(f, "TR", config.disclaimer["TR"])
              if s.key == "talking_points")
    assert any("Piyasa ortalamasındaki mevduat faizi" in s.text for s in tp.sentences)


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_prompt_n9(lang, config):
    s = system_prompt(lang, config)
    assert "Do not compare the ING deposit with the market deposit rate" in s
    assert "and the baseline for comparison" not in s
