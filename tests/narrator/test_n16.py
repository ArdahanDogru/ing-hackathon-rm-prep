"""N16 (docs/narrator.md): the text for the client page. oneriler has 1-2
sentences per option, no facts sentence and no option name at the start; the
shared risk once in dikkat; no past-return reminder in teklif_metni; short
sentences. Prompt n11. Fake LLM only."""

import dataclasses

import pytest

from rmprep.contracts import NarrativeSection, NarrativeSentence
from rmprep.narrator.facts import build_facts
from rmprep.narrator.prompt import system_prompt
from rmprep.narrator.template import (
    TEXTS,
    template_draft,
    template_need_tags,
    template_sections,
    to_markdown,
)
from rmprep.narrator.validator import name_forms, validate
from tests.narrator.conftest import CREATED, engine_result_on, evidence_n13

PROMPT_VERSION = "n11"      # config/narrator.yaml gets it from the lead at the merge


@pytest.fixture(scope="module")
def ev():
    return evidence_n13()


@pytest.fixture(scope="module")
def r02(ev):
    return engine_result_on(ev, "p02", note="Şirket nakdini ayrıca konuşalım.")


@pytest.fixture(scope="module")
def f02(r02, ev):
    return build_facts(r02, ev)


@pytest.fixture(scope="module")
def config_n11(config):
    return dataclasses.replace(config, prompt_version=PROMPT_VERSION)


def _section(sections, key):
    return next(s for s in sections if s.key == key)


def _mine(sections, oid):
    return [s for s in _section(sections, "oneriler").sentences if s.option_ids[:1] == (oid,)]


# --- prompt ----------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_prompt_oneriler_one_or_two_sentences_no_facts(lang, config):
    s = system_prompt(lang, config)
    assert "1-2 sentences" in s and "exactly 3 sentences" not in s
    assert "no facts sentence" in s
    assert "a trade-off of its own" in s and "else no (c)" in s
    assert "not the risk that the selected funds share" in s


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_prompt_no_name_at_the_start_of_oneriler(lang, config):
    s = system_prompt(lang, config)
    assert "must start with the option's name" not in s
    assert "Do not start an oneriler sentence with the option's name" in s


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_prompt_shared_risk_once_in_dikkat(lang, config):
    s = system_prompt(lang, config)
    assert "the risk that the selected funds share" in s
    assert "once, citing the funds it covers" in s


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_prompt_past_returns_only_in_dikkat(lang, config):
    s = system_prompt(lang, config)
    assert "past-return reminder" not in s.split("teklif_metni:", 1)[1].split("- varsayimlar", 1)[0] \
        or "No past-return reminder" in s
    assert "No past-return reminder" in s
    assert "Write the past-return caveat only in dikkat." in s
    assert "only in dikkat and teklif_metni" not in s


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_prompt_short_sentences(lang, config):
    s = system_prompt(lang, config)
    assert "at most about 100 characters" in s and "one idea per sentence" in s


# --- validator -------------------------------------------------------------------------------

def _with_oneriler(sections, sentences):
    return [NarrativeSection("oneriler", tuple(sentences)) if s.key == "oneriler" else s
            for s in sections]


def test_validator_accepts_a_sentence_without_the_name(f02, r02, config):
    sections = list(template_sections(f02, "TR", config.disclaimer["TR"]))
    oid = r02.rm_selected[0]
    ok = _with_oneriler(sections, [*_section(sections, "oneriler").sentences,
                                   NarrativeSentence("Bu fon müşteriye uyar.", (oid,))])
    assert validate(ok, f02, r02, config, "TR") == ()


def test_validator_accepts_one_sentence_per_option(f02, r02, config):
    sections = list(template_sections(f02, "TR", config.disclaimer["TR"]))
    one = [NarrativeSentence("Kısa vadeli nakit ihtiyacına uyduğunu anlatın.", (oid,))
           for oid in r02.rm_selected]
    assert validate(_with_oneriler(sections, one), f02, r02, config, "TR") == ()


def test_validator_has_no_name_check():
    import rmprep.narrator.validator as v

    assert not hasattr(v, "_check_shape")


def test_validator_still_checks_the_rest(f02, r02, config):
    """Dropping the name check keeps the other checks: a number not in the facts fails."""
    sections = list(template_sections(f02, "TR", config.disclaimer["TR"]))
    oid = r02.rm_selected[0]
    bad = _with_oneriler(sections, [*_section(sections, "oneriler").sentences,
                                    NarrativeSentence("Getirisi %987,65 oldu.", (oid,))])
    assert validate(bad, f02, r02, config, "TR") != ()


# --- template --------------------------------------------------------------------------------

def _starts_with_name(text, o):
    """The text starts with the label, the short name, a name form or the fund code."""
    start = text.casefold()
    names = {o.label, o.name, *name_forms(o.label), o.option_id.split(":", 1)[-1]}
    return any(n and start.startswith(n.casefold()) for n in names)


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_oneriler_no_name_no_facts(f02, r02, config, lang):
    sections = template_sections(f02, lang, config.disclaimer[lang])
    named = f02.named_options()
    for oid in r02.rm_selected:
        mine = _mine(sections, oid)
        assert 1 <= len(mine) <= 2, [s.text for s in mine]
        o = named[oid]
        for s in mine:
            assert not _starts_with_name(s.text, o), s.text
            assert "%" not in s.text and "TEFAS" not in s.text, s.text   # no facts sentence
    assert validate(sections, f02, r02, config, lang) == ()


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_shared_risk_once_in_dikkat(f02, r02, config, lang):
    sections = template_sections(f02, lang, config.disclaimer[lang])
    notes = {f02.risks[oid].note[lang] for oid in r02.rm_selected
             if f02.risks.get(oid) and f02.risks[oid].note.get(lang)}
    assert notes
    oneriler = " ".join(s.text for s in _section(sections, "oneriler").sentences)
    dikkat = _section(sections, "dikkat").sentences
    for note in notes:
        assert note.rstrip(".") not in oneriler
        hits = [s for s in dikkat if note.rstrip(".") in s.text]
        assert len(hits) == 1, note
        covered = {oid for oid in r02.rm_selected if f02.risks[oid].note.get(lang) == note}
        assert set(hits[0].option_ids) == covered


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_teklif_has_no_past_return_reminder(f02, config, lang):
    sections = template_sections(f02, lang, config.disclaimer[lang])
    teklif = " ".join(s.text for s in _section(sections, "teklif_metni").sentences)
    assert ("geçmiş" if lang == "TR" else "past") not in teklif.lower()
    dikkat = " ".join(s.text for s in _section(sections, "dikkat").sentences)
    assert TEXTS[lang]["past"] in dikkat


@pytest.mark.parametrize("pid", ["p01", "p02", "p04"])
@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_passes_the_validator(pid, lang, ev, config):
    r = engine_result_on(ev, pid)
    f = build_facts(r, ev)
    sections = template_sections(f, lang, config.disclaimer[lang])
    assert validate(sections, f, r, config, lang, need_tags=template_need_tags(f)) == ()


def test_markdown_keeps_the_heading_per_option(f02, r02, config_n11):
    d = template_draft(f02, "TR", config_n11, created_at=CREATED)
    assert d.prompt_version == PROMPT_VERSION
    md = to_markdown(d)
    for oid in r02.rm_selected:
        assert f"### {oid.split(':', 1)[1]}" in md
