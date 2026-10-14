"""N14 (docs/narrator.md): deletable blocks (contract v1.9: rm_edits[block] == ""
= deleted) and the disclaimer that always stays."""

import dataclasses

import pytest

import rmprep.edits as edits
from rmprep.contracts import NarrativeDraft
from rmprep.narrator.blocks import block_ids
from rmprep.narrator.facts import build_facts
from rmprep.narrator.template import apply_edits, template_draft, to_markdown
from tests.narrator.conftest import CREATED, evidence


@pytest.fixture(scope="module")
def draft_p01(approved_p01, config):
    return template_draft(build_facts(approved_p01, evidence()), "TR", config, created_at=CREATED)


@pytest.fixture(scope="module")
def draft_p01_en(approved_p01, config):
    return template_draft(build_facts(approved_p01, evidence()), "EN", config, created_at=CREATED)


def _deleted(d: NarrativeDraft, *prefixes: str) -> NarrativeDraft:
    """d with every block that starts with one of prefixes deleted."""
    gone = {b: "" for b in block_ids(d) if b.startswith(prefixes)}
    return dataclasses.replace(d, rm_edits={**d.rm_edits, **gone})


def _section(d, key):
    return next((s for s in d.sections if s.key == key), None)


def _last_line(md: str) -> str:
    return md.rstrip("\n").splitlines()[-1]


# --- apply_edits ------------------------------------------------------------------------

def test_apply_edits_drops_a_deleted_block(draft_p01):
    d = apply_edits(_deleted(draft_p01, "dikkat"))
    assert d.rm_edits == {}
    sec = _section(d, "dikkat")
    assert sec is None or sec.sentences == ()
    assert _section(d, "ozet").sentences == _section(draft_p01, "ozet").sentences


def test_apply_edits_drops_one_option_only(draft_p01, approved_p01):
    first, second = approved_p01.rm_selected[:2]
    d = apply_edits(_deleted(draft_p01, f"oneriler:{first}"))
    ids = {s.option_ids[0] for s in _section(d, "oneriler").sentences if s.option_ids}
    assert first not in ids and second in ids


def test_apply_edits_with_deletions_matches_the_lead_glue(draft_p01, approved_p01):
    d = _deleted(draft_p01, "ozet", "talking_points:0", f"oneriler:{approved_p01.rm_selected[0]}")
    assert to_markdown(apply_edits(d)) == to_markdown(edits.apply_edits(d))


# --- to_markdown: no empty headings -------------------------------------------------------

def test_markdown_deleting_one_block(draft_p01):
    md = to_markdown(_deleted(draft_p01, "dikkat"))
    assert "## Dikkat" not in md
    assert "## Özet" in md and "## Öneriler" in md


@pytest.mark.parametrize("key, heading", [("oneriler", "## Öneriler"),
                                          ("talking_points", "## Müşteriyle konuşulacaklar")])
def test_markdown_deleting_all_blocks_of_a_section(draft_p01, key, heading):
    d = _deleted(draft_p01, f"{key}:")
    md = to_markdown(d)
    assert heading not in md
    if key == "oneriler":
        assert "\n### " not in md.split("## Ek bilgiler")[0]
    assert md == to_markdown(edits.apply_edits(d))       # the API's path (app.py)


def test_markdown_ek_bilgiler_only_with_a_section_left(draft_p01):
    md = to_markdown(_deleted(draft_p01, "alternatifler", "sorular"))
    assert "## Ek bilgiler" in md and "### Varsayımlar" in md and "### Sorular" not in md
    md = to_markdown(_deleted(draft_p01, "alternatifler", "sorular", "varsayimlar"))
    assert "## Ek bilgiler" not in md


def test_markdown_everything_deleted_keeps_title_and_disclaimer(draft_p01, config):
    d = _deleted(draft_p01, *block_ids(draft_p01))
    md = to_markdown(d)
    assert "## " not in md
    assert _last_line(md) == config.disclaimer["TR"]
    assert md.splitlines()[0].startswith("# Görüşme metni")


def test_markdown_no_double_blank_lines_after_deletions(draft_p01, approved_p01):
    d = _deleted(draft_p01, "ozet", "dikkat", "talking_points:",
                 f"oneriler:{approved_p01.rm_selected[0]}")
    assert "\n\n\n" not in to_markdown(d)


# --- the disclaimer always stays ----------------------------------------------------------

def test_disclaimer_once_when_ozet_is_kept(draft_p01, config):
    md = to_markdown(draft_p01)
    assert md.count(config.disclaimer["TR"]) == 1


def test_deleted_ozet_puts_the_disclaimer_last(draft_p01, config):
    md = to_markdown(_deleted(draft_p01, "ozet"))
    assert "## Özet" not in md
    assert md.count(config.disclaimer["TR"]) == 1
    assert _last_line(md) == config.disclaimer["TR"]


def test_edited_ozet_without_the_disclaimer(draft_p01, config):
    d = dataclasses.replace(draft_p01, rm_edits={"ozet": "Kısa bir özet."})
    md = to_markdown(d)
    assert "Kısa bir özet." in md
    assert _last_line(md) == config.disclaimer["TR"]


def test_edited_ozet_that_keeps_the_disclaimer(draft_p01, config):
    d = dataclasses.replace(draft_p01,
                            rm_edits={"ozet": "Kısa bir özet. " + config.disclaimer["TR"]})
    assert to_markdown(d).count(config.disclaimer["TR"]) == 1


def test_english_disclaimer(draft_p01_en, config):
    md = to_markdown(_deleted(draft_p01_en, "ozet"))
    assert _last_line(md) == config.disclaimer["EN"]


def test_disclaimer_argument(draft_p01):
    md = to_markdown(_deleted(draft_p01, "ozet"), disclaimer="Tavsiye değildir.")
    assert _last_line(md) == "Tavsiye değildir."


# --- restore, and the edits file keeps "" --------------------------------------------------

def test_restore_after_delete(draft_p01):
    d = edits.with_edit(draft_p01, "dikkat", "", ())
    assert d.rm_edits == {"dikkat": ""} and d.edit_checks == {}
    assert "dikkat" in block_ids(d)                       # still there, so it can come back
    d = edits.with_edit(d, "dikkat", None, ())
    assert d.rm_edits == {}
    assert to_markdown(d) == to_markdown(draft_p01)


def test_deleted_block_survives_the_json_round_trip(draft_p01):
    d = edits.with_edit(draft_p01, "ozet", "", ())
    back = NarrativeDraft.from_dict(d.to_dict())
    assert back.rm_edits == {"ozet": ""}
    assert to_markdown(back) == to_markdown(d)
