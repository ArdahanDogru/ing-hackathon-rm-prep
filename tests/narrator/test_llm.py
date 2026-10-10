"""The Anthropic adapter with a fake SDK object: no network."""

import dataclasses
import json

import anthropic
import httpx2
import pytest
from anthropic.types.beta import BetaMessage

from rmprep.narrator.llm import AnthropicClient, LlmError, LlmRequest, client_from_env

REQ = LlmRequest(system="sys", user_blocks=("facts", "task"),
                 schema={"type": "object", "properties": {}, "required": [],
                         "additionalProperties": False})


def _message(**over) -> BetaMessage:
    data = {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
        "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                    {"type": "text", "text": '{"ozet": []}'}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 8000, "output_tokens": 1500,
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    }
    data.update(over)
    return BetaMessage.model_validate(data)


class _Messages:
    def __init__(self, result):
        self.result, self.kwargs = result, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeSdk:
    def __init__(self, result):
        self.messages = _Messages(result)
        self.beta = self


def _client(config, result):
    sdk = FakeSdk(result)
    return AnthropicClient(config, sdk=sdk), sdk.messages


def test_request_shape(config):
    client, calls = _client(config, _message())
    client.complete(REQ)
    k = calls.kwargs
    assert k["model"] == "claude-sonnet-5-5"
    assert k["max_tokens"] == config.max_tokens
    assert k["output_config"] == {"effort": config.effort,
                                  "format": {"type": "json_schema", "schema": REQ.schema}}
    assert k["betas"] == ["server-side-fallback-2026-07-01"] and k["fallbacks"] == "default"
    assert "thinking" not in k and "temperature" not in k     # adaptive thinking by default
    assert k["system"] == [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}]
    (msg,) = k["messages"]
    assert msg["role"] == "user"
    facts, task = msg["content"]
    assert facts == {"type": "text", "text": "facts", "cache_control": {"type": "ephemeral"}}
    assert task == {"type": "text", "text": "task"}


def test_reply_fields(config):
    client, _ = _client(config, _message(
        model="claude-sonnet-5",
        usage={"input_tokens": 100, "output_tokens": 50, "cache_creation_input_tokens": 7000,
               "cache_read_input_tokens": 900}))
    r = client.complete(REQ)
    assert r.text == '{"ozet": []}'
    assert r.model == "claude-sonnet-5"          # served by the fallback model
    assert (r.input_tokens, r.output_tokens, r.cache_write_tokens, r.cache_read_tokens) == \
        (100, 50, 7000, 900)
    assert r.stop_reason == "end_turn" and r.refusal_category is None


def test_refusal_reply(config):
    client, _ = _client(config, _message(
        content=[], stop_reason="refusal",
        stop_details={"type": "refusal", "category": "general_harms", "explanation": None}))
    r = client.complete(REQ)
    assert r.stop_reason == "refusal" and r.refusal_category == "general_harms"
    assert r.text is None


_REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize("error, kind", [
    (anthropic.AuthenticationError("bad key", response=httpx2.Response(401, request=_REQ),
                                   body=None), "auth"),
    (anthropic.BadRequestError("bad", response=httpx2.Response(400, request=_REQ), body=None),
     "request"),
    (anthropic.RateLimitError("slow", response=httpx2.Response(429, request=_REQ), body=None),
     "rate_limit"),
    (anthropic.InternalServerError("down", response=httpx2.Response(529, request=_REQ),
                                   body=None), "server"),
    (anthropic.APIConnectionError(request=_REQ), "connection"),
])
def test_sdk_errors_become_llm_errors(error, kind, config):
    client, _ = _client(config, error)
    with pytest.raises(LlmError) as e:
        client.complete(REQ)
    assert e.value.kind == kind


def test_client_from_env(config):
    assert client_from_env(config, {}) is None
    assert client_from_env(config, {"ANTHROPIC_API_KEY": ""}) is None
    assert isinstance(client_from_env(config, {"ANTHROPIC_API_KEY": "sk-test"}), AnthropicClient)


class _SdkRecorder:
    """Stands in for anthropic.Anthropic: records the constructor arguments."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture
def recorder(monkeypatch):
    monkeypatch.setattr(anthropic, "Anthropic", _SdkRecorder)


def test_workspace_header_from_env(recorder, config):
    cfg = dataclasses.replace(config, workspace_id_env="ANTHROPIC_WORKSPACE_ID")
    client = client_from_env(cfg, {"ANTHROPIC_API_KEY": "sk-test",
                                   "ANTHROPIC_WORKSPACE_ID": "wrkspc_test"})
    assert client._sdk.kwargs == {"api_key": "sk-test",
                                  "default_headers": {"anthropic-workspace-id": "wrkspc_test"}}


@pytest.mark.parametrize("env", [{}, {"ANTHROPIC_WORKSPACE_ID": ""},
                                 {"ANTHROPIC_WORKSPACE_ID": "  "}])
def test_no_workspace_header_without_the_var(env, recorder, config):
    cfg = dataclasses.replace(config, workspace_id_env="ANTHROPIC_WORKSPACE_ID")
    client = client_from_env(cfg, {"ANTHROPIC_API_KEY": "sk-test", **env})
    assert client._sdk.kwargs == {"api_key": "sk-test"}


def test_no_workspace_header_without_the_config_key(recorder, config):
    cfg = dataclasses.replace(config, workspace_id_env=None)
    client = client_from_env(cfg, {"ANTHROPIC_API_KEY": "sk-test",
                                   "ANTHROPIC_WORKSPACE_ID": "wrkspc_test"})
    assert client._sdk.kwargs == {"api_key": "sk-test"}


def _markers(x) -> int:
    """Number of cache_control breakpoints in a request part."""
    if isinstance(x, dict):
        return ("cache_control" in x) + sum(_markers(v) for v in x.values())
    if isinstance(x, list):
        return sum(_markers(v) for v in x)
    return 0


def test_system_is_one_cached_prefix_for_every_client(config):
    """N6: the same system bytes for two different results in one language,
    a breakpoint after the system prompt and one after the facts pack."""
    from rmprep.narrator.facts import build_facts
    from rmprep.narrator.prompt import build_request
    from tests.narrator.conftest import evidence, p02, p03

    sent = []
    for make in (p02, p03):
        client, calls = _client(config, _message())
        client.complete(build_request(build_facts(make(), evidence()), "TR", config))
        sent.append(calls.kwargs)
    a, b = sent
    assert json.dumps(a["system"], sort_keys=True) == json.dumps(b["system"], sort_keys=True)
    assert a["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert a["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert _markers(a) == 2
    for r in (p02(), p03()):
        assert r.run_id not in a["system"][0]["text"]
        assert r.persona.profil not in a["system"][0]["text"]
    assert a["messages"] != b["messages"]
