"""N10: the dashboard brief (contract v1.4; docs/web-ui.md "LLM brief"). Fake LLM, no network."""

import dataclasses
import json

import pytest

from rmprep.brief import plain_brief
from rmprep.contracts import BRIEF_MAX_CHARS, DecisionState, NarrativeBrief
from rmprep.grouping import top_heads
from rmprep.narrator.brief import (
    BRIEF_SCHEMA,
    brief_pack,
    brief_request,
    build_brief_facts,
    validate_brief,
)
from rmprep.narrator.llm import LlmError, LlmReply
from rmprep.narrator.service import Narrator
from tests.narrator.conftest import CREATED, evidence
from tests.narrator.test_service import FakeLlm


def brief_reply(text, cite=(), **over) -> LlmReply:
    fields = dict(text=json.dumps({"text": text, "cite": list(cite)}, ensure_ascii=False),
                  model="claude-haiku-5-5", input_tokens=2000, output_tokens=300,
                  stop_reason="end_turn")
    fields.update(over)
    return LlmReply(**fields)


def _good_text(r) -> tuple[str, tuple[str, ...]]:
    """A brief that passes: the client's situation and the first top option."""
    head = top_heads(r.options, 3)[0].option
    return (f"Varlığı TL mevduat ağırlıklı emekli girişimci; görüşmede {head.label} ile "
            f"düzenli gelir seçeneklerini konuşun.", (head.option_id,))


@pytest.fixture
def make(tmp_path, config):
    def _make(*replies, client=True, cfg=None):
        llm = FakeLlm(*replies)
        return Narrator(cfg or config, llm if client else None, tmp_path,
                        clock=lambda: CREATED), llm
    return _make


def allowed_cites(r, ev) -> set[str]:
    f = build_brief_facts(r, ev).facts
    return set(f.named_options()) | set(f.evidence_ids())


# --- the plan's tests ---------------------------------------------------------------------

def test_brief_llm_path(ready_p01, make):
    text, cite = _good_text(ready_p01)
    n, llm = make(brief_reply(text, cite))
    b = n.brief(ready_p01, evidence(), "TR")
    assert b.source == "llm" and b.model == "claude-haiku-5-5" and b.checks == (), b.checks
    assert 0 < len(b.text) <= 280 and set(b.cite) <= allowed_cites(ready_p01, evidence())
    assert b.prompt_version == "b1" and b.cost_usd > 0
    assert len(llm.requests) == 1


def test_brief_no_retry_on_failure(ready_p01, make):
    n, llm = make(brief_reply("Müşteri 99 yaşında; %77 getiri bekliyor."))
    b = n.brief(ready_p01, evidence(), "TR")
    assert b.source == "template" and b.checks and len(llm.requests) == 1
    assert b.text == plain_brief(ready_p01, "TR")


def test_brief_without_key_is_the_plain_sentence(ready_p01, make):
    n, _ = make(client=False)
    b = n.brief(ready_p01, evidence(), "TR")
    assert b.source == "template" and ready_p01.persona.durum in b.text


def test_brief_is_cached(ready_p01, make, tmp_path, config):
    text, cite = _good_text(ready_p01)
    n, llm = make(brief_reply(text, cite))
    assert n.brief(ready_p01, evidence(), "TR") == n.brief(ready_p01, evidence(), "TR")
    assert len(llm.requests) == 1
    (path,) = tmp_path.glob(f"{ready_p01.run_id}-TR-brief-*.json")
    assert path.name == f"{ready_p01.run_id}-TR-brief-b1-claude-haiku-5-5.json"
    assert NarrativeBrief.from_dict(json.loads(path.read_text(encoding="utf-8"))).source == "llm"


def test_brief_has_no_rm_only_fact(ready_p01, make):
    """ING vs market is the RM-only warning deposit_vs_market: the brief facts have
    no ING deposit, so naming it (and its rate) fails."""
    n, _ = make(brief_reply("ING Turuncu Hesap %23 faiz veriyor; piyasa ortalaması %43,82.",
                            ("deposit:ing_turuncu",)))
    b = n.brief(ready_p01, evidence(), "TR")
    assert b.source == "template"


def test_brief_for_a_pending_run_uses_the_top_3(ready_p01):
    f = build_brief_facts(ready_p01, evidence())
    assert [o.option_id for o in f.options] == [o.option.option_id
                                                for o in top_heads(ready_p01.options, 3)]


# --- more ------------------------------------------------------------------------------------

def test_the_run_is_pending(ready_p01):
    assert ready_p01.state == DecisionState.READY and not ready_p01.rm_selected


def test_brief_pack_has_only_dashboard_facts(ready_p01):
    pack = brief_pack(build_brief_facts(ready_p01, evidence()))
    assert set(pack) == {"run_id", "client", "dosyadaki_not", "talking_points", "top_options",
                         "warnings"}
    assert "rm_notu" not in pack["client"]
    assert len(pack["top_options"]) == 3
    rm_codes = {w.code for w in ready_p01.warnings if w.audience == "rm"}
    assert not any(w["code"] in rm_codes for w in pack["warnings"])
    assert len(json.dumps(pack, ensure_ascii=False)) < 4_000


def test_brief_request(ready_p01, config):
    req = brief_request(build_brief_facts(ready_p01, evidence()), "TR", config)
    assert req.model == "claude-haiku-5-5" and req.fallback is False
    assert req.effort == "low" and req.schema == BRIEF_SCHEMA
    assert "280" in req.system and "RM" in req.system
    assert BRIEF_SCHEMA["required"] == ["text", "cite"]


@pytest.mark.parametrize("text, rule", [
    ("x" * (BRIEF_MAX_CHARS + 1), "length"),
    ("Müşteri garanti getiri istiyor.", "phrase"),
    ("Kaynak needs_check işaretli.", "internal"),
    ("Müşteri 99 yaşında.", "number"),
])
def test_validate_brief(ready_p01, config, text, rule):
    f = build_brief_facts(ready_p01, evidence())
    findings = validate_brief(text, (), f, ready_p01, config, "TR")
    assert rule in {x.split(":", 1)[0] for x in findings}


def test_validate_brief_unknown_cite(ready_p01, config):
    f = build_brief_facts(ready_p01, evidence())
    text, _ = _good_text(ready_p01)
    findings = validate_brief(text, ("Edeadbeef",), f, ready_p01, config, "TR")
    assert {x.split(":", 1)[0] for x in findings} == {"citation"}


def test_good_brief_passes(ready_p01, config):
    f = build_brief_facts(ready_p01, evidence())
    text, cite = _good_text(ready_p01)
    assert validate_brief(text, cite, f, ready_p01, config, "TR") == ()


def test_api_error_gives_the_plain_sentence_not_cached(ready_p01, make, tmp_path):
    text, cite = _good_text(ready_p01)
    n, llm = make(LlmError("server", "529"), brief_reply(text, cite))
    assert n.brief(ready_p01, evidence(), "TR").source == "template"
    assert n.brief(ready_p01, evidence(), "TR").source == "llm"
    assert len(llm.requests) == 2


def test_brief_counts_against_the_daily_limit(ready_p01, make, config):
    cfg = dataclasses.replace(config, max_cost_usd_per_day=0.0)
    n, llm = make(cfg=cfg)
    b = n.brief(ready_p01, evidence(), "TR")
    assert b.source == "template" and b.checks[0].startswith("budget:") and llm.requests == []


def test_brief_cost_uses_the_brief_prices(ready_p01, make, config):
    text, cite = _good_text(ready_p01)
    n, _ = make(brief_reply(text, cite))
    b = n.brief(ready_p01, evidence(), "TR")
    p = config.brief
    assert b.cost_usd == pytest.approx((2000 * p.price_input_per_mtok
                                        + 300 * p.price_output_per_mtok) / 1e6)


def test_brief_of_a_run_that_needs_input_raises(make):
    from tests.narrator.conftest import result

    n, _ = make()
    with pytest.raises(ValueError, match="ready"):
        n.brief(result("decision_test_needs_input"), evidence(), "TR")


def test_refusal_gives_the_plain_sentence(ready_p01, make):
    n, _ = make(brief_reply("", stop_reason="refusal", refusal_category="general_harms"))
    b = n.brief(ready_p01, evidence(), "TR")
    assert b.source == "template" and b.checks[0].startswith("llm: refusal")


def test_english_brief(ready_p01, make):
    n, _ = make(client=False)
    b = n.brief(ready_p01, evidence(), "EN")
    assert b.lang == "EN" and b.text == plain_brief(ready_p01, "EN")


def test_brief_config(config):
    assert config.brief.model == "claude-haiku-5-5"
    assert config.brief.max_chars == 280 and config.brief.prompt_version == "b1"


def test_a_long_brief_keeps_the_whole_sentences_that_fit(ready_p01, make):
    """Live run b1: Haiku wrote 389 characters. Whole sentences up to the limit
    are kept (never a cut sentence); then the validator runs."""
    first, cite = _good_text(ready_p01)
    long_text = first + " " + "Müşterinin dosyadaki notunu da dikkate alarak görüşmeyi " * 6 + "planlayın."
    n, _ = make(brief_reply(long_text, cite))
    b = n.brief(ready_p01, evidence(), "TR")
    assert b.source == "llm", b.checks
    assert b.text == first and len(b.text) <= 280


def test_a_first_sentence_over_the_limit_fails(ready_p01, make):
    n, _ = make(brief_reply("Müşteri " + "çok " * 100 + "önemli."))
    b = n.brief(ready_p01, evidence(), "TR")
    assert b.source == "template" and b.checks[0].startswith("length:")


def test_fit_sentences():
    from rmprep.narrator.brief import fit_sentences

    assert fit_sentences("A bb. Cc dd. Ee.", 9) == "A bb."
    assert fit_sentences("A bb. Cc dd.", 100) == "A bb. Cc dd."
    assert fit_sentences("Oran %43,82 oldu. Sonra.", 18) == "Oran %43,82 oldu."
    assert fit_sentences("Çok uzun tek cümle.", 5) == "Çok uzun tek cümle."   # validator decides


def test_brief_prompt_states_the_limit_in_words(ready_p01, config):
    req = brief_request(build_brief_facts(ready_p01, evidence()), "TR", config)
    assert "40 words" in req.system and "two short sentences" in req.system
