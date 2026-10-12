"""N7 (docs/narrator.md): no internal values in the text, one data-quality
pointer, every selected option linked to a client need, a client-based script."""

import dataclasses

import pytest

from rmprep.contracts import NarrativeSection, NarrativeSentence
from rmprep.narrator.facts import build_facts
from rmprep.narrator.prompt import prompt_facts, system_prompt
from rmprep.narrator.template import template_sections
from rmprep.narrator.validator import validate
from tests.narrator.conftest import evidence, p02, p03

INCOME_REASON = "Düzenli gelir uygunluğu (ürün türüne göre): 0.6."


def _p02_with_internal_reason():
    """P02 with the real engine text of an internal score in BBF's income reason."""
    r = p02()
    options = tuple(dataclasses.replace(o, reasons={**o.reasons, "income": INCOME_REASON})
                    if o.option.option_id == "fund:BBF" else o for o in r.options)
    return dataclasses.replace(r, options=options)


def _setup(make=p02, lang="TR", config=None):
    r = make()
    f = build_facts(r, evidence())
    return r, f, list(template_sections(f, lang, config.disclaimer[lang]))


def _with(sections, key, *sentences, replace=False):
    out = []
    for s in sections:
        if s.key == key:
            s = NarrativeSection(key, tuple(sentences) if replace else (*s.sentences, *sentences))
        out.append(s)
    return out


def _codes(findings):
    return {x.split(":", 1)[0] for x in findings}


def _section(sections, key):
    return next(s for s in sections if s.key == key)


# --- validator: internal names and values ---------------------------------------------

@pytest.mark.parametrize("text", [
    "Bazı değerler needs_check işaretli.",
    "Veriler tefas_web kaynağından.",
    "Bu fonda penalty:principal var.",
    "Değer out_of_range.",
])
def test_internal_names(text, config):
    r, f, sections = _setup(config=config)
    bad = _with(sections, "dikkat", NarrativeSentence(text, ("fund:BBF",)))
    assert _codes(validate(bad, f, r, config, "TR")) == {"internal"}


@pytest.mark.parametrize("text", [
    "BBF için gelir uygunluğu 0,6.",       # an internal score in a reason text
    "BBF güven düzeyi 0,9.",               # confidence
    "254 değer kontrol gerektiriyor.",     # a row count of a data-quality note
])
def test_internal_numbers(text, config):
    r = _p02_with_internal_reason()
    f = build_facts(r, evidence())
    sections = list(template_sections(f, "TR", config.disclaimer["TR"]))
    bad = _with(sections, "dikkat", NarrativeSentence(text, ("fund:BBF",)))
    assert _codes(validate(bad, f, r, config, "TR")) == {"internal"}


def test_varsayimlar_may_hold_internal_names(config):
    r, f, sections = _setup(config=config)
    assert any("_" in a for a in r.assumptions)        # "doviz_maruz_kalma_tercihi" ...
    assert validate(sections, f, r, config, "TR") == ()


# --- validator: coverage and pointer ---------------------------------------------------

def test_every_selected_option_needs_an_oneriler_sentence(config):
    r, f, sections = _setup(config=config)
    oneriler = _section(sections, "oneriler")
    kept = [s for s in oneriler.sentences if "fund:AAL" not in s.option_ids]
    findings = validate(_with(sections, "oneriler", *kept, replace=True), f, r, config, "TR")
    assert _codes(findings) == {"coverage"} and "fund:AAL" in findings[0]


def test_no_pointer_needed_without_data_quality_notes(config):
    """(N9c: there is no pointer to a screen section at all; see test_n9c.)"""
    r = dataclasses.replace(p02(), data_quality=())
    f = build_facts(r, evidence())
    sections = template_sections(f, "TR", config.disclaimer["TR"])
    assert "Olası sorunlar" not in " ".join(s.text for sec in sections for s in sec.sentences)
    assert validate(sections, f, r, config, "TR") == ()


# --- template ----------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_passes_with_an_internal_reason(lang, config):
    r = _p02_with_internal_reason()
    f = build_facts(r, evidence())
    sections = template_sections(f, lang, config.disclaimer[lang])
    text = " ".join(s.text for sec in sections for s in sec.sentences)
    assert INCOME_REASON not in text
    assert validate(sections, f, r, config, lang) == ()


@pytest.mark.parametrize("make", [p02, p03])
def test_template_links_each_option_to_a_client_need(make, config):
    r, f, sections = _setup(make, config=config)
    needs = [v for k, v in f.client.items() if isinstance(v, str) and k != "profil"]
    links = []
    for o in f.selected:
        mine = [s.text for s in _section(sections, "oneriler").sentences
                if s.option_ids == (o.option_id,)]
        link = [t for t in mine if any(f'"{n}"' in t for n in needs)]
        assert link, (o.option_id, mine)
        links.append(link[0].replace(o.label, ""))
    assert len(set(links)) == len(links)          # the options do not read alike


def test_template_script_is_built_on_the_client(config):
    r, f, sections = _setup(config=config)
    script = " ".join(s.text for s in _section(sections, "teklif_metni").sentences)
    assert r.persona.yatirim_amaci in script and r.persona.durum in script
    assert "geçmiş getiri" in script


# --- prompt pack and system prompt -----------------------------------------------------

def test_pack_has_no_internal_values():
    r = _p02_with_internal_reason()
    pack = prompt_facts(build_facts(r, evidence()))
    bbf = next(o for o in pack["selected"] if o["option_id"] == "fund:BBF")
    assert "confidence" not in bbf and INCOME_REASON not in bbf["reasons"]
    assert bbf["fits"] == ["liquidity", "income", "principal"]
    assert pack["client"]["likidite_ihtiyaci"] == r.persona.likidite_ihtiyaci
    assert "rejected" not in pack and "data_quality" not in pack


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_system_prompt_states_the_internal_rule(lang, config):
    s = system_prompt(lang, config)
    assert "needs_check" in s and "fits" in s
    assert "Olası sorunlar" not in s and "Possible issues" not in s     # N9c
