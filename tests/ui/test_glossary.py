"""U11: "Terimler" / "Terms" from config/glossary.yaml under the meeting text and
in the summary card; only the terms that appear in the shown text."""

import html

import pytest

from rmprep.contracts import RmStatus
from rmprep.ui import card, glossary
from rmprep.ui.i18n import t
from tests.ui.conftest import CONTRACT_FIX, SNAPSHOT, app_test, run

REAL = CONTRACT_FIX.parents[2] / "config" / "glossary.yaml"

MINI = """\
version: 1
terms:
  valor:
    forms: {TR: ["valör"], EN: ["value date"]}
    TR: "Valör açıklaması."
    EN: "Value date explanation."
  stopaj:
    forms: {TR: ["stopaj"], EN: ["withholding tax"]}
    TR: "Stopaj açıklaması."
    EN: "Withholding tax explanation."
  reel_getiri:
    forms: {TR: ["reel getiri", "reel"], EN: ["real return"]}
    TR: "Reel açıklaması."
    EN: "Real return explanation."
  guven:
    forms: {TR: ["güven"], EN: ["confidence"]}
    TR: "Güven açıklaması."
    EN: "Confidence explanation."
"""


@pytest.fixture
def mini(tmp_path):
    p = tmp_path / "glossary.yaml"
    p.write_text(MINI, encoding="utf-8")
    return glossary.load(p)


def _keys(found):
    return [f.term.key for f in found]


# --- loader -------------------------------------------------------------------

def test_the_real_glossary_loads_all_terms():
    terms = glossary.load(REAL)
    assert len(terms) == 16
    assert all(term.forms["TR"] and term.forms["EN"] and term.text["TR"] and term.text["EN"]
               for term in terms)


def test_a_missing_file_gives_no_terms(tmp_path):
    assert glossary.load(tmp_path / "nope.yaml") == ()


@pytest.mark.parametrize("content", [
    "terms: [this is: not: yaml",
    "just a string",
    "terms: {valor: {forms: {TR: ['valör']}, TR: 'x'}}",          # no EN
    "terms: {valor: {forms: {TR: 'valör', EN: ['v']}, TR: 'x', EN: 'y'}}",   # forms not a list
    "terms: []",
])
def test_a_broken_file_gives_no_terms(tmp_path, content):
    p = tmp_path / "glossary.yaml"
    p.write_text(content, encoding="utf-8")
    assert glossary.load(p) == ()


def test_tr_lower():
    assert glossary.tr_lower("İSTANBUL IŞIK TÜFE") == "istanbul ışık tüfe"


# --- matching -----------------------------------------------------------------

def test_a_text_with_valor_and_stopaj_shows_those_two_terms(mini):
    found = glossary.find_terms("Satış VALÖRÜ değil: valör 2 gün; Stopaj dahil değil.", mini, "TR")
    assert _keys(found) == ["valor", "stopaj"]
    assert [f.explanation for f in found] == ["Valör açıklaması.", "Stopaj açıklaması."]


def test_terms_are_in_the_order_of_first_appearance(mini):
    assert _keys(glossary.find_terms("stopaj, sonra valör", mini, "TR")) == ["stopaj", "valor"]


def test_whole_words_only(mini):
    assert glossary.find_terms("reelleşme ve güvenli liman", mini, "TR") == []
    assert _keys(glossary.find_terms("Reel getiri ve güven 0.90.", mini, "TR")) == [
        "reel_getiri", "guven"]


def test_a_term_matches_once_with_its_first_form(mini):
    found = glossary.find_terms("reel, sonra reel getiri", mini, "TR")
    assert _keys(found) == ["reel_getiri"] and found[0].form == "reel"


def test_english_page_uses_english_forms_and_explanations(mini):
    found = glossary.find_terms("The value date is 2 days; withholding tax applies.", mini, "EN")
    assert _keys(found) == ["valor", "stopaj"]
    assert found[0].explanation == "Value date explanation."


def test_english_page_also_finds_turkish_forms_of_the_engine_texts(mini):
    found = glossary.find_terms("Reason: valör 2 gün.", mini, "EN")
    assert _keys(found) == ["valor"] and found[0].explanation == "Value date explanation."


def test_turkish_page_does_not_match_english_forms(mini):
    assert glossary.find_terms("value date", mini, "TR") == []


def test_no_terms_without_a_glossary():
    assert glossary.find_terms("valör stopaj", (), "TR") == []


# --- card ---------------------------------------------------------------------

def _approved(fake):
    p = next(p for p in fake.list_personas() if p.persona_id == "P02")
    r = fake.decide(p, SNAPSHOT)
    return fake.approve(r.run_id, RmStatus.APPROVED, "", (r.options[1].option.option_id,))


def test_card_lists_the_terms_of_its_own_text(fake, mini):
    r = _approved(fake)
    ev = fake.evidence(SNAPSHOT)
    plain = card.render_markdown(r, ev, "TR")
    assert "stopaj" in plain and "valör" not in plain.lower()
    md = card.render_markdown(r, ev, "TR", glossary_terms=mini)
    assert f"## {t('terms')}" in md
    assert "Stopaj açıklaması." in md and "Valör açıklaması." not in md
    doc = card.render_html(r, ev, "TR", glossary_terms=mini)
    assert html.escape(t("terms")) in doc and "Stopaj açıklaması." in doc
    assert "Valör açıklaması." not in doc


def test_card_terms_include_the_approved_meeting_text(fake, mini):
    r = _approved(fake)
    ev = fake.evidence(SNAPSHOT)
    a = fake.approve_narrative(r.run_id, "TR", "Valör 2 gün.")
    md = card.render_markdown(r, ev, "TR", narrative=a, glossary_terms=mini)
    assert md.index("Valör açıklaması.") > md.index(t("nar_title"))


def test_card_without_a_glossary_has_no_terms_section(fake):
    r = _approved(fake)
    assert f"## {t('terms')}" not in card.render_markdown(r, fake.evidence(SNAPSHOT), "TR")


# --- page ---------------------------------------------------------------------

def _approved_page(monkeypatch, path):
    from rmprep.ui import page

    monkeypatch.setattr(page, "GLOSSARY", path)
    at = run(app_test())
    at.selectbox(key="persona").set_value("P02")
    run(at)
    r = at.session_state["result"]
    at.checkbox(key=f"sel:{r.run_id}:{r.options[1].option.option_id}").check()
    at.button(key="approve").click()
    return run(at), r.run_id


def _terms_under_the_text(at):
    return [m.value for m in at.markdown if m.value.startswith("- **") and "açıklaması" in m.value]


def test_terms_under_the_meeting_text_follow_the_shown_text(monkeypatch, tmp_path):
    p = tmp_path / "glossary.yaml"
    p.write_text(MINI, encoding="utf-8")
    at, run_id = _approved_page(monkeypatch, p)
    assert any(m.value == f"**{t('terms')}**" for m in at.markdown)
    at.text_area(key=f"nar_text:{run_id}:TR").input("Valör ve stopaj.")
    run(at)
    assert _terms_under_the_text(at) == ["- **valör**: Valör açıklaması.",
                                         "- **stopaj**: Stopaj açıklaması."]


def test_english_page_explains_in_english(monkeypatch, tmp_path):
    p = tmp_path / "glossary.yaml"
    p.write_text(MINI, encoding="utf-8")
    at, run_id = _approved_page(monkeypatch, p)
    at.radio(key="lang").set_value("EN")
    run(at)
    at.text_area(key=f"nar_text:{run_id}:EN").input("The value date is 2 days.")
    run(at)
    assert "- **value date**: Value date explanation." in [m.value for m in at.markdown]


def test_a_missing_glossary_gives_no_section_and_no_crash(monkeypatch, tmp_path):
    at, run_id = _approved_page(monkeypatch, tmp_path / "missing.yaml")
    assert not any(m.value == f"**{t('terms')}**" for m in at.markdown)
    assert not any(f"## {t('terms')}" in m.value for m in at.markdown)
