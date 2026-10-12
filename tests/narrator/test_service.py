"""Narrator.draft with a fake LLM: retry, fallback, cache, budget. No network."""

import dataclasses
import json
from datetime import datetime, timedelta

import pytest

from rmprep.contracts import TR_TZ, NarrativeDraft
from rmprep.narrator.facts import build_facts
from rmprep.narrator.llm import LlmError, LlmReply
from rmprep.narrator.prompt import sections_json
from rmprep.narrator.service import Narrator, facts_hash
from rmprep.narrator.template import (
    BANNER,
    banner,
    template_need_tags,
    template_sections,
    to_markdown,
)
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
    return reply(sections_json(template_sections(f, lang, config.disclaimer[lang]),
                               template_need_tags(f)))


def bad(config, lang="TR") -> LlmReply:
    data = json.loads(good(lang=lang, config=config).text)
    data["sentences"].append({"section": "teklif_metni", "text": "Bu fon garantili kazanç sağlar.",
                              "title": "", "cite": []})
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
    assert path.name == (f"R02examp1e0-TR-{config.prompt_version}-{config.model}-"
                         f"{facts_hash(build_facts(p02(), evidence()))}.json")
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


# --- N12: the cache key holds a hash of the facts (selection, notes) ---------------------

def test_facts_hash_is_short_and_stable():
    h = facts_hash(build_facts(p02(), evidence()))
    assert len(h) == 10 and int(h, 16) >= 0
    assert h == facts_hash(build_facts(p02(), evidence()))


@pytest.mark.parametrize("change", [
    lambda r: dataclasses.replace(r, rm_selected=("fund:AAL",), rm_option_notes={}),
    lambda r: dataclasses.replace(r, rm_note="Başka bir onay notu."),
    lambda r: dataclasses.replace(r, rm_option_notes={"fund:BBF": "Başka not."}),
])
def test_other_selection_or_note_makes_a_new_text(change, make, config):
    """The eval bug: an approved run with another selection (same run id) got
    the old text from the cache."""
    other = change(p02())
    n, llm = make(good(config=config), reply(sections_json(
        template_sections(build_facts(other, evidence()), "TR", config.disclaimer["TR"]),
        template_need_tags(build_facts(other, evidence())))))
    first = n.draft(p02(), evidence(), "TR")
    second = n.draft(other, evidence(), "TR")
    assert len(llm.requests) == 2
    assert first.run_id == second.run_id and second.source == "llm"
    assert n.draft(other, evidence(), "TR") == second       # the new text is cached
    assert len(llm.requests) == 2


def test_approved_text_files_are_not_cache_files(make, config, tmp_path):
    """RealBackend keeps <run_id>-<lang>-approved.json in the same folder."""
    (tmp_path / "R02examp1e0-TR-approved.json").write_text("not a draft", encoding="utf-8")
    n, llm = make(good(config=config))
    assert n.draft(p02(), evidence(), "TR").source == "llm"
    assert (tmp_path / "R02examp1e0-TR-approved.json").read_text(encoding="utf-8") == "not a draft"


# --- N13d: findings of each attempt in the cost ledger ------------------------------------

def _rows(tmp_path):
    return [json.loads(x) for x in (tmp_path / "costs.jsonl").read_text("utf-8").splitlines()]


def test_ledger_rows_hold_the_attempt_and_its_findings(make, config, tmp_path):
    n, _ = make(bad(config), good(config=config))
    d = n.draft(p02(), evidence(), "TR")
    assert d.source == "llm" and d.checks == ()                  # the draft is unchanged
    first, second = _rows(tmp_path)
    assert (first["attempt"], second["attempt"]) == (1, 2)
    assert first["findings"] and all(x.startswith("phrase:") for x in first["findings"])
    assert second["findings"] == []
    assert first["kind"] == second["kind"] == "text"


def test_ledger_row_of_an_unusable_reply(make, config, tmp_path):
    n, _ = make(reply("not json"), good(config=config))
    n.draft(p02(), evidence(), "TR")
    assert _rows(tmp_path)[0]["findings"][0].startswith("format:")


def test_brief_ledger_row_holds_its_findings(ready_p01, make, tmp_path):
    from tests.narrator.test_brief import brief_reply

    n, _ = make(brief_reply("Müşteri 99 yaşında."))
    n.brief(ready_p01, evidence(), "TR")
    (row,) = _rows(tmp_path)
    assert row["kind"] == "brief" and row["attempt"] == 1
    assert any(x.startswith("number:") for x in row["findings"])


def test_first_attempt_findings_by_kind(make, config, tmp_path):
    from rmprep.narrator.service import findings_by_kind

    n, _ = make(bad(config), good(config=config), reply("not json"), reply("not json"))
    n.draft(p02(), evidence(), "TR")
    n.draft(p03(), evidence(), "TR")
    with open(tmp_path / "costs.jsonl", "a", encoding="utf-8") as fh:   # a row from before N13d
        fh.write(json.dumps({"date": "2026-10-10", "cost_usd": 0.01, "run_id": "R0"}) + "\n")
    path = tmp_path / "costs.jsonl"
    assert findings_by_kind(path) == {"attempts": 2, "failed": 2, "phrase": 1, "format": 1}
    assert findings_by_kind(path, attempt=2) == {"attempts": 2, "failed": 1, "format": 1}
    assert findings_by_kind(path, kind="brief") == {"attempts": 0, "failed": 0}
