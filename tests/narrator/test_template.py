import pytest

from rmprep.contracts import NARRATIVE_SECTIONS_V13, NarrativeDraft
from rmprep.narrator.facts import build_facts
from rmprep.narrator.template import fmt_number, template_draft, to_markdown, tr_lower
from tests.narrator.conftest import CREATED, evidence, p02, p03

CITED = ("oneriler", "alternatifler", "dikkat")
CASES = [(p02, "TR"), (p02, "EN"), (p03, "TR"), (p03, "EN")]


def _draft(make, lang, config) -> tuple:
    r = make()
    f = build_facts(r, evidence())
    return r, f, template_draft(f, lang, config, created_at=CREATED)


def _section(d: NarrativeDraft, key: str):
    return next(s for s in d.sections if s.key == key)


def _text(d: NarrativeDraft) -> str:
    return " ".join(s.text for sec in d.sections for s in sec.sentences)


@pytest.mark.parametrize("make, lang", CASES)
def test_template_draft_shape(make, lang, config):
    r, _, d = _draft(make, lang, config)
    assert d.run_id == r.run_id and d.lang == lang
    assert (d.source, d.model, d.cost_usd, d.checks) == ("template", "", 0.0, ())
    assert d.prompt_version == config.prompt_version
    assert d.created_at == CREATED
    assert tuple(s.key for s in d.sections) == NARRATIVE_SECTIONS_V13
    assert all(s.sentences and all(x.text.strip() for x in s.sentences) for s in d.sections)


@pytest.mark.parametrize("make, lang", CASES)
def test_every_cited_sentence_has_known_citations(make, lang, config):
    _, f, d = _draft(make, lang, config)
    known_options, known_evidence = set(f.named_options()), f.evidence_ids()
    for key in CITED:
        for s in _section(d, key).sentences:
            assert s.option_ids or s.evidence_ids, (key, s.text)
            assert set(s.option_ids) <= known_options
            assert set(s.evidence_ids) <= known_evidence


@pytest.mark.parametrize("make, lang", CASES)
def test_no_rejected_or_unnamed_option(make, lang, config):
    r, f, d = _draft(make, lang, config)
    text = _text(d)
    named = set(f.named_options())
    for o in r.options:
        if o.option.option_id not in named:
            assert o.option.label not in text
    for rej in r.rejected:
        assert rej.option.label not in text and rej.option.option_id not in text


@pytest.mark.parametrize("make, lang", CASES)
def test_disclaimer_and_no_forbidden_phrase(make, lang, config):
    _, _, d = _draft(make, lang, config)
    text = _text(d)
    assert config.disclaimer[lang] in text
    low = tr_lower(text)
    for phrase in config.forbidden_phrases[lang]:
        assert tr_lower(phrase) not in low, phrase


def test_oneriler_one_block_per_selected_option(config):
    _, f, d = _draft(p02, "TR", config)
    sents = _section(d, "oneriler").sentences
    for o in f.selected:
        mine = [s for s in sents if s.option_ids == (o.option_id,)]
        assert mine and not mine[0].text.startswith(o.name)        # N16: no name, no facts
    text = " ".join(s.text for s in sents)
    assert "%52,51" not in text                # BBF 1-year return: the page shows it
    assert "Vade ufkuna uygun." in text        # the RM note of the option


def test_alternatifler_names_the_group_alternatives(config):
    _, f, d = _draft(p02, "TR", config)
    sents = _section(d, "alternatifler").sentences
    ake = f.alternatives[0]
    assert any(ake.label in s.text and "fund:AKE" in s.option_ids for s in sents)
    # N13c: no ING deposit baseline in alternatifler (the comparison is an RM-only note)
    assert not any("deposit:ing_turuncu" in s.option_ids for s in sents)


def test_dikkat_has_warnings_a_pane_pointer_and_the_past_return_caveat(config):
    """N7: client warnings, one data-quality pointer, no internal values."""
    r, _, d = _draft(p02, "TR", config)
    text = " ".join(s.text for s in _section(d, "dikkat").sentences)
    for w in r.warnings:
        assert (w.message in text) == (w.audience == "client")      # N9
    assert r.data_quality[0].message not in text and "needs_check" not in text
    assert "Olası sorunlar" not in text                      # N9c: no screen names
    assert "geçmiş getiri" in text
    assert "elendi" not in text and "risk tavanı" not in text


def test_sorular_and_varsayimlar_from_the_result(config):
    r, _, d = _draft(p02, "TR", config)
    sorular = " ".join(s.text for s in _section(d, "sorular").sentences)
    assert r.questions[0].text in sorular
    for k in r.persona.acik_kisitlar:
        assert k in sorular
    assert tuple(s.text for s in _section(d, "varsayimlar").sentences) == r.assumptions


def test_english_template_is_english(config):
    _, _, d = _draft(p03, "EN", config)
    assert "client" in _text(d).lower()
    assert "müşteri" not in tr_lower(" ".join(s.text for s in _section(d, "teklif_metni").sentences))


def test_unknown_language(config):
    f = build_facts(p02(), evidence())
    with pytest.raises(ValueError, match="lang"):
        template_draft(f, "DE", config, created_at=CREATED)


def test_markdown_has_every_section_and_sentence(config):
    _, _, d = _draft(p02, "TR", config)
    md = to_markdown(d)
    # N13: ## per main section + "Ek bilgiler"; ### for its three sections and per option
    assert md.count("\n## ") == 6
    assert md.count("\n### ") == 3 + len({s.option_ids[0] for sec in d.sections
                                           if sec.key == "oneriler" for s in sec.sentences})
    for sec in d.sections:
        for s in sec.sentences:
            assert s.text in md


@pytest.mark.parametrize("value, unit, lang, out", [
    (52.5143, "pct", "TR", "%52,51"),
    (52.5143, "pct", "EN", "52.51%"),
    (1054.6369, "pct", "TR", "%1.054,64"),
    (1054.6369, "pct", "EN", "1,054.64%"),
    (-8.3, "pct", "TR", "%-8,30"),
    (2.0, "level", "TR", "2"),
    (41.98, "TRY", "EN", "41.98"),
])
def test_fmt_number(value, unit, lang, out):
    assert fmt_number(value, unit, lang) == out


def test_tr_lower():
    assert tr_lower("GARANTİ RİSKSİZ") == "garanti risksiz"
    assert tr_lower("IRAK") == "ırak"


def test_oneriler_punctuation_and_counts(config):
    """Reasons joined without ".;" or "..", whole counts without decimals, the
    deposit rate named as such (N9 review of a P01 draft)."""
    from tests.narrator.conftest import engine_result

    r = engine_result("p01")
    f = build_facts(r, evidence())
    d = template_draft(f, "TR", config, created_at=CREATED)
    text = " ".join(s.text for s in _section(d, "oneriler").sentences)
    assert ".;" not in text and ".." not in text
    assert ",00 (TEFAS" not in text
    assert "yıllık faiz oranı" not in text
    assert "piyasa mevduat faizi" not in text          # N13: the market rate is not per option


@pytest.mark.parametrize("value, unit, lang, out", [
    (1053.0, "count", "TR", "1.053"),
    (19526.0, "count", "EN", "19,526"),
])
def test_fmt_number_whole_counts(value, unit, lang, out):
    assert fmt_number(value, unit, lang) == out
