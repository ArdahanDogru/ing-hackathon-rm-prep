"""A1: the Anthropic client of the agent with a fake SDK (no network)."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from rmprep.agent.client import AgentError, AnthropicAgentClient, agent_client_from_env


class _Block(SimpleNamespace):
    def to_dict(self, **_):
        return dict(vars(self))


def _msg(*blocks, stop="tool_use", model="claude-sonnet-5-5", details=None):
    usage = SimpleNamespace(input_tokens=1200, output_tokens=300, cache_creation_input_tokens=900,
                            cache_read_input_tokens=0)
    return SimpleNamespace(content=list(blocks), stop_reason=stop, model=model, usage=usage,
                           stop_details=details)


class FakeSdk:
    def __init__(self, reply=None, error=None):
        self.calls = []
        self.reply, self.error = reply, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        if self.error is not None:
            raise self.error
        return self.reply


def test_step_sends_tools_with_auto_choice_and_maps_calls(cfg):
    thinking = _Block(type="thinking", thinking="", signature="sig")
    use = _Block(type="tool_use", id="toolu_1", name="karsilastir",
                 input={"a": "fund:A", "b": "fund:B", "amac": "Karşılaştır."})
    sdk = FakeSdk(_msg(thinking, use))
    client = AnthropicAgentClient(cfg, api_key="k", sdk=sdk)
    tools = [{"name": "karsilastir", "input_schema": {}}]
    msgs = [{"role": "user", "content": [{"type": "text", "text": "pack"}]}]
    turn = client.step("system", msgs, tools)
    kw = sdk.calls[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["tools"] == tools
    assert kw["tool_choice"] == {"type": "auto"}                # Sonnet 5.5 rejects "any"
    assert kw["output_config"] == {"effort": "medium"}
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["messages"] == msgs
    assert turn.calls[0].name == "karsilastir" and turn.calls[0].input["a"] == "fund:A"
    assert turn.content == ({"type": "thinking", "thinking": "", "signature": "sig"},
                            {"type": "tool_use", "id": "toolu_1", "name": "karsilastir",
                             "input": {"a": "fund:A", "b": "fund:B", "amac": "Karşılaştır."}})
    assert (turn.input_tokens, turn.output_tokens, turn.cache_write_tokens) == (1200, 300, 900)


def test_refusal_is_an_error(cfg):
    sdk = FakeSdk(_msg(stop="refusal", details=SimpleNamespace(category="general_harms")))
    with pytest.raises(AgentError) as e:
        AnthropicAgentClient(cfg, api_key="k", sdk=sdk).step("s", [], [])
    assert e.value.kind == "refusal"


def test_sdk_errors_map_to_kinds(cfg):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx2.Response(429, request=req)
    err = anthropic.RateLimitError("slow down", response=resp, body=None)
    with pytest.raises(AgentError) as e:
        AnthropicAgentClient(cfg, api_key="k", sdk=FakeSdk(error=err)).step("s", [], [])
    assert e.value.kind == "rate_limit"
    conn = anthropic.APIConnectionError(request=req)
    with pytest.raises(AgentError) as e:
        AnthropicAgentClient(cfg, api_key="k", sdk=FakeSdk(error=conn)).step("s", [], [])
    assert e.value.kind == "connection"


def test_client_from_env(cfg):
    assert agent_client_from_env(cfg, {}) is None
    assert agent_client_from_env(cfg, {"ANTHROPIC_API_KEY": "  "}) is None
    assert isinstance(agent_client_from_env(cfg, {"ANTHROPIC_API_KEY": "sk-test"}),
                      AnthropicAgentClient)
