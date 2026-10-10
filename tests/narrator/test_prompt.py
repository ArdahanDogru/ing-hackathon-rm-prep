import json

import pytest

from rmprep.contracts import NARRATIVE_SECTIONS
from rmprep.narrator.facts import build_facts
from rmprep.narrator.prompt import (
    SCHEMA,
    build_request,
    parse_sections,
    sections_json,
    system_prompt,
)
from rmprep.narrator.template import template_sections
from tests.narrator.conftest import evidence, p02


def _facts():
    return build_facts(p02(), evidence())


def test_schema_requires_every_section_and_sentence_field():
    assert SCHEMA["required"] == list(NARRATIVE_SECTIONS)
    assert SCHEMA["additionalProperties"] is False
    sentence = SCHEMA["properties"]["ozet"]["items"]
    assert sentence["required"] == ["text", "option_ids", "evidence_ids"]
    assert sentence["additionalProperties"] is False


def test_sections_round_trip(config):
    sections = template_sections(_facts(), "TR", config.disclaimer["TR"])
    assert parse_sections(sections_json(sections)) == sections


@pytest.mark.parametrize("text", ["not json", "[]", '{"ozet": "x"}', '{"ozet": [{"text": 1}]}'])
def test_parse_rejects_bad_shapes(text):
    with pytest.raises(ValueError):
        parse_sections(text)


def test_missing_section_parses_as_empty():
    sections = parse_sections(json.dumps({"ozet": [{"text": "a", "option_ids": [],
                                                    "evidence_ids": []}]}))
    assert [s.key for s in sections] == list(NARRATIVE_SECTIONS)
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
    assert json.loads(facts_block) == f.to_dict()
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
