"""The model behind a small protocol: the agent service sees only AgentClient, so
tests use a scripted fake and never touch the network.

AnthropicAgentClient: one Messages API call per step with the agent's tools.
Claude Sonnet 5.5 rejects a forced tool_choice ("any" / "tool" are a 400), so
the request uses tool_choice "auto" with strict tools, and the service checks
that a call was made. Adaptive thinking (the Sonnet 5.5 default: no `thinking`
parameter) at the effort of the config; the server-side refusal fallback
("default"), as the narrator. The assistant content comes back as dicts so the
service can send it back unchanged (thinking blocks are bound to the
conversation); it is never stored or shown. The SDK retries 408/409/429/5xx and
connection errors itself; what is left becomes an AgentError."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from rmprep.agent.config import AgentConfig

FALLBACK_BETA = "server-side-fallback-2026-07-01"
WORKSPACE_HEADER = "anthropic-workspace-id"   # needed by an API key that is not scoped to a workspace


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: Mapping[str, Any]


@dataclass(frozen=True)
class AgentTurn:
    calls: tuple[ToolCall, ...]
    input_tokens: int
    output_tokens: int
    stop_reason: str
    model: str
    content: tuple[Mapping[str, Any], ...] = ()      # the assistant content, sent back as it is
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0


class AgentError(Exception):
    """The call failed. kind: auth | request | rate_limit | server | connection | refusal."""

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message


class AgentClient(Protocol):
    def step(self, system: str, messages: list[dict], tools: list[dict]) -> AgentTurn: ...


def _block(b) -> dict:
    return b.to_dict(mode="json") if hasattr(b, "model_dump") else b.to_dict()


class AnthropicAgentClient:
    def __init__(self, config: AgentConfig, *, api_key: str | None = None,
                 workspace_id: str | None = None, sdk=None):
        # Speed (2026-10-17): the SDK is made on the first agent step, not at the
        # server start (the import takes ~10 s on Windows)
        self._sdk_obj = sdk
        self._sdk_args = (api_key, workspace_id)
        self._config = config

    @property
    def _sdk(self):
        if self._sdk_obj is None:
            import anthropic         # optional extra [narrator]

            api_key, workspace_id = self._sdk_args
            extra = {"default_headers": {WORKSPACE_HEADER: workspace_id}} if workspace_id else {}
            self._sdk_obj = anthropic.Anthropic(api_key=api_key, timeout=self._config.timeout_s,
                                                max_retries=1, **extra)
        return self._sdk_obj

    def step(self, system: str, messages: list[dict], tools: list[dict]) -> AgentTurn:
        import anthropic

        c = self._config
        try:
            msg = self._sdk.beta.messages.create(
                model=c.model, max_tokens=c.max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=messages, tools=tools, tool_choice={"type": "auto"},
                output_config={"effort": c.effort},
                betas=[FALLBACK_BETA], fallbacks="default")
        except anthropic.AuthenticationError as e:
            raise AgentError("auth", e.message) from e
        except anthropic.PermissionDeniedError as e:
            raise AgentError("auth", e.message) from e
        except (anthropic.BadRequestError, anthropic.NotFoundError,
                anthropic.UnprocessableEntityError) as e:
            raise AgentError("request", e.message) from e
        except anthropic.RateLimitError as e:
            raise AgentError("rate_limit", e.message) from e
        except anthropic.APIStatusError as e:
            kind = "server" if e.status_code >= 500 else "request"
            raise AgentError(kind, f"{e.status_code} {e.message}") from e
        except anthropic.APIConnectionError as e:       # includes APITimeoutError
            raise AgentError("connection", str(e)) from e

        if msg.stop_reason == "refusal":
            details = msg.stop_details
            raise AgentError("refusal", str(getattr(details, "category", None) or "no category"))
        calls = tuple(ToolCall(b.id, b.name, dict(b.input)) for b in msg.content
                      if b.type == "tool_use")
        u = msg.usage
        return AgentTurn(calls=calls, input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                         stop_reason=msg.stop_reason or "", model=msg.model,
                         content=tuple(_block(b) for b in msg.content),
                         cache_write_tokens=u.cache_creation_input_tokens or 0,
                         cache_read_tokens=u.cache_read_input_tokens or 0)


def agent_client_from_env(config: AgentConfig, env: Mapping[str, str]) -> AnthropicAgentClient | None:
    """A client if env holds the API key (config.api_key_env), else None. With the
    workspace variable set, every request carries the workspace header. The key
    and the workspace id are passed on, never logged."""
    key = env.get(config.api_key_env, "")
    if not key.strip():
        return None
    workspace = env.get(config.workspace_id_env, "").strip()
    return AnthropicAgentClient(config, api_key=key, workspace_id=workspace or None)
