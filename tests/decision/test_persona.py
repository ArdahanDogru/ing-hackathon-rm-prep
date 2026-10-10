"""Persona text -> levels, questions and assumptions (docs/decision.md section 3)."""

import dataclasses

import pytest

from rmprep.decision.persona import normalize, read_persona
from tests.decision.conftest import PERSONA_IDS, load_persona


def _edit(pid, **changes):
    return dataclasses.replace(load_persona(pid), **changes)


# --- normalization -----------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Muhafazakâr", "muhafazakâr"),
    ("  İLERİ   Yaşlı ", "ileri yaşlı"),
    ("IŞIK", "ışık"),
    ("1-3 yıl", "1-3 yıl"),
    ("5+ Yıl.", "5+ yıl"),
    ("düzenli gelir!", "düzenli gelir"),
    ("a, b; (c)", "a b c"),
])
def test_normalize(text, expected):
    assert normalize(text) == expected


# --- p01-p05 -------------------------------------------------------------------------

EXPECTED = {
    #       ceiling appetite period liq  inc  prin fx  liq_int liq_w0 diversity boosts
    "P01": (2, 0.0, "1y", 0.5, 1.0, 1.0, 1.0, 0.5, False, False,
            {"income": 1, "liquidity": 1, "low_risk": 1}),
    "P02": (5, 0.6666666667, "1y", 0.5, 0.5, 0.5, 1.0, 0.5, False, True,
            {"liquidity": 1}),
    "P03": (7, 1.0, "3y", 0.0, 0.0, 0.0, 0.0, 0.0, True, True,
            {"return": 2}),
    "P04": (5, 0.6666666667, "3y", 0.5, 0.5, 0.5, 0.0, 0.5, False, True,
            {"low_risk": 1}),
    "P05": (3, 0.3333333333, "1y", 1.0, 0.5, 1.0, 1.0, 1.0, False, False,
            {"liquidity": 1, "principal": 1, "simplicity": 1}),
}


@pytest.mark.parametrize("pid", PERSONA_IDS)
def test_personas_map_to_levels(config, pid):
    r = read_persona(load_persona(pid), config)
    lv = r.levels
    assert not r.blocked
    (ceiling, appetite, period, liq, inc, prin, fx, liq_int, liq_w0, diversity,
     boosts) = EXPECTED[pid]
    assert lv.ceiling == ceiling
    assert lv.appetite == pytest.approx(appetite)
    assert lv.period == period
    assert (lv.liquidity, lv.income, lv.principal) == (liq, inc, prin)
    assert lv.fx_intensity == fx
    assert lv.liquidity_intensity == liq_int
    assert (lv.liquidity_weight == 0.0) is liq_w0
    assert lv.diversity is diversity
    assert dict(lv.boosts) == boosts


def test_p01_constraint_caps_the_ceiling_only_downwards(config):
    p = _edit("P01", risk_profili="Agresif")
    assert read_persona(p, config).levels.ceiling == 4
    assert read_persona(load_persona("P01"), config).levels.ceiling == 2


def test_p02_fx_text_is_an_open_non_blocking_question(config):
    r = read_persona(load_persona("P02"), config)
    assert not r.blocked
    [q] = r.questions
    assert q.question_id == "q:doviz_maruz_kalma_tercihi"
    assert q.about == "doviz_maruz_kalma_tercihi"
    assert q.blocking is False and q.answer is None
    assert q.choices == ("Sınırlı", "Açık", "Çeşitlendirilmiş")
    assert "Mevcut döviz gelirini dikkate alarak kontrollü" in q.reason
    assert any("güvenli düzey \"Sınırlı\"" in a for a in r.assumptions)


@pytest.mark.parametrize("pid", ["P01", "P03", "P04", "P05"])
def test_other_personas_have_no_questions(config, pid):
    assert read_persona(load_persona(pid), config).questions == ()


def test_priority_notes_and_unused_priorities_become_assumptions(config):
    p02 = read_persona(load_persona("P02"), config)
    assert any("kur riskini yönetme" in a for a in p02.assumptions)
    p04 = read_persona(load_persona("P04"), config)
    assert any("kuşaklar arası planlama" in a for a in p04.assumptions)
    p = read_persona(_edit("P01", oncelikler=("düzenli gelir", "bilinmeyen öncelik")), config)
    assert "Kullanılmayan öncelik: \"bilinmeyen öncelik\"." in p.assumptions
    assert not p.questions


# --- unknown text -> questions -------------------------------------------------------

def test_unknown_constraint_is_a_blocking_question(config):
    r = read_persona(_edit("P01", acik_kisitlar=("bilinmeyen bir kısıt",)), config)
    assert r.blocked and r.levels is None
    [q] = r.questions
    assert q.question_id == "q:acik_kisitlar[0]"
    assert q.about == "acik_kisitlar[0]"
    assert q.blocking is True
    assert q.choices[-1] == "Dikkate alma"
    assert "Risk tavanını 4 ile sınırla" in q.choices
    assert q.text == "Bu kısıt nasıl uygulanmalı: \"bilinmeyen bir kısıt\"?"


def test_unknown_risk_profile_is_a_blocking_question(config):
    r = read_persona(_edit("P03", risk_profili="Çok agresif"), config)
    assert r.blocked
    [q] = r.questions
    assert q.question_id == "q:risk_profili"
    assert q.choices == ("Muhafazakâr", "Temkinli", "Dengeli", "Agresif")


@pytest.mark.parametrize("field,attr,safe", [
    ("likidite_ihtiyaci", "liquidity", 1.0),
    ("anapara_koruma_tercihi", "principal", 1.0),
    ("gelir_nakit_akisi_ihtiyaci", "income", 0.5),
])
def test_unknown_level_text_uses_the_safe_level(config, field, attr, safe):
    r = read_persona(_edit("P04", **{field: "belki"}), config)
    assert not r.blocked
    assert getattr(r.levels, attr) == safe
    [q] = r.questions
    assert q.question_id == f"q:{field}" and not q.blocking
    assert q.choices == ("Düşük", "Orta", "Yüksek")
    assert any(f"\"{field}\" için \"belki\"" in a for a in r.assumptions)


def test_unknown_level_text_for_liquidity_sets_the_intensity_too(config):
    r = read_persona(_edit("P01", likidite_ihtiyaci="belki"), config)
    assert r.levels.liquidity == 1.0 and r.levels.liquidity_intensity == 1.0


@pytest.mark.parametrize("text,period", [
    ("1-3 yıl", "1y"), ("5+ yıl", "3y"), ("0-1 yıl", "6m"), ("1+ yıl", "6m"),
    ("2-5 yıl", "3y"), ("3+ yıl", "1y"),
])
def test_horizon_patterns(config, text, period):
    assert read_persona(_edit("P01", yatirim_ufku=text), config).levels.period == period


def test_unknown_horizon_uses_6m(config):
    r = read_persona(_edit("P01", yatirim_ufku="emekliliğe kadar"), config)
    assert r.levels.period == "6m"
    [q] = r.questions
    assert q.question_id == "q:yatirim_ufku" and q.choices == ("6m", "1y", "3y")
    assert not q.blocking


# --- answers -------------------------------------------------------------------------

def test_answer_resolves_a_blocking_constraint(config):
    p = _edit("P03", acik_kisitlar=("bilinmeyen bir kısıt",))
    r = read_persona(p, config, {"q:acik_kisitlar[0]": "Risk tavanını 4 ile sınırla"})
    assert not r.blocked
    assert r.levels.ceiling == 4
    assert r.levels.effects == ("risk_cap",)
    [q] = r.questions
    assert q.answer == "Risk tavanını 4 ile sınırla"


def test_answer_ignore_drops_the_constraint(config):
    p = _edit("P03", acik_kisitlar=("bilinmeyen bir kısıt",))
    r = read_persona(p, config, {"q:acik_kisitlar[0]": "Dikkate alma"})
    assert not r.blocked and r.levels.ceiling == 7


def test_answer_sets_a_non_blocking_level_without_an_assumption(config):
    r = read_persona(load_persona("P02"), config, {"q:doviz_maruz_kalma_tercihi": "Açık"})
    assert r.levels.fx_intensity == 0.5      # the fx_limit constraint of P02 still applies
    assert r.questions[0].answer == "Açık"
    assert not any("güvenli düzey" in a for a in r.assumptions)


def test_answer_sets_the_risk_profile(config):
    p = _edit("P03", risk_profili="Çok agresif")
    r = read_persona(p, config, {"q:risk_profili": "Dengeli"})
    assert r.levels.ceiling == 5 and r.levels.appetite == pytest.approx(2 / 3)


def test_answer_sets_the_horizon(config):
    p = _edit("P01", yatirim_ufku="emekliliğe kadar")
    assert read_persona(p, config, {"q:yatirim_ufku": "3y"}).levels.period == "3y"


def test_answer_not_in_choices_is_an_error(config):
    with pytest.raises(ValueError, match="choices"):
        read_persona(load_persona("P02"), config, {"q:doviz_maruz_kalma_tercihi": "Çok"})


def test_answer_to_an_unknown_question_is_an_error(config):
    with pytest.raises(ValueError, match="q:risk_profili"):
        read_persona(load_persona("P02"), config, {"q:risk_profili": "Dengeli"})


def test_constraint_order_is_kept(config):
    p = _edit("P01", acik_kisitlar=("kısa vadeli nakit ihtiyacı varsayılmamalı",
                                     "uzun süre kilitli veya düşük likiditeli seçeneklerden kaçınma"))
    lv = read_persona(p, config).levels
    assert lv.liquidity_intensity == 1.0 and lv.liquidity_weight == 0.0
    assert lv.effects == ("no_liquidity_need", "liquidity_need")
