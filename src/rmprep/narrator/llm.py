"""The LLM behind a small protocol: the narrator service sees only LlmClient,
so tests use a fake and never touch the network.

AnthropicClient: one Messages API call with structured output
(output_config.format), adaptive thinking (the Sonnet 5.5 default: no
`thinking` parameter), the effort of the config, and the server-side refusal
fallback ("default"). The SDK retries 408/409/429/5xx and connection errors
itself (max_retries); what is left becomes an LlmError."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from rmprep.narrator.config import NarratorConfig

FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class LlmRequest:
    system: str
    user_blocks: tuple[str, ...]        # first block: the facts (cached prefix)
    schema: Mapping[str, Any]           # JSON schema of the reply


@dataclass(frozen=True)
class LlmReply:
    text: str | None                    # the JSON text; None if there is none (refusal)
    model: str                          # the model that served the reply
    input_tokens: int
    output_tokens: int
    stop_reason: str                    # end_turn | max_tokens | refusal | ...
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    refusal_category: str | None = None


class LlmError(Exception):
    """The call failed. kind: auth | request | rate_limit | server | connection."""

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message


class LlmClient(Protocol):
    def complete(self, request: LlmRequest) -> LlmReply: ...


class AnthropicClient:
    def __init__(self, config: NarratorConfig, *, api_key: str | None = None, sdk=None):
        if sdk is None:
            import anthropic         # optional extra [narrator]

            sdk = anthropic.Anthropic(api_key=api_key)
        self._sdk = sdk
        self._config = config

    def complete(self, request: LlmRequest) -> LlmReply:
        import anthropic

        first, *rest = request.user_blocks
        content = [{"type": "text", "text": first, "cache_control": {"type": "ephemeral"}}]
        content += [{"type": "text", "text": b} for b in rest]
        try:
            msg = self._sdk.beta.messages.create(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": content}],
                output_config={"effort": self._config.effort,
                               "format": {"type": "json_schema", "schema": dict(request.schema)}},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as e:
            raise LlmError("auth", e.message) from e
        except anthropic.PermissionDeniedError as e:
            raise LlmError("auth", e.message) from e
        except (anthropic.BadRequestError, anthropic.NotFoundError,
                anthropic.UnprocessableEntityError) as e:
            raise LlmError("request", e.message) from e
        except anthropic.RateLimitError as e:
            raise LlmError("rate_limit", e.message) from e
        except anthropic.APIStatusError as e:
            kind = "server" if e.status_code >= 500 else "request"
            raise LlmError(kind, f"{e.status_code} {e.message}") from e
        except anthropic.APIConnectionError as e:       # includes APITimeoutError
            raise LlmError("connection", str(e)) from e

        text = next((b.text for b in msg.content if b.type == "text"), None)
        details = msg.stop_details if msg.stop_reason == "refusal" else None
        u = msg.usage
        return LlmReply(
            text=text, model=msg.model, input_tokens=u.input_tokens,
            output_tokens=u.output_tokens, stop_reason=msg.stop_reason or "",
            cache_write_tokens=u.cache_creation_input_tokens or 0,
            cache_read_tokens=u.cache_read_input_tokens or 0,
            refusal_category=details.category if details else None)


def client_from_env(config: NarratorConfig, env: Mapping[str, str]) -> AnthropicClient | None:
    """A client if env holds the API key (config.api_key_env), else None. The key
    is passed on, never logged."""
    key = env.get(config.api_key_env, "")
    return AnthropicClient(config, api_key=key) if key.strip() else None
