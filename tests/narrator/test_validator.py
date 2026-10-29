import dataclasses
from datetime import date

import pytest

from rmprep.contracts import NarrativeSection, NarrativeSentence
from rmprep.narrator.facts import build_facts
from rmprep.narrator.template import template_sections
from rmprep.narrator.validator import dates_in, numbers_in, validate
from tests.narrator.conftest import approved, evidence, p02, p03, result

CASES = [(p02, "TR"), (p02, "EN"), (p03, "TR"), (p03, "EN")]


def _setup(make=p02, lang="TR", config=None):
    r = make()
    f = build_facts(r, evidence())
    return r, f, list(template_sections(f, lang, config.disclaimer[lang]))


def _check(sections, f, r, config, lang="TR"):
    return validate(sections, f, r, config, lang)


def _with(sections, key, *sentences, replace=False):
    """sections with sentences added to (or replacing) section key."""
    out = []
    for s in sections:
        if s.key == key:
            s = NarrativeSection(key, tuple(sentences) if replace else (*s.sentences, *sentences))
        out.append(s)
    return out


def _codes(findings):
    return {x.split(":", 1)[0] for x in findings}


@pytest.mark.parametrize("make, lang", CASES)
def test_template_text_passes(make, lang, config):
    r, f, sections = _setup(make, lang, config)
    assert _check(sections, f, r, config, lang) == ()


# --- rule 1: numbers -------------------------------------------------------------

@pytest.mark.parametrize("text, ok", [
    ("BBF son bir yılda %52,51 getirdi.", True),
    ("BBF son bir yılda %52,5 getirdi.", True),          # rounded
    ("BBF son bir yılda yaklaşık %53 getirdi.", True),   # rounded to an integer
    ("BBF son bir yılda %57,10 getirdi.", False),
    ("BBF son bir yılda %52,61 getirdi.", False),
    ("Müşteri 48 yaşında, ufku 1-3 yıl.", True),
    ("Müşteri 49 yaşında.", False),
    ("Veri tarihi 09.10.2026.", True),
    ("AFO beş yılda %1.054,64 getirdi.", False),        # only in a data-quality note
    ("Mevduat faizi %23 ve piyasa ortalaması %43,82.", False),   # RM-only warning (N9)
    ("2 seçenek konuşulacak, 1 seçenek elendi.", True),
    ("Risk düzeyi 9.", False),
])
def test_numbers_must_come_from_the_facts(text, ok, config):
    r, f, sections = _setup(config=config)
    bad = _with(sections, "dikkat", NarrativeSentence(text, ("fund:BBF",)))
    findings = _check(bad, f, r, config)
    assert (findings == ()) == ok, findings
    if not ok:
        assert _codes(findings) == {"number"}


def test_english_numbers(config):
    r, f, sections = _setup(lang="EN", config=config)
    good = _with(sections, "oneriler", NarrativeSentence("BBF returned 52.51%, AAL 42.25%.",
                                                         ("fund:BBF",)))
    assert _check(good, f, r, config, "EN") == ()
    bad = _with(sections, "oneriler", NarrativeSentence("BBF returned 61.2%.", ("fund:BBF",)))
    assert _codes(_check(bad, f, r, config, "EN")) == {"number"}


def test_numbers_in():
    assert numbers_in("%1.054,64 ve 52.51% ile 1-3 yıl") >= {(1054.64, 2), (52.51, 2), (1.0, 0),
                                                             (3.0, 0)}
    assert numbers_in("09.10.2026 ve 2026-10-09") == set()      # dates are checked as dates
    assert dates_in("09.10.2026 ve 2026-10-08") == {date(2026, 10, 9), date(2026, 10, 8)}
    assert numbers_in("kanıt E42b47116 ve fund:A1B") == set()   # ids are not numbers


def test_a_date_must_be_a_date_of_the_facts(config):
    r, f, sections = _setup(config=config)
    bad = _with(sections, "dikkat", NarrativeSentence("Veri tarihi 08.10.2026.", ("fund:BBF",)))
    assert _codes(_check(bad, f, r, config)) == {"number"}


# --- rule 2: only named options ---------------------------------------------------

def test_rejected_option_by_label(config):
    r, f, sections = _setup(config=config)
    label = r.rejected[0].option.label
    bad = _with(sections, "dikkat", NarrativeSentence(f"{label} elendi.", ("fund:BBF",)))
    assert _codes(_check(bad, f, r, config)) == {"option"}


def test_rejected_option_label_in_another_case(config):
    r, f, sections = _setup(config=config)
    label = "Ata Portföy İkinci Hisse Senedi (TL) Fonu (Hisse Senedi Yoğun Fon)"
    bad = _with(sections, "teklif_metni", NarrativeSentence(f"{label} de var."))
    assert _codes(_check(bad, f, r, config)) == {"option"}


def test_option_outside_the_named_ones(config):
    r, f, sections = _setup(config=config)
    abu = next(o.option for o in r.options if o.option.option_id == "fund:ABU")
    bad = _with(sections, "teklif_metni", NarrativeSentence(f"{abu.label} da düşünülebilir."))
    assert _codes(_check(bad, f, r, config)) == {"option"}


def test_fund_code_outside_the_named_ones(config):
    r, f, sections = _setup(config=config)
    bad = _with(sections, "teklif_metni", NarrativeSentence("AAV fonu da konuşulabilir."))
    assert _codes(_check(bad, f, r, config)) == {"option"}
    ok = _with(sections, "teklif_metni", NarrativeSentence("BBF fonu öne çıkıyor."))
    assert _check(ok, f, r, config) == ()


# --- rule 3: forbidden phrases ----------------------------------------------------

@pytest.mark.parametrize("lang, text", [
    ("TR", "Bu fon size garantili bir getiri sağlar."),
    ("TR", "GARANTİ veriyoruz."),
    ("TR", "Bu seçenekte Risk Yok."),
    ("EN", "This fund is risk-free."),
    ("EN", "You cannot lose with it."),
])
def test_forbidden_phrases(lang, text, config):
    r, f, sections = _setup(lang=lang, config=config)
    bad = _with(sections, "teklif_metni", NarrativeSentence(text))
    assert _codes(_check(bad, f, r, config, lang)) == {"phrase"}


# --- rule 4: citations -------------------------------------------------------------

@pytest.mark.parametrize("key", ["oneriler", "alternatifler", "dikkat"])
def test_sentence_without_citation(key, config):
    r, f, sections = _setup(config=config)
    bad = _with(sections, key, NarrativeSentence("Bu cümlenin kaynağı yok."))
    assert _codes(_check(bad, f, r, config)) == {"citation"}


def test_uncited_sentence_is_fine_in_other_sections(config):
    r, f, sections = _setup(config=config)
    ok = _with(sections, "sorular", NarrativeSentence("Nakit ihtiyacınız değişti mi?"))
    assert _check(ok, f, r, config) == ()


@pytest.mark.parametrize("sentence", [
    NarrativeSentence("Kaynak.", ("fund:ZZZ",)),
    NarrativeSentence("Kaynak.", ("fund:AAV",)),          # rejected
    NarrativeSentence("Kaynak.", (), ("Edeadbeef",)),
])
def test_unknown_citation(sentence, config):
    r, f, sections = _setup(config=config)
    bad = _with(sections, "sorular", sentence)
    assert _codes(_check(bad, f, r, config)) == {"citation"}


# --- rule 5: disclaimer, structure, assumptions -----------------------------------------

def test_disclaimer_missing(config):
    r, f, sections = _setup(config=config)
    ozet = next(s for s in sections if s.key == "ozet")
    kept = [s for s in ozet.sentences if s.text != config.disclaimer["TR"]]
    bad = _with(sections, "ozet", *kept, replace=True)
    assert _codes(_check(bad, f, r, config)) == {"disclaimer"}


def test_disclaimer_in_other_case_and_spacing_passes(config):
    r, f, sections = _setup(config=config)
    ozet = next(s for s in sections if s.key == "ozet")
    loose = "  bu metin RM'in   görüşme hazırlığı içindir; yatırım tavsiyesi değildir. "
    kept = [s if s.text != config.disclaimer["TR"] else dataclasses.replace(s, text=loose)
            for s in ozet.sentences]
    assert _check(_with(sections, "ozet", *kept, replace=True), f, r, config) == ()


def test_section_missing_or_empty(config):
    r, f, sections = _setup(config=config)
    missing = [s for s in sections if s.key != "sorular"]
    assert _codes(_check(missing, f, r, config)) == {"section"}
    empty = _with(sections, "sorular", replace=True)
    assert _codes(_check(empty, f, r, config)) == {"section"}


def test_assumptions_must_be_verbatim(config):
    r, f, sections = _setup(config=config)
    bad = _with(sections, "varsayimlar", NarrativeSentence(r.assumptions[0]), replace=True)
    findings = _check(bad, f, r, config)
    assert _codes(findings) == {"assumption"} and len(findings) == len(r.assumptions) - 1


def test_findings_name_section_and_text(config):
    r, f, sections = _setup(config=config)
    bad = _with(sections, "dikkat", NarrativeSentence("Getiri %77,7 oldu.", ("fund:BBF",)))
    (finding,) = _check(bad, f, r, config)
    assert finding.startswith("number: ") and "dikkat" in finding and "77,7" in finding


@pytest.mark.parametrize("name", ["decision_p02_ready", "decision_p03_ready"])
@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_passes_for_every_single_selection(name, lang, config):
    """The template is the fallback: it must pass for any selection."""
    for o in result(name).options:
        r = approved(name, (o.option.option_id,))
        f = build_facts(r, evidence())
        sections = template_sections(f, lang, config.disclaimer[lang])
        assert validate(sections, f, r, config, lang) == (), o.option.option_id


# --- N5: a fund label is not a forbidden phrase ---------------------------------------

GARANTI = "GARANTİ PORTFÖY PARA PİYASASI KATILIM (TL) FONU"


def _garanti():
    """P02 with the selected fund AAL renamed to a Garanti Portföy fund."""
    r = p02()
    options = tuple(dataclasses.replace(o, option=dataclasses.replace(o.option, label=GARANTI))
                    if o.option.option_id == "fund:AAL" else o for o in r.options)
    r = dataclasses.replace(r, options=options)
    return r, build_facts(r, evidence())


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_naming_a_garanti_fund_passes(lang, config):
    r, f = _garanti()
    sections = template_sections(f, lang, config.disclaimer[lang])
    assert validate(sections, f, r, config, lang) == ()


@pytest.mark.parametrize("name", [GARANTI, "Garanti Portföy Para Piyasası Katılım (TL) Fonu",
                                  "garanti portföy para piyasası katılım (tl) fonu"])
def test_a_garanti_fund_label_in_any_case_passes(name, config):
    r, f = _garanti()
    sections = list(template_sections(f, "TR", config.disclaimer["TR"]))
    ok = _with(sections, "oneriler", NarrativeSentence(f"{name} likiditesi yüksek bir fondur.",
                                                       ("fund:AAL",)))
    assert _check(ok, f, r, config) == ()


@pytest.mark.parametrize("text", ["Garanti Portföy AAL likiditesi yüksek bir fondur.",
                                  "Garanti Portföy fonu likiditesi yüksektir."])
def test_the_issuer_with_its_code_passes(text, config):
    """Eval 20261017-160939 (found and fixed): "Garanti Portföy GZP" (the issuer and
    the code, the N16 short form) was read as the phrase "garanti"."""
    r, f = _garanti()
    sections = list(template_sections(f, "TR", config.disclaimer["TR"]))
    ok = _with(sections, "oneriler", NarrativeSentence(text, ("fund:AAL",)))
    assert _check(ok, f, r, config) == ()


@pytest.mark.parametrize("text", ["Fon sepeti grubunda Garanti AAL bulunur.",
                                  "GARANTİ AAL likiditesi yüksek bir fondur."])
def test_the_short_issuer_with_its_code_passes(text, config):
    """Eval 20261029-153753 (found and fixed): the model wrote "Garanti GZP" (the issuer
    without "Portföy" and the code); the first attempt failed on "garanti"."""
    r, f = _garanti()
    sections = list(template_sections(f, "TR", config.disclaimer["TR"]))
    ok = _with(sections, "oneriler", NarrativeSentence(text, ("fund:AAL",)))
    assert _check(ok, f, r, config) == ()


@pytest.mark.parametrize("text", ["Garanti AAL getiriyi garanti eder.",
                                  "Garanti ile AAL getirisi korunur."])
def test_garanti_without_the_code_right_after_still_fails(text, config):
    r, f = _garanti()
    sections = list(template_sections(f, "TR", config.disclaimer["TR"]))
    bad = _with(sections, "oneriler", NarrativeSentence(text, ("fund:AAL",)))
    assert _codes(_check(bad, f, r, config)) == {"phrase"}


def test_a_real_garanti_next_to_the_issuer_still_fails(config):
    r, f = _garanti()
    sections = list(template_sections(f, "TR", config.disclaimer["TR"]))
    bad = _with(sections, "oneriler", NarrativeSentence("Garanti Portföy AAL getiriyi garanti eder.",
                                                        ("fund:AAL",)))
    assert _codes(_check(bad, f, r, config)) == {"phrase"}


def test_a_real_garanti_next_to_the_label_still_fails(config):
    r, f = _garanti()
    sections = list(template_sections(f, "TR", config.disclaimer["TR"]))
    bad = _with(sections, "oneriler", NarrativeSentence(f"{GARANTI} ile getiri garantilidir.",
                                                        ("fund:AAL",)))
    findings = _check(bad, f, r, config)
    assert _codes(findings) == {"phrase"} and "garanti" in findings[0]


def test_a_data_quality_row_count_is_internal(config):
    """N7: row counts of data-quality notes are internal values."""
    from rmprep.contracts import DataQualityNote

    r = p02()
    ids = tuple(d.id for d in evidence().datapoints)[:11]
    r = dataclasses.replace(r, data_quality=(DataQualityNote("Bazı değerler eski.",
                                                             evidence_ids=ids),))
    f = build_facts(r, evidence())
    sections = list(template_sections(f, "TR", config.disclaimer["TR"]))
    bad = _with(sections, "dikkat", NarrativeSentence("11 kayıt eski.", ("fund:BBF",)))
    assert _codes(validate(bad, f, r, config, "TR")) == {"internal"}
