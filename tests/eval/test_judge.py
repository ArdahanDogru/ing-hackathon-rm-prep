"""The LLM judge with a fake SDK object (no network), its cache and grade_texts."""

import json

import anthropic
import httpx2
import pytest
from anthropic.types import Message

from rmprep.eval.config import load_config
from rmprep.eval.judge import (
    DEFINITIONS, CachedJudge, Grade, HaikuJudge, grade_texts, judge_from_env, schema, system_text,
    user_text,
)
from rmprep.eval.scenario import Scenario
from tests.eval.conftest import PROJECT, FakeNarrator
from tests.eval.test_runner import runner

CFG = load_config(PROJECT / "config" / "eval.yaml").judge
RUBRIC = CFG.rubric
GOOD = {r.id: {"choice": "yes", "reason": "ok"} for r in RUBRIC}


def _message(text=json.dumps(GOOD), **over) -> Message:
    data = {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
        "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                    {"type": "text", "text": text}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 20000, "output_tokens": 400},
    }
    data.update(over)
    return Message.model_validate(data)


class _Messages:
    def __init__(self, result):
        self.result, self.calls = result, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeSdk:
    def __init__(self, result):
        self.messages = _Messages(result)


@pytest.fixture
def approved(root):
    sr = runner(root, narrator=FakeNarrator()).run([Scenario(id="b", group="base", persona="P01")])[0]
    run = sr.runs[0]
    return run.approved, run.narratives["TR"], sr


def test_request_shape_and_grade(approved):
    result, draft, _ = approved
    sdk = FakeSdk(_message())
    g = HaikuJudge(CFG, sdk=sdk).grade(result, draft, RUBRIC)
    [k] = sdk.messages.calls
    assert k["model"] == "claude-haiku-5-5" and k["max_tokens"] == CFG.max_tokens
    assert k["output_config"] == {"effort": "low",
                                  "format": {"type": "json_schema", "schema": schema(RUBRIC)}}
    assert "thinking" not in k and "betas" not in k and "fallbacks" not in k
    assert k["system"] == [{"type": "text", "text": system_text(RUBRIC),
                            "cache_control": {"type": "ephemeral"}}]
    assert result.persona.profil in k["messages"][0]["content"]
    assert g.error is None and g.items["tailored"] == ("yes", "ok")
    assert g.cost_usd == pytest.approx((20000 * 0.10 + 400 * 0.50) / 1e6)


def test_the_system_block_is_identical_for_two_texts(root):
    out = runner(root, narrator=FakeNarrator()).run([
        Scenario(id="a", group="base", persona="P01"), Scenario(id="b", group="base", persona="P03")])
    sdk = FakeSdk(_message())
    judge = HaikuJudge(CFG, sdk=sdk)
    for sr in out:
        judge.grade(sr.runs[0].approved, sr.runs[0].narratives["TR"], RUBRIC)
    a, b = sdk.messages.calls
    assert json.dumps(a["system"]).encode() == json.dumps(b["system"]).encode()
    assert a["messages"] != b["messages"]
    assert a["system"][-1]["cache_control"] == {"type": "ephemeral"}


def test_the_system_block_holds_the_rubric_and_no_per_call_value(approved):
    result, draft, _ = approved
    t = system_text(RUBRIC)
    assert all(r.question in t and DEFINITIONS[r.id] in t for r in RUBRIC)
    assert result.run_id not in t and result.persona.profil not in t
    # Haiku 5.5 caches a prefix of 512 tokens or more; English is about 1.3 tokens per word
    assert len(t.split()) * 1.3 >= 512 * 1.15


def test_cost_counts_cache_writes_and_reads(approved):
    result, draft, _ = approved
    usage = {"input_tokens": 3000, "output_tokens": 400,
             "cache_creation_input_tokens": 800, "cache_read_input_tokens": 0}
    g = HaikuJudge(CFG, sdk=FakeSdk(_message(usage=usage))).grade(result, draft, RUBRIC)
    assert g.cache_write_tokens == 800 and g.cost_usd == pytest.approx(
        ((3000 + 1.25 * 800) * 0.10 + 400 * 0.50) / 1e6)
    usage |= {"cache_creation_input_tokens": 0, "cache_read_input_tokens": 800}
    g = HaikuJudge(CFG, sdk=FakeSdk(_message(usage=usage))).grade(result, draft, RUBRIC)
    assert g.cache_read_tokens == 800 and g.cost_usd == pytest.approx(
        ((3000 + 0.1 * 800) * 0.10 + 400 * 0.50) / 1e6)
    assert Grade.from_dict(g.to_dict()) == g


def test_schema_has_every_rubric_item_and_fixed_choices():
    s = schema(RUBRIC)
    assert s["required"] == [r.id for r in RUBRIC] and s["additionalProperties"] is False
    assert s["properties"]["balanced"]["properties"]["choice"]["enum"] == ["yes", "partly", "no"]


def test_user_text_holds_client_selection_and_text_but_not_the_rubric(approved):
    result, draft, _ = approved
    t = user_text(result, draft)
    assert result.persona.rm_notu in t and "<meeting_text" in t
    assert not any(r.question in t for r in RUBRIC)
    labels = {o.option.option_id: o.option.label for o in result.options}
    assert labels[result.rm_selected[0]] in t


_REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize("result, error", [
    (_message(stop_reason="refusal", content=[]), "refusal"),
    (_message(stop_reason="max_tokens"), "max_tokens"),
    (_message(text="not json"), "bad reply"),
    (_message(text=json.dumps({**GOOD, "tailored": {"choice": "maybe", "reason": "x"}})), "choice"),
    (anthropic.RateLimitError("slow", response=httpx2.Response(429, request=_REQ), body=None),
     "rate_limit"),
    (anthropic.InternalServerError("down", response=httpx2.Response(529, request=_REQ), body=None),
     "api 529"),
])
def test_failures_become_a_grade_with_an_error(approved, result, error):
    r, d, _ = approved
    g = HaikuJudge(CFG, sdk=FakeSdk(result)).grade(r, d, RUBRIC)
    assert g.items == {} and error in g.error


class _SdkRecorder:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_judge_from_env_and_the_workspace_header(monkeypatch):
    monkeypatch.setattr(anthropic, "Anthropic", _SdkRecorder)
    assert judge_from_env(CFG, {}) is None and judge_from_env(CFG, {"ANTHROPIC_API_KEY": " "}) is None
    j = judge_from_env(CFG, {"ANTHROPIC_API_KEY": "sk-test", "ANTHROPIC_WORKSPACE_ID": "wrkspc_t"})
    assert j._sdk.kwargs == {"api_key": "sk-test",
                             "default_headers": {"anthropic-workspace-id": "wrkspc_t"}}
    j = judge_from_env(CFG, {"ANTHROPIC_API_KEY": "sk-test"})
    assert j._sdk.kwargs == {"api_key": "sk-test"}


class CountingJudge:
    model = "fake-judge"

    def __init__(self, error=None, cost=0.01):
        self.calls, self.error, self.cost = 0, error, cost

    def grade(self, result, draft, rubric):
        self.calls += 1
        items = {} if self.error else {r.id: ("partly", "r") for r in rubric}
        return Grade(result.run_id, draft.lang, self.model, items, self.cost, self.error)


def test_cache_hit_makes_no_call_and_errors_are_not_cached(approved, tmp_path):
    r, d, _ = approved
    inner = CountingJudge()
    j = CachedJudge(inner, tmp_path / "grades")
    first, second = j.grade(r, d, RUBRIC), j.grade(r, d, RUBRIC)
    assert inner.calls == 1 and first.items == second.items
    assert first.cost_usd == 0.01 and second.cost_usd == 0.0
    bad = CachedJudge(CountingJudge(error="refusal"), tmp_path / "bad")
    bad.grade(r, d, RUBRIC)
    bad.grade(r, d, RUBRIC)
    assert bad.inner.calls == 2


def test_grade_texts_grades_llm_texts_once_within_the_budget(root, tmp_path):
    out = runner(root).run([Scenario(id=f"b{p}", group="base", persona=p, repeat=2)
                            for p in ("P01", "P02", "P03")])
    inner = CountingJudge(cost=0.02)
    spent = []
    graded = grade_texts(out, CachedJudge(inner, tmp_path), RUBRIC,
                         budget_left=lambda: 0.03 - sum(spent), spend=spent.append)
    assert [g.scenario_id for g in graded] == ["bP01", "bP02", "bP03"]
    assert [g.grade.error for g in graded] == [None, None, "budget: eval limit reached"]
    assert inner.calls == 2
    assert grade_texts(out, None, RUBRIC) == []
