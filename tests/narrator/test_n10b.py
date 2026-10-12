"""N10b: an option outside the allowed set (or a rejected one) must not appear
by its short name either (rmprep.api.names.short_name). The issuer must be in
the text: a short label alone is a fund type ("Para Piyasası", "Altın")."""

import dataclasses

import pytest

from rmprep.contracts import NarrativeSection, NarrativeSentence
from rmprep.grouping import top_heads
from rmprep.api.names import short_name
from rmprep.narrator.brief import build_brief_facts, validate_brief
from rmprep.narrator.facts import build_facts
from rmprep.narrator.template import template_sections
from rmprep.narrator.validator import name_forms, validate
from tests.narrator.conftest import approved, evidence

LABELS = {
    "fund:AAL": "AK PORTFÖY PARA PİYASASI KATILIM FONU",            # selected (allowed)
    "fund:BBF": "AK PORTFÖY PARA PİYASASI FONU",                    # not allowed
    "fund:AKE": "İSTANBUL PORTFÖY KISA VADELİ BORÇLANMA ARAÇLARI (TL) FONU",  # not allowed
    "fund:ABU": "ZİRAAT PORTFÖY ALTIN FONU",                        # not allowed
    "fund:AAV": "NUROL PORTFÖY ALTIN FONU",                         # rejected
}


def _relabel(o):
    label = LABELS.get(o.option.option_id)
    return o if label is None else dataclasses.replace(
        o, option=dataclasses.replace(o.option, label=label))


def _result():
    """P02 with only AAL selected (the debt group is then not named)."""
    r = approved("decision_p02_ready", ("fund:AAL",))
    return dataclasses.replace(r, options=tuple(_relabel(o) for o in r.options),
                               rejected=tuple(_relabel(x) for x in r.rejected))


def _findings(text, config):
    r = _result()
    f = build_facts(r, evidence())
    assert set(f.named_options()) == {"deposit:ing_turuncu", "fund:AAL"}
    sections = [NarrativeSection(s.key, (*s.sentences, NarrativeSentence(text, ("fund:AAL",))))
                if s.key == "oneriler" else s
                for s in template_sections(f, "TR", config.disclaimer["TR"])]
    return validate(sections, f, r, config, "TR")


def _codes(findings):
    return {x.split(":", 1)[0] for x in findings}


@pytest.mark.parametrize("text", [
    "Nurol Altın fonu da düşünülebilir.",                 # rejected, issuer core + short label
    "Nurol Portföy Altın fonu da var.",                   # rejected, issuer + short label
    "AK Para Piyasası fonu da konuşulabilir.",            # same issuer as the allowed fund
    "İstanbul Kısa Vadeli Borçlanma fonu da var.",        # "KV" written out
    "İstanbul Portföy KV Borçlanma (TL) da var.",         # the screen's short name
    "İSTANBUL KISA VADELİ BORÇLANMA ARAÇLARI fonu da var.",   # the full fund type
    "Ziraat Altın da uygun olabilir.",
])
def test_short_name_of_an_option_outside_the_set(text, config):
    findings = _findings(text, config)
    assert _codes(findings) == {"option"}, findings


@pytest.mark.parametrize("text", [
    "AK Para Piyasası Katılım fonu öne çıkıyor.",         # the allowed fund itself
    "Ak Portföy Para Piyasası Katılım fonunu anlatın.",
    "Para piyasası fonları likittir.",                    # a fund type, no issuer
    "Altın fiyatları dalgalıdır.",
    "Kısa vadeli borçlanma araçları faize duyarlıdır.",
    "Katılım esaslı bir fondur.",
])
def test_no_hit_without_the_issuer_or_for_the_allowed_fund(text, config):
    assert _findings(text, config) == ()


def test_name_forms():
    forms = name_forms("İSTANBUL PORTFÖY KISA VADELİ BORÇLANMA ARAÇLARI (TL) FONU")
    assert "ıstanbul kısa vadeli borçlanma" in forms or "istanbul kısa vadeli borçlanma" in forms
    assert any(f.endswith("portföy kv borçlanma") for f in forms)
    assert name_forms("ING Turuncu Hesap (standart)") == ()      # no issuer: no short form


def test_brief_short_name_of_a_fund_outside_the_top_3(ready_p01, config):
    f = build_brief_facts(ready_p01, evidence())
    top = {o.option.option_id for o in top_heads(ready_p01.options, 3)}
    allowed = " ".join(name_forms(o.label)[0] for o in f.options if name_forms(o.label))
    other = next(o.option for o in ready_p01.options
                 if o.option.option_id not in top and o.option.kind == "fund"
                 and name_forms(o.option.label)
                 and name_forms(o.option.label)[0] not in allowed)
    issuer, short = short_name(other.label)
    text = f"{issuer.replace(' Portföy', '')} {short.split(' (')[0]} fonunu da konuşun."
    findings = validate_brief(text, (), f, ready_p01, config, "TR")
    assert "option" in _codes(findings), (text, findings)
