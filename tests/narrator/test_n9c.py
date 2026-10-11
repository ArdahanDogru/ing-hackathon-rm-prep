"""N9c: the market deposit rate and the ING rate are separate, named facts; the
ING deposit name never carries a number that is not an ING rate; no RM-only
facts or UI section names in the text."""

import dataclasses

import pytest

from rmprep.contracts import NarrativeSection, NarrativeSentence
from rmprep.narrator.facts import build_facts
from rmprep.narrator.prompt import prompt_facts, system_prompt
from rmprep.narrator.template import template_draft, template_need_tags, template_sections, to_markdown
from rmprep.narrator.validator import validate
from tests.narrator.conftest import CREATED, engine_result, evidence, p02

MARKET = "piyasa_mevduat_faizi"
ING = "ing_mevduat_faizi"


def _with(sections, key, *sentences):
    return [NarrativeSection(s.key, (*s.sentences, *sentences)) if s.key == key else s
            for s in sections]


def _codes(findings):
    return {x.split(":", 1)[0] for x in findings}


def _setup(make=p02, lang="TR", config=None):
    r = make()
    f = build_facts(r, evidence())
    return r, f, list(template_sections(f, lang, config.disclaimer[lang]))


# --- facts -------------------------------------------------------------------------------

def test_deposit_rates_are_named_facts():
    f = build_facts(engine_result("p01"), evidence())
    names = {n.name: n.value for o in f.named_options().values() for n in o.numbers
             if n.quantity == "deposit_rate"}
    assert names[ING] == pytest.approx(23.0)
    assert names[MARKET] == pytest.approx(43.82)


def test_pack_uses_the_names():
    pack = prompt_facts(build_facts(engine_result("p01"), evidence()))
    keys = {k for o in [pack["baseline"], *pack["selected"], *pack["alternatives"]]
            for k in o["numbers"]}
    assert ING in keys and MARKET in keys and "deposit_rate" not in keys


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_system_prompt_explains_the_two_rates(lang, config):
    s = system_prompt(lang, config)
    assert MARKET in s and ING in s


def test_template_names_the_market_rate(config):
    r = engine_result("p01")
    f = build_facts(r, evidence())
    md = to_markdown(template_draft(f, "TR", config, created_at=CREATED))
    assert "piyasa mevduat faizi" in md
    assert "ING mevduat faizi %23,00" in md


# --- validator: the ING name and its numbers ------------------------------------------------

@pytest.mark.parametrize("text, ok", [
    ("Karşılaştırma için ING Turuncu Hesap (standart) mevduat oranı %43,82.", False),
    ("Turuncu Hesap %43,82 faiz veriyor.", False),
    ("ING Turuncu Hesap (standart) %23 faiz veriyor.", True),
    ("ING Turuncu Hesap %23 veriyor, piyasa ortalaması ise %43,82.", True),
    ("Piyasa mevduat faizi %43,82.", True),
    ("ING Turuncu Hesap 100.000-249.999 TL dilimi için geçerlidir.", True),   # no percent
])
def test_ing_name_only_with_an_ing_rate(text, ok, config):
    r = engine_result("p01")
    f = build_facts(r, evidence())
    sections = _with(list(template_sections(f, "TR", config.disclaimer["TR"])),
                     "alternatifler", NarrativeSentence(text, ("deposit:ing_turuncu",)))
    findings = validate(sections, f, r, config, "TR", need_tags=template_need_tags(f))
    assert (findings == ()) == ok, findings
    if not ok:
        assert _codes(findings) == {"label"}


# --- no UI section names, no RM-only facts -----------------------------------------------------

@pytest.mark.parametrize("text", [
    'Veri kalitesi notları için "Olası sorunlar" bölümüne bakın.',
    'See the "Possible issues" pane.',
    "RM notları bölümüne bakın.",
])
def test_ui_section_names_are_internal(text, config):
    r, f, sections = _setup(config=config)
    bad = _with(sections, "dikkat", NarrativeSentence(text, ("fund:BBF",)))
    assert _codes(validate(bad, f, r, config, "TR")) == {"internal"}


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_has_no_ui_pointer(lang, config):
    r, f, sections = _setup(lang=lang, config=config)
    text = " ".join(s.text for sec in sections for s in sec.sentences)
    assert r.data_quality and "Olası sorunlar" not in text and "Possible issues" not in text


def test_pack_has_no_data_quality_flag():
    pack = prompt_facts(build_facts(p02(), evidence()))
    assert "data_quality_notes" not in pack


def test_no_pointer_rule_any_more(config):
    """dikkat without any data-quality sentence passes (N9c replaces the N7 pointer)."""
    r, f, sections = _setup(config=config)
    dikkat = next(s for s in sections if s.key == "dikkat")
    assert not any("Olası" in s.text for s in dikkat.sentences)
    assert validate(sections, f, r, config, "TR") == ()


def test_time_deposit_rate_is_named():
    """An ING e-Vadeli row gets its own name, not the market's or Turuncu's."""
    from rmprep.narrator.facts import deposit_rate_name
    from rmprep.decision.config import load_config

    cfg = load_config()
    assert deposit_rate_name("ING e-Vadeli Mevduat, 32-45 gün, x", cfg) == "ing_vadeli_mevduat_faizi"
    assert deposit_rate_name(cfg.raw["deposit"]["market_entity"], cfg) == MARKET
    assert deposit_rate_name("ING Turuncu Hesap standart, 100.000-249.999 TL", cfg) == ING
    assert deposit_rate_name("Başka banka", cfg) == "deposit_rate"
