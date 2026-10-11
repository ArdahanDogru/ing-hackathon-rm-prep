import json

import pytest

from rmprep.contracts import NARRATIVE_SECTIONS, NARRATIVE_SECTIONS_V13
from rmprep.narrator.facts import build_facts
from rmprep.narrator.prompt import (
    SCHEMA,
    build_request,
    parse_sections,
    prompt_facts,
    sections_json,
    system_prompt,
)
from rmprep.narrator.template import template_sections
from tests.narrator.conftest import evidence, p02


def _facts():
    return build_facts(p02(), evidence())


def test_schema_is_one_flat_sentence_list():
    """N9b: one sentence schema for all sections (the per-section schema was a
    grammar too large for structured outputs: HTTP 400)."""
    assert SCHEMA["required"] == ["sentences", "need_tags"]
    assert SCHEMA["additionalProperties"] is False
    sentence = SCHEMA["properties"]["sentences"]["items"]
    assert sentence["required"] == ["section", "text", "title", "cite"]
    assert sentence["properties"]["section"]["enum"] == list(NARRATIVE_SECTIONS_V13)
    assert sentence["additionalProperties"] is False


def test_schema_stays_small():
    """Guard against the 400 "compiled grammar is too large": the N9 schema had
    3,250 characters and 10 object schemas."""
    text = json.dumps(SCHEMA)
    assert len(text) < 1_000, len(text)
    assert text.count('"type": "object"') <= 3


def test_sections_round_trip(config):
    sections = template_sections(_facts(), "TR", config.disclaimer["TR"])
    assert parse_sections(sections_json(sections)) == sections


@pytest.mark.parametrize("text", [
    "not json", "[]", '{"sentences": "x"}', '{"sentences": [{"text": 1, "section": "ozet"}]}',
    '{"sentences": [{"text": "a", "section": "nope"}]}',
    '{"sentences": [{"text": "a", "section": "ozet", "cite": "E12345678"}]}',
])
def test_parse_rejects_bad_shapes(text):
    with pytest.raises(ValueError):
        parse_sections(text)


def test_cite_splits_into_option_and_evidence_ids():
    (s,) = parse_sections(json.dumps({"sentences": [
        {"section": "dikkat", "text": "a", "title": "",
         "cite": ["fund:BBF", "E42b47116", "deposit:ing_turuncu"]}]}))[3].sentences
    assert s.option_ids == ("fund:BBF", "deposit:ing_turuncu")
    assert s.evidence_ids == ("E42b47116",)


def test_sentences_keep_their_order_within_a_section():
    sections = parse_sections(json.dumps({"sentences": [
        {"section": "sorular", "text": "b", "title": "", "cite": []},
        {"section": "ozet", "text": "a", "title": "", "cite": []},
        {"section": "sorular", "text": "c", "title": "", "cite": []}]}))
    by_key = {s.key: [x.text for x in s.sentences] for s in sections}
    assert by_key["sorular"] == ["b", "c"] and by_key["ozet"] == ["a"]


def test_missing_section_parses_as_empty():
    sections = parse_sections(json.dumps({"sentences": [
        {"section": "ozet", "text": "a", "title": "", "cite": []}]}))
    assert [s.key for s in sections] == list(NARRATIVE_SECTIONS_V13)
    assert sections[1].sentences == ()


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_system_prompt_states_the_rules(lang, config):
    s = system_prompt(lang, config)
    assert config.disclaimer[lang] in s
    for phrase in config.forbidden_phrases[lang]:
        assert phrase in s
    for key in NARRATIVE_SECTIONS:
        assert key in s
    assert ("Turkish" if lang == "TR" else "English") in s


def test_request_carries_the_facts_and_the_task(config):
    f = _facts()
    req = build_request(f, "TR", config)
    facts_block, task = req.user_blocks
    assert json.loads(facts_block) == prompt_facts(f)
    assert "TR" in task
    assert req.schema == SCHEMA
    assert req.system == system_prompt("TR", config)


def test_facts_block_is_stable(config):
    """Same facts -> same bytes (prompt cache and replay)."""
    assert build_request(_facts(), "TR", config) == build_request(_facts(), "TR", config)


def test_retry_request_keeps_the_prefix_and_adds_the_findings(config):
    f = _facts()
    first = build_request(f, "TR", config)
    retry = build_request(f, "TR", config, previous='{"ozet": []}',
                          findings=("phrase: teklif_metni: forbidden phrase \"garanti\"",))
    assert retry.user_blocks[:2] == first.user_blocks
    assert '{"ozet": []}' in retry.user_blocks[2]
    assert "garanti" in retry.user_blocks[2]
