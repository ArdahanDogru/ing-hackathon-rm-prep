"""N13 (docs/narrator.md): risk lines, market facts at the top, real return
first, oneriler sentences that start with their fund, less repetition, screen
order of the Markdown. Fake LLM only."""

import json

import pytest

from rmprep.contracts import NarrativeSection, NarrativeSentence
from rmprep.narrator.facts import build_facts
from rmprep.narrator.prompt import prompt_facts, system_prompt
from rmprep.narrator.template import template_draft, template_sections, to_markdown
from rmprep.narrator.validator import validate
from tests.narrator.conftest import CREATED, engine_result_on, evidence_n13


@pytest.fixture(scope="module")
def ev():
    return evidence_n13()


@pytest.fixture(scope="module")
def r02(ev):
    return engine_result_on(ev, "p02", note="Şirket nakdini ayrıca konuşalım.")


@pytest.fixture(scope="module")
def f02(r02, ev):
    return build_facts(r02, ev)


def _section(sections, key):
    return next(s for s in sections if s.key == key)


# --- facts pack -------------------------------------------------------------------------

def test_risk_line_per_selected_option(f02, r02, config):
    pack = prompt_facts(f02, "TR")
    for o, opt in zip(pack["selected"], (x for x in r02.options
                                         if x.option.option_id in r02.rm_selected)):
        risk = o["risk"]
        assert risk["access"] == "Aynı gün"
        assert risk["note"] == config.risk_notes["by_class"][opt.option.asset_class]["TR"]
        assert risk["cite"]


def test_market_facts_at_the_top_not_per_option(f02):
    pack = prompt_facts(f02, "TR")
    assert {"piyasa_mevduat_faizi", "tufe_yillik"} <= set(pack["market"])
    for o in [*pack["selected"], *pack["alternatives"]]:
        assert not {"piyasa_mevduat_faizi", "tufe_yillik", "fund_buyable"} & set(o["numbers"])


def test_real_return_is_the_first_number(f02):
    for o in prompt_facts(f02, "TR")["selected"]:
        assert list(o["numbers"])[0] == "real_return_1y"


def test_pack_names_and_unmatched_priorities(f02, r02):
    pack = prompt_facts(f02, "TR")
    assert pack["unmatched_priorities"] == ["kur riskini yönetme"]   # a note, no criterion
    assert all(o["name"] and "PORTFÖY" not in o["name"] for o in pack["selected"])


def test_english_pack_has_the_english_risk_note(f02, r02, config):
    o = prompt_facts(f02, "EN")["selected"][0]
    cls = next(x.option.asset_class for x in r02.options if x.option.option_id == o["option_id"])
    assert o["risk"]["note"] == config.risk_notes["by_class"][cls]["EN"]


# --- prompt --------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_system_prompt_n13(lang, config):
    s = system_prompt(lang, config)
    for word in ("3 sentences", "start with", "unmatched_priorities", "real_return_1y",
                 "market", "risk", "only in dikkat and teklif_metni"):
        assert word in s, word


# --- validator: oneriler sentences start with their fund ------------------------------------

def test_oneriler_sentence_must_start_with_its_fund(f02, r02, ev, config):
    sections = list(template_sections(f02, "TR", config.disclaimer["TR"]))
    oid = r02.rm_selected[0]
    bad = [NarrativeSection("oneriler", (*_section(sections, "oneriler").sentences,
                                         NarrativeSentence("Bu fon müşteriye uyar.", (oid,))))
           if s.key == "oneriler" else s for s in sections]
    findings = validate(bad, f02, r02, config, "TR")
    assert {x.split(":", 1)[0] for x in findings} == {"shape"}


@pytest.mark.parametrize("start", ["label", "short", "issuer_core", "code"])
def test_any_name_of_the_fund_may_start_the_sentence(start, f02, r02, config):
    from rmprep.api.names import short_name

    oid = r02.rm_selected[0]
    opt = next(o.option for o in r02.options if o.option.option_id == oid)
    issuer, short = short_name(opt.label)
    name = {"label": opt.label, "short": f"{issuer} {short}",
            "issuer_core": f"{issuer.replace(' Portföy', '')} {short.split(' (')[0]}",
            "code": opt.entity}[start]
    sections = list(template_sections(f02, "TR", config.disclaimer["TR"]))
    ok = [NarrativeSection("oneriler", (*_section(sections, "oneriler").sentences,
                                        NarrativeSentence(f"{name} müşteriye uyar.", (oid,))))
          if s.key == "oneriler" else s for s in sections]
    assert validate(ok, f02, r02, config, "TR") == ()


# --- template ------------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_oneriler_three_sentences_per_option(f02, r02, config, lang):
    sections = template_sections(f02, lang, config.disclaimer[lang])
    for oid in r02.rm_selected:
        mine = [s for s in _section(sections, "oneriler").sentences if s.option_ids[:1] == (oid,)]
        assert len(mine) == 3, [s.text for s in mine]
    assert validate(sections, f02, r02, config, lang) == ()


def test_template_first_sentence_leads_with_the_real_return(f02, r02, config):
    sections = template_sections(f02, "TR", config.disclaimer["TR"])
    first = next(s for s in _section(sections, "oneriler").sentences
                 if s.option_ids[:1] == (r02.rm_selected[0],))
    assert first.text.index("reel") < first.text.index("1 yıllık getiri")


def test_template_dikkat_watch_items_only_for_new_facts(f02, r02, config):
    """N13b replaces "one watch item per option": only slow access or fees."""
    dikkat = _section(template_sections(f02, "TR", config.disclaimer["TR"]), "dikkat")
    for oid in r02.rm_selected:
        risk = f02.risks[oid]
        expected = bool(risk.fees or (risk.access_days or 0) > 0)
        assert any(s.option_ids == (oid,) for s in dikkat.sentences) is expected


def test_template_repetition(f02, r02, config):
    sections = template_sections(f02, "TR", config.disclaimer["TR"])
    for key in ("ozet", "oneriler", "alternatifler"):
        assert "geçmiş" not in " ".join(s.text for s in _section(sections, key).sentences), key
    assert len(_section(sections, "ozet").sentences) <= 4       # 3 + the disclaimer
    tp = " ".join(s.text for s in _section(sections, "talking_points").sentences)
    assert r02.persona.durum not in tp


def test_template_asks_about_unmatched_priorities(f02, config):
    sorular = " ".join(s.text for s in _section(
        template_sections(f02, "TR", config.disclaimer["TR"]), "sorular").sentences)
    assert "kur riskini yönetme" in sorular


# --- Markdown: screen order -------------------------------------------------------------------------

def _headings(md):
    return [line for line in md.splitlines() if line.startswith("#")]


def test_markdown_screen_order(f02, r02, config):
    d = template_draft(f02, "TR", config, created_at=CREATED)
    heads = _headings(to_markdown(d))[1:]
    assert heads[:3] == ["## Özet", "## Müşteriyle konuşulacaklar", "## Teklif metni"]
    assert heads[3] == "## Öneriler"
    per_option = heads[4:4 + len(r02.rm_selected)]
    assert all(h.startswith("### ") for h in per_option)
    assert heads[4 + len(r02.rm_selected):] == ["## Dikkat", "## Ek bilgiler", "### Alternatifler",
                                                "### Sorular", "### Varsayımlar"]


def test_markdown_option_headings(f02, r02, config):
    d = template_draft(f02, "TR", config, created_at=CREATED)
    oid = r02.rm_selected[0]
    assert f"### {oid.split(':', 1)[1]}" in to_markdown(d)                     # the fund code
    assert "### Nurol Para" in to_markdown(d, names={oid: "Nurol Para"})


@pytest.mark.parametrize("pid", ["p01", "p02", "p04"])
@pytest.mark.parametrize("lang", ["TR", "EN"])
def test_template_passes_on_real_returns_and_access(pid, lang, ev, config):
    from rmprep.narrator.template import template_need_tags

    r = engine_result_on(ev, pid)
    f = build_facts(r, ev)
    sections = template_sections(f, lang, config.disclaimer[lang])
    assert validate(sections, f, r, config, lang, need_tags=template_need_tags(f)) == ()


def test_markdown_has_no_double_blank_lines(f02, config):
    md = to_markdown(template_draft(f02, "TR", config, created_at=CREATED))
    assert "\n\n\n" not in md
