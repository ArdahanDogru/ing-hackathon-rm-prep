"""N9 (docs/narrator.md, docs/web-ui.md section 5): talking points, need tags,
client-only warnings, note names, contract v1.3 sections."""

import dataclasses
import json

import pytest

from rmprep.contracts import (
    NARRATIVE_SECTIONS_V13,
    NarrativeSection,
    NarrativeSentence,
)
from rmprep.narrator.facts import build_facts
from rmprep.narrator.prompt import (
    SCHEMA,
    parse_need_tags,
    parse_sections,
    prompt_facts,
    sections_json,
    system_prompt,
)
from rmprep.narrator.service import Narrator
from rmprep.narrator.template import template_draft, template_need_tags, template_sections, to_markdown
from rmprep.narrator.validator import validate, validate_need_tags
from tests.narrator.conftest import CREATED, engine_result, evidence, p02
from tests.narrator.test_service import FakeLlm, reply


def pack_warnings(pack: dict) -> list[dict]:
    return pack["warnings"]


def pack_value(pack, key: str):
    """The value of the first key `key` anywhere in the pack."""
    if isinstance(pack, dict):
        if key in pack:
            return pack[key]
        for v in pack.values():
            found = pack_value(v, key)
            if found is not None:
                return found
    if isinstance(pack, list):
        for v in pack:
            found = pack_value(v, key)
            if found is not None:
                return found
    return None


def _template(r, lang, config):
    f = build_facts(r, evidence())
    return f, template_draft(f, lang, config, created_at=CREATED)


def _codes(findings):
    return {x.split(":", 1)[0] for x in findings}


def _with(sections, key, *sentences, replace=False):
    out = []
    for s in sections:
        if s.key == key:
            s = NarrativeSection(key, tuple(sentences) if replace else (*s.sentences, *sentences))
        out.append(s)
    return out


# --- facts pack -----------------------------------------------------------------------

def test_facts_pack_has_only_client_warnings(approved_p01):
    pack = prompt_facts(build_facts(approved_p01, evidence()))
    codes = {w.code for w in approved_p01.warnings if w.audience == "rm"}
    assert codes                                          # P01 has RM-only warnings
    assert not any(w["code"] in codes for w in pack_warnings(pack))


def test_client_warnings_stay():
    r = p02()                                             # fx_exposure is for the client
    f = build_facts(r, evidence())
    assert [w.code for w in f.warnings] == ["fx_exposure"]


def test_note_names(approved_p01):
    pack = prompt_facts(build_facts(approved_p01, evidence()))
    assert pack_value(pack, "dosyadaki_not") == approved_p01.persona.rm_notu
    assert pack_value(pack, "rm_onay_notu") == approved_p01.rm_note
    assert pack_value(pack, "rm_notu") is None and pack_value(pack, "rm_note") is None


def test_pack_has_talking_points_and_why(approved_p01):
    f = build_facts(approved_p01, evidence())
    pack = prompt_facts(f)
    tp = approved_p01.talking_points[0]
    assert pack["talking_points"][0]["title"] == tp.label
    assert pack["talking_points"][0]["text"] == tp.text
    first = pack["selected"][0]
    assert [w[0] for w in first["why"]] == list(f.why[first["option_id"]][i][0]
                                                for i in range(len(f.why[first["option_id"]])))


def test_talking_point_options_are_named(approved_p01):
    f = build_facts(approved_p01, evidence())
    for tp in approved_p01.talking_points:
        assert set(tp.option_ids) <= set(f.named_options())


# --- template ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_has_talking_points_and_tags(approved_p01, lang, config):
    _, d = _template(approved_p01, lang, config)
    assert tuple(s.key for s in d.sections) == NARRATIVE_SECTIONS_V13
    tp = next(s for s in d.sections if s.key == "talking_points")
    assert 2 <= len(tp.sentences) <= 3 and all(s.title for s in tp.sentences)
    assert all(s.option_ids or s.evidence_ids for s in tp.sentences)
    assert set(d.need_tags) == set(approved_p01.rm_selected)


def test_template_talking_points_start_with_the_engine_points(approved_p01, config):
    _, d = _template(approved_p01, "TR", config)
    tp = next(s for s in d.sections if s.key == "talking_points")
    first = approved_p01.talking_points[0]
    assert (tp.sentences[0].title, tp.sentences[0].text) == (first.label, first.text)


def test_template_tags_come_from_the_why_lines(approved_p01, config):
    f = build_facts(approved_p01, evidence())
    tags = template_need_tags(f)
    for oid in approved_p01.rm_selected:
        assert tags[oid] == tuple(p for p, _ in f.why[oid])[:3]
        assert set(tags[oid]) <= set(approved_p01.persona.oncelikler)
    assert any(tags.values())


@pytest.mark.parametrize("pid", ["p01", "p02", "p04"])
@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_passes_the_validator_for_engine_results(pid, lang, config):
    r = engine_result(pid)
    f = build_facts(r, evidence())
    sections = template_sections(f, lang, config.disclaimer[lang])
    assert validate(sections, f, r, config, lang, need_tags=template_need_tags(f)) == ()


def test_markdown_shows_the_titles(approved_p01, config):
    _, d = _template(approved_p01, "TR", config)
    md = to_markdown(d)
    tp = next(s for s in d.sections if s.key == "talking_points")
    for s in tp.sentences:
        assert f"**{s.title}:** {s.text}" in md


# --- need tags ----------------------------------------------------------------------------

def test_need_tags_turkish_case(approved_p01):
    ok = validate_need_tags({"fund:X": ("Sınırlı Dalgalanma",)}, approved_p01.persona)
    bad = validate_need_tags({"fund:X": ("yüksek getiri",)}, approved_p01.persona)
    assert ok == [] and bad


def test_need_tags_dotted_capital_i():
    from tests.narrator.conftest import persona

    p = dataclasses.replace(persona("p01"), oncelikler=("likiditeyi koruma",))
    assert validate_need_tags({"fund:X": ("LİKİDİTEYİ KORUMA",)}, p) == []


@pytest.mark.parametrize("change, rule", [
    (lambda t, sel: {**t, sel[0]: ("yüksek getiri",)}, "tag"),
    (lambda t, sel: {**t, "fund:ZZZ": ("düzenli gelir",)}, "tag"),
    (lambda t, sel: {k: v for k, v in t.items() if k != sel[0]}, "tag"),
    (lambda t, sel: {**t, sel[0]: ("düzenli gelir", "likiditeyi koruma", "sınırlı dalgalanma",
                                   "düzenli gelir")}, "tag"),
])
def test_need_tag_rules(change, rule, approved_p01, config):
    r = approved_p01
    f = build_facts(r, evidence())
    sections = template_sections(f, "TR", config.disclaimer["TR"])
    tags = change(template_need_tags(f), r.rm_selected)
    assert _codes(validate(sections, f, r, config, "TR", need_tags=tags)) == {rule}


# --- talking_points section rules -------------------------------------------------------

@pytest.mark.parametrize("make", [
    lambda s: s[:1],                                                     # one sentence
    lambda s: (*s, *s)[:4],                                              # four sentences
    lambda s: (dataclasses.replace(s[0], title=""), *s[1:]),             # no title
])
def test_talking_points_rules(make, approved_p01, config):
    r = approved_p01
    f = build_facts(r, evidence())
    sections = list(template_sections(f, "TR", config.disclaimer["TR"]))
    tp = next(s for s in sections if s.key == "talking_points")
    bad = _with(sections, "talking_points", *make(tp.sentences), replace=True)
    assert "talking" in _codes(validate(bad, f, r, config, "TR"))


def test_talking_point_needs_a_citation(approved_p01, config):
    r = approved_p01
    f = build_facts(r, evidence())
    sections = list(template_sections(f, "TR", config.disclaimer["TR"]))
    tp = next(s for s in sections if s.key == "talking_points")
    bad = _with(sections, "talking_points", tp.sentences[0],
                NarrativeSentence("Hedefini konuşun.", title="Müşterinin hedefi"), replace=True)
    assert _codes(validate(bad, f, r, config, "TR")) == {"citation"}


# --- prompt and parser ------------------------------------------------------------------------

def test_schema_has_titles_and_need_tags():
    assert SCHEMA["required"] == [*NARRATIVE_SECTIONS_V13, "need_tags"]
    sentence = SCHEMA["properties"]["talking_points"]["items"]
    assert "title" in sentence["required"]
    tag = SCHEMA["properties"]["need_tags"]["items"]
    assert tag["required"] == ["option_id", "tags"]


@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_system_prompt_n9(lang, config):
    s = system_prompt(lang, config)
    for word in ("talking_points", "need_tags", "dosyadaki_not", "rm_onay_notu", "oncelikler"):
        assert word in s
    assert "anlatın" in s                          # the card speaks to the RM


@pytest.fixture
def fake_llm_text_n4(approved_p01, config):
    f = build_facts(approved_p01, evidence())
    return sections_json(template_sections(f, "TR", config.disclaimer["TR"]),
                         template_need_tags(f))


def test_llm_output_with_titles_parses(fake_llm_text_n4, approved_p01):
    sections = parse_sections(fake_llm_text_n4)
    tp = next(s for s in sections if s.key == "talking_points")
    assert tp.sentences[0].title
    assert set(parse_need_tags(fake_llm_text_n4)) == set(approved_p01.rm_selected)


@pytest.mark.parametrize("text", ['{"need_tags": "x"}', '{"need_tags": [{"option_id": 1}]}'])
def test_need_tags_parser_rejects_bad_shapes(text):
    with pytest.raises(ValueError):
        parse_need_tags(text)


# --- service --------------------------------------------------------------------------------

def _narrator(tmp_path, config, *replies):
    llm = FakeLlm(*replies)
    return Narrator(config, llm, tmp_path, clock=lambda: CREATED), llm


def test_rm_only_text_never_in_draft(approved_p01, fake_llm_text_n4, tmp_path, config):
    n, _ = _narrator(tmp_path, config, reply(fake_llm_text_n4))
    d = n.draft(approved_p01, evidence(), "TR")
    assert d.source == "llm", d.checks
    rm_msgs = [w.message for w in approved_p01.warnings if w.audience == "rm"]
    assert rm_msgs and not any(m in to_markdown(d) for m in rm_msgs)


def test_llm_need_tags_are_kept_in_the_persona_wording(approved_p01, fake_llm_text_n4,
                                                       tmp_path, config):
    data = json.loads(fake_llm_text_n4)
    oid = approved_p01.rm_selected[0]
    data["need_tags"] = [{"option_id": x, "tags": ["Sınırlı Dalgalanma"] if x == oid else []}
                         for x in approved_p01.rm_selected]
    n, _ = _narrator(tmp_path, config, reply(json.dumps(data, ensure_ascii=False)))
    d = n.draft(approved_p01, evidence(), "TR")
    assert d.source == "llm", d.checks
    assert d.need_tags[oid] == ("sınırlı dalgalanma",)


def test_unknown_tag_retries_then_template(approved_p01, fake_llm_text_n4, tmp_path, config):
    data = json.loads(fake_llm_text_n4)
    data["need_tags"][0]["tags"] = ["yüksek getiri"]
    bad = reply(json.dumps(data, ensure_ascii=False))
    n, llm = _narrator(tmp_path, config, bad, bad)
    d = n.draft(approved_p01, evidence(), "TR")
    assert len(llm.requests) == 2 and d.source == "template"
    assert any(c.startswith("tag:") for c in d.checks)
    assert set(d.need_tags) == set(approved_p01.rm_selected)
