"""N11: blocks of the meeting text, the check of one edited block, Markdown with
the edits (contract v1.5; docs/web-ui.md "Section-by-section editing")."""

import dataclasses

import pytest

from rmprep.contracts import BLOCKING_CHECK_KINDS
from rmprep.narrator.blocks import block_ids, block_text, check_block
from rmprep.narrator.facts import build_facts
from rmprep.narrator.template import apply_edits, template_draft, to_markdown
from tests.narrator.conftest import CREATED, evidence, p02


@pytest.fixture(scope="module")
def draft_p01(approved_p01, config):
    return template_draft(build_facts(approved_p01, evidence()), "TR", config, created_at=CREATED)


@pytest.fixture
def rejected_short_name(approved_p01):
    assert "fund:AAV" in {x.option.option_id for x in approved_p01.rejected}
    return "Ata İkinci Hisse Senedi"           # ATA PORTFÖY İKİNCİ HİSSE SENEDİ (TL) FONU (...)


def _kinds(findings):
    return {x.split(":", 1)[0] for x in findings}


# --- the plan's tests ---------------------------------------------------------------------

def test_block_ids_cover_every_sentence(draft_p01):
    ids = block_ids(draft_p01)
    assert "ozet" in ids and any(i.startswith("oneriler:") for i in ids)
    assert any(i.startswith("talking_points:") for i in ids)


def test_check_block_kinds(draft_p01, approved_p01):
    f = check_block(draft_p01, approved_p01, evidence(), "ozet", "Kesin getiri; ayrıca %77,7 faiz.")
    assert {"phrase", "number"} <= _kinds(f), f


def test_check_block_turkish_case(draft_p01, approved_p01):
    f = check_block(draft_p01, approved_p01, evidence(), "ozet", "GARANTİ ediyoruz.")
    assert any(x.startswith("phrase:") for x in f)


def test_check_block_rejected_fund_by_short_name(draft_p01, approved_p01, rejected_short_name):
    f = check_block(draft_p01, approved_p01, evidence(), "dikkat",
                    f"{rejected_short_name} de düşünülebilir.")
    assert any(x.startswith("option:") for x in f), f


def test_clean_edit_has_no_findings(draft_p01, approved_p01):
    assert check_block(draft_p01, approved_p01, evidence(), "ozet",
                       "Görüşmede düşük riskli seçenekleri konuşun.") == ()


def test_markdown_uses_the_edit(draft_p01):
    d = dataclasses.replace(draft_p01, rm_edits={"ozet": "YENİ ÖZET."})
    md = to_markdown(d)
    assert "YENİ ÖZET." in md and block_text(draft_p01, "ozet") not in md


# --- block ids and texts -----------------------------------------------------------------------

def test_block_ids_scheme(draft_p01, approved_p01):
    ids = block_ids(draft_p01)
    whole = [i for i in ids if ":" not in i]
    assert set(whole) <= {"ozet", "teklif_metni", "dikkat", "alternatifler", "sorular",
                          "varsayimlar"}
    tp = next(s for s in draft_p01.sections if s.key == "talking_points")
    assert [i for i in ids if i.startswith("talking_points:")] == [
        f"talking_points:{i}" for i in range(len(tp.sentences))]
    assert [i for i in ids if i.startswith("oneriler:")] == [
        f"oneriler:{o}" for o in approved_p01.rm_selected]


def test_block_ids_match_the_lead_glue(draft_p01):
    """rmprep.edits uses these ids; the stand-in scheme must not change."""
    import rmprep.edits as edits

    assert edits.block_ids(draft_p01) == block_ids(draft_p01)


def test_block_text_joins_the_sentences_of_the_block(draft_p01, approved_p01):
    oid = approved_p01.rm_selected[0]
    oneriler = next(s for s in draft_p01.sections if s.key == "oneriler")
    mine = [s.text for s in oneriler.sentences if s.option_ids and s.option_ids[0] == oid]
    assert block_text(draft_p01, f"oneriler:{oid}") == " ".join(mine)


def test_unknown_block(draft_p01, approved_p01):
    with pytest.raises(ValueError, match="unknown block"):
        block_text(draft_p01, "nope")
    with pytest.raises(ValueError, match="unknown block"):
        check_block(draft_p01, approved_p01, evidence(), "oneriler:fund:ZZZ", "x")


# --- check_block: kinds and messages ----------------------------------------------------------

@pytest.mark.parametrize("text, kind", [
    ("Veriler needs_check işaretli.", "internal"),
    ('"Olası sorunlar" bölümüne bakın.', "internal"),
    ("ING Turuncu Hesap (standart) faizi %43,82.", "label"),
    ("Müşteri 99 yaşında.", "number"),
    ("Risksiz bir seçenek.", "phrase"),
])
def test_check_block_each_kind(draft_p01, approved_p01, text, kind):
    f = check_block(draft_p01, approved_p01, evidence(), "dikkat", text)
    assert kind in _kinds(f), f


def test_findings_are_kind_colon_message_in_the_draft_language(draft_p01, approved_p01, config):
    f = check_block(draft_p01, approved_p01, evidence(), "ozet", "Kesin getiri; %77,7 faiz.")
    assert all(x.split(":", 1)[0] in (*BLOCKING_CHECK_KINDS, "number") for x in f)
    assert "number: 77,7 olgularda yok" in f
    assert any(x.startswith("phrase: 'kesin getiri'") and "kullanılmamalı" in x for x in f)
    en = template_draft(build_facts(approved_p01, evidence()), "EN", config, created_at=CREATED)
    f_en = check_block(en, approved_p01, evidence(), "ozet", "A sure profit of 77.7%.")
    assert "number: 77.7 is not in the facts" in f_en
    assert any(x.startswith("phrase: 'sure profit'") for x in f_en)


def test_option_finding_names_the_fund(draft_p01, approved_p01, rejected_short_name):
    (f,) = [x for x in check_block(draft_p01, approved_p01, evidence(), "dikkat",
                                   f"{rejected_short_name} de düşünülebilir.")
            if x.startswith("option:")]
    assert "ATA PORTFÖY İKİNCİ HİSSE SENEDİ" in f


def test_varsayimlar_may_keep_engine_names(draft_p01, approved_p01):
    original = block_text(draft_p01, "varsayimlar")
    assert check_block(draft_p01, approved_p01, evidence(), "varsayimlar", original) == ()


def test_every_original_block_is_clean(draft_p01, approved_p01):
    for b in block_ids(draft_p01):
        assert check_block(draft_p01, approved_p01, evidence(), b, block_text(draft_p01, b)) == (), b


def test_the_selected_fund_may_be_named_in_its_block(draft_p01, approved_p01):
    oid = approved_p01.rm_selected[0]
    label = next(o.option.label for o in approved_p01.options if o.option.option_id == oid)
    assert check_block(draft_p01, approved_p01, evidence(), f"oneriler:{oid}",
                       f"{label} müşterinin düzenli gelir önceliğine uyar.") == ()


# --- Markdown with the edits ---------------------------------------------------------------------

def test_markdown_with_edits_equals_the_applied_draft(draft_p01, approved_p01):
    oid = approved_p01.rm_selected[0]
    edits = {"ozet": "Yeni özet.", "talking_points:0": "Yeni nokta.",
             f"oneriler:{oid}": "Yeni öneri metni.", "varsayimlar": "Varsayım."}
    d = dataclasses.replace(draft_p01, rm_edits=edits)
    assert to_markdown(d) == to_markdown(apply_edits(d))
    md = to_markdown(d)
    for text in edits.values():
        assert md.count(text) == 1
    title = next(s for s in d.sections if s.key == "talking_points").sentences[0].title
    assert f"**{title}:** Yeni nokta." in md
    assert block_text(draft_p01, f"oneriler:{oid}") not in md


def test_apply_edits_matches_the_lead_glue(draft_p01, approved_p01):
    import rmprep.edits as edits

    d = dataclasses.replace(draft_p01, rm_edits={"ozet": "Yeni.", "talking_points:1": "Nokta."})
    assert apply_edits(d) == edits.apply_edits(d)


def test_markdown_without_edits_is_unchanged(config):
    f = build_facts(p02(), evidence())
    d = template_draft(f, "TR", config, created_at=CREATED)
    assert to_markdown(d) == to_markdown(apply_edits(d))


def test_check_block_without_evidence(draft_p01, approved_p01):
    """FakeBackend (fixtures, no evidence set) calls check_block(..., None, ...):
    the rules that need no evidence still run; nothing raises."""
    f = check_block(draft_p01, approved_p01, None, "ozet", "Risksiz bir seçenek.")
    assert "phrase" in _kinds(f)
    assert check_block(draft_p01, approved_p01, None, "ozet", "Seçenekleri konuşun.") == ()
