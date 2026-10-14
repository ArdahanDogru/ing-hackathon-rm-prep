"""Claude web search provider, the fallback of Exa (docs/research.md section 8):
the Messages API with the server tool web_search. Findings are the cited text
blocks of the reply; a citation counts only when its URL is a web_search_result
of the same reply and not on an excluded domain. Cost: tokens at the config
prices plus price_per_search per search. Key and workspace id go only to the SDK."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime

from rmprep.contracts import TR_TZ, ProductOption
from rmprep.research.checks import is_excluded, is_web_url, norm_url
from rmprep.research.config import ClaudeSearchConfig
from rmprep.research.exa import option_code
from rmprep.research.types import Finding, ProductResearch, QuestionAnswer, ResearchError, Source

FALLBACK_BETA = "server-side-fallback-2026-07-01"   # refusal fallback, as the narrator (llm.py)
WORKSPACE_HEADER = "anthropic-workspace-id"
MAX_CONTINUATIONS = 2                                # pause_turn: send the paused turn back
MIN_CHARS = 15
MARKER = re.compile(r"(?:ŞİRKET|COMPANY)\s*:\s*(.+)", re.IGNORECASE)
PRODUCT_PROMPT = {
    "TR": ("Şu yatırım ürününü ve onu yöneten veya ihraç eden şirketi web'de araştır: {label} ({code}). "
           "Önce ürün hakkında kısa, kaynaklı cümleler yaz. Sonra 'ŞİRKET: <şirket adı>' satırını yaz "
           "ve şirket hakkında kısa, kaynaklı cümleler yaz."),
    "EN": ("Research this investment product and the company that manages or issues it on the web: "
           "{label} ({code}). First write short, sourced sentences about the product. Then write the "
           "line 'COMPANY: <company name>' and short, sourced sentences about the company."),
}
QUESTION_PROMPT = {
    "TR": "{question}\n\nİlgili ürünler: {products}. Kısa, kaynaklı cümlelerle yanıtla.",
    "EN": "{question}\n\nRelated products: {products}. Answer in short, sourced sentences.",
}
FORMAT = {"TR": " Her cümle bir web kaynağına dayansın.", "EN": " Base every sentence on a web source."}


def parse_blocks(blocks: Sequence, domains: Iterable[str],
                 start_topic: str) -> tuple[list[Finding], str, int]:
    """(findings, company, dropped). Text blocks with citations become findings;
    a block that holds the company marker switches the topic from urun to sirket."""
    domains = tuple(domains)
    allowed: dict[str, Source] = {}
    for b in blocks:
        if getattr(b, "type", "") == "web_search_tool_result" and isinstance(getattr(b, "content", None), list):
            for r in b.content:
                url = getattr(r, "url", "") or ""
                if url and is_web_url(url):
                    allowed.setdefault(norm_url(url), Source(url, getattr(r, "title", "") or ""))
    topic, company, findings, dropped = start_topic, "", [], 0
    for b in blocks:
        if getattr(b, "type", "") != "text":
            continue
        text = b.text or ""
        m = MARKER.search(text)
        if m and start_topic == "urun":
            topic = "sirket"
            company = company or m.group(1).strip().strip("*").strip()
            text = text[:m.start()] + text[m.end():]
        text = " ".join(text.split())
        cits = getattr(b, "citations", None) or []
        if not cits or len(text) < MIN_CHARS:
            continue
        sources: dict[str, Source] = {}
        for c in cits:
            src = allowed.get(norm_url(getattr(c, "url", "") or ""))
            if src is not None and not is_excluded(src.url, domains):
                sources.setdefault(norm_url(src.url), src)
        if not sources:
            dropped += 1
            continue
        findings.append(Finding(text, topic, tuple(sources.values())))
    return findings, company, dropped


class ClaudeSearchProvider:
    name = "claude"

    def __init__(self, config: ClaudeSearchConfig, system_prompt: Mapping[str, str],
                 exclude_domains: Iterable[str], *, api_key: str | None = None,
                 workspace_id: str | None = None, sdk=None,
                 now: Callable[[], datetime] = lambda: datetime.now(TR_TZ)) -> None:
        if sdk is None:
            import anthropic          # optional extra [narrator]
            extra = {"default_headers": {WORKSPACE_HEADER: workspace_id}} if workspace_id else {}
            sdk = anthropic.Anthropic(api_key=api_key, **extra)
        self._sdk = sdk
        self._config = config
        self._system = system_prompt
        self._domains = tuple(exclude_domains)
        self._now = now

    @classmethod
    def from_env(cls, config: ClaudeSearchConfig, system_prompt: Mapping[str, str],
                 exclude_domains: Iterable[str], env: Mapping[str, str]) -> ClaudeSearchProvider | None:
        key = env.get(config.api_key_env, "").strip()
        if not key:
            return None
        workspace = env.get(config.workspace_id_env, "").strip() or None
        try:
            return cls(config, system_prompt, exclude_domains, api_key=key, workspace_id=workspace)
        except ImportError:           # the [narrator] extra is not installed
            return None

    def research_product(self, option: ProductOption, lang: str) -> ProductResearch:
        prompt = PRODUCT_PROMPT[lang].format(label=option.label, code=option_code(option))
        blocks, cost = self._run(prompt, lang)
        findings, company, dropped = parse_blocks(blocks, self._domains, "urun")
        checks = (f"{dropped} findings without a valid source dropped",) if dropped else ()
        return ProductResearch(option.option_id, option.label, company, "", tuple(findings), lang,
                               self.name, self._now(), cost, checks)

    def answer_question(self, question: str, products: Sequence[ProductOption],
                        lang: str) -> QuestionAnswer:
        names = "; ".join(f"{p.label} ({option_code(p)})" for p in products) or "-"
        blocks, cost = self._run(QUESTION_PROMPT[lang].format(question=question, products=names), lang)
        findings, _, dropped = parse_blocks(blocks, self._domains, "soru")
        checks = (f"{dropped} findings without a valid source dropped",) if dropped else ()
        return QuestionAnswer(question, "", tuple(findings), lang, self.name, self._now(), cost, checks)

    def _run(self, prompt: str, lang: str) -> tuple[list, float]:
        messages: list[dict] = [{"role": "user", "content": prompt}]
        blocks: list = []
        cost = 0.0
        for _ in range(MAX_CONTINUATIONS + 1):
            msg = self._create(messages, lang)
            cost += self._cost(msg.usage)
            blocks += list(msg.content)
            if msg.stop_reason == "refusal":
                raise ResearchError("request", "the model refused the request")
            if msg.stop_reason != "pause_turn":
                break
            messages = [*messages, {"role": "assistant", "content": msg.content}]
        return blocks, cost

    def _create(self, messages: list[dict], lang: str):
        import anthropic
        tool = {"type": "web_search_20260209", "name": "web_search", "max_uses": self._config.max_uses}
        if self._domains:
            tool["blocked_domains"] = list(self._domains)
        try:
            return self._sdk.beta.messages.create(
                model=self._config.model, max_tokens=self._config.max_tokens,
                system=self._system[lang] + FORMAT[lang], messages=messages, tools=[tool],
                betas=[FALLBACK_BETA], fallbacks="default")
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise ResearchError("auth", e.message) from e
        except anthropic.RateLimitError as e:
            raise ResearchError("rate_limit", e.message) from e
        except anthropic.APIStatusError as e:
            if "credit" in str(e.message).lower():
                raise ResearchError("credit", e.message) from e
            raise ResearchError("server" if e.status_code >= 500 else "request",
                                f"{e.status_code} {e.message}") from e
        except anthropic.APIConnectionError as e:     # includes timeouts
            raise ResearchError("connection", str(e)) from e

    def _cost(self, usage) -> float:
        c = self._config
        n = lambda name: getattr(usage, name, 0) or 0          # noqa: E731
        tokens_in = n("input_tokens") + 1.25 * n("cache_creation_input_tokens") + 0.1 * n("cache_read_input_tokens")
        searches = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0
        return (tokens_in * c.price_input_per_mtok + n("output_tokens") * c.price_output_per_mtok) / 1e6 \
            + searches * c.price_per_search
