"""N13b (prompt n8): dikkat does not repeat oneriler; a watch item only for what
oneriler does not say (slow access, fees); length targets."""

import dataclasses

import pytest

from rmprep.contracts import NarrativeSection, NarrativeSentence
from rmprep.narrator.facts import build_facts
from rmprep.narrator.prompt import prompt_facts, system_prompt
from rmprep.narrator.template import template_sections
from rmprep.narrator.validator import repeats, validate
from tests.narrator.conftest import engine_result_on, evidence_n13


@pytest.fixture(scope="module")
def ev():
    return evidence_n13()


@pytest.fixture(scope="module")
def r02(ev):
    return engine_result_on(ev, "p02")


@pytest.fixture(scope="module")
def f02(r02, ev):
    return build_facts(r02, ev)


def _section(sections, key):
    return next(s for s in sections if s.key == key)


def _with_dikkat(sections, sentence):
    return [NarrativeSection("dikkat", (*s.sentences, sentence)) if s.key == "dikkat" else s
            for s in sections]


def _codes(findings):
    return {x.split(":", 1)[0] for x in findings}


# --- the repeat rule ------------------------------------------------------------------------

RISK = ("Nurol Portföy Para Piyasası (TL) için getirisi faiz değişimine bağlıdır; mevduat gibi "
        "anapara güvencesi yoktur, bunu anapara korumayı önemseyen müşteriye açıkça söyleyin.")


@pytest.mark.parametrize("dikkat, hit", [
    ("Nurol Portföy Para Piyasası (TL) için getirisi faiz değişimine bağlıdır; mevduat gibi "
     "anapara güvencesi yoktur.", True),                                   # the live finding
    (RISK, True),                                                         # a full copy
    ("Nurol Portföy Para Piyasası (TL): paraya erişim 2 iş günü.", False),   # a new fact
    ("Seçilen fonların fiyatlarını düzenli izleyin.", False),
    ("Nurol Portföy Para Piyasası (TL).", False),                         # only the name
])
def test_repeats(dikkat, hit):
    names = ["nurol portföy para piyasası (tl)", "nurol portföy para piyasası"]
    assert repeats(dikkat, [RISK, "Başka bir cümle."], names) is hit


def test_validator_finds_a_dikkat_copy_of_oneriler(f02, r02, config):
    sections = list(template_sections(f02, "TR", config.disclaimer["TR"]))
    oid = r02.rm_selected[0]
    copy = next(s for s in _section(sections, "oneriler").sentences
                if s.option_ids[:1] == (oid,) and "Getirisi" in s.text)
    findings = validate(_with_dikkat(sections, NarrativeSentence(copy.text, (oid,))),
                        f02, r02, config, "TR")
    assert _codes(findings) == {"repeat"}, findings


# --- template: watch items only for slow access or fees -------------------------------------------

def test_no_watch_item_for_same_day_access_without_fees(f02, r02, config):
    dikkat = _section(template_sections(f02, "TR", config.disclaimer["TR"]), "dikkat")
    assert all(f02.risks[o].access == "Aynı gün" and not f02.risks[o].fees
               for o in r02.rm_selected)
    assert not any(s.option_ids == (o,) for s in dikkat.sentences for o in r02.rm_selected)


def test_watch_item_for_slow_access(f02, r02, config):
    oid = r02.rm_selected[0]
    slow = dataclasses.replace(f02.risks[oid], access="2 iş günü", access_days=2.0)
    f = dataclasses.replace(f02, risks={**f02.risks, oid: slow})
    sections = template_sections(f, "TR", config.disclaimer["TR"])
    mine = [s for s in _section(sections, "dikkat").sentences if s.option_ids == (oid,)]
    assert len(mine) == 1 and "2 iş günü" in mine[0].text
    assert validate(sections, f, r02, config, "TR") == ()


def test_template_teklif_at_most_4_sentences(f02, config):
    for lang in ("TR", "EN"):
        teklif = _section(template_sections(f02, lang, config.disclaimer[lang]), "teklif_metni")
        assert len(teklif.sentences) <= 4


# --- pack and prompt ----------------------------------------------------------------------------

def test_pack_says_if_access_is_slow(f02):
    for o in prompt_facts(f02, "TR")["selected"]:
        assert o["risk"]["access_slow"] is False


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_prompt_n8(lang, config):
    s = system_prompt(lang, config)
    for words in ("450 words", "teklif_metni at most 4 sentences", "does not say",
                  "do not repeat"):
        assert words in s, words
