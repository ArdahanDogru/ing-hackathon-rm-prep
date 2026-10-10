"""Narrator.draft with a fake LLM: retry, fallback, cache, budget. No network."""

import dataclasses
import json
from datetime import datetime, timedelta

import pytest

from rmprep.contracts import TR_TZ, NarrativeDraft
from rmprep.narrator.facts import build_facts
from rmprep.narrator.llm import LlmError, LlmReply
from rmprep.narrator.prompt import sections_json
from rmprep.narrator.service import Narrator
from rmprep.narrator.template import BANNER, banner, template_sections, to_markdown
from tests.narrator.conftest import CREATED, evidence, p02, p03, result

COST = 8000 * 2.0 / 1e6 + 1500 * 10.0 / 1e6      # one call at the config prices: $0.031


class FakeLlm:
    """Scripted replies (or errors), in order; records every request."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []

    def complete(self, request):
        self.requests.append(request)
        if not self.replies:
            raise AssertionError("unexpected LLM call")
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def reply(text, **over) -> LlmReply:
    fields = dict(text=text, model="claude-sonnet-5-5", input_tokens=8000, output_tokens=1500,
                  stop_reason="end_turn")
    fields.update(over)
    return LlmReply(**fields)


def good(make=p02, lang="TR", config=None) -> LlmReply:
    """A text that passes the validator: the template sections as JSON."""
    f = build_facts(make(), evidence())
    return reply(sections_json(template_sections(f, lang, config.disclaimer[lang])))


def bad(config, lang="TR") -> LlmReply:
    data = json.loads(good(lang=lang, config=config).text)
    data["teklif_metni"].append({"text": "Bu fon garantili kazanç sağlar.", "option_ids": [],
                                 "evidence_ids": []})
    return reply(json.dumps(data, ensure_ascii=False))


@pytest.fixture
def make(tmp_path, config):
    def _make(*replies, cfg=None, client=True, now=CREATED):
        llm = FakeLlm(*replies)
        n = Narrator(cfg or config, llm if client else None, tmp_path, clock=lambda: now)
        return n, llm
    return _make


def test_only_an_approved_result(make):
    n, llm = make()
    with pytest.raises(ValueError, match="approved"):
        n.draft(result("decision_p02_ready"), evidence(), "TR")
    assert llm.requests == []


def test_llm_text_that_passes(make, config):
    n, llm = make(good(config=config))
    d = n.draft(p02(), evidence(), "TR")
    assert (d.source, d.model, d.checks, d.lang, d.run_id) == ("llm", "claude-sonnet-5-5", (),
                                                               "TR", "R02examp1e0")
    assert d.prompt_version == config.prompt_version and d.created_at == CREATED
    assert d.cost_usd == pytest.approx(COST)
    assert len(llm.requests) == 1
    assert banner(d) is None


def test_model_of_the_reply_is_recorded(make, config):
    n, _ = make(dataclasses.replace(good(config=config), model="claude-sonnet-5"))
    assert n.draft(p02(), evidence(), "TR").model == "claude-sonnet-5"


def test_retry_with_the_findings_then_pass(make, config):
    first = bad(config)
    n, llm = make(first, good(config=config))
    d = n.draft(p02(), evidence(), "TR")
    assert d.source == "llm" and d.checks == ()
    assert d.cost_usd == pytest.approx(2 * COST)
    retry = llm.requests[1]
    assert first.text in retry.user_blocks[2] and "garanti" in retry.user_blocks[2]


def test_second_failure_gives_the_template_with_a_banner(make, config):
    n, llm = make(bad(config), bad(config))
    d = n.draft(p02(), evidence(), "TR")
    assert (d.source, d.model) == ("template", "")
    assert d.checks and all(c.startswith("phrase:") for c in d.checks)
    assert d.cost_usd == pytest.approx(2 * COST)
    assert len(llm.requests) == 2
    assert banner(d) == BANNER["TR"]
    assert BANNER["TR"] in to_markdown(d)


@pytest.mark.parametrize("first, finding", [
    (reply("not json"), "format:"),
    (reply(None, stop_reason="refusal", refusal_category="general_harms"), "llm: refusal"),
    (reply('{"ozet": [', stop_reason="max_tokens"), "llm: the text was cut off"),
])
def test_unusable_replies_are_failures(first, finding, make, config):
    n, llm = make(first, first)
    d = n.draft(p02(), evidence(), "TR")
    assert d.source == "template"
    assert any(c.startswith(finding) for c in d.checks), d.checks
    assert len(llm.requests) == 2


def test_api_error_gives_the_template_without_a_retry(make):
    n, llm = make(LlmError("rate_limit", "429 after the SDK retries"))
    d = n.draft(p02(), evidence(), "TR")
    assert d.source == "template" and d.checks == ("llm: rate_limit: 429 after the SDK retries",)
    assert len(llm.requests) == 1


def test_no_client_gives_the_template(make):
    n, _ = make(client=False)
    d = n.draft(p02(), evidence(), "TR")
    assert d.source == "template" and d.checks[0].startswith("llm: no API key")


def test_cache_hit_makes_no_call(make, config, tmp_path):
    n, llm = make(good(config=config))
    first = n.draft(p02(), evidence(), "TR")
    assert n.draft(p02(), evidence(), "TR") == first
    again = Narrator(config, FakeLlm(), tmp_path, clock=lambda: CREATED)     # new process
    assert again.draft(p02(), evidence(), "TR") == first
    assert len(llm.requests) == 1
    (path,) = tmp_path.glob("R02examp1e0-*.json")
    assert path.name == f"R02examp1e0-TR-{config.prompt_version}-{config.model}.json"
    assert NarrativeDraft.from_dict(json.loads(path.read_text(encoding="utf-8"))) == first


def test_one_draft_per_language(make, config):
    n, llm = make(good(config=config), good(lang="EN", config=config))
    assert n.draft(p02(), evidence(), "TR").lang == "TR"
    assert n.draft(p02(), evidence(), "EN").lang == "EN"
    assert len(llm.requests) == 2


def test_failed_validation_is_cached_but_an_api_error_is_not(make, config):
    n, llm = make(bad(config), bad(config), LlmError("server", "529"), good(p03, config=config))
    n.draft(p02(), evidence(), "TR")
    n.draft(p02(), evidence(), "TR")                     # cached template: no call
    assert len(llm.requests) == 2
    assert n.draft(p03(), evidence(), "TR").source == "template"
    assert n.draft(p03(), evidence(), "TR").source == "llm"   # the error was not cached
    assert len(llm.requests) == 4


def test_every_call_is_in_the_cost_ledger(make, config, tmp_path):
    n, _ = make(bad(config), good(config=config))
    n.draft(p02(), evidence(), "TR")
    rows = [json.loads(x) for x in (tmp_path / "costs.jsonl").read_text("utf-8").splitlines()]
    assert [r["run_id"] for r in rows] == ["R02examp1e0", "R02examp1e0"]
    assert rows[0]["date"] == "2026-10-10" and rows[0]["cost_usd"] == pytest.approx(COST)
    assert rows[0]["input_tokens"] == 8000 and rows[0]["model"] == "claude-sonnet-5-5"
    assert n.spent_today() == pytest.approx(2 * COST)


def test_cache_tokens_are_priced(make, config):
    n, _ = make(dataclasses.replace(good(config=config), input_tokens=1000,
                                    cache_write_tokens=6000, cache_read_tokens=1000,
                                    output_tokens=0))
    d = n.draft(p02(), evidence(), "TR")
    assert d.cost_usd == pytest.approx((1000 + 6000 * 1.25 + 1000 * 0.1) * 2.0 / 1e6)


def test_over_the_daily_limit_no_call(make, config, tmp_path):
    cfg = dataclasses.replace(config, max_cost_usd_per_day=0.05)
    n, llm = make(good(config=config), cfg=cfg)
    n.draft(p02(), evidence(), "TR")                     # $0.031 spent
    n2, llm2 = make(cfg=cfg)
    n2._ledger_add(run_id="R0", lang="TR", reply=good(config=config))   # $0.062 today
    d = n2.draft(p03(), evidence(), "TR")
    assert d.source == "template" and d.checks[0].startswith("budget:")
    assert llm2.requests == []
    assert banner(d) == BANNER["TR"]


def test_yesterday_does_not_count(make, config):
    cfg = dataclasses.replace(config, max_cost_usd_per_day=0.04)
    n, _ = make(good(config=config), cfg=cfg, now=CREATED - timedelta(days=1))
    n.draft(p02(), evidence(), "TR")
    n2, llm2 = make(good(p03, config=config), cfg=cfg)
    assert n2.draft(p03(), evidence(), "TR").source == "llm"


def test_limit_reached_before_the_retry(make, config):
    cfg = dataclasses.replace(config, max_cost_usd_per_day=0.03)
    n, llm = make(bad(config), cfg=cfg)
    d = n.draft(p02(), evidence(), "TR")
    assert d.source == "template" and len(llm.requests) == 1
    assert any(c.startswith("budget:") for c in d.checks)
    assert any(c.startswith("phrase:") for c in d.checks)


def test_created_at_is_the_clock(make, config):
    t = datetime(2026, 10, 11, 8, 30, tzinfo=TR_TZ)
    n, _ = make(good(config=config), now=t)
    assert n.draft(p02(), evidence(), "TR").created_at == t


def test_from_root_reads_the_key_from_dotenv(tmp_path, monkeypatch, config):
    from rmprep.narrator.llm import AnthropicClient
    from rmprep.narrator.service import narrator_from_root

    from rmprep.narrator.config import DEFAULT_PATH

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "narrator.yaml").write_bytes(DEFAULT_PATH.read_bytes())
    n = narrator_from_root(tmp_path)
    assert n.client is None
    assert n.cache_dir == tmp_path / "data" / "narratives"
    assert n.config == config
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-test\n", encoding="utf-8")
    assert isinstance(narrator_from_root(tmp_path).client, AnthropicClient)
